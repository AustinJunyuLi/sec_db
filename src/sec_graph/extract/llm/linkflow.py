"""Linkflow adapter for typed semantic claims."""

from __future__ import annotations

import asyncio
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
    DEFAULT_REQUEST_MODE,
    LLMContractError,
    LLMExtractionResponse,
    LLMProviderConfig,
    LLMWindowRequest,
    LinkflowProviderContractError,
    ProviderUsage,
    SemanticClaimsPayload,
)
from sec_graph.extract.llm.prompt import build_window_messages
from sec_graph.extract.llm.requests import build_llm_windows

_ARTIFACT_ROOT = Path("artifacts/linkflow")
_MAX_ATTEMPTS = 3
_BACKOFF_SECONDS = (5.0, 15.0)


_CLAIM_ARRAY_BY_TYPE = {
    "actor": "actor_claims",
    "event": "event_claims",
    "bid": "bid_claims",
    "participation_count": "participation_count_claims",
    "actor_relation": "actor_relation_claims",
}

_RELATION_TYPE_ORDER = [
    "member_of",
    "affiliate_of",
    "controls",
    "acquisition_vehicle_of",
    "advises",
    "finances",
    "supports",
    "voting_support_for",
    "rollover_holder_for",
    "committee_member_of",
    "recused_from",
]

_RELATION_ENUMS_BY_OBLIGATION_LABEL = {
    "Buyer group composition": [
        "member_of",
        "affiliate_of",
        "controls",
        "acquisition_vehicle_of",
    ],
    "Financial advisor for target": ["advises"],
    "Legal advisor for target": ["advises"],
    "Voting support agreement": ["voting_support_for"],
    "Rollover holder": ["rollover_holder_for"],
    "Special committee membership": ["committee_member_of"],
    "Recusal from sale process": ["recused_from"],
}


def _semantic_claim_schema(request: LLMWindowRequest | None = None) -> dict[str, Any]:
    schema = SemanticClaimsPayload.model_json_schema()
    _inline_refs(schema)
    _strictify(schema)
    if request is not None:
        _constrain_coverage_obligations(schema, request)
    return schema


def _constrain_coverage_obligations(schema: dict[str, Any], request: LLMWindowRequest) -> None:
    obligations_by_type = {
        claim_type: [
            obligation.obligation_id
            for obligation in request.coverage_obligations
            if obligation.expected_claim_type == claim_type
        ]
        for claim_type in _CLAIM_ARRAY_BY_TYPE
    }
    for claim_type, array_name in _CLAIM_ARRAY_BY_TYPE.items():
        ids = obligations_by_type[claim_type] or [f"__no_{claim_type}_coverage_obligation__"]
        coverage_schema = schema["properties"][array_name]["items"]["properties"]["coverage_obligation_id"]
        coverage_schema["enum"] = ids
    if _only_obligation_label(request, "bid", "Final transaction price"):
        schema["properties"]["bid_claims"]["items"]["properties"]["bid_stage"]["enum"] = ["final"]
    relation_enum = _actor_relation_enum_for_request(request)
    if relation_enum is not None:
        schema["properties"]["actor_relation_claims"]["items"]["properties"]["relation_type"]["enum"] = [
            *relation_enum,
        ]


def _only_obligation_label(request: LLMWindowRequest, claim_type: str, label: str) -> bool:
    matching = [
        obligation
        for obligation in request.coverage_obligations
        if obligation.expected_claim_type == claim_type
    ]
    return bool(matching) and all(obligation.obligation_label == label for obligation in matching)


def _actor_relation_enum_for_request(request: LLMWindowRequest) -> list[str] | None:
    relation_obligations = [
        obligation
        for obligation in request.coverage_obligations
        if obligation.expected_claim_type == "actor_relation"
    ]
    if not relation_obligations:
        return None
    relation_values: set[str] = set()
    for obligation in relation_obligations:
        mapped = _RELATION_ENUMS_BY_OBLIGATION_LABEL.get(obligation.obligation_label)
        if mapped is None:
            raise LLMContractError(
                "unmapped actor-relation obligation label "
                f"{obligation.obligation_label!r}; refusing to widen relation_type enum"
            )
        relation_values.update(mapped)
    return [value for value in _RELATION_TYPE_ORDER if value in relation_values]


def _inline_refs(schema: dict[str, Any]) -> None:
    defs = schema.pop("$defs", {})

    def resolve(node: Any) -> Any:
        if isinstance(node, dict):
            ref = node.get("$ref")
            if isinstance(ref, str) and ref.startswith("#/$defs/"):
                key = ref.rsplit("/", maxsplit=1)[1]
                return resolve(json.loads(json.dumps(defs[key])))
            return {key: resolve(value) for key, value in node.items()}
        if isinstance(node, list):
            return [resolve(item) for item in node]
        return node

    resolved = resolve({"type": "object", **schema})
    schema.clear()
    schema.update(resolved)


def _strictify(node: Any) -> None:
    if isinstance(node, dict):
        _normalize_nullable_union(node)
        for keyword in (
            "default",
            "examples",
            "format",
            "maximum",
            "maxLength",
            "minimum",
            "minItems",
            "minLength",
            "pattern",
            "title",
        ):
            node.pop(keyword, None)
        if node.get("type") == "object":
            node["additionalProperties"] = False
            properties = node.get("properties")
            if isinstance(properties, dict):
                node["required"] = list(properties.keys())
        for value in node.values():
            _strictify(value)
    elif isinstance(node, list):
        for value in node:
            _strictify(value)


def _normalize_nullable_union(node: dict[str, Any]) -> None:
    any_of = node.get("anyOf")
    if not isinstance(any_of, list) or len(any_of) != 2:
        return
    null_nodes = [item for item in any_of if isinstance(item, dict) and item.get("type") == "null"]
    value_nodes = [item for item in any_of if isinstance(item, dict) and item.get("type") != "null"]
    if len(null_nodes) != 1 or len(value_nodes) != 1:
        return
    value_node = value_nodes[0]
    if not _is_scalar_schema(value_node):
        return
    node.pop("anyOf")
    node.update(value_node)
    value_type = node.get("type")
    if isinstance(value_type, str):
        node["type"] = [value_type, "null"]
    enum = node.get("enum")
    if isinstance(enum, list) and None not in enum:
        node["enum"] = [*enum, None]


def _is_scalar_schema(node: dict[str, Any]) -> bool:
    value_type = node.get("type")
    if isinstance(value_type, str) and value_type in {"string", "number", "integer", "boolean"}:
        return True
    return isinstance(node.get("enum"), list)


def _response_payload(request: LLMWindowRequest, config: LLMProviderConfig) -> dict[str, Any]:
    return {
        "model": config.model,
        "reasoning": {"effort": config.reasoning_effort},
        "input": build_window_messages(request),
        "text": {
            "format": {
                "type": "json_schema",
                "name": "sec_graph_semantic_claims",
                "strict": True,
                "schema": _semantic_claim_schema(request),
            }
        },
    }


def _artifact_dir(run_id: str) -> Path:
    return _ARTIFACT_ROOT / run_id


def _write_artifact(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(payload, indent=2, sort_keys=True)
    tmp = path.with_name(f".{path.name}.tmp")
    with tmp.open("w", encoding="utf-8") as handle:
        handle.write(encoded)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)


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


def _parse_payload(text: str) -> SemanticClaimsPayload:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise LLMContractError(f"provider output is not valid JSON: {exc.msg}") from exc
    try:
        return SemanticClaimsPayload.model_validate(payload)
    except ValidationError as exc:
        errors = [
            {
                "loc": ".".join(str(part) for part in error.get("loc", ())),
                "type": error.get("type"),
                "msg": error.get("msg"),
            }
            for error in exc.errors(include_input=False, include_context=False)
        ][:25]
        raise LLMContractError(
            "provider semantic claim payload failed validation: "
            + json.dumps(errors, sort_keys=True, separators=(",", ":"))
        ) from exc


def _make_openai_client(*, api_key: str, base_url: str):
    try:
        from openai import AsyncOpenAI
    except ImportError as exc:
        raise LLMContractError("openai is required for live Linkflow calls") from exc
    return AsyncOpenAI(api_key=api_key, base_url=base_url, max_retries=0)


def _event_delta(event: Any) -> str:
    if isinstance(event, dict):
        return str(event.get("delta") or "") if event.get("type") == "response.output_text.delta" else ""
    return str(getattr(event, "delta", "") or "") if getattr(event, "type", "") == "response.output_text.delta" else ""


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
        return False
    if isinstance(exc, (asyncio.TimeoutError, TimeoutError)):
        return True
    if getattr(exc, "code", None) == "stream_read_error":
        return True
    status = _status_code(exc)
    if status is not None:
        return status in {408, 409, 425, 429} or status >= 500
    return type(exc).__name__ in {"APITimeoutError", "APIConnectionError", "RateLimitError", "InternalServerError"}


async def _stream_once(request: LLMWindowRequest, config: LLMProviderConfig, client: Any) -> tuple[str, str, Any]:
    text_parts: list[str] = []
    final_response = None
    try:
        async with client.responses.stream(**_response_payload(request, config)) as stream:
            async for event in stream:
                delta = _event_delta(event)
                if delta:
                    text_parts.append(delta)
            if hasattr(stream, "get_final_response"):
                final_response = await stream.get_final_response()
    except RuntimeError as exc:
        if _is_missing_completed_event(exc):
            raise LinkflowProviderContractError("Linkflow stream did not deliver response.completed event") from exc
        raise
    if final_response is None:
        raise LinkflowProviderContractError("Linkflow stream produced no final response")
    status = str(_response_value(final_response, "status") or "")
    if status != "completed":
        raise LinkflowProviderContractError(f"Linkflow stream finished with non-completed status {status!r}")
    if not text_parts:
        text_parts.append(_extract_output_text(final_response))
    return "".join(text_parts), status, final_response


async def _stream_with_retry(request: LLMWindowRequest, config: LLMProviderConfig, client: Any) -> tuple[str, str, int, Any, int]:
    attempts = 0
    start = time.monotonic()
    while True:
        attempts += 1
        try:
            output_text, finish_reason, final_response = await asyncio.wait_for(
                _stream_once(request, config, client),
                timeout=config.timeout_seconds,
            )
            return output_text, finish_reason, attempts, final_response, int((time.monotonic() - start) * 1000)
        except BaseException as exc:
            if not _is_retryable(exc) or attempts >= _MAX_ATTEMPTS:
                raise
            await asyncio.sleep(_BACKOFF_SECONDS[min(attempts - 1, len(_BACKOFF_SECONDS) - 1)])


async def _stream_with_client(request: LLMWindowRequest, config: LLMProviderConfig, api_key: str) -> tuple[str, str, int, Any, int]:
    client = _make_openai_client(api_key=api_key, base_url=config.base_url)
    try:
        return await _stream_with_retry(request, config, client)
    finally:
        close = getattr(client, "close", None)
        if close is not None:
            await close()


def extract(request: LLMWindowRequest, config: LLMProviderConfig, *, run_id: str) -> LLMExtractionResponse:
    api_key = os.environ.get(config.api_key_env)
    if not api_key:
        raise LLMContractError(f"{config.api_key_env} is required for live Linkflow calls")
    try:
        output_text, _finish_reason, attempts, final_response, latency_ms = asyncio.run(
            _stream_with_client(request, config, api_key)
        )
    except BaseException as exc:
        _write_failure_artifact(request, config, run_id, exc)
        if isinstance(exc, LLMContractError):
            raise
        raise LLMContractError("Linkflow request failed") from exc

    digest = hashlib.sha256(output_text.encode("utf-8")).hexdigest()
    try:
        payload = _parse_payload(output_text)
    except LLMContractError as exc:
        _write_contract_failure(request, config, run_id, digest, str(exc))
        raise
    return LLMExtractionResponse(
        request_id=request.request_id,
        provider_name=config.provider_name,
        provider_model=config.model,
        reasoning_effort=config.reasoning_effort,
        payload=payload,
        raw_response_sha256=digest,
        finish_status="completed",
        latency_ms=latency_ms,
        attempt_count=attempts,
        usage=_usage(final_response),
    )


def _usage(final_response: Any) -> ProviderUsage:
    usage = _response_value(final_response, "usage")
    if usage is None:
        return ProviderUsage()
    input_tokens = _response_value(usage, "input_tokens")
    output_tokens = _response_value(usage, "output_tokens")
    if isinstance(input_tokens, int) and isinstance(output_tokens, int):
        return ProviderUsage(input_tokens=input_tokens, output_tokens=output_tokens, token_source="actual")
    return ProviderUsage()


def _write_failure_artifact(request: LLMWindowRequest, config: LLMProviderConfig, run_id: str, exc: BaseException) -> None:
    status = _status_code(exc)
    finish_status = "provider_incomplete"
    if status is not None and 400 <= status < 500 and status not in {408, 409, 425, 429}:
        finish_status = "provider_rejected"
    if isinstance(exc, LLMContractError):
        finish_status = "contract_invalid"
    _write_artifact(
        _artifact_dir(run_id) / f"{request.request_id}_{config.reasoning_effort}_failure.json",
        {
            "run_id": run_id,
            "request_id": request.request_id,
            "deal_slug": request.deal_slug,
            "window_id": request.window_id,
            "provider_name": config.provider_name,
            "provider_model": config.model,
            "reasoning_effort": config.reasoning_effort,
            "finish_status": finish_status,
            "http_status": status,
            "error_type": type(exc).__name__,
            "response_digest": hashlib.sha256(str(exc).encode("utf-8")).hexdigest(),
        },
    )


def _write_contract_failure(request: LLMWindowRequest, config: LLMProviderConfig, run_id: str, digest: str, message: str) -> None:
    _write_artifact(
        _artifact_dir(run_id) / f"{request.request_id}_{config.reasoning_effort}_failure.json",
        {
            "run_id": run_id,
            "request_id": request.request_id,
            "deal_slug": request.deal_slug,
            "window_id": request.window_id,
            "provider_name": config.provider_name,
            "provider_model": config.model,
            "reasoning_effort": config.reasoning_effort,
            "finish_status": "contract_invalid",
            "response_digest": digest,
            "error_type": "LLMContractError",
            "contract_error": message,
        },
    )


def _write_success_artifact(request: LLMWindowRequest, config: LLMProviderConfig, run_id: str, response: LLMExtractionResponse, inserted_count: int) -> None:
    claim_count = sum(
        len(items)
        for items in (
            response.payload.actor_claims,
            response.payload.event_claims,
            response.payload.bid_claims,
            response.payload.participation_count_claims,
            response.payload.actor_relation_claims,
        )
    )
    _write_artifact(
        _artifact_dir(run_id) / f"{request.request_id}_{config.reasoning_effort}_success.json",
        {
            "run_id": run_id,
            "request_id": request.request_id,
            "deal_slug": request.deal_slug,
            "window_id": request.window_id,
            "provider_name": config.provider_name,
            "provider_model": config.model,
            "reasoning_effort": config.reasoning_effort,
            "finish_status": response.finish_status,
            "attempt_count": response.attempt_count,
            "latency_ms": response.latency_ms,
            "token_usage": response.usage.model_dump(),
            "response_digest": response.raw_response_sha256,
            "claim_count": claim_count,
            "inserted_claim_count": inserted_count,
            "coverage_obligation_count": len(request.coverage_obligations),
        },
    )


def run_linkflow_requests(
    conn: duckdb.DuckDBPyConnection,
    *,
    filing_id: str,
    run_id: str,
    config: LLMProviderConfig,
    request_mode: str = DEFAULT_REQUEST_MODE,
) -> list[str]:
    inserted: list[str] = []
    for request in build_llm_windows(conn, filing_id=filing_id, request_mode=request_mode):
        response = extract(request, config, run_id=run_id)
        try:
            claim_ids = insert_llm_response(conn, request, response, run_id=run_id)
        except LLMContractError as exc:
            _write_contract_failure(request, config, run_id, response.raw_response_sha256, str(exc))
            raise
        _write_success_artifact(request, config, run_id, response, len(claim_ids))
        _insert_cost_record(conn, request, run_id, config, response)
        inserted.extend(claim_ids)
    return inserted


def _insert_cost_record(
    conn: duckdb.DuckDBPyConnection,
    request: LLMWindowRequest,
    run_id: str,
    config: LLMProviderConfig,
    response: LLMExtractionResponse,
) -> None:
    record_id = f"{request.window_id}_cost_1"
    input_tokens = response.usage.input_tokens
    output_tokens = response.usage.output_tokens
    token_source = response.usage.token_source
    if input_tokens is None:
        prompt_text = "".join(message["content"] for message in build_window_messages(request))
        input_tokens = max(1, len(prompt_text) // 4)
        token_source = "estimated"
    if output_tokens is None:
        output_tokens = max(1, len(response.payload.model_dump_json()) // 4)
        token_source = "estimated"
    conn.execute(
        "INSERT INTO cost_runtime_records VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            record_id,
            run_id,
            request.deal_slug,
            request.window_id,
            config.provider_name,
            config.model,
            config.reasoning_effort,
            input_tokens,
            output_tokens,
            token_source,
            response.latency_ms,
            response.attempt_count - 1,
            None,
        ],
    )
