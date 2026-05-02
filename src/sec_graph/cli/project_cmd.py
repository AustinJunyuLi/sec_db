"""Project canonical DuckDB rows to estimator-facing artifacts."""

from __future__ import annotations

import argparse
from pathlib import Path

from sec_graph.project.summaries import write_projection_outputs
from sec_graph.schema import DEFAULT_DB_PATH, connect


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH, help="DuckDB input path")
    parser.add_argument("--run-dir", type=Path, default=Path("runs/latest"), help="run artifact directory")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    write_projection_outputs(connect(args.db), args.run_dir)
    print(f"projection artifacts: {args.run_dir}")
    return 0
