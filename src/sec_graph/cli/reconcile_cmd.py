"""Reconcile extraction candidates into canonical DuckDB rows."""

from __future__ import annotations

import argparse
from pathlib import Path

from sec_graph.reconcile.pipeline import reconcile_all
from sec_graph.schema import DEFAULT_DB_PATH, connect


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH, help="DuckDB input/output path")
    # `--run-id` defaults to `None`; `reconcile_all` then generates a generic
    # UTC-timestamped id. Passing an explicit value is preferred for any
    # provenance-bearing run.
    parser.add_argument(
        "--run-id",
        default=None,
        help="explicit run_id for canonical rows (default: UTC timestamp)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    conn = connect(args.db)
    reconcile_all(conn, run_id=args.run_id)
    count = conn.execute("SELECT count(*) FROM deals").fetchone()[0]
    print(f"reconciled canonical rows for {count} deal(s)")
    return 0
