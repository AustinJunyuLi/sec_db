import os
from pathlib import Path

import pytest

from sec_graph.extract.llm.convert import insert_llm_response
from sec_graph.extract.llm.linkflow import extract
from sec_graph.extract.llm.models import LLMProviderConfig
from sec_graph.extract.llm.requests import build_llm_requests
from sec_graph.ingest.pipeline import ingest_examples
from sec_graph.schema import connect, init_schema


def _live_enabled() -> bool:
    return os.environ.get("SEC_GRAPH_LIVE_LINKFLOW") == "1" and bool(os.environ.get("LINKFLOW_API_KEY"))


@pytest.mark.skipif(not _live_enabled(), reason="live Linkflow test requires SEC_GRAPH_LIVE_LINKFLOW=1 and LINKFLOW_API_KEY")
def test_live_linkflow_gpt55_reasoning_efforts() -> None:
    conn = connect(":memory:")
    init_schema(conn)
    ingest_examples(conn, examples_dir=Path("data/examples"))
    requests = build_llm_requests(conn, filing_id="petsmart-inc_filing_1", limit=30)
    request = min(
        (request for request in requests if "Buyer Group" in request.paragraph_text),
        key=lambda request: len(request.paragraph_text),
    ).model_copy(update={"allowed_candidate_types": ["actor_mention"]})
    efforts = [
        effort.strip()
        for effort in os.environ.get("SEC_GRAPH_LINKFLOW_EFFORTS", "low,medium,high,xhigh").split(",")
        if effort.strip()
    ]
    assert {"low", "high"} <= set(efforts)

    for effort in efforts:
        config = LLMProviderConfig(
            provider_name="linkflow",
            model="gpt-5.5",
            reasoning_effort=effort,  # type: ignore[arg-type]
            base_url=os.environ.get("LINKFLOW_BASE_URL", "https://www.linkflow.run/v1"),
            timeout_seconds=240,
        )
        response = extract(request, config)
        inserted = insert_llm_response(conn, request, response, run_id=f"live-{effort}")
        assert response.finish_status == "completed"
        assert inserted
        assert {candidate.candidate_type for candidate in inserted} == {"actor_mention"}
