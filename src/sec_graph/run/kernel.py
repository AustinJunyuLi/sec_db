"""Run kernel facade and conservative resume checks."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .ids import RunClock
from .io import append_jsonl_atomic, atomic_write_json, sha256_file


class ResumeRefused(RuntimeError):
    """Raised when explicit resume invariants fail."""


@dataclass(frozen=True)
class ResumeDecision:
    can_resume: bool
    reused_artifacts: list[str]


_PROGRESS_STATES = {
    "queued",
    "ingested",
    "evidence_mapped",
    "llm_artifacts_written",
    "claims_imported",
    "reconciled",
    "validated",
    "projected",
    "blocked",
}


class RunKernel:
    def __init__(self, run_dir: Path, *, run_id: str, config_hash: str) -> None:
        self.run_dir = run_dir
        self.run_id = run_id
        self.config_hash = config_hash
        self.clock = RunClock.from_run_id(run_id, config_hash=config_hash)

    @classmethod
    def create(
        cls,
        run_dir: Path,
        *,
        run_id: str,
        config_hash: str,
        run_config: dict[str, Any] | None = None,
    ) -> "RunKernel":
        run_dir.mkdir(parents=True, exist_ok=True)
        atomic_write_json(run_dir / "run_manifest.json", {"run_id": run_id, "config_hash": config_hash, "run_config": run_config or {}})
        return cls(run_dir, run_id=run_id, config_hash=config_hash)

    def append_progress(
        self,
        *,
        deal_slug: str,
        stage: str,
        state: str,
        attempt: int,
        artifact_digests: dict[str, str] | None = None,
        failure_reason: str | None = None,
    ) -> dict[str, Any]:
        if state not in _PROGRESS_STATES:
            raise ValueError(f"unknown progress state: {state}")
        if attempt < 1:
            raise ValueError("attempt must be positive")
        row = {
            "run_id": self.run_id,
            "deal_slug": deal_slug,
            "stage": stage,
            "state": state,
            "attempt": attempt,
            "artifact_digests": artifact_digests or {},
            "created_at": self.clock.timestamp(f"progress:{stage}:{deal_slug}", sequence=attempt),
        }
        if failure_reason is not None:
            row["failure_reason"] = failure_reason
        append_jsonl_atomic(self.run_dir / "progress_ledger.jsonl", row)
        return row

    def record_stage_artifact(
        self,
        path: Path,
        *,
        artifact_kind: str,
        owning_stage: str,
        deal_slug: str | None = None,
    ) -> dict[str, Any]:
        row = {
            "run_id": self.run_id,
            "artifact_path": str(path.relative_to(self.run_dir)),
            "artifact_kind": artifact_kind,
            "owning_stage": owning_stage,
            "deal_slug": deal_slug,
            "sha256": sha256_file(path),
            "finalized": True,
            "created_by": owning_stage,
            "created_at": self.clock.timestamp(f"artifact:{owning_stage}:{path.relative_to(self.run_dir)}"),
        }
        append_jsonl_atomic(self.run_dir / "stage_artifacts.jsonl", row)
        return row


def check_resume_config(run_dir: Path, *, run_id: str, config_hash: str) -> ResumeDecision:
    manifest_path = run_dir / "run_manifest.json"
    if not manifest_path.exists():
        raise ResumeRefused("run_manifest.json missing")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("run_id") != run_id:
        raise ResumeRefused("run id mismatch")
    if manifest.get("config_hash") != config_hash:
        raise ResumeRefused("config hash mismatch")
    reused: list[str] = []
    artifact_path = run_dir / "stage_artifacts.jsonl"
    if artifact_path.exists():
        for line in artifact_path.read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            path = run_dir / row["artifact_path"]
            if not path.exists() or sha256_file(path) != row["sha256"]:
                raise ResumeRefused(f"artifact digest mismatch: {row['artifact_path']}")
            reused.append(row["artifact_path"])
    return ResumeDecision(can_resume=True, reused_artifacts=reused)
