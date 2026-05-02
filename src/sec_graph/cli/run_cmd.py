"""Run ingest, extract, reconcile, validate, and project end to end."""

from __future__ import annotations

import argparse
from pathlib import Path

from sec_graph.extract.rules import run_rules
from sec_graph.ingest.pipeline import DEFAULT_EXAMPLES_DIR, ingest_examples_to_db
from sec_graph.project.summaries import write_projection_outputs
from sec_graph.reconcile.pipeline import reconcile_all
from sec_graph.schema import DEFAULT_DB_PATH, connect
from sec_graph.validate.integrity import write_validation_outputs


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--all", action="store_true", required=True, help="run all example filings")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH, help="DuckDB output path")
    parser.add_argument("--examples-dir", type=Path, default=DEFAULT_EXAMPLES_DIR, help="example markdown directory")
    parser.add_argument("--run-dir", type=Path, default=Path("runs/latest"), help="run artifact directory")
    parser.add_argument("--run-id", default="run-all", help="run_id for canonical rows")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    filings = ingest_examples_to_db(args.db, examples_dir=args.examples_dir)
    conn = connect(args.db)
    for filing in filings:
        run_rules(conn, filing_id=filing.filing_id, run_id=args.run_id)
    reconcile_all(conn, run_id=args.run_id)
    report = write_validation_outputs(conn, args.run_dir)
    if not report["passed"]:
        print(f"run failed validation; artifacts: {args.run_dir}")
        return 1
    write_projection_outputs(conn, args.run_dir)
    print(f"run complete; artifacts: {args.run_dir}")
    return 0
