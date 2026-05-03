"""Run deterministic extraction rules over ingested filings."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from sec_graph.extract.llm.models import LLMProviderConfig
from sec_graph.extract.pipeline import run_extract
from sec_graph.schema import DEFAULT_DB_PATH, connect


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--filing-id", help="extract one filing by filing_id")
    group.add_argument("--all", action="store_true", help="extract every filing in the DB")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH, help="DuckDB input/output path")
    parser.add_argument("--run-id", required=True, help="explicit top-level run id")
    parser.add_argument("--llm-provider", choices=["linkflow"], help="optional LLM typed-claim provider")
    parser.add_argument("--llm-model", default="gpt-5.5", help="LLM model name")
    parser.add_argument("--llm-reasoning-effort", choices=["low", "medium", "high", "xhigh"], default="high")
    parser.add_argument(
        "--request-mode",
        choices=["semantic_claims_v1"],
        default="semantic_claims_v1",
        help="fixed semantic claim request mode",
    )
    return parser


def llm_config_from_args(args: argparse.Namespace) -> LLMProviderConfig | None:
    if args.llm_provider is None:
        return None
    return LLMProviderConfig(
        provider_name=args.llm_provider,
        model=args.llm_model,
        reasoning_effort=args.llm_reasoning_effort,
        base_url=os.environ.get("LINKFLOW_BASE_URL", "https://www.linkflow.run/v1"),
    )


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    conn = connect(args.db)
    filing_ids = (
        [row[0] for row in conn.execute("SELECT filing_id FROM filings ORDER BY filing_id").fetchall()]
        if args.all
        else [args.filing_id]
    )
    llm_config = llm_config_from_args(args)
    for filing_id in filing_ids:
        run_extract(
            conn,
            filing_id=filing_id,
            run_id=args.run_id,
            llm_config=llm_config,
            request_mode=args.request_mode,
        )
    print(f"extracted typed claims for {len(filing_ids)} filing(s)")
    return 0
