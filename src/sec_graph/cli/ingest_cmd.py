"""Ingest SEC merger filing markdown into the DuckDB evidence store."""

from __future__ import annotations

import argparse
from pathlib import Path

from sec_graph.ingest.pipeline import DEFAULT_EXAMPLES_DIR, example_sources, ingest_examples_to_db, ingest_source
from sec_graph.schema import DEFAULT_DB_PATH, connect, init_schema


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--slug", help="ingest one example filing by slug")
    group.add_argument("--all", action="store_true", help="ingest every example filing")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH, help="DuckDB output path")
    parser.add_argument("--examples-dir", type=Path, default=DEFAULT_EXAMPLES_DIR, help="example markdown directory")
    parser.add_argument("--fresh", action="store_true", help="replace an existing DuckDB file")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.all:
        filings = ingest_examples_to_db(args.db, examples_dir=args.examples_dir, fresh=args.fresh)
    else:
        sources = [source for source in example_sources(args.examples_dir) if source.slug == args.slug]
        if not sources:
            raise SystemExit(f"slug {args.slug} not found under {args.examples_dir}")
        if args.db.exists() and not args.fresh:
            raise SystemExit(f"{args.db} exists; pass --fresh to replace it")
        if args.db.exists():
            args.db.unlink()
        args.db.parent.mkdir(parents=True, exist_ok=True)
        conn = connect(args.db)
        init_schema(conn)
        filings = [ingest_source(conn, sources[0])]
    print(f"ingested {len(filings)} filing(s) into {args.db}")
    return 0
