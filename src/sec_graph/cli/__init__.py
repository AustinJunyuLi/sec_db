"""sec_graph command-line dispatcher."""

from __future__ import annotations

import argparse

from sec_graph.cli import extract_cmd, ingest_cmd, project_cmd, reconcile_cmd, run_cmd, validate_cmd


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m sec_graph")
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command, help_text, module in (
        ("ingest", "ingest filing markdown", ingest_cmd),
        ("extract", "extract candidates from ingested filings", extract_cmd),
        ("reconcile", "reconcile candidates into canonical rows", reconcile_cmd),
        ("validate", "validate canonical rows", validate_cmd),
        ("project", "project bidder-cycle rows", project_cmd),
        ("run", "run the full deterministic pipeline", run_cmd),
    ):
        command_parser = subparsers.add_parser(command, help=help_text)
        for action in module.build_parser()._actions:
            if action.dest == "help":
                continue
            command_parser._add_action(action)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args, unknown = parser.parse_known_args(argv)
    if args.command == "ingest":
        return ingest_cmd.main(_argv_from_namespace(args, unknown))
    if args.command == "extract":
        return extract_cmd.main(_argv_from_namespace(args, unknown))
    if args.command == "reconcile":
        return reconcile_cmd.main(_argv_from_namespace(args, unknown))
    if args.command == "validate":
        return validate_cmd.main(_argv_from_namespace(args, unknown))
    if args.command == "project":
        return project_cmd.main(_argv_from_namespace(args, unknown))
    if args.command == "run":
        return run_cmd.main(_argv_from_namespace(args, unknown))
    raise SystemExit(f"unknown command {args.command}")


def _argv_from_namespace(args: argparse.Namespace, unknown: list[str]) -> list[str]:
    rebuilt: list[str] = []
    if getattr(args, "slug", None) is not None:
        rebuilt.extend(["--slug", args.slug])
    if getattr(args, "all", False):
        rebuilt.append("--all")
    if getattr(args, "slugs", None) is not None:
        rebuilt.append("--slugs")
        rebuilt.extend(args.slugs)
    if getattr(args, "source", None) is not None:
        rebuilt.extend(["--source", args.source])
    if getattr(args, "filing_id", None) is not None:
        rebuilt.extend(["--filing-id", args.filing_id])
    if getattr(args, "db", None) is not None:
        rebuilt.extend(["--db", str(args.db)])
    if getattr(args, "examples_dir", None) is not None:
        rebuilt.extend(["--examples-dir", str(args.examples_dir)])
    if getattr(args, "run_dir", None) is not None:
        rebuilt.extend(["--run-dir", str(args.run_dir)])
    if getattr(args, "run_id", None) is not None:
        rebuilt.extend(["--run-id", str(args.run_id)])
    if getattr(args, "projection", None) is not None:
        rebuilt.extend(["--projection", str(args.projection)])
    if getattr(args, "llm_provider", None) is not None:
        rebuilt.extend(["--llm-provider", args.llm_provider])
    if getattr(args, "llm_model", None) is not None:
        rebuilt.extend(["--llm-model", args.llm_model])
    if getattr(args, "llm_reasoning_effort", None) is not None:
        rebuilt.extend(["--llm-reasoning-effort", args.llm_reasoning_effort])
    if getattr(args, "llm_limit", None) is not None:
        rebuilt.extend(["--llm-limit", str(args.llm_limit)])
    if getattr(args, "fresh", False):
        rebuilt.append("--fresh")
    rebuilt.extend(unknown)
    return rebuilt
