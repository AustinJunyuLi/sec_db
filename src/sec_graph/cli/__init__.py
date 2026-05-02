"""sec_graph command-line dispatcher."""

from __future__ import annotations

import argparse

from sec_graph.cli import ingest_cmd


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m sec_graph")
    subparsers = parser.add_subparsers(dest="command", required=True)
    ingest_parser = subparsers.add_parser("ingest", help="ingest filing markdown")
    for action in ingest_cmd.build_parser()._actions:
        if action.dest == "help":
            continue
        ingest_parser._add_action(action)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args, unknown = parser.parse_known_args(argv)
    if args.command == "ingest":
        return ingest_cmd.main(_argv_from_namespace(args, unknown))
    raise SystemExit(f"unknown command {args.command}")


def _argv_from_namespace(args: argparse.Namespace, unknown: list[str]) -> list[str]:
    rebuilt: list[str] = []
    if getattr(args, "slug", None) is not None:
        rebuilt.extend(["--slug", args.slug])
    if getattr(args, "all", False):
        rebuilt.append("--all")
    if getattr(args, "db", None) is not None:
        rebuilt.extend(["--db", str(args.db)])
    if getattr(args, "examples_dir", None) is not None:
        rebuilt.extend(["--examples-dir", str(args.examples_dir)])
    rebuilt.extend(unknown)
    return rebuilt
