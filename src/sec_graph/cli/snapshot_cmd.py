"""Copy an immutable run directory into a new snapshot directory."""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True, help="existing run directory")
    parser.add_argument("--snapshot-dir", type=Path, required=True, help="new snapshot directory")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not args.run_dir.exists():
        raise SystemExit(f"{args.run_dir} does not exist")
    if args.snapshot_dir.exists():
        raise SystemExit(f"{args.snapshot_dir} already exists")
    shutil.copytree(args.run_dir, args.snapshot_dir)
    print(f"snapshot artifacts: {args.snapshot_dir}")
    return 0
