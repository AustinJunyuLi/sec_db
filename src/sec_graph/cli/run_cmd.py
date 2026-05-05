"""Run the hard-reset evidence/claim/canonical/proof pipeline."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
from pathlib import Path

from sec_graph.cli.extract_cmd import llm_config_from_args
from sec_graph.corpus import create_corpus_skeleton
from sec_graph.extract.disposition import dispose_claims_for_filing
from sec_graph.extract.llm.models import DEFAULT_REQUEST_MODE, LLMProviderConfig
from sec_graph.extract.pipeline import run_extract
from sec_graph.ingest.pipeline import DEFAULT_EXAMPLES_DIR, IngestSource, example_sources, filing_sources, ingest_sources
from sec_graph.judgments import derive_judgments
from sec_graph.project.summaries import default_cost_envelope_assumptions, observed_deal_metrics, write_projection_outputs
from sec_graph.reconcile.pipeline import reconcile_all
from sec_graph.run import (
    RunClock,
    RunLock,
    append_progress,
    atomic_write_json,
    config_hash,
    record_artifact,
    validate_run_id,
)
from sec_graph.schema import connect, init_schema, versions
from sec_graph.validate.integrity import write_validation_outputs


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--all", action="store_true", help="run all available filings for the selected source")
    group.add_argument("--slugs", nargs="+", help="deal slugs to run in order")
    parser.add_argument("--source", choices=["examples", "filings"], default="examples", help="input source")
    parser.add_argument("--db", type=Path, help="optional working DuckDB path")
    parser.add_argument("--examples-dir", type=Path, default=DEFAULT_EXAMPLES_DIR, help="example markdown directory")
    parser.add_argument("--run-dir", type=Path, required=True, help="run artifact directory")
    parser.add_argument("--run-id", required=True, help="explicit top-level run id")
    parser.add_argument("--resume", action="store_true", help="explicit conservative resume")
    parser.add_argument("--projection", default="bidder_cycle_baseline_v1", help="projection name")
    parser.add_argument("--llm-provider", choices=["linkflow"], help="optional LLM typed-claim provider")
    parser.add_argument("--llm-model", default="gpt-5.5", help="LLM model name")
    parser.add_argument("--llm-reasoning-effort", choices=["low", "medium", "high", "xhigh"], default="medium")
    parser.add_argument("--request-mode", choices=[DEFAULT_REQUEST_MODE], default=DEFAULT_REQUEST_MODE)
    return parser


def run_pipeline(
    *,
    run_id: str,
    run_dir: Path,
    source: str,
    slugs: list[str] | None,
    projection_name: str,
    examples_dir: Path = DEFAULT_EXAMPLES_DIR,
    db_path: Path | None = None,
    llm_config: LLMProviderConfig | None = None,
    request_mode: str = DEFAULT_REQUEST_MODE,
    resume: bool = False,
) -> dict[str, object]:
    validate_run_id(run_id)
    selected_sources = _sources(source, slugs, all_selected=slugs is None, examples_dir=examples_dir)
    clock = RunClock(run_id)
    manifest = _manifest_payload(
        run_id=run_id,
        source=source,
        sources=selected_sources,
        projection_name=projection_name,
        llm_config=llm_config,
        request_mode=request_mode,
        clock=clock,
    )
    _validate_resume(run_dir, manifest, resume)
    with RunLock(run_dir, run_id):
        manifest_path = run_dir / "run_manifest.json"
        if not manifest_path.exists():
            atomic_write_json(manifest_path, manifest)
            record_artifact(run_dir, run_id=run_id, path=manifest_path, artifact_kind="json_manifest", owning_stage="run_kernel", deal_slug=None, created_by="run_pipeline")
        working_db = db_path or run_dir / "working.duckdb"
        if working_db.exists() and not resume:
            raise FileExistsError(f"{working_db} already exists; pass --resume or choose a new run")
        if working_db.exists() and resume:
            working_db.unlink()
        conn = connect(working_db)
        init_schema(conn)
        _insert_manifest(conn, manifest)
        for source_item in selected_sources:
            append_progress(run_dir, run_id=run_id, deal_slug=source_item.slug, stage="run", state="queued", attempt=1, recorded_at=clock.timestamp("run", sequence=1))
        filings = ingest_sources(conn, selected_sources, run_id=run_id)
        for filing in filings:
            append_progress(run_dir, run_id=run_id, deal_slug=filing.deal_slug, stage="ingest", state="ingested", attempt=1, recorded_at=clock.timestamp("ingest", sequence=1))
            claim_ids = run_extract(
                conn,
                filing_id=filing.filing_id,
                run_id=run_id,
                llm_config=llm_config,
                request_mode=request_mode,
            )
            append_progress(run_dir, run_id=run_id, deal_slug=filing.deal_slug, stage="extract", state="claims_imported", attempt=1, recorded_at=clock.timestamp("extract", sequence=1), artifact_digest=str(len(claim_ids)))
            dispose_claims_for_filing(conn, filing_id=filing.filing_id, run_id=run_id)
            append_progress(
                run_dir,
                run_id=run_id,
                deal_slug=filing.deal_slug,
                stage="dispose",
                state="claims_disposed",
                attempt=1,
                recorded_at=clock.timestamp("dispose", sequence=1),
            )
        reconcile_all(conn, run_id=run_id)
        for filing in filings:
            append_progress(run_dir, run_id=run_id, deal_slug=filing.deal_slug, stage="reconcile", state="reconciled", attempt=1, recorded_at=clock.timestamp("reconcile", sequence=1))
        derive_judgments(conn, run_id=run_id)
        for filing in filings:
            append_progress(
                run_dir,
                run_id=run_id,
                deal_slug=filing.deal_slug,
                stage="judgments",
                state="judgments_derived",
                attempt=1,
                recorded_at=clock.timestamp("judgments", sequence=1),
            )
        report = write_validation_outputs(conn, run_dir, allow_existing=True)
        record_artifact(run_dir, run_id=run_id, path=run_dir / "validation_report.json", artifact_kind="json_report", owning_stage="validate", deal_slug=None, created_by="write_validation_outputs")
        if not report["passed"]:
            _write_failed_validation_proof(
                run_dir=run_dir,
                run_id=run_id,
                manifest=manifest,
                validation_report=report,
                llm_config=llm_config,
                request_mode=request_mode,
            )
            record_artifact(
                run_dir,
                run_id=run_id,
                path=run_dir / "failed_validation_proof.json",
                artifact_kind="json_report",
                owning_stage="validate",
                deal_slug=None,
                created_by="_write_failed_validation_proof",
            )
            raise RuntimeError(f"run failed validation; artifacts: {run_dir}")
        proof = write_projection_outputs(conn, run_dir, run_id=run_id, projection_name=projection_name, allow_existing=True)
        for artifact in (
            "proof_summary.json",
            "bidder_rows.jsonl",
            "bidder_summary.csv",
            "coverage_results.csv",
            "claim_dispositions.csv",
            "cost_runtime_summary.json",
            "cost_runtime_summary.csv",
            "provider_usage_ledger.jsonl",
            "latency_ledger.jsonl",
            "run_memo.md",
        ):
            record_artifact(run_dir, run_id=run_id, path=run_dir / artifact, artifact_kind="proof_artifact", owning_stage="project", deal_slug=None, created_by="write_projection_outputs")
        metrics = observed_deal_metrics(conn, run_id)
        if len(metrics) == 3:
            corpus_result = create_corpus_skeleton(
                run_dir=run_dir / "corpus_skeleton",
                run_id=run_id,
                deal_slugs=[item.slug for item in selected_sources],
                observed_metrics=metrics,
                assumptions=default_cost_envelope_assumptions(),
            )
            for path in corpus_result.artifact_paths:
                record_artifact(
                    run_dir,
                    run_id=run_id,
                    path=path,
                    artifact_kind="corpus_skeleton_artifact",
                    owning_stage="corpus",
                    deal_slug=None,
                    created_by="create_corpus_skeleton",
                )
        for filing in filings:
            append_progress(run_dir, run_id=run_id, deal_slug=filing.deal_slug, stage="project", state="projected", attempt=1, recorded_at=clock.timestamp("project", sequence=1))
        conn.close()
        _atomic_copy(working_db, run_dir / "canonical.duckdb")
        record_artifact(run_dir, run_id=run_id, path=run_dir / "canonical.duckdb", artifact_kind="duckdb_snapshot", owning_stage="run_kernel", deal_slug=None, created_by="run_pipeline")
        atomic_write_json(run_dir / "resume_report.json", {"run_id": run_id, "resume": bool(resume), "reused": [], "recomputed": [item.slug for item in selected_sources], "refused": []})
        return proof


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    llm_config = llm_config_from_args(args)
    try:
        run_pipeline(
            run_id=args.run_id,
            run_dir=args.run_dir,
            source=args.source,
            slugs=args.slugs if not args.all else None,
            projection_name=args.projection,
            examples_dir=args.examples_dir,
            db_path=args.db,
            llm_config=llm_config,
            request_mode=args.request_mode,
            resume=args.resume,
        )
    except Exception as exc:
        print(str(exc))
        return 1
    print(f"run complete; artifacts: {args.run_dir}")
    return 0


def _sources(source: str, slugs: list[str] | None, all_selected: bool, examples_dir: Path) -> list[IngestSource]:
    if source == "examples":
        available = example_sources(examples_dir)
        if all_selected:
            return available
        wanted = set(slugs or [])
        selected = [item for item in available if item.slug in wanted]
        missing = wanted - {item.slug for item in selected}
        if missing:
            raise FileNotFoundError(f"example slug(s) not found: {sorted(missing)}")
        return selected
    if all_selected:
        raise ValueError("--all is not supported for source=filings; pass explicit --slugs")
    if not slugs:
        raise ValueError("source=filings requires --slugs")
    return filing_sources(slugs)


def _manifest_payload(
    *,
    run_id: str,
    source: str,
    sources: list[IngestSource],
    projection_name: str,
    llm_config: LLMProviderConfig | None,
    request_mode: str,
    clock: RunClock,
) -> dict[str, object]:
    input_hashes = {item.slug: hashlib.sha256(item.source_path.read_bytes()).hexdigest() for item in sources}
    payload = {
        "run_id": run_id,
        "run_type": "proof",
        "source": source,
        "slugs": [item.slug for item in sources],
        "source_manifest_hash": config_hash(input_hashes),
        "projection_name": projection_name,
        "schema_version": versions.SCHEMA_VERSION,
        "extract_version": versions.EXTRACT_VERSION,
        "reconcile_version": versions.RECONCILE_VERSION,
        "validate_version": versions.VALIDATE_VERSION,
        "project_version": versions.PROJECT_VERSION,
        "provider": llm_config.provider_name if llm_config else None,
        "model": llm_config.model if llm_config else None,
        "reasoning_effort": llm_config.reasoning_effort if llm_config else None,
        "request_modes": [request_mode],
        "started_at": clock.started_at,
        "code_identity": _git_head(),
        "input_hashes": input_hashes,
    }
    payload["config_hash"] = config_hash(payload)
    return payload


def _insert_manifest(conn, manifest: dict[str, object]) -> None:
    conn.execute(
        "INSERT INTO run_manifest VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            manifest["run_id"],
            manifest["run_type"],
            manifest["source_manifest_hash"],
            manifest["schema_version"],
            manifest["extract_version"],
            manifest["reconcile_version"],
            manifest["validate_version"],
            manifest["project_version"],
            manifest["provider"],
            manifest["model"],
            manifest["reasoning_effort"],
            json.dumps(manifest["request_modes"], sort_keys=True),
            manifest["started_at"],
            manifest["code_identity"],
            json.dumps(manifest["input_hashes"], sort_keys=True),
            manifest["config_hash"],
        ],
    )


def _validate_resume(run_dir: Path, manifest: dict[str, object], resume: bool) -> None:
    manifest_path = run_dir / "run_manifest.json"
    if not run_dir.exists():
        return
    if not resume:
        raise FileExistsError(f"{run_dir} already exists; pass --resume for conservative resume")
    if not manifest_path.exists():
        raise RuntimeError("cannot resume run without run_manifest.json")
    existing = json.loads(manifest_path.read_text(encoding="utf-8"))
    if existing.get("config_hash") != manifest["config_hash"]:
        raise RuntimeError("cannot resume run because run configuration or inputs changed")


def _atomic_copy(src: Path, dst: Path) -> None:
    tmp = dst.with_name(f".{dst.name}.tmp")
    shutil.copy2(src, tmp)
    os.replace(tmp, dst)


def _write_failed_validation_proof(
    *,
    run_dir: Path,
    run_id: str,
    manifest: dict[str, object],
    validation_report: dict[str, object],
    llm_config: LLMProviderConfig | None,
    request_mode: str,
) -> None:
    artifact_root = Path("artifacts/linkflow") / run_id
    success_count = len(list(artifact_root.glob("*_success.json"))) if artifact_root.exists() else 0
    failure_count = len(list(artifact_root.glob("*_failure.json"))) if artifact_root.exists() else 0
    atomic_write_json(
        run_dir / "failed_validation_proof.json",
        {
            "run_id": run_id,
            "resolved_commit": manifest.get("code_identity"),
            "validation_passed": bool(validation_report.get("passed")),
            "validation_failure_count": len(validation_report.get("hard_failures", [])),
            "provider": llm_config.provider_name if llm_config else None,
            "model": llm_config.model if llm_config else None,
            "reasoning_effort": llm_config.reasoning_effort if llm_config else None,
            "request_mode": request_mode,
            "artifact_counts": {
                "linkflow_success": success_count,
                "linkflow_failure": failure_count,
            },
        },
    )


def _git_head() -> str | None:
    import subprocess

    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:
        return None
