"""Run deterministic extraction rules over ingested filings."""

from __future__ import annotations

import argparse
from pathlib import Path

from sec_graph.extract.rules import run_rules
from sec_graph.schema import DEFAULT_DB_PATH, connect


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--filing-id", help="extract one filing by filing_id")
    group.add_argument("--all", action="store_true", help="extract every filing in the DB")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH, help="DuckDB input/output path")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    conn = connect(args.db)
    filing_ids = (
        [row[0] for row in conn.execute("SELECT filing_id FROM filings ORDER BY filing_id").fetchall()]
        if args.all
        else [args.filing_id]
    )
    for filing_id in filing_ids:
        run_rules(conn, filing_id=filing_id)
    print(f"extracted candidates for {len(filing_ids)} filing(s)")
    return 0
