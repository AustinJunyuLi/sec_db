"""sec_review_compiler command-line interface."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

from datetime import datetime, timezone

import duckdb

from .canonical import CanonicalCompiler
from .errors import MissingLinkflowCredentialsError
from .filing.examples import SYNTHETIC_FILING_PATH
from .llm.linkflow import LinkflowClientConfig, build_responses_client
from .orchestration import (
    LiveLinkflowExtractor,
    LiveLinkflowVerifier,
    OfflineConfidentialityExtractor,
    OfflineFakeVerifier,
    Orchestrator,
    ProviderCallRecorder,
    SliceResult,
    ToolCallRecorder,
)
from .run.ids import RunId
from .run.manifest import RunManifest


# ---------------------------------------------------------------- init-run

def init_run(deal_slug: str, run_root: Path) -> Path:
    """Create a new run directory under `run_root` and write its manifest."""
    run_id = RunId.new(deal_slug)
    run_dir = Path(run_root) / str(run_id)
    config = {"deal_slug": deal_slug, "run_root": str(Path(run_root))}
    manifest = RunManifest.for_run(run_id, config)
    manifest.write(run_dir)
    return run_dir


# ---------------------------------------------------------------- run-synthetic

def _build_offline_orchestrator(deal_slug: str) -> Orchestrator:
    return Orchestrator(
        deal_slug=deal_slug,
        extractor=OfflineConfidentialityExtractor(),
        verifier=OfflineFakeVerifier(),
    )


def _build_live_orchestrator(deal_slug: str, *, env: dict | None = None) -> Orchestrator:
    """Build a Linkflow-backed orchestrator. Refuses without credentials."""
    config = LinkflowClientConfig.from_env(env=env)
    config.require_credentials()  # pre-network gate
    client = build_responses_client(config, env=env)
    provider_recorder = ProviderCallRecorder()
    tool_recorder = ToolCallRecorder()
    extractor = LiveLinkflowExtractor(
        client=client,
        config=config,
        provider_recorder=provider_recorder,
        tool_recorder=tool_recorder,
    )
    verifier = LiveLinkflowVerifier(
        client=client,
        config=config,
        provider_recorder=provider_recorder,
        tool_recorder=tool_recorder,
    )
    return Orchestrator(
        deal_slug=deal_slug,
        extractor=extractor,
        verifier=verifier,
        provider_recorder=provider_recorder,
        tool_recorder=tool_recorder,
    )


def run_synthetic(
    *,
    run_root: Path,
    deal_slug: str,
    mode: str,
    filing_path: Path,
    orchestrator_factory=None,
) -> SliceResult:
    """Execute the synthetic vertical slice.

    `orchestrator_factory(deal_slug, mode)` is injected by tests to swap
    the live orchestrator for one driven by FakeResponsesClient.
    """
    run_root = Path(run_root)
    run_id = RunId.new(deal_slug)
    run_dir = run_root / str(run_id)
    run_dir.mkdir(parents=True, exist_ok=True)
    # Persist run manifest at the run root.
    manifest = RunManifest.for_run(
        run_id, {"deal_slug": deal_slug, "mode": mode, "run_root": str(run_root)}
    )
    manifest.write(run_dir)

    if orchestrator_factory is None:
        if mode == "live":
            orch = _build_live_orchestrator(deal_slug)
        elif mode == "offline":
            orch = _build_offline_orchestrator(deal_slug)
        else:
            raise ValueError(f"unknown mode {mode!r}; expected 'live' or 'offline'")
    else:
        orch = orchestrator_factory(deal_slug, mode)

    result = orch.run_synthetic_vertical_slice(
        run_dir=run_dir,
        filing_path=filing_path,
        run_id=run_id,
    )

    # Canonical compile pass over the populated deal-room.
    from .store.repository import DealRoomRepository

    conn = duckdb.connect(str(result.db_path))
    try:
        repo = DealRoomRepository(conn)
        compiler = CanonicalCompiler(
            repo,
            run_id=str(run_id),
            deal_slug=deal_slug,
            compiled_at_run_clock=datetime.now(timezone.utc),
        )
        compiler.compile()
    finally:
        conn.close()
    return result


# ---------------------------------------------------------------- summarize-run

def summarize_run(deal_dir: Path) -> dict:
    """Read the deal-room DuckDB and emit a summary dict."""
    deal_dir = Path(deal_dir)
    db_path = deal_dir / "deal_room.duckdb"
    if not db_path.exists():
        raise FileNotFoundError(f"no deal_room.duckdb at {db_path}")
    conn = duckdb.connect(str(db_path), read_only=True)
    try:
        attempts = conn.execute(
            "SELECT status, COUNT(*) FROM claim_attempts GROUP BY status"
        ).fetchall()
        canonical = conn.execute(
            "SELECT canonical_table, COUNT(*) FROM canonical_rows GROUP BY canonical_table"
        ).fetchall()
        review_queue_size = conn.execute(
            "SELECT COUNT(*) FROM claim_attempts "
            "WHERE status IN ('verified_rejected', 'escalated', 'binding_failed')"
        ).fetchone()[0]
        verdict_counts = conn.execute(
            "SELECT verdict, COUNT(*) FROM verifier_verdicts GROUP BY verdict"
        ).fetchall()
    finally:
        conn.close()

    provider_log = deal_dir / "provider_calls.jsonl"
    tool_log = deal_dir / "tool_calls.jsonl"
    n_provider = (
        sum(1 for _ in provider_log.read_text(encoding="utf-8").splitlines())
        if provider_log.exists()
        else 0
    )
    n_tool = (
        sum(1 for _ in tool_log.read_text(encoding="utf-8").splitlines())
        if tool_log.exists()
        else 0
    )

    return {
        "deal_dir": str(deal_dir),
        "attempts_by_status": dict(attempts),
        "verdicts_by_kind": dict(verdict_counts),
        "canonical_rows_by_table": dict(canonical),
        "review_queue_size": review_queue_size,
        "provider_call_count": n_provider,
        "tool_call_count": n_tool,
    }


# ---------------------------------------------------------------- parser

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

    rs = sub.add_parser(
        "run-synthetic",
        help="Run the synthetic vertical slice end-to-end.",
    )
    rs.add_argument("--run-root", required=True, type=Path)
    rs.add_argument("--deal-slug", required=True)
    rs.add_argument(
        "--mode",
        choices=("live", "offline"),
        default="live",
        help="Live calls Linkflow with credentials from env; offline uses the rule-based extractor + verifier.",
    )
    rs.add_argument(
        "--filing-path",
        type=Path,
        default=SYNTHETIC_FILING_PATH,
        help="Path to a filing text file. Defaults to the bundled synthetic fixture.",
    )

    sum_p = sub.add_parser(
        "summarize-run",
        help="Print a summary of a deal-room directory.",
    )
    sum_p.add_argument("deal_dir", type=Path)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "init-run":
        run_dir = init_run(args.deal_slug, args.run_root)
        print(str(run_dir))
        return 0

    if args.command == "run-synthetic":
        try:
            result = run_synthetic(
                run_root=args.run_root,
                deal_slug=args.deal_slug,
                mode=args.mode,
                filing_path=args.filing_path,
            )
        except MissingLinkflowCredentialsError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 2
        print(json.dumps({
            "run_id": result.run_id,
            "deal_dir": str(result.deal_dir),
            "accepted": len(result.accepted_attempt_ids),
            "rejected": len(result.rejected_attempt_ids),
            "superseded": len(result.superseded_attempt_ids),
            "corrections": len(result.correction_attempt_ids),
            "can_publish_trusted": result.can_publish_trusted,
        }, indent=2))
        return 0

    if args.command == "summarize-run":
        try:
            summary = summarize_run(args.deal_dir)
        except FileNotFoundError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 2
        print(json.dumps(summary, indent=2, sort_keys=True))
        return 0

    parser.error(f"unknown command: {args.command}")
    return 2  # unreachable
