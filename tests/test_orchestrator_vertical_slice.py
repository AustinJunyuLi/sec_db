"""Phase 6 (US-007) — first offline orchestrator vertical slice."""

from __future__ import annotations

import json
from pathlib import Path

import duckdb
import pytest

from sec_review_compiler.filing.examples import SYNTHETIC_FILING_PATH
from sec_review_compiler.orchestration import (
    OfflineConfidentialityExtractor,
    OfflineFakeVerifier,
    Orchestrator,
    SliceResult,
    VerifierProposal,
)


# ---------------------------------------------------------------- helpers

def _make_run_dir(tmp_path: Path) -> Path:
    run_dir = tmp_path / "20260508T140000Z_synthetic-demo_deadbeef"
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir


@pytest.fixture()
def slice_result(tmp_path: Path) -> SliceResult:
    orch = Orchestrator(
        deal_slug="synthetic-demo",
        extractor=OfflineConfidentialityExtractor(),
        verifier=OfflineFakeVerifier(),
    )
    return orch.run_synthetic_vertical_slice(
        run_dir=_make_run_dir(tmp_path),
        filing_path=SYNTHETIC_FILING_PATH,
    )


# ---------------------------------------------------------------- slice produces an NDA attempt

class TestSliceProducesNDAAttempt:
    def test_at_least_one_confidentiality_agreement_attempt(self, slice_result: SliceResult) -> None:
        conn = duckdb.connect(str(slice_result.db_path))
        rows = conn.execute(
            """
            SELECT attempt_id, payload_json, status, origin_agent_role
            FROM claim_attempts
            ORDER BY created_sequence
            """
        ).fetchall()
        conn.close()
        assert rows, "slice produced zero claim attempts"
        nda_rows = [r for r in rows if "confidentiality_agreement" in r[1]]
        assert nda_rows, "slice did not produce a confidentiality-agreement attempt"

    def test_claim_quote_is_bound_by_verify_quote(self, slice_result: SliceResult) -> None:
        raw_text = SYNTHETIC_FILING_PATH.read_text(encoding="utf-8")
        conn = duckdb.connect(str(slice_result.db_path))
        bindings = conn.execute(
            """
            SELECT eb.quote_text, eb.binding_status, eb.char_start, eb.char_end
            FROM evidence_bindings eb
            JOIN claim_attempts ca ON ca.attempt_id = eb.attempt_id
            WHERE ca.payload_json LIKE '%confidentiality_agreement%'
              AND ca.supersedes_attempt_id IS NULL
            """
        ).fetchall()
        conn.close()
        assert bindings, "no evidence bindings for the NDA attempt"
        for quote, binding_status, char_start, char_end in bindings:
            assert binding_status == "accepted"
            assert raw_text[char_start:char_end] == quote


# ---------------------------------------------------------------- accepted claim has exact evidence

class TestAcceptedClaimHasExactEvidence:
    def test_accepted_attempt_evidence_slices_back_to_text(self, slice_result: SliceResult) -> None:
        assert slice_result.accepted_attempt_ids, "no accepted attempts"
        raw_text = SYNTHETIC_FILING_PATH.read_text(encoding="utf-8")
        conn = duckdb.connect(str(slice_result.db_path))
        for attempt_id in slice_result.accepted_attempt_ids:
            rows = conn.execute(
                "SELECT quote_text, char_start, char_end FROM evidence_bindings "
                "WHERE attempt_id = ? AND binding_status = 'accepted'",
                (attempt_id,),
            ).fetchall()
            assert rows, f"accepted attempt {attempt_id} has no accepted evidence"
            for quote, start, end in rows:
                assert raw_text[start:end] == quote
        conn.close()


# ---------------------------------------------------------------- rejected does NOT enter canonical

class _AlwaysRejectVerifier:
    def verify(self, **kwargs):
        return VerifierProposal(
            verdict="reject",
            reasoning_summary="test-only verifier rejects every attempt",
            supporting_evidence_paragraph_ids=(),
            proposed_correction_json=None,
            confidence=1.0,
        )


class TestRejectionBlocksCanonical:
    def test_rejected_attempts_never_become_accepted(self, tmp_path: Path) -> None:
        orch = Orchestrator(
            deal_slug="synthetic-demo",
            extractor=OfflineConfidentialityExtractor(),
            verifier=_AlwaysRejectVerifier(),
        )
        result = orch.run_synthetic_vertical_slice(
            run_dir=_make_run_dir(tmp_path),
            filing_path=SYNTHETIC_FILING_PATH,
        )
        assert result.accepted_attempt_ids == ()
        assert result.rejected_attempt_ids, "expected at least one rejected attempt"
        conn = duckdb.connect(str(result.db_path))
        statuses = conn.execute(
            "SELECT status FROM claim_attempts WHERE supersedes_attempt_id IS NULL"
        ).fetchall()
        conn.close()
        states = {r[0] for r in statuses}
        assert "accepted" not in states
        assert "consistent" not in states


# ---------------------------------------------------------------- partial → new attempt

class _AlwaysPartialVerifier:
    def __init__(self) -> None:
        self.calls = 0

    def verify(self, **kwargs):
        self.calls += 1
        return VerifierProposal(
            verdict="partial",
            reasoning_summary="test-only verifier requests correction",
            supporting_evidence_paragraph_ids=tuple(kwargs["cited_paragraph_ids"]),
            proposed_correction_json=json.dumps(
                {"corrected": True, "field": "date_granularity"},
                sort_keys=True,
            ),
            confidence=0.7,
        )


class TestPartialCorrectionCreatesNewAttempt:
    def test_partial_yields_corrected_attempt_with_supersedes(self, tmp_path: Path) -> None:
        verifier = _AlwaysPartialVerifier()
        orch = Orchestrator(
            deal_slug="synthetic-demo",
            extractor=OfflineConfidentialityExtractor(),
            verifier=verifier,
        )
        result = orch.run_synthetic_vertical_slice(
            run_dir=_make_run_dir(tmp_path),
            filing_path=SYNTHETIC_FILING_PATH,
        )
        assert verifier.calls > 0
        assert result.correction_attempt_ids, "expected a corrected attempt"
        assert result.superseded_attempt_ids, "expected an original to be superseded"
        conn = duckdb.connect(str(result.db_path))
        for new_id in result.correction_attempt_ids:
            row = conn.execute(
                "SELECT supersedes_attempt_id, status FROM claim_attempts WHERE attempt_id = ?",
                (new_id,),
            ).fetchone()
            assert row is not None
            supersedes, status = row
            assert supersedes is not None
            assert supersedes in result.superseded_attempt_ids
            assert status == "proposed"
        for orig_id in result.superseded_attempt_ids:
            status = conn.execute(
                "SELECT status FROM claim_attempts WHERE attempt_id = ?", (orig_id,)
            ).fetchone()[0]
            assert status == "superseded"
        conn.close()


# ---------------------------------------------------------------- artifact location

class TestArtifactsUnderRunDir:
    def test_all_artifacts_under_run_deal_dir(self, slice_result: SliceResult) -> None:
        for artifact in slice_result.artifacts:
            assert slice_result.deal_dir in artifact.path.parents or slice_result.deal_dir == artifact.path.parent
            assert artifact.path.exists(), f"missing artifact {artifact.name}"
        assert slice_result.db_path.exists()
        assert slice_result.db_path.parent == slice_result.deal_dir
        assert (slice_result.deal_dir / "filing_package_manifest.json").exists()

    def test_artifact_set(self, slice_result: SliceResult) -> None:
        names = {a.name for a in slice_result.artifacts}
        assert names == {
            "claim_cards.csv",
            "review_queue.csv",
            "human_decisions_template.csv",
            "provider_calls.jsonl",
            "tool_calls.jsonl",
        }
