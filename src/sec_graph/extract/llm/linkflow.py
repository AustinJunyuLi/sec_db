"""Linkflow adapter for the within-deal narrative window LLM contract.

Stream completion policy:
- A response without an explicit response.completed event MUST raise
  LinkflowProviderContractError.
- Salvage that promotes incomplete streams to finish_status='completed' is
  forbidden.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any

import duckdb
from pydantic import ValidationError

from sec_graph.extract.llm.convert import insert_llm_response
from sec_graph.extract.llm.models import (
    LinkflowProviderContractError,
    LLMCandidatePayload,
    LLMContractError,
    LLMExtractionResponse,
    LLMProviderConfig,
    LLMWindowRequest,
)
from sec_graph.extract.llm.prompt import build_window_prompt
from sec_graph.extract.llm.requests import build_llm_windows

_ARTIFACT_ROOT = Path("artifacts/linkflow")
_MAX_ATTEMPTS = 3
_BACKOFF_SECONDS = (5.0, 15.0)


def _candidate_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["candidates"],
        "properties": {
            "candidates": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": [
                        "candidate_type",
                        "raw_value",
                        "normalized_value",
                        "confidence",
                        "quote_text",
                        "dependencies",
                    ],
                    "properties": {
                        "candidate_type": {
                            "type": "string",
                            "enum": [
                                "actor_mention",
                                "dated_event",
                                "bid_value",
                                "participation_count",
                            ],
                        },
                        "raw_value": {"type": "string"},
                        "normalized_value": {"type": "string"},
                        "confidence": {
                            "type": "string",
                            "enum": ["low", "medium", "high"],
                        },
                        "quote_text": {"type": "string"},
                        "dependencies": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                    },
                },
            }
        },
    }


def _response_payload(
    request: LLMWindowRequest, config: LLMProviderConfig
) -> dict[str, Any]:
    return {
        "model": config.model,
        "reasoning": {"effort": config.reasoning_effort},
        "input": [
            {
                "role": "user",
                "content": build_window_prompt(request),
            }
        ],
        "text": {
            "format": {
                "type": "json_schema",
                "name": "sec_graph_llm_candidates",
                "strict": True,
                "schema": _candidate_schema(),
            }
        },
    }


def _artifact_dir() -> Path:
    return _ARTIFACT_ROOT / f"{dt.date.today().isoformat()}_stage8_live"


def _write_artifact(name: str, payload: dict[str, Any]) -> Path:
    path = _artifact_dir() / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8"
    )
    return path


def _response_value(response: Any, name: str) -> Any:
    if isinstance(response, dict):
        return response.get(name)
    return getattr(response, name, None)


def _model_dump(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if hasattr(value, "model_dump"):
        return value.model_dump()
    return {}


def _extract_output_text(response_json: Any) -> str:
    output_text = _response_value(response_json, "output_text")
    if isinstance(output_text, str):
        return output_text
    pieces: list[str] = []
    for item in _response_value(response_json, "output") or []:
        item_dict = _model_dump(item)
        for content in item_dict.get("content", []):
            if isinstance(content, dict) and isinstance(content.get("text"), str):
                pieces.append(content["text"])
    if pieces:
        return "".join(pieces)
    raise LLMContractError("provider response did not include output text")


def _parse_candidates(text: str) -> list[LLMCandidatePayload]:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise LLMContractError(
            f"provider output is not valid JSON: {exc.msg}"
        ) from exc
    if not isinstance(payload, dict) or not isinstance(
        payload.get("candidates"), list
    ):
        raise LLMContractError("provider output must contain a candidates array")
    try:
        return [
            LLMCandidatePayload.model_validate(candidate)
            for candidate in payload["candidates"]
        ]
    except ValidationError as exc:
        raise LLMContractError(
            "provider candidate payload failed validation"
        ) from exc


def _write_contract_failure(
    request: LLMWindowRequest,
    config: LLMProviderConfig,
    digest: str,
    message: str,
) -> None:
    _write_artifact(
        f"{request.request_id}_{config.reasoning_effort}_failure.json",
        {
            "request_id": request.request_id,
            "provider_name": config.provider_name,
            "provider_model": config.model,
            "reasoning_effort": config.reasoning_effort,
            "finish_status": "contract_invalid",
            "raw_response_sha256": digest,
            "contract_error": message,
        },
    )


def _make_openai_client(*, api_key: str, base_url: str):
    try:
        from openai import AsyncOpenAI
    except ImportError as exc:
        raise LLMContractError(
            "openai is required for live Linkflow calls"
        ) from exc
    return AsyncOpenAI(api_key=api_key, base_url=base_url, max_retries=0)


def _event_delta(event: Any) -> str:
    if isinstance(event, dict):
        if event.get("type") == "response.output_text.delta":
            return str(event.get("delta") or "")
        return ""
    if getattr(event, "type", "") == "response.output_text.delta":
        return str(getattr(event, "delta", "") or "")
    return ""


def _is_missing_completed_event(exc: BaseException) -> bool:
    return "response.completed" in str(exc)


def _status_code(exc: BaseException) -> int | None:
    status = getattr(exc, "status_code", None)
    if isinstance(status, int):
        return status
    response = getattr(exc, "response", None)
    status = getattr(response, "status_code", None)
    return status if isinstance(status, int) else None


def _is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, LinkflowProviderContractError):
        # Provider contract failures are NOT retryable - they are fail-loud.
        return False
    if isinstance(exc, (asyncio.TimeoutError, TimeoutError)):
        return True
    if getattr(exc, "code", None) == "stream_read_error":
        return True
    status = _status_code(exc)
    if status is not None:
        return status in {408, 409, 425, 429} or status >= 500
    return type(exc).__name__ in {
        "APITimeoutError",
        "APIConnectionError",
        "RateLimitError",
        "InternalServerError",
    }


async def _stream_once(
    request: LLMWindowRequest, config: LLMProviderConfig, client: Any
) -> tuple[str, str]:
    """Stream a single Linkflow request to completion.

    Fail-loud policy: if the SDK raises a missing response.completed error or
    the stream finishes without a completed status, raise
    LinkflowProviderContractError. No salvage to finish_status='completed'.
    """

    text_parts: list[str] = []
    final_response = None
    try:
        async with client.responses.stream(
            **_response_payload(request, config)
        ) as stream:
            async for event in stream:
                delta = _event_delta(event)
                if delta:
                    text_parts.append(delta)
            if hasattr(stream, "get_final_response"):
                final_response = await stream.get_final_response()
    except RuntimeError as exc:
        if _is_missing_completed_event(exc):
            # Per docs/llm-interface.md and docs/spec.md, a stream that loses
            # response.completed is a hard provider contract failure. We do
            # not promote streamed text to finish_status='completed'.
            raise LinkflowProviderContractError(
                "Linkflow stream did not deliver response.completed event"
            ) from exc
        raise

    if final_response is None:
        raise LinkflowProviderContractError(
            "Linkflow stream produced no final response"
        )
    status = str(_response_value(final_response, "status") or "")
    if status != "completed":
        raise LinkflowProviderContractError(
            f"Linkflow stream finished with non-completed status {status!r}"
        )
    if not text_parts:
        text_parts.append(_extract_output_text(final_response))
    if not text_parts:
        raise LLMContractError("provider stream did not include output text")
    return "".join(text_parts), status


async def _stream_with_retry(
    request: LLMWindowRequest, config: LLMProviderConfig, client: Any
) -> tuple[str, str, int]:
    attempts = 0
    while True:
        attempts += 1
        try:
            output_text, finish_reason = await asyncio.wait_for(
                _stream_once(request, config, client),
                timeout=config.timeout_seconds,
            )
            return output_text, finish_reason, attempts
        except BaseException as exc:
            if not _is_retryable(exc) or attempts >= _MAX_ATTEMPTS:
                raise
            await asyncio.sleep(
                _BACKOFF_SECONDS[min(attempts - 1, len(_BACKOFF_SECONDS) - 1)]
            )


async def _stream_with_client(
    request: LLMWindowRequest, config: LLMProviderConfig, api_key: str
) -> tuple[str, str, int]:
    client = _make_openai_client(api_key=api_key, base_url=config.base_url)
    try:
        return await _stream_with_retry(request, config, client)
    finally:
        close = getattr(client, "close", None)
        if close is not None:
            await close()


def extract(
    request: LLMWindowRequest, config: LLMProviderConfig
) -> LLMExtractionResponse:
    api_key = os.environ.get(config.api_key_env)
    if not api_key:
        raise LLMContractError(
            f"{config.api_key_env} is required for live Linkflow calls"
        )
    try:
        output_text, finish_reason, attempts = asyncio.run(
            _stream_with_client(request, config, api_key)
        )
    except LinkflowProviderContractError as exc:
        digest = hashlib.sha256(str(exc).encode("utf-8")).hexdigest()
        _write_artifact(
            f"{request.request_id}_{config.reasoning_effort}_failure.json",
            {
                "request_id": request.request_id,
                "provider_name": config.provider_name,
                "provider_model": config.model,
                "reasoning_effort": config.reasoning_effort,
                "finish_status": "provider_incomplete",
                "raw_response_sha256": digest,
                "error_type": type(exc).__name__,
            },
        )
        raise
    except BaseException as exc:
        status = _status_code(exc)
        digest = hashlib.sha256(str(exc).encode("utf-8")).hexdigest()
        finish_status = (
            "provider_rejected"
            if status is not None
            and 400 <= status < 500
            and status not in {408, 409, 425, 429}
            else "provider_incomplete"
        )
        _write_artifact(
            f"{request.request_id}_{config.reasoning_effort}_failure.json",
            {
                "request_id": request.request_id,
                "provider_name": config.provider_name,
                "provider_model": config.model,
                "reasoning_effort": config.reasoning_effort,
                "finish_status": finish_status,
                "http_status": status,
                "error_type": type(exc).__name__,
                "raw_response_sha256": digest,
            },
        )
        detail = (
            f"Linkflow HTTP error {status}"
            if status is not None
            else "Linkflow request failed"
        )
        raise LLMContractError(detail) from exc

    digest = hashlib.sha256(output_text.encode("utf-8")).hexdigest()
    try:
        candidates = _parse_candidates(output_text)
    except LLMContractError as exc:
        _write_contract_failure(request, config, digest, str(exc))
        raise
    response = LLMExtractionResponse(
        request_id=request.request_id,
        provider_name=config.provider_name,
        provider_model=config.model,
        reasoning_effort=config.reasoning_effort,
        candidates=candidates,
        raw_response_sha256=digest,
        finish_status="completed",
    )
    return response


def _write_success_artifact(
    request: LLMWindowRequest,
    config: LLMProviderConfig,
    response: LLMExtractionResponse,
    inserted_count: int,
) -> None:
    _write_artifact(
        f"{request.request_id}_{config.reasoning_effort}_success.json",
        {
            "request_id": request.request_id,
            "provider_name": config.provider_name,
            "provider_model": config.model,
            "reasoning_effort": config.reasoning_effort,
            "finish_status": response.finish_status,
            "raw_response_sha256": response.raw_response_sha256,
            "candidate_count": len(response.candidates),
            "inserted_candidate_count": inserted_count,
        },
    )


def run_linkflow_requests(
    conn: duckdb.DuckDBPyConnection,
    filing_id: str,
    run_id: str,
    config: LLMProviderConfig,
    limit: int | None = None,
):
    """Drive LLM extraction for a filing, one within-deal window at a time."""

    inserted = []
    windows = build_llm_windows(conn, filing_id=filing_id)
    if limit is not None:
        windows = windows[:limit]
    for request in windows:
        response = extract(request, config)
        try:
            window_inserted = insert_llm_response(conn, request, response, run_id=run_id)
        except LLMContractError as exc:
            _write_contract_failure(request, config, response.raw_response_sha256, str(exc))
            raise
        _write_success_artifact(request, config, response, len(window_inserted))
        inserted.extend(window_inserted)
    return inserted
