"""sec_review_compiler command-line interface."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from .run.ids import RunId
from .run.manifest import RunManifest


def init_run(deal_slug: str, run_root: Path) -> Path:
    """Create a new run directory under `run_root` and write its manifest.

    Returns the absolute path to the newly created run directory.
    """
    run_id = RunId.new(deal_slug)
    run_dir = Path(run_root) / str(run_id)
    config = {"deal_slug": deal_slug, "run_root": str(Path(run_root))}
    manifest = RunManifest.for_run(run_id, config)
    manifest.write(run_dir)
    return run_dir


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sec_review_compiler",
        description="SEC merger filing agentic review compiler CLI.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    init = sub.add_parser(
        "init-run",
        help="Initialise a new compiler run directory and write its manifest.",
    )
    init.add_argument("--deal-slug", required=True, help="Deal slug (lowercase alnum/hyphen).")
    init.add_argument("--run-root", required=True, type=Path, help="Root directory for runs.")

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "init-run":
        run_dir = init_run(args.deal_slug, args.run_root)
        print(str(run_dir))
        return 0
    parser.error(f"unknown command: {args.command}")
    return 2  # unreachable; parser.error raises SystemExit
