import json
from pathlib import Path

import pytest

from sec_graph.extract.llm.convert import insert_llm_response
from sec_graph.extract.llm import linkflow
from sec_graph.extract.llm.models import LLMCandidatePayload, LLMContractError, LLMExtractionResponse
from sec_graph.extract.llm.prompt import build_prompt
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


def test_prompt_declares_complete_candidate_payload_shape() -> None:
    conn = _conn()
    request = build_llm_requests(conn, filing_id="petsmart-inc_filing_1", limit=1)[0]

    prompt = build_prompt(request)

    for key in (
        "candidate_type",
        "raw_value",
        "normalized_value",
        "confidence",
        "quote_text",
        "quote_start",
        "quote_end",
        "dependencies",
    ):
        assert key in prompt


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


def test_linkflow_contract_failure_writes_sanitized_artifact(tmp_path, monkeypatch) -> None:
    conn = _conn()
    request = build_llm_requests(conn, filing_id="petsmart-inc_filing_1", limit=1)[0]
    quote = request.paragraph_text[:10]
    raw = json.dumps(
        {
            "output_text": json.dumps(
                {
                    "candidates": [
                        {
                            "candidate_type": "actor_mention",
                            "quote_text": quote,
                            "quote_start": 0,
                            "quote_end": len(quote),
                        }
                    ]
                }
            )
        }
    ).encode("utf-8")

    class _Response:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return raw

    def _urlopen(http_request, timeout):
        return _Response()

    monkeypatch.setenv("LINKFLOW_API_KEY", "test-key")
    monkeypatch.setattr(linkflow, "_ARTIFACT_ROOT", tmp_path)
    monkeypatch.setattr(linkflow.urllib.request, "urlopen", _urlopen)

    config = linkflow.LLMProviderConfig(
        provider_name="linkflow",
        model="gpt-5.5",
        reasoning_effort="low",
    )
    with pytest.raises(LLMContractError):
        linkflow.extract(request, config)

    artifact = next(tmp_path.glob("*_stage8_live/*_failure.json"))
    payload = json.loads(artifact.read_text(encoding="utf-8"))
    assert payload["finish_status"] == "contract_invalid"
    assert payload["raw_response_sha256"]
    assert "output_text" not in payload
