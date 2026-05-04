"""Hard-reset extraction orchestration."""

from __future__ import annotations

import duckdb

from sec_graph.extract.evidence_map import build_evidence_map
from sec_graph.extract.llm.models import DEFAULT_REQUEST_MODE, LLMProviderConfig


def run_extract(
    conn: duckdb.DuckDBPyConnection,
    *,
    filing_id: str,
    run_id: str,
    llm_config: LLMProviderConfig | None = None,
    request_mode: str = DEFAULT_REQUEST_MODE,
) -> list[str]:
    """Build evidence map and import typed claims.

    Rules-only mode records evidence-map obligations only. It is allowed for
    offline tests but cannot produce a SOUND proof verdict.
    """

    build_evidence_map(conn, filing_id=filing_id, run_id=run_id)
    if llm_config is None:
        return []

    from sec_graph.extract.llm.linkflow import run_linkflow_requests

    return run_linkflow_requests(
        conn,
        filing_id=filing_id,
        run_id=run_id,
        config=llm_config,
        request_mode=request_mode,
    )
