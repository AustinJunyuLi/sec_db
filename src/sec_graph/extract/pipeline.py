"""Extraction orchestration with optional LLM augmentation."""

from __future__ import annotations

import duckdb

from sec_graph.extract.llm.models import LLMProviderConfig
from sec_graph.extract.rules import run_rules


def run_extract(
    conn: duckdb.DuckDBPyConnection,
    filing_id: str,
    run_id: str = "extract-smoke",
    llm_config: LLMProviderConfig | None = None,
    llm_limit: int | None = None,
):
    candidates = run_rules(conn, filing_id=filing_id, run_id=run_id)
    if llm_config is None:
        return candidates

    from sec_graph.extract.llm.linkflow import run_linkflow_requests

    llm_candidates = run_linkflow_requests(
        conn,
        filing_id=filing_id,
        run_id=run_id,
        config=llm_config,
        limit=llm_limit,
    )
    return [*candidates, *llm_candidates]
