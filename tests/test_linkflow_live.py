"""Live Linkflow proof against a multi-paragraph within-deal window.

This is the live proof: it sends a real within-deal narrative window (at least
two ordered paragraphs from the same filing) and confirms the provider returns
candidates that round-trip to evidence-bound spans. Skipped when live
credentials are absent so default CI keeps passing.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from sec_graph.extract.llm.convert import insert_llm_response
from sec_graph.extract.llm.linkflow import extract
from sec_graph.extract.llm.models import LLMProviderConfig, LLMWindowRequest
from sec_graph.extract.llm.requests import build_llm_windows
from sec_graph.ingest.pipeline import ingest_examples
from sec_graph.schema import connect, init_schema


def _live_enabled() -> bool:
    return os.environ.get("SEC_GRAPH_LIVE_LINKFLOW") == "1" and bool(
        os.environ.get("LINKFLOW_API_KEY")
    )


def _multi_paragraph_window(conn) -> LLMWindowRequest:
    windows = build_llm_windows(conn, filing_id="petsmart-inc_filing_1")
    multi = [w for w in windows if len(w.ordered_paragraphs) > 1]
    assert multi, "expected at least one multi-paragraph window"
    return multi[0].model_copy(update={"extraction_tasks": ["actor_aliases"]})


def test_live_window_request_is_within_deal_and_multi_paragraph() -> None:
    """Structural contract that runs unconditionally with mock fixtures: live proof
    must exercise a multi-paragraph window from one filing only."""
    conn = connect(":memory:")
    init_schema(conn)
    ingest_examples(conn, examples_dir=Path("data/examples"))

    window = _multi_paragraph_window(conn)
    assert window.deal_id == "petsmart-inc"
    assert window.filing_id == "petsmart-inc_filing_1"
    assert len(window.ordered_paragraphs) >= 2
    # All paragraphs in the window must come from the same filing.
    para_ids = [p.paragraph_id for p in window.ordered_paragraphs]
    placeholders = ",".join(["?"] * len(para_ids))
    rows = conn.execute(
        f"SELECT DISTINCT filing_id FROM paragraphs WHERE paragraph_id IN ({placeholders})",
        para_ids,
    ).fetchall()
    assert len(rows) == 1
    assert rows[0][0] == "petsmart-inc_filing_1"


@pytest.mark.skipif(
    not _live_enabled(),
    reason="live Linkflow test requires SEC_GRAPH_LIVE_LINKFLOW=1 and LINKFLOW_API_KEY",
)
def test_live_linkflow_gpt55_window_extraction() -> None:
    conn = connect(":memory:")
    init_schema(conn)
    ingest_examples(conn, examples_dir=Path("data/examples"))
    window = _multi_paragraph_window(conn)

    efforts = [
        effort.strip()
        for effort in os.environ.get(
            "SEC_GRAPH_LINKFLOW_EFFORTS", "low,high"
        ).split(",")
        if effort.strip()
    ]
    assert {"low", "high"} <= set(efforts)

    for effort in efforts:
        config = LLMProviderConfig(
            provider_name="linkflow",
            model="gpt-5.5",
            reasoning_effort=effort,  # type: ignore[arg-type]
            base_url=os.environ.get(
                "LINKFLOW_BASE_URL", "https://www.linkflow.run/v1"
            ),
            timeout_seconds=240,
        )
        response = extract(window, config)
        inserted = insert_llm_response(conn, window, response, run_id=f"live-{effort}")
        assert response.finish_status == "completed"
        assert inserted
