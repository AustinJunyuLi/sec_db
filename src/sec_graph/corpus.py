"""Corpus skeleton artifact writer.

This module keeps a tiny local atomic temp+rename helper because the current
allowed run-kernel surface does not expose a reusable atomic write helper.
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

from sec_graph.costs import (
    CostEnvelopeAssumptions,
    DealCostRuntimeMetrics,
    build_cost_runtime_summary,
    cost_summary_csv_rows,
)

REQUIRED_CORPUS_ARTIFACTS = (
    "corpus_manifest.jsonl",
    "shard_plan.jsonl",
    "attempt_ledger.jsonl",
    "failure_ledger.jsonl",
    "progress_ledger.jsonl",
    "stage_artifacts.jsonl",
    "cost_runtime_summary.csv",
    "cost_runtime_summary.json",
    "aggregate_proof_summary.json",
    "resume_report.json",
)


@dataclass(frozen=True)
class CorpusSkeletonResult:
    run_dir: Path
    artifact_paths: tuple[Path, ...]
    cost_usage_basis: str


def create_corpus_skeleton(
    *,
    run_dir: Path,
    run_id: str,
    deal_slugs: list[str],
    observed_metrics: list[DealCostRuntimeMetrics],
    assumptions: CostEnvelopeAssumptions,
    shard_size: int = 1,
) -> CorpusSkeletonResult:
    """Create corpus-run skeleton artifacts under ``run_dir``.

    The helper is intentionally strict: it refuses empty deal lists, invalid
    shard sizes, duplicate slugs, non-three-deal observed metrics, and existing
    target artifacts.
    """

    if not run_id:
        raise ValueError("run_id is required")
    if not deal_slugs:
        raise ValueError("deal_slugs is required")
    if len(set(deal_slugs)) != len(deal_slugs):
        raise ValueError("deal_slugs must be unique")
    if shard_size <= 0:
        raise ValueError("shard_size must be positive")

    cost_summary = build_cost_runtime_summary(observed_metrics, assumptions)
    run_dir.mkdir(parents=True, exist_ok=True)
    existing = [name for name in REQUIRED_CORPUS_ARTIFACTS if (run_dir / name).exists()]
    if existing:
        raise FileExistsError(f"refusing to overwrite existing corpus artifact(s): {', '.join(existing)}")

    shard_rows = _shard_rows(run_id, deal_slugs, shard_size)
    corpus_manifest_rows = _corpus_manifest_rows(run_id, deal_slugs, shard_rows)
    payloads: dict[str, str] = {
        "corpus_manifest.jsonl": _jsonl(corpus_manifest_rows),
        "shard_plan.jsonl": _jsonl(shard_rows),
        "attempt_ledger.jsonl": _jsonl(_attempt_rows(run_id, deal_slugs)),
        "failure_ledger.jsonl": "",
        "progress_ledger.jsonl": _jsonl(_progress_rows(run_id, deal_slugs)),
        "cost_runtime_summary.json": _json(
            {
                "run_id": run_id,
                **cost_summary,
            }
        ),
        "cost_runtime_summary.csv": _csv(cost_summary_csv_rows(cost_summary)),
        "aggregate_proof_summary.json": _json(
            {
                "run_id": run_id,
                "summary_version": "aggregate_proof_summary_v1",
                "status": "failed_system",
                "reason": "corpus skeleton only; no deal proof artifacts imported",
                "deals_planned": len(deal_slugs),
                "deals_completed": 0,
                "deals_failed_system": 0,
                "deals_passed_clean": 0,
                "deals_needs_review": 0,
                "deals_high_burden": 0,
            }
        ),
        "resume_report.json": _json(
            {
                "run_id": run_id,
                "summary_version": "resume_report_v1",
                "resume_supported": True,
                "reused": [],
                "recomputed": [],
                "refused": [],
                "pending_deals": deal_slugs,
                "status": "not_started",
            }
        ),
    }
    payloads["stage_artifacts.jsonl"] = _jsonl(_stage_artifact_rows(run_dir, payloads))

    written: list[Path] = []
    for name in REQUIRED_CORPUS_ARTIFACTS:
        path = run_dir / name
        _atomic_write_text(path, payloads[name])
        written.append(path)
    return CorpusSkeletonResult(
        run_dir=run_dir,
        artifact_paths=tuple(written),
        cost_usage_basis=str(cost_summary["usage_basis"]),
    )


def _shard_rows(run_id: str, deal_slugs: list[str], shard_size: int) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for index in range(0, len(deal_slugs), shard_size):
        rows.append(
            {
                "run_id": run_id,
                "shard_id": f"shard-{len(rows) + 1:04d}",
                "deal_slugs": deal_slugs[index : index + shard_size],
                "parallel_linkflow_artifact_writers": True,
                "duckdb_writer": "single_import_reconcile_validate_project_writer",
            }
        )
    return rows


def _corpus_manifest_rows(
    run_id: str,
    deal_slugs: list[str],
    shard_rows: list[dict[str, object]],
) -> list[dict[str, object]]:
    shard_by_slug = {
        slug: str(row["shard_id"])
        for row in shard_rows
        for slug in row["deal_slugs"]  # type: ignore[union-attr]
    }
    return [
        {
            "run_id": run_id,
            "deal_slug": slug,
            "source_order": index + 1,
            "shard_id": shard_by_slug[slug],
            "status": "queued",
        }
        for index, slug in enumerate(deal_slugs)
    ]


def _attempt_rows(run_id: str, deal_slugs: list[str]) -> list[dict[str, object]]:
    return [
        {
            "run_id": run_id,
            "deal_slug": slug,
            "attempt": 1,
            "state": "not_started",
        }
        for slug in deal_slugs
    ]


def _progress_rows(run_id: str, deal_slugs: list[str]) -> list[dict[str, object]]:
    return [
        {
            "run_id": run_id,
            "deal_slug": slug,
            "stage": "corpus",
            "state": "queued",
            "attempt": 1,
            "artifact_digests": {},
            "failure_reason": None,
        }
        for slug in deal_slugs
    ]


def _stage_artifact_rows(run_dir: Path, payloads: dict[str, str]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for name in REQUIRED_CORPUS_ARTIFACTS:
        payload = payloads.get(name, "")
        self_referential = name == "stage_artifacts.jsonl"
        rows.append(
            {
                "artifact_path": name,
                "artifact_kind": _artifact_kind(name),
                "owning_stage": "corpus",
                "deal_slug": None,
                "digest": None if self_referential else hashlib.sha256(payload.encode("utf-8")).hexdigest(),
                "digest_status": "self_referential_digest_not_recorded" if self_referential else "recorded",
                "byte_count": None if self_referential else len(payload.encode("utf-8")),
                "created_by": "create_corpus_skeleton",
                "finalized": True,
                "path_scope": "run_dir_relative",
                "run_dir": str(run_dir),
            }
        )
    return rows


def _artifact_kind(name: str) -> str:
    if name.endswith(".jsonl"):
        return "jsonl_ledger"
    if name.endswith(".csv"):
        return "csv_summary"
    return "json_summary"


def _jsonl(rows: list[dict[str, object]]) -> str:
    if not rows:
        return ""
    return "\n".join(json.dumps(row, sort_keys=True, separators=(",", ":")) for row in rows) + "\n"


def _json(payload: dict[str, object]) -> str:
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def _csv(rows: list[dict[str, object]]) -> str:
    if not rows:
        return ""
    fieldnames = list(rows[0].keys())
    with tempfile.SpooledTemporaryFile(mode="w+", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
        handle.seek(0)
        return handle.read()


def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, path)
        _fsync_dir(path.parent)
    except Exception:
        try:
            tmp_path.unlink()
        except FileNotFoundError:
            pass
        raise


def _fsync_dir(path: Path) -> None:
    if not hasattr(os, "O_DIRECTORY"):
        return
    try:
        fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    except OSError:
        return
    try:
        os.fsync(fd)
    finally:
        os.close(fd)
