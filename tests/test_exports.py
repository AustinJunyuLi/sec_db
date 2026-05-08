"""Phase 6 (US-007) — review exports."""

from __future__ import annotations

import csv
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


# ---------------------------------------------------------------- file presence

def test_required_export_files_exist(slice_result: SliceResult) -> None:
    deal_dir = slice_result.deal_dir
    assert (deal_dir / "exports" / "claim_cards.csv").exists()
    assert (deal_dir / "exports" / "review_queue.csv").exists()
    assert (deal_dir / "exports" / "human_decisions_template.csv").exists()
    assert (deal_dir / "provider_calls.jsonl").exists()
    assert (deal_dir / "tool_calls.jsonl").exists()


# ---------------------------------------------------------------- claim_cards

def test_claim_cards_columns_and_rows(slice_result: SliceResult) -> None:
    path = slice_result.deal_dir / "exports" / "claim_cards.csv"
    rows = list(csv.DictReader(path.open()))
    expected_cols = {
        "attempt_id", "deal_slug", "claim_type", "claim_fingerprint",
        "status", "supersedes_attempt_id", "origin_agent_role",
        "evidence_paragraph_ids", "evidence_quote_count", "payload_json",
    }
    assert set(rows[0].keys()) == expected_cols
    assert any("confidentiality_agreement" in r["payload_json"] for r in rows)
    nda_row = next(r for r in rows if "confidentiality_agreement" in r["payload_json"])
    assert nda_row["status"] == "accepted"
    assert int(nda_row["evidence_quote_count"]) >= 1


# ---------------------------------------------------------------- review_queue (rejected case)

class _AlwaysRejectVerifier:
    def verify(self, **kwargs):
        return VerifierProposal(
            verdict="reject",
            reasoning_summary="test-only verifier rejects",
            supporting_evidence_paragraph_ids=(),
            proposed_correction_json=None,
            confidence=1.0,
        )


def test_review_queue_contains_rejected_and_escalated(tmp_path: Path) -> None:
    orch = Orchestrator(
        deal_slug="synthetic-demo",
        extractor=OfflineConfidentialityExtractor(),
        verifier=_AlwaysRejectVerifier(),
    )
    result = orch.run_synthetic_vertical_slice(
        run_dir=_make_run_dir(tmp_path),
        filing_path=SYNTHETIC_FILING_PATH,
    )
    rq_path = result.deal_dir / "exports" / "review_queue.csv"
    rq_rows = list(csv.DictReader(rq_path.open()))
    assert rq_rows, "review queue should contain rejected/escalated attempts"
    assert all(
        r["status"] in {"escalated", "verified_rejected", "binding_failed"}
        for r in rq_rows
    )


def test_review_queue_empty_when_all_confirmed(slice_result: SliceResult) -> None:
    rq_path = slice_result.deal_dir / "exports" / "review_queue.csv"
    rq_rows = list(csv.DictReader(rq_path.open()))
    assert rq_rows == []


# ---------------------------------------------------------------- human_decisions_template

def test_human_decisions_template_has_header_only(slice_result: SliceResult) -> None:
    path = slice_result.deal_dir / "exports" / "human_decisions_template.csv"
    rows = list(csv.reader(path.open()))
    assert rows[0] == [
        "attempt_id", "decision", "correction_json", "reviewer", "reviewed_at", "notes"
    ]
    # No data rows in the template.
    assert len(rows) == 1


# ---------------------------------------------------------------- jsonl files

def test_provider_calls_jsonl_is_valid(slice_result: SliceResult) -> None:
    path = slice_result.deal_dir / "provider_calls.jsonl"
    text = path.read_text(encoding="utf-8")
    # Empty is acceptable for offline runs; otherwise each line is JSON.
    for line in text.splitlines():
        json.loads(line)


def test_tool_calls_jsonl_is_valid(slice_result: SliceResult) -> None:
    path = slice_result.deal_dir / "tool_calls.jsonl"
    text = path.read_text(encoding="utf-8")
    for line in text.splitlines():
        json.loads(line)
