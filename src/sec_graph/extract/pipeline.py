"""Hard-reset extraction orchestration."""

from __future__ import annotations

from pathlib import Path

import duckdb

from sec_graph.extract.evidence_map import build_evidence_map
from sec_graph.extract.llm.models import DEFAULT_REQUEST_MODE, LLMProviderConfig


def run_extract(
    conn: duckdb.DuckDBPyConnection,
    *,
    filing_id: str,
    run_id: str,
    run_dir: Path,
    llm_config: LLMProviderConfig,
    request_mode: str = DEFAULT_REQUEST_MODE,
    max_concurrency: int | None = None,
    client_factory=None,
) -> list[str]:
    """Build the evidence map and import typed claims for one filing.

    The provider step fans region requests out under one ``asyncio.gather`` and
    inserts successful responses sequentially in original window order.
    ``llm_config`` is required.
    """

    build_evidence_map(conn, filing_id=filing_id, run_id=run_id)

    from sec_graph.extract.llm.linkflow import run_linkflow_requests

    return run_linkflow_requests(
        conn,
        filing_id=filing_id,
        run_id=run_id,
        run_dir=run_dir,
        config=llm_config,
        request_mode=request_mode,
        max_concurrency=max_concurrency,
        client_factory=client_factory,
    )
