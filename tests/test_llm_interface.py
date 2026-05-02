"""LLM extraction interface contract tests (within-deal narrative windows).

These tests replace the old paragraph-only tests. The contract is:
- requests are within-deal windows (built by build_llm_windows);
- prompts surface prior_deal_memory and forbid offset payloads;
- candidate quotes are exact substrings of the assembled window text;
- relation candidates use the typed first-class payload (not JSON-in-string);
- streaming completion is fail-loud on missing response.completed.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from sec_graph.extract.llm import linkflow
from sec_graph.extract.llm.convert import insert_llm_response
from sec_graph.extract.llm.models import (
    LLMCandidatePayload,
    LLMContractError,
    LLMExtractionResponse,
    LLMProviderConfig,
    LLMWindowRequest,
)
from sec_graph.extract.llm.prompt import build_window_prompt
from sec_graph.extract.llm.requests import build_llm_windows
from sec_graph.ingest.pipeline import ingest_examples
from sec_graph.schema import connect, init_schema, validate_quote


def _conn():
    conn = connect(":memory:")
    init_schema(conn)
    ingest_examples(conn, examples_dir=Path("data/examples"))
    return conn


def _windows(conn) -> list[LLMWindowRequest]:
    return build_llm_windows(conn, filing_id="petsmart-inc_filing_1")


def _first_window(conn) -> LLMWindowRequest:
    return _windows(conn)[0]


def _window_containing(conn, quote: str) -> LLMWindowRequest:
    return next(
        window
        for window in _windows(conn)
        if any(quote in p.paragraph_text for p in window.ordered_paragraphs)
    )


def test_build_llm_windows_returns_within_deal_window_requests() -> None:
    conn = _conn()
    windows = _windows(conn)
    assert windows
    first = windows[0]
    assert isinstance(first, LLMWindowRequest)
    assert first.deal_id == "petsmart-inc"
    assert first.filing_id == "petsmart-inc_filing_1"
    assert first.window_id.startswith("petsmart-inc_window_")
    assert first.request_id.startswith("petsmart-inc_llmrequest_")
    assert first.ordered_paragraphs


def test_window_prompt_declares_payload_shape_and_forbids_offsets() -> None:
    conn = _conn()
    window = _first_window(conn)

    prompt = build_window_prompt(window)

    for key in (
        "candidate_type",
        "raw_value",
        "normalized_value",
        "confidence",
        "quote_text",
        "dependencies",
    ):
        assert key in prompt
    assert "quote_start" not in prompt
    assert "quote_end" not in prompt
    assert "char_start" not in prompt
    assert "char_end" not in prompt
    assert "ordered paragraphs" in prompt
    assert "single filing" in prompt or "one filing" in prompt


def test_linkflow_schema_accepts_every_live_declared_candidate_type() -> None:
    schema = linkflow._candidate_schema()
    allowed = schema["properties"]["candidates"]["items"]["properties"]["candidate_type"]["enum"]

    assert allowed == ["actor_mention", "dated_event", "bid_value", "participation_count"]


def test_linkflow_provider_config_defaults_to_high_reasoning_timeout() -> None:
    config = LLMProviderConfig(provider_name="linkflow", model="gpt-5.5", reasoning_effort="high")

    assert config.timeout_seconds == 240


def test_insert_llm_response_writes_candidates_and_extract_spans() -> None:
    conn = _conn()
    window = _window_containing(conn, "On May 21, 2014,")
    response = LLMExtractionResponse(
        request_id=window.request_id,
        provider_name="offline",
        provider_model="mock",
        reasoning_effort="low",
        candidates=[
            LLMCandidatePayload(
                candidate_type="dated_event",
                raw_value="On May 21, 2014,",
                normalized_value="2014-05-21",
                confidence="medium",
                quote_text="On May 21, 2014,",
                dependencies=[],
            )
        ],
        raw_response_sha256="0" * 64,
        finish_status="completed",
    )

    inserted = insert_llm_response(conn, window, response, run_id="llm-offline")

    assert len(inserted) == 1
    candidate_id = inserted[0].candidate_id
    evidence_id = inserted[0].evidence_ids[0]
    row = conn.execute(
        "SELECT char_start, char_end, quote_hash FROM spans WHERE evidence_id = ?",
        [evidence_id],
    ).fetchone()
    filing_text = Path("data/examples/petsmart-inc.md").read_text(encoding="utf-8")
    assert validate_quote(filing_text, row[0], row[1], row[2])
    assert conn.execute(
        "SELECT count(*) FROM candidates WHERE candidate_id = ?", [candidate_id]
    ).fetchone()[0] == 1


def test_insert_llm_response_fails_on_non_exact_quote_text() -> None:
    conn = _conn()
    window = _first_window(conn)
    response = LLMExtractionResponse(
        request_id=window.request_id,
        provider_name="offline",
        provider_model="mock",
        reasoning_effort="low",
        candidates=[
            LLMCandidatePayload(
                candidate_type="actor_mention",
                raw_value="Bad",
                normalized_value="Bad",
                confidence="high",
                quote_text="zzzzzzzzz_definitely_not_in_window_zzzzzzzzz",
                dependencies=[],
            )
        ],
        raw_response_sha256="0" * 64,
        finish_status="completed",
    )

    with pytest.raises(LLMContractError):
        insert_llm_response(conn, window, response, run_id="llm-offline")


def test_candidate_payload_rejects_old_offset_fields() -> None:
    with pytest.raises(ValueError):
        LLMCandidatePayload.model_validate(
            {
                "candidate_type": "actor_mention",
                "raw_value": "Company",
                "normalized_value": "Company",
                "confidence": "high",
                "quote_text": "Company",
                "quote_start": 0,
                "quote_end": 7,
                "dependencies": [],
            }
        )


def test_insert_llm_response_fails_on_ambiguous_quote_text() -> None:
    conn = _conn()
    window = _window_containing(conn, "On May 21, 2014,")
    response = LLMExtractionResponse(
        request_id=window.request_id,
        provider_name="offline",
        provider_model="mock",
        reasoning_effort="low",
        candidates=[
            LLMCandidatePayload(
                candidate_type="actor_mention",
                raw_value="the",
                normalized_value="the",
                confidence="low",
                quote_text="the",
                dependencies=[],
            )
        ],
        raw_response_sha256="0" * 64,
        finish_status="completed",
    )

    with pytest.raises(LLMContractError, match="ambiguous"):
        insert_llm_response(conn, window, response, run_id="llm-offline")


def test_insert_llm_response_rejects_non_iso_dated_event_normalization() -> None:
    conn = _conn()
    window = _window_containing(conn, "On May 21, 2014,")
    response = LLMExtractionResponse(
        request_id=window.request_id,
        provider_name="offline",
        provider_model="mock",
        reasoning_effort="low",
        candidates=[
            LLMCandidatePayload(
                candidate_type="dated_event",
                raw_value="On May 21, 2014,",
                normalized_value="May 21",
                confidence="medium",
                quote_text="On May 21, 2014,",
                dependencies=[],
            )
        ],
        raw_response_sha256="0" * 64,
        finish_status="completed",
    )

    with pytest.raises(LLMContractError, match="YYYY-MM-DD"):
        insert_llm_response(conn, window, response, run_id="llm-offline")


def test_insert_llm_response_rejects_provider_bid_units() -> None:
    conn = _conn()
    window = _window_containing(conn, "$81.00 to $83.00 per share")
    response = LLMExtractionResponse(
        request_id=window.request_id,
        provider_name="offline",
        provider_model="mock",
        reasoning_effort="low",
        candidates=[
            LLMCandidatePayload(
                candidate_type="bid_value",
                raw_value="$81.00 to $83.00 per share",
                normalized_value="81.00-83.00 USD/share",
                confidence="high",
                quote_text="$81.00 to $83.00 per share",
                dependencies=[],
            )
        ],
        raw_response_sha256="0" * 64,
        finish_status="completed",
    )

    with pytest.raises(LLMContractError, match="numeric amount"):
        insert_llm_response(conn, window, response, run_id="llm-offline")


def test_insert_llm_response_rejects_non_integer_participation_count() -> None:
    conn = _conn()
    window = _window_containing(conn, "Three bidders")
    response = LLMExtractionResponse(
        request_id=window.request_id,
        provider_name="offline",
        provider_model="mock",
        reasoning_effort="low",
        candidates=[
            LLMCandidatePayload(
                candidate_type="participation_count",
                raw_value="three bidders",
                normalized_value="3 bidders",
                confidence="high",
                quote_text="Three bidders",
                dependencies=[],
            )
        ],
        raw_response_sha256="0" * 64,
        finish_status="completed",
    )

    with pytest.raises(LLMContractError, match="positive integer"):
        insert_llm_response(conn, window, response, run_id="llm-offline")


def test_insert_llm_response_does_not_partially_insert_invalid_response() -> None:
    conn = _conn()
    window = _window_containing(conn, "On May 21, 2014,")
    response = LLMExtractionResponse(
        request_id=window.request_id,
        provider_name="offline",
        provider_model="mock",
        reasoning_effort="low",
        candidates=[
            LLMCandidatePayload(
                candidate_type="dated_event",
                raw_value="On May 21, 2014,",
                normalized_value="2014-05-21",
                confidence="medium",
                quote_text="On May 21, 2014,",
                dependencies=[],
            ),
            LLMCandidatePayload(
                candidate_type="actor_mention",
                raw_value="the",
                normalized_value="the",
                confidence="low",
                quote_text="the",
                dependencies=[],
            ),
        ],
        raw_response_sha256="0" * 64,
        finish_status="completed",
    )

    with pytest.raises(LLMContractError, match="ambiguous"):
        insert_llm_response(conn, window, response, run_id="llm-offline")

    assert conn.execute(
        "SELECT count(*) FROM candidates WHERE candidate_id LIKE ?",
        ["petsmart-inc_llmcandidate_%"],
    ).fetchone()[0] == 0
    assert conn.execute(
        "SELECT count(*) FROM spans WHERE evidence_id LIKE ?",
        ["petsmart-inc_llmspan_%"],
    ).fetchone()[0] == 0


def test_linkflow_contract_failure_writes_sanitized_artifact(tmp_path, monkeypatch) -> None:
    conn = _conn()
    window = _first_window(conn)
    quote = window.ordered_paragraphs[0].paragraph_text[:10]
    output_text = json.dumps(
        {
            "candidates": [
                {
                    "candidate_type": "actor_mention",
                    "quote_text": quote,
                }
            ]
        }
    )

    class _FakeStream:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        def __aiter__(self):
            return self._events()

        async def _events(self):
            yield {"type": "response.output_text.delta", "delta": output_text}

        async def get_final_response(self):
            return {"status": "completed"}

    class _FakeResponses:
        def stream(self, **kwargs):
            return _FakeStream()

    class _FakeClient:
        responses = _FakeResponses()

    monkeypatch.setenv("LINKFLOW_API_KEY", "test-key")
    monkeypatch.setattr(linkflow, "_ARTIFACT_ROOT", tmp_path)
    monkeypatch.setattr(linkflow, "_make_openai_client", lambda **kwargs: _FakeClient())

    config = linkflow.LLMProviderConfig(
        provider_name="linkflow",
        model="gpt-5.5",
        reasoning_effort="low",
    )
    with pytest.raises(LLMContractError):
        linkflow.extract(window, config)

    artifact = next(tmp_path.glob("*_stage8_live/*_failure.json"))
    payload = json.loads(artifact.read_text(encoding="utf-8"))
    assert payload["finish_status"] == "contract_invalid"
    assert payload["raw_response_sha256"]
    assert "output_text" not in payload


def test_linkflow_streams_responses_with_schema_and_reasoning(tmp_path, monkeypatch) -> None:
    conn = _conn()
    window = _first_window(conn)
    output_text = json.dumps(
        {
            "candidates": [
                {
                    "candidate_type": "actor_mention",
                    "raw_value": "Company",
                    "normalized_value": "Company",
                    "confidence": "high",
                    "quote_text": "Company",
                    "dependencies": [],
                }
            ]
        }
    )

    class _FakeStream:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        def __aiter__(self):
            return self._events()

        async def _events(self):
            yield {"type": "response.output_text.delta", "delta": output_text[:20]}
            yield {"type": "response.output_text.delta", "delta": output_text[20:]}

        async def get_final_response(self):
            return {"status": "completed"}

    class _FakeResponses:
        def __init__(self):
            self.kwargs = None

        def stream(self, **kwargs):
            self.kwargs = kwargs
            return _FakeStream()

    class _FakeClient:
        def __init__(self):
            self.responses = _FakeResponses()

    fake_client = _FakeClient()

    monkeypatch.setenv("LINKFLOW_API_KEY", "test-key")
    monkeypatch.setattr(linkflow, "_ARTIFACT_ROOT", tmp_path)
    monkeypatch.setattr(linkflow, "_make_openai_client", lambda **kwargs: fake_client)

    config = linkflow.LLMProviderConfig(
        provider_name="linkflow",
        model="gpt-5.5",
        reasoning_effort="high",
    )
    response = linkflow.extract(window, config)

    kwargs = fake_client.responses.kwargs
    assert kwargs["model"] == "gpt-5.5"
    assert kwargs["reasoning"] == {"effort": "high"}
    assert kwargs["input"][0]["role"] == "user"
    assert kwargs["text"]["format"]["type"] == "json_schema"
    assert kwargs["text"]["format"]["strict"] is True
    candidate_schema = kwargs["text"]["format"]["schema"]["properties"]["candidates"]["items"]
    assert "quote_start" not in candidate_schema["properties"]
    assert "quote_end" not in candidate_schema["properties"]
    assert response.finish_status == "completed"
    assert len(response.candidates) == 1


def test_linkflow_incomplete_stream_is_not_completed(tmp_path, monkeypatch) -> None:
    """A stream that emits text but never gets response.completed must NOT
    produce finish_status='completed'. Salvage-into-completed is forbidden."""
    conn = _conn()
    window = _first_window(conn)
    output_text = json.dumps(
        {
            "candidates": [
                {
                    "candidate_type": "actor_mention",
                    "raw_value": "Company",
                    "normalized_value": "Company",
                    "confidence": "high",
                    "quote_text": "Company",
                    "dependencies": [],
                }
            ]
        }
    )

    class _FakeStream:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        def __aiter__(self):
            return self._events()

        async def _events(self):
            yield {"type": "response.output_text.delta", "delta": output_text}

        async def get_final_response(self):
            raise RuntimeError("Didn't receive a `response.completed` event.")

    class _FakeResponses:
        def stream(self, **kwargs):
            return _FakeStream()

    class _FakeClient:
        responses = _FakeResponses()

    monkeypatch.setenv("LINKFLOW_API_KEY", "test-key")
    monkeypatch.setattr(linkflow, "_ARTIFACT_ROOT", tmp_path)
    monkeypatch.setattr(linkflow, "_make_openai_client", lambda **kwargs: _FakeClient())

    config = linkflow.LLMProviderConfig(
        provider_name="linkflow",
        model="gpt-5.5",
        reasoning_effort="high",
    )

    with pytest.raises(LLMContractError):
        linkflow.extract(window, config)


def test_linkflow_missing_completed_event_fails_loudly(tmp_path, monkeypatch) -> None:
    """The stream completion policy is fail-loud: any path that loses
    response.completed must raise rather than promote the response."""
    conn = _conn()
    window = _first_window(conn)
    output_text = json.dumps(
        {
            "candidates": [
                {
                    "candidate_type": "actor_mention",
                    "raw_value": "Company",
                    "normalized_value": "Company",
                    "confidence": "high",
                    "quote_text": "Company",
                    "dependencies": [],
                }
            ]
        }
    )

    class _FakeStream:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        def __aiter__(self):
            return self._events()

        async def _events(self):
            yield {"type": "response.output_text.delta", "delta": output_text}

        async def get_final_response(self):
            raise RuntimeError("Didn't receive a `response.completed` event.")

    class _FakeResponses:
        def stream(self, **kwargs):
            return _FakeStream()

    class _FakeClient:
        responses = _FakeResponses()

    monkeypatch.setenv("LINKFLOW_API_KEY", "test-key")
    monkeypatch.setattr(linkflow, "_ARTIFACT_ROOT", tmp_path)
    monkeypatch.setattr(linkflow, "_make_openai_client", lambda **kwargs: _FakeClient())

    config = linkflow.LLMProviderConfig(
        provider_name="linkflow",
        model="gpt-5.5",
        reasoning_effort="high",
    )

    with pytest.raises(LLMContractError, match="response.completed"):
        linkflow.extract(window, config)


def test_actor_relation_is_not_smuggled_through_llm_flat_payload() -> None:
    """The current LLM schema deliberately excludes actor relations.

    Relation candidates in the deterministic extraction layer use structured
    local payloads; provider output cannot smuggle relation JSON through the
    flat normalized_value string.
    """
    with pytest.raises(ValueError):
        LLMCandidatePayload.model_validate(
            {
                "candidate_type": "actor_relation",
                "raw_value": "x",
                "normalized_value": "{\"subject\": \"a\"}",
                "confidence": "high",
                "quote_text": "x",
                "dependencies": [],
            }
        )
