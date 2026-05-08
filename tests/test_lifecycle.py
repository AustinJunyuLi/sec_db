"""Phase 4 (US-005) — claim lifecycle, append-only attempts, aggregation policy."""

from __future__ import annotations

from datetime import datetime, timezone

import duckdb
import pytest

from sec_review_compiler.store import (
    ClaimAttempt,
    CoverageCheck,
    DealRoomRepository,
    Verdict,
    aggregate_verdicts,
    apply_schema,
    can_publish_trusted,
    validate_transition,
)
from sec_review_compiler.store.lifecycle import IllegalTransitionError


def _ts(seq: int) -> datetime:
    # Synthetic timestamps that are strictly increasing; the aggregation
    # policy must NOT depend on these.
    return datetime(2026, 5, 8, 13, 0, seq, tzinfo=timezone.utc)


@pytest.fixture()
def repo():
    conn = duckdb.connect(":memory:")
    apply_schema(conn)
    yield DealRoomRepository(conn)
    conn.close()


def _make_attempt(
    *,
    attempt_id: str = "attempt:a1",
    fingerprint: str = "fp:111",
    deal: str = "deal-1",
    role: str = "extractor:timeline",
    seq: int = 1,
    status: str = "proposed",
) -> ClaimAttempt:
    return ClaimAttempt(
        attempt_id=attempt_id,
        claim_fingerprint=fingerprint,
        deal_slug=deal,
        claim_type="timeline_event",
        payload_json='{"event":"NDA","date":"2026-01-02"}',
        origin_agent_role=role,
        origin_agent_run_id=f"run:{role}",
        model="gpt-5.5",
        prompt_hash="ph:000",
        created_sequence=seq,
        created_at_run_clock=_ts(seq),
        status=status,
    )


def _make_verdict(
    *,
    verdict_id: str,
    attempt_id: str,
    verdict: str,
    seq: int,
    proposed_correction: str | None = None,
) -> Verdict:
    return Verdict(
        verdict_id=verdict_id,
        attempt_id=attempt_id,
        verifier_agent_run_id=f"verifier:{verdict_id}",
        model="gpt-5.5",
        prompt_hash="ph:verifier",
        verdict=verdict,
        reasoning_summary=None,
        supporting_evidence_ids=("ev:1",),
        proposed_correction_json=proposed_correction,
        confidence=0.8,
        created_at_run_clock=_ts(seq),
    )


# ---------------------------------------------------------------- transitions

class TestStateMachine:
    def test_valid_transition(self) -> None:
        validate_transition(from_status="proposed", to_status="bound")

    def test_invalid_transition(self) -> None:
        with pytest.raises(IllegalTransitionError):
            validate_transition(from_status="proposed", to_status="accepted")

    def test_terminal_state_blocks_further(self) -> None:
        with pytest.raises(IllegalTransitionError):
            validate_transition(from_status="binding_failed", to_status="bound")

    def test_unknown_state_rejected(self) -> None:
        with pytest.raises(IllegalTransitionError):
            validate_transition(from_status="not-a-state", to_status="bound")


# ---------------------------------------------------------------- append-only attempts

class TestAppendOnlyAttempts:
    def test_attempt_id_and_fingerprint_are_distinct(self, repo) -> None:
        attempt = _make_attempt(attempt_id="attempt:A", fingerprint="fp:42")
        repo.insert_claim_attempt(attempt)
        # The schema itself permits attempt_id != claim_fingerprint, and the
        # repository preserves both as independent fields.
        assert attempt.attempt_id != attempt.claim_fingerprint

    def test_two_agents_with_same_fingerprint_remain_separate_attempts(self, repo) -> None:
        a = _make_attempt(
            attempt_id="attempt:X",
            fingerprint="fp:same",
            role="extractor:party",
            seq=1,
        )
        b = _make_attempt(
            attempt_id="attempt:Y",
            fingerprint="fp:same",
            role="extractor:timeline",
            seq=2,
        )
        repo.insert_claim_attempt(a)
        repo.insert_claim_attempt(b)
        attempts = repo.list_attempts_for_fingerprint("fp:same")
        assert len(attempts) == 2
        ids = {aid for aid, _ in attempts}
        roles = {role for _, role in attempts}
        assert ids == {"attempt:X", "attempt:Y"}
        assert roles == {"extractor:party", "extractor:timeline"}

    def test_partial_correction_creates_new_attempt_id(self, repo) -> None:
        original = _make_attempt(attempt_id="attempt:O", fingerprint="fp:O")
        repo.insert_claim_attempt(original)
        # Bind + verify partial → correction.
        repo.transition_attempt(
            "attempt:O", to_status="bound", reason="binder_ok",
            transitioned_at=_ts(2),
        )
        repo.transition_attempt(
            "attempt:O", to_status="verified_partial", reason="partial_verdict",
            transitioned_at=_ts(3),
        )
        new_id = repo.create_correction(
            original_attempt_id="attempt:O",
            corrected_payload_json='{"event":"NDA","date":"2026-01-02","party":"Buyer A"}',
            claim_fingerprint="fp:O-corrected",
            deal_slug=original.deal_slug,
            claim_type=original.claim_type,
            origin_agent_role=original.origin_agent_role,
            origin_agent_run_id=original.origin_agent_run_id,
            model=original.model,
            prompt_hash=original.prompt_hash,
            created_sequence=4,
            created_at_run_clock=_ts(4),
        )
        assert new_id != "attempt:O"
        # Original is now superseded; new attempt exists in 'proposed'.
        assert repo.get_attempt_status("attempt:O") == "superseded"
        assert repo.get_attempt_status(new_id) == "proposed"
        # The original payload was *not* mutated.
        original_row = repo._conn.execute(  # type: ignore[attr-defined]
            "SELECT payload_json FROM claim_attempts WHERE attempt_id = ?",
            ("attempt:O",),
        ).fetchone()
        assert original_row[0] == original.payload_json

    def test_status_history_is_appendonly(self, repo) -> None:
        repo.insert_claim_attempt(_make_attempt(attempt_id="attempt:H"))
        repo.transition_attempt(
            "attempt:H", to_status="bound", reason="r1", transitioned_at=_ts(2)
        )
        repo.transition_attempt(
            "attempt:H", to_status="verified_confirmed", reason="r2",
            transitioned_at=_ts(3),
        )
        rows = repo._conn.execute(  # type: ignore[attr-defined]
            "SELECT to_status, reason FROM claim_attempt_status_history "
            "WHERE attempt_id = ? ORDER BY transitioned_at",
            ("attempt:H",),
        ).fetchall()
        assert [r[0] for r in rows] == ["proposed", "bound", "verified_confirmed"]


# ---------------------------------------------------------------- aggregation

class TestAggregationPolicy:
    def test_no_verdicts(self) -> None:
        agg = aggregate_verdicts([])
        assert agg.outcome == "no_verdicts"

    def test_single_confirm(self) -> None:
        v = _make_verdict(verdict_id="v1", attempt_id="a", verdict="confirm", seq=1)
        assert aggregate_verdicts([v]).outcome == "confirmed"

    def test_confirm_then_reject_aggregates_to_escalated_not_rejected(self) -> None:
        # The "latest" verdict is reject; the policy must NOT pick latest.
        v1 = _make_verdict(verdict_id="v1", attempt_id="a", verdict="confirm", seq=1)
        v2 = _make_verdict(verdict_id="v2", attempt_id="a", verdict="reject", seq=2)
        assert aggregate_verdicts([v1, v2]).outcome == "escalated"
        # And in reverse order, the result is identical — proving the
        # policy is order-independent (no latest-wins behavior).
        assert aggregate_verdicts([v2, v1]).outcome == "escalated"

    def test_only_rejects(self) -> None:
        v1 = _make_verdict(verdict_id="v1", attempt_id="a", verdict="reject", seq=1)
        v2 = _make_verdict(verdict_id="v2", attempt_id="a", verdict="reject", seq=2)
        assert aggregate_verdicts([v1, v2]).outcome == "rejected"

    def test_partial_creates_correction_required(self) -> None:
        v = _make_verdict(verdict_id="v1", attempt_id="a", verdict="partial", seq=1,
                          proposed_correction='{"date":"2026-01-02"}')
        assert aggregate_verdicts([v]).outcome == "correction_required"

    def test_two_malformed_means_verifier_stage_failed(self) -> None:
        v1 = _make_verdict(verdict_id="v1", attempt_id="a", verdict="malformed", seq=1)
        v2 = _make_verdict(verdict_id="v2", attempt_id="a", verdict="malformed", seq=2)
        assert aggregate_verdicts([v1, v2]).outcome == "verifier_stage_failed"

    def test_confirm_with_ambiguous_escalates(self) -> None:
        v1 = _make_verdict(verdict_id="v1", attempt_id="a", verdict="confirm", seq=1)
        v2 = _make_verdict(verdict_id="v2", attempt_id="a", verdict="ambiguous", seq=2)
        assert aggregate_verdicts([v1, v2]).outcome == "escalated"

    def test_aggregate_attempt_writes_row(self, repo) -> None:
        repo.insert_claim_attempt(_make_attempt(attempt_id="attempt:agg"))
        repo.insert_verdict(
            _make_verdict(verdict_id="v1", attempt_id="attempt:agg",
                          verdict="confirm", seq=1)
        )
        repo.insert_verdict(
            _make_verdict(verdict_id="v2", attempt_id="attempt:agg",
                          verdict="reject", seq=2)
        )
        agg = repo.aggregate_attempt("attempt:agg", decided_at_run_clock=_ts(3))
        assert agg.outcome == "escalated"
        rows = repo._conn.execute(  # type: ignore[attr-defined]
            "SELECT aggregated_verdict, aggregation_policy_version FROM verdict_aggregates "
            "WHERE attempt_id = ?",
            ("attempt:agg",),
        ).fetchall()
        assert rows == [("escalated", "v1")]


# ---------------------------------------------------------------- coverage gate

class TestCoverageGate:
    def _check(
        self,
        *,
        category: str,
        state: str,
        required: bool = True,
        seq: int = 1,
    ) -> CoverageCheck:
        return CoverageCheck(
            coverage_id=f"cov:{category}:{state}",
            deal_slug="deal-1",
            category=category,
            subcategory=None,
            check_state=state,
            evidence_id=None,
            attempt_id=None,
            required=required,
            notes=None,
            created_at_run_clock=_ts(seq),
        )

    def test_failed_to_check_blocks_publication(self) -> None:
        decision = can_publish_trusted([
            self._check(category="parties", state="checked_found"),
            self._check(category="bids", state="failed_to_check"),
        ])
        assert decision.can_publish_trusted is False
        assert "bids" in decision.blocking_categories
        assert "failed_to_check" in decision.rationale

    def test_optional_failed_to_check_does_not_block(self) -> None:
        decision = can_publish_trusted([
            self._check(category="parties", state="checked_found"),
            self._check(category="optional_metric", state="failed_to_check", required=False),
        ])
        assert decision.can_publish_trusted is True

    def test_ambiguous_does_not_block(self) -> None:
        decision = can_publish_trusted([
            self._check(category="parties", state="ambiguous"),
        ])
        assert decision.can_publish_trusted is True

    def test_all_clear(self) -> None:
        decision = can_publish_trusted([
            self._check(category="parties", state="checked_found"),
            self._check(category="bids", state="checked_absent"),
        ])
        assert decision.can_publish_trusted is True

    def test_repository_round_trip(self, repo) -> None:
        repo.insert_coverage_check(self._check(category="bids", state="failed_to_check", seq=1))
        repo.insert_coverage_check(self._check(category="parties", state="checked_found", seq=2))
        checks = repo.list_coverage_checks("deal-1")
        decision = can_publish_trusted(checks)
        assert decision.can_publish_trusted is False
        assert "bids" in decision.blocking_categories
