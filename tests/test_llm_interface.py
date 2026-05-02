from pathlib import Path

import pytest

from sec_graph.extract.llm.convert import insert_llm_response
from sec_graph.extract.llm.models import LLMCandidatePayload, LLMContractError, LLMExtractionResponse
from sec_graph.extract.llm.requests import build_llm_requests
from sec_graph.ingest.pipeline import ingest_examples
from sec_graph.schema import connect, init_schema, validate_quote


def _conn():
    conn = connect(":memory:")
    init_schema(conn)
    ingest_examples(conn, examples_dir=Path("data/examples"))
    return conn


def test_build_llm_requests_is_paragraph_scoped_and_evidence_bound() -> None:
    conn = _conn()
    requests = build_llm_requests(conn, filing_id="petsmart-inc_filing_1", limit=1)
    request = requests[0]

    assert request.request_id == "petsmart-inc_llmrequest_1"
    assert request.parent_evidence_id
    assert request.paragraph_text
    assert request.allowed_candidate_types == ["actor_mention", "dated_event", "bid_value", "participation_count"]


def test_insert_llm_response_writes_candidates_and_extract_spans() -> None:
    conn = _conn()
    request = build_llm_requests(conn, filing_id="petsmart-inc_filing_1", limit=20)[2]
    start = request.paragraph_text.index("Company")
    response = LLMExtractionResponse(
        request_id=request.request_id,
        provider_name="offline",
        provider_model="mock",
        reasoning_effort="low",
        candidates=[
            LLMCandidatePayload(
                candidate_type="actor_mention",
                raw_value="Company",
                normalized_value="Company",
                confidence="high",
                quote_text="Company",
                quote_start=start,
                quote_end=start + len("Company"),
                dependencies=[],
            )
        ],
        raw_response_sha256="0" * 64,
        finish_status="completed",
    )

    inserted = insert_llm_response(conn, request, response, run_id="llm-offline")

    assert len(inserted) == 1
    candidate_id = inserted[0].candidate_id
    evidence_id = inserted[0].evidence_ids[0]
    row = conn.execute(
        "SELECT child.char_start, child.char_end, child.quote_hash FROM spans AS child WHERE evidence_id = ?",
        [evidence_id],
    ).fetchone()
    filing_text = Path("data/examples/petsmart-inc.md").read_text(encoding="utf-8")
    assert validate_quote(filing_text, row[0], row[1], row[2])
    assert conn.execute("SELECT count(*) FROM candidates WHERE candidate_id = ?", [candidate_id]).fetchone()[0] == 1


def test_insert_llm_response_fails_on_bad_quote_offsets() -> None:
    conn = _conn()
    request = build_llm_requests(conn, filing_id="petsmart-inc_filing_1", limit=1)[0]
    response = LLMExtractionResponse(
        request_id=request.request_id,
        provider_name="offline",
        provider_model="mock",
        reasoning_effort="low",
        candidates=[
            LLMCandidatePayload(
                candidate_type="actor_mention",
                raw_value="Bad",
                normalized_value="Bad",
                confidence="high",
                quote_text="not present",
                quote_start=0,
                quote_end=11,
                dependencies=[],
            )
        ],
        raw_response_sha256="0" * 64,
        finish_status="completed",
    )

    with pytest.raises(LLMContractError):
        insert_llm_response(conn, request, response, run_id="llm-offline")
