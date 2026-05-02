"""Run ingest, extract, reconcile, validate, project, and snapshot."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

from sec_graph.cli.extract_cmd import llm_config_from_args
from sec_graph.extract.llm.models import LLMProviderConfig
from sec_graph.extract.pipeline import run_extract
from sec_graph.ingest.pipeline import (
    DEFAULT_EXAMPLES_DIR,
    IngestSource,
    example_sources,
    filing_sources,
    ingest_sources,
)
from sec_graph.project.summaries import write_projection_outputs
from sec_graph.reconcile.pipeline import reconcile_all
from sec_graph.schema import connect, init_schema
from sec_graph.validate.integrity import write_validation_outputs


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--all", action="store_true", help="run all available filings for the selected source")
    group.add_argument("--slugs", nargs="+", help="deal slugs to run in order")
    parser.add_argument("--source", choices=["examples", "filings"], default="examples", help="input source")
    parser.add_argument("--db", type=Path, help="optional new working DuckDB path")
    parser.add_argument("--examples-dir", type=Path, default=DEFAULT_EXAMPLES_DIR, help="example markdown directory")
    parser.add_argument("--run-dir", type=Path, required=True, help="immutable run artifact directory")
    parser.add_argument("--run-id", required=True, help="explicit run_id for canonical rows")
    parser.add_argument("--projection", default="bidder_cycle_baseline_v1", help="projection name")
    parser.add_argument("--llm-provider", choices=["linkflow"], help="optional LLM candidate provider")
    parser.add_argument("--llm-model", default="gpt-5.5", help="LLM model name")
    parser.add_argument("--llm-reasoning-effort", choices=["low", "medium", "high", "xhigh"], default="high")
    parser.add_argument("--llm-limit", type=int, help="maximum paragraph requests per filing")
    return parser


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


def _write_manifest(
    run_dir: Path,
    *,
    run_id: str,
    source: str,
    filings: list[object],
    projection_name: str,
    llm_config: LLMProviderConfig | None,
) -> None:
    manifest = {
        "run_id": run_id,
        "source": source,
        "slugs": [getattr(filing, "deal_slug") for filing in filings],
        "input_hashes": {getattr(filing, "deal_slug"): getattr(filing, "raw_sha256") for filing in filings},
        "source_paths": {getattr(filing, "deal_slug"): getattr(filing, "source_path") for filing in filings},
        "projection_name": projection_name,
        "llm": None
        if llm_config is None
        else {
            "provider": llm_config.provider_name,
            "model": llm_config.model,
            "reasoning_effort": llm_config.reasoning_effort,
            "base_url": llm_config.base_url,
        },
    }
    (run_dir / "run_manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")


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
    llm_limit: int | None = None,
) -> dict[str, object]:
    if run_dir.exists():
        raise FileExistsError(f"{run_dir} already exists")
    run_dir.mkdir(parents=True)
    working_db = db_path or run_dir / "working.duckdb"
    if working_db.exists():
        raise FileExistsError(f"{working_db} already exists")

    conn = connect(working_db)
    init_schema(conn)
    selected_sources = _sources(source, slugs, all_selected=slugs is None, examples_dir=examples_dir)
    filings = ingest_sources(conn, selected_sources, run_id=run_id)
    for filing in filings:
        run_extract(conn, filing_id=filing.filing_id, run_id=run_id, llm_config=llm_config, llm_limit=llm_limit)
    reconcile_all(conn, run_id=run_id)
    _write_manifest(
        run_dir,
        run_id=run_id,
        source=source,
        filings=filings,
        projection_name=projection_name,
        llm_config=llm_config,
    )
    report = write_validation_outputs(conn, run_dir)
    if not report["passed"]:
        raise RuntimeError(f"run failed validation; artifacts: {run_dir}")
    write_projection_outputs(conn, run_dir, projection_name=projection_name)
    conn.close()
    shutil.copy2(working_db, run_dir / "canonical.duckdb")
    return report


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
            llm_limit=args.llm_limit,
        )
    except Exception as exc:
        print(str(exc))
        return 1
    print(f"run complete; artifacts: {args.run_dir}")
    return 0
