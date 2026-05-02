"""Linkflow adapter for the provider-neutral LLM extraction interface."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import duckdb
from pydantic import ValidationError

from sec_graph.extract.llm.convert import insert_llm_response
from sec_graph.extract.llm.models import (
    LLMCandidatePayload,
    LLMContractError,
    LLMExtractionRequest,
    LLMExtractionResponse,
    LLMProviderConfig,
)
from sec_graph.extract.llm.prompt import build_prompt
from sec_graph.extract.llm.requests import build_llm_requests

_ARTIFACT_ROOT = Path("artifacts/linkflow")


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
                        "quote_start",
                        "quote_end",
                        "dependencies",
                    ],
                    "properties": {
                        "candidate_type": {
                            "type": "string",
                            "enum": ["actor_mention", "dated_event", "bid_value", "participation_count"],
                        },
                        "raw_value": {"type": "string"},
                        "normalized_value": {"type": "string"},
                        "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
                        "quote_text": {"type": "string"},
                        "quote_start": {"type": "integer"},
                        "quote_end": {"type": "integer"},
                        "dependencies": {"type": "array", "items": {"type": "string"}},
                    },
                },
            }
        },
    }


def _response_payload(request: LLMExtractionRequest, config: LLMProviderConfig) -> dict[str, Any]:
    return {
        "model": config.model,
        "reasoning": {"effort": config.reasoning_effort},
        "input": [
            {
                "role": "user",
                "content": build_prompt(request),
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
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return path


def _extract_output_text(response_json: dict[str, Any]) -> str:
    output_text = response_json.get("output_text")
    if isinstance(output_text, str):
        return output_text
    pieces: list[str] = []
    for item in response_json.get("output", []):
        if not isinstance(item, dict):
            continue
        for content in item.get("content", []):
            if isinstance(content, dict) and isinstance(content.get("text"), str):
                pieces.append(content["text"])
    if pieces:
        return "".join(pieces)
    raise LLMContractError("provider response did not include output text")


def _parse_candidates(text: str) -> list[LLMCandidatePayload]:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise LLMContractError(f"provider output is not valid JSON: {exc.msg}") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("candidates"), list):
        raise LLMContractError("provider output must contain a candidates array")
    try:
        return [LLMCandidatePayload.model_validate(candidate) for candidate in payload["candidates"]]
    except ValidationError as exc:
        raise LLMContractError("provider candidate payload failed validation") from exc


def extract(request: LLMExtractionRequest, config: LLMProviderConfig) -> LLMExtractionResponse:
    api_key = os.environ.get(config.api_key_env)
    if not api_key:
        raise LLMContractError(f"{config.api_key_env} is required for live Linkflow calls")
    url = f"{config.base_url.rstrip('/')}/responses"
    body = json.dumps(_response_payload(request, config)).encode("utf-8")
    http_request = urllib.request.Request(
        url,
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(http_request, timeout=config.timeout_seconds) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        raw_error = exc.read()
        digest = hashlib.sha256(raw_error).hexdigest()
        _write_artifact(
            f"{request.request_id}_{config.reasoning_effort}_failure.json",
            {
                "request_id": request.request_id,
                "provider_name": config.provider_name,
                "provider_model": config.model,
                "reasoning_effort": config.reasoning_effort,
                "finish_status": "provider_rejected",
                "http_status": exc.code,
                "raw_response_sha256": digest,
            },
        )
        raise LLMContractError(f"Linkflow HTTP error {exc.code}") from exc
    except urllib.error.URLError as exc:
        _write_artifact(
            f"{request.request_id}_{config.reasoning_effort}_failure.json",
            {
                "request_id": request.request_id,
                "provider_name": config.provider_name,
                "provider_model": config.model,
                "reasoning_effort": config.reasoning_effort,
                "finish_status": "provider_incomplete",
                "error_type": type(exc.reason).__name__,
            },
        )
        raise LLMContractError("Linkflow request failed") from exc
    digest = hashlib.sha256(raw).hexdigest()
    response_json = json.loads(raw.decode("utf-8"))
    output_text = _extract_output_text(response_json)
    candidates = _parse_candidates(output_text)
    response = LLMExtractionResponse(
        request_id=request.request_id,
        provider_name=config.provider_name,
        provider_model=config.model,
        reasoning_effort=config.reasoning_effort,
        candidates=candidates,
        raw_response_sha256=digest,
        finish_status="completed",
    )
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
        },
    )
    return response


def run_linkflow_requests(
    conn: duckdb.DuckDBPyConnection,
    filing_id: str,
    run_id: str,
    config: LLMProviderConfig,
    limit: int | None = None,
):
    inserted = []
    for request in build_llm_requests(conn, filing_id=filing_id, limit=limit):
        response = extract(request, config)
        inserted.extend(insert_llm_response(conn, request, response, run_id=run_id))
    return inserted
