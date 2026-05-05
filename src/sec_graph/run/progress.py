"""Append-only run ledgers."""

from __future__ import annotations

import json
from pathlib import Path

from .io import atomic_write_jsonl, file_sha256


_PROGRESS_STATES = {
    "queued",
    "ingested",
    "evidence_mapped",
    "llm_artifacts_written",
    "claims_imported",
    "claims_disposed",
    "reconciled",
    "judgments_derived",
    "validated",
    "projected",
    "blocked",
}


def append_progress(
    run_dir: Path,
    *,
    run_id: str,
    deal_slug: str,
    stage: str,
    state: str,
    attempt: int,
    recorded_at: str,
    artifact_digest: str | None = None,
    failure_reason: str | None = None,
) -> None:
    if state not in _PROGRESS_STATES:
        raise ValueError(f"unknown progress state: {state}")
    if attempt < 1:
        raise ValueError("attempt must be positive")
    path = run_dir / "progress_ledger.jsonl"
    rows = _read_jsonl(path)
    rows.append(
        {
            "run_id": run_id,
            "deal_slug": deal_slug,
            "stage": stage,
            "attempt": attempt,
            "state": state,
            "artifact_digest": artifact_digest,
            "failure_reason": failure_reason,
            "recorded_at": recorded_at,
        }
    )
    atomic_write_jsonl(path, rows)


def record_artifact(
    run_dir: Path,
    *,
    run_id: str,
    path: Path,
    artifact_kind: str,
    owning_stage: str,
    deal_slug: str | None,
    created_by: str,
) -> dict[str, object]:
    digest = file_sha256(path)
    rel_path = str(path.relative_to(run_dir)) if path.is_relative_to(run_dir) else str(path)
    row = {
        "run_id": run_id,
        "artifact_path": rel_path,
        "artifact_kind": artifact_kind,
        "owning_stage": owning_stage,
        "deal_slug": deal_slug,
        "sha256": digest,
        "created_by": created_by,
        "finalized": True,
    }
    ledger = run_dir / "stage_artifacts.jsonl"
    rows = _read_jsonl(ledger)
    rows.append(row)
    atomic_write_jsonl(ledger, rows)
    return row


def _read_jsonl(path: Path) -> list[dict[str, object]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
