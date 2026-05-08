"""Phase 8 (US-009) — human decision import + coverage ledger."""

from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path

import duckdb
import pytest

from sec_review_compiler.exports.human_decisions import (
    HumanDecisionImport,
    HumanDecisionImportError,
    apply_human_decisions,
    parse_human_decisions_csv,
)
from sec_review_compiler.filing.examples import SYNTHETIC_FILING_PATH
from sec_review_compiler.orchestration import (
    OfflineConfidentialityExtractor,
    OfflineFakeVerifier,
    Orchestrator,
)
from sec_review_compiler.store.repository import DealRoomRepository


RUN_ID = "20260508T140000Z_synthetic-demo_deadbeef"


def _run_dir(tmp_path: Path) -> Path:
    p = tmp_path / RUN_ID
    p.mkdir(parents=True, exist_ok=True)
    return p


def _populate_deal(tmp_path: Path):
    orch = Orchestrator(
        deal_slug="synthetic-demo",
        extractor=OfflineConfidentialityExtractor(),
        verifier=OfflineFakeVerifier(),
    )
    return orch.run_synthetic_vertical_slice(
        run_dir=_run_dir(tmp_path),
        filing_path=SYNTHETIC_FILING_PATH,
    )


# ---------------------------------------------------------------- CSV parsing

class TestParseCSV:
    def test_round_trip(self, tmp_path: Path) -> None:
        path = tmp_path / "decisions.csv"
        with path.open("w", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(["attempt_id", "decision", "correction_json", "reviewer", "reviewed_at", "notes"])
            w.writerow(["a:1", "accept", "", "alice", "2026-05-08T14:00:00Z", ""])
            w.writerow(["a:2", "correct", '{"x":1}', "bob", "2026-05-08T14:01:00Z", "needs review"])
        records = parse_human_decisions_csv(path)
        assert [r.attempt_id for r in records] == ["a:1", "a:2"]
        assert records[0].decision == "accept"
        assert records[1].correction_json == '{"x":1}'

    def test_invalid_decision_raises(self, tmp_path: Path) -> None:
        path = tmp_path / "decisions.csv"
        with path.open("w", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(["attempt_id", "decision", "correction_json", "reviewer", "reviewed_at", "notes"])
            w.writerow(["a:1", "ignore", "", "alice", "2026-05-08T14:00:00Z", ""])
        with pytest.raises(HumanDecisionImportError):
            parse_human_decisions_csv(path)

    def test_missing_required_columns_raises(self, tmp_path: Path) -> None:
        path = tmp_path / "decisions.csv"
        with path.open("w", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(["attempt_id", "decision"])  # missing reviewer/reviewed_at
            w.writerow(["a:1", "accept"])
        with pytest.raises(HumanDecisionImportError):
            parse_human_decisions_csv(path)


# ---------------------------------------------------------------- correct → new attempt

class TestHumanCorrect:
    def test_correct_creates_new_attempt_and_supersedes_original(self, tmp_path: Path) -> None:
        slice_result = _populate_deal(tmp_path)
        accepted = slice_result.accepted_attempt_ids[0]
        conn = duckdb.connect(str(slice_result.db_path))
        original_payload = conn.execute(
            "SELECT payload_json FROM claim_attempts WHERE attempt_id = ?",
            (accepted,),
        ).fetchone()[0]
        repo = DealRoomRepository(conn)

        result = apply_human_decisions(
            repo,
            decisions=[
                HumanDecisionImport(
                    attempt_id=accepted,
                    decision="correct",
                    correction_json=json.dumps({"event_type": "confidentiality_agreement", "note": "human revised"}),
                    reviewer="alice",
                    reviewed_at=datetime(2026, 5, 8, 14, 0, 0, tzinfo=timezone.utc),
                    notes=None,
                )
            ],
            deal_slug="synthetic-demo",
        )
        applied = result.applied[0]
        assert applied.new_attempt_id is not None
        assert applied.final_status == "superseded"

        # Original payload preserved.
        new_status, new_payload = conn.execute(
            "SELECT status, payload_json FROM claim_attempts WHERE attempt_id = ?",
            (accepted,),
        ).fetchone()
        assert new_status == "superseded"
        assert new_payload == original_payload

        # New attempt exists with supersedes_attempt_id pinned.
        supersedes = conn.execute(
            "SELECT supersedes_attempt_id, status FROM claim_attempts WHERE attempt_id = ?",
            (applied.new_attempt_id,),
        ).fetchone()
        conn.close()
        assert supersedes[0] == accepted
        assert supersedes[1] == "proposed"

    def test_notes_only_correct_does_not_create_attempt(self, tmp_path: Path) -> None:
        slice_result = _populate_deal(tmp_path)
        accepted = slice_result.accepted_attempt_ids[0]
        conn = duckdb.connect(str(slice_result.db_path))
        repo = DealRoomRepository(conn)
        before_attempt_count = conn.execute(
            "SELECT COUNT(*) FROM claim_attempts"
        ).fetchone()[0]

        result = apply_human_decisions(
            repo,
            decisions=[
                HumanDecisionImport(
                    attempt_id=accepted,
                    decision="correct",
                    correction_json=None,
                    reviewer="alice",
                    reviewed_at=datetime(2026, 5, 8, 14, 0, 0, tzinfo=timezone.utc),
                    notes="just a comment, no payload change",
                )
            ],
            deal_slug="synthetic-demo",
        )
        after_attempt_count = conn.execute(
            "SELECT COUNT(*) FROM claim_attempts"
        ).fetchone()[0]
        # Decision row written, but no new claim attempt.
        decision_count = conn.execute(
            "SELECT COUNT(*) FROM human_decisions"
        ).fetchone()[0]
        conn.close()
        assert after_attempt_count == before_attempt_count
        assert decision_count == 1
        assert result.applied[0].new_attempt_id is None
        assert "notes-only" in result.applied[0].note


# ---------------------------------------------------------------- reject → quarantine

class TestHumanReject:
    def test_reject_quarantines_accepted_attempt(self, tmp_path: Path) -> None:
        slice_result = _populate_deal(tmp_path)
        accepted = slice_result.accepted_attempt_ids[0]
        conn = duckdb.connect(str(slice_result.db_path))
        repo = DealRoomRepository(conn)
        apply_human_decisions(
            repo,
            decisions=[
                HumanDecisionImport(
                    attempt_id=accepted,
                    decision="reject",
                    correction_json=None,
                    reviewer="bob",
                    reviewed_at=datetime(2026, 5, 8, 14, 0, 0, tzinfo=timezone.utc),
                    notes=None,
                )
            ],
            deal_slug="synthetic-demo",
        )
        status = conn.execute(
            "SELECT status FROM claim_attempts WHERE attempt_id = ?", (accepted,)
        ).fetchone()[0]
        conn.close()
        assert status == "superseded"


# ---------------------------------------------------------------- accept escalates → accepted

class TestHumanAccept:
    def test_accept_escalated_attempt_becomes_accepted(self, tmp_path: Path) -> None:
        # Force an escalated attempt: use a verifier that yields confirm + reject
        # to push aggregate to escalated. Simplest: use AlwaysReject then
        # human accepts.
        from tests.test_orchestrator_vertical_slice import _AlwaysRejectVerifier  # type: ignore  # noqa: E501
        orch = Orchestrator(
            deal_slug="synthetic-demo",
            extractor=OfflineConfidentialityExtractor(),
            verifier=_AlwaysRejectVerifier(),
        )
        slice_result = orch.run_synthetic_vertical_slice(
            run_dir=_run_dir(tmp_path),
            filing_path=SYNTHETIC_FILING_PATH,
        )
        rejected = slice_result.rejected_attempt_ids[0]
        conn = duckdb.connect(str(slice_result.db_path))
        repo = DealRoomRepository(conn)
        starting_status = conn.execute(
            "SELECT status FROM claim_attempts WHERE attempt_id = ?", (rejected,)
        ).fetchone()[0]
        # The orchestrator stops the rejected branch at 'verified_rejected'
        # (no automatic escalation in the slice).
        assert starting_status in {"verified_rejected", "escalated"}
        apply_human_decisions(
            repo,
            decisions=[
                HumanDecisionImport(
                    attempt_id=rejected,
                    decision="accept",
                    correction_json=None,
                    reviewer="alice",
                    reviewed_at=datetime(2026, 5, 8, 14, 0, 0, tzinfo=timezone.utc),
                    notes="human override after independent re-review",
                )
            ],
            deal_slug="synthetic-demo",
        )
        final_status = conn.execute(
            "SELECT status FROM claim_attempts WHERE attempt_id = ?", (rejected,)
        ).fetchone()[0]
        conn.close()
        assert final_status == "accepted"


# ---------------------------------------------------------------- defer → no transition

class TestHumanDefer:
    def test_defer_records_decision_and_does_not_transition(self, tmp_path: Path) -> None:
        slice_result = _populate_deal(tmp_path)
        accepted = slice_result.accepted_attempt_ids[0]
        conn = duckdb.connect(str(slice_result.db_path))
        repo = DealRoomRepository(conn)
        apply_human_decisions(
            repo,
            decisions=[
                HumanDecisionImport(
                    attempt_id=accepted,
                    decision="defer",
                    correction_json=None,
                    reviewer="alice",
                    reviewed_at=datetime(2026, 5, 8, 14, 0, 0, tzinfo=timezone.utc),
                    notes="needs more review",
                )
            ],
            deal_slug="synthetic-demo",
        )
        status = conn.execute(
            "SELECT status FROM claim_attempts WHERE attempt_id = ?", (accepted,)
        ).fetchone()[0]
        decision = conn.execute(
            "SELECT decision FROM human_decisions WHERE attempt_id = ?", (accepted,)
        ).fetchone()[0]
        conn.close()
        # accepted attempts that are deferred remain accepted.
        assert status == "accepted"
        assert decision == "defer"
