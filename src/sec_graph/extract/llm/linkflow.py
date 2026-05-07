"""Linkflow adapter for typed semantic claims.

Region requests for one filing fan out under ``asyncio.gather`` against a
shared ``AsyncOpenAI`` client and a bounded ``Semaphore``. Successful
responses are sorted back into original window order and inserted under one
DuckDB transaction on the caller thread. If any window's retries are
exhausted the whole filing attempt is failed; failure artifacts remain on
disk for audit but no claim, coverage, canonical, or projection row is
written.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any, Sequence

import duckdb
from pydantic import BaseModel, ConfigDict, Field, ValidationError

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
from sec_graph.run import record_artifact

_MAX_ATTEMPTS = 3
_BACKOFF_SECONDS = (5.0, 15.0)
_REGION_CONCURRENCY_ENV = "SEC_GRAPH_REGION_MAX_CONCURRENCY"
_DEFAULT_REGION_CONCURRENCY = 2


_CLAIM_ARRAY_BY_TYPE = {
    "actor": "actor_claims",
    "event": "event_claims",
    "bid": "bid_claims",
    "participation_count": "participation_count_claims",
    "actor_relation": "actor_relation_claims",
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
    if _only_obligation_label(request, "bid", "Final bid price"):
        schema["properties"]["bid_claims"]["items"]["properties"]["bid_stage"]["enum"] = ["final"]
    if _only_obligation_label(request, "actor_relation", "Buyer group composition"):
        schema["properties"]["actor_relation_claims"]["items"]["properties"]["relation_type"]["enum"] = [
            "member_of",
            "affiliate_of",
            "controls",
            "acquisition_vehicle_of",
        ]


def _only_obligation_label(request: LLMWindowRequest, claim_type: str, label: str) -> bool:
    matching = [
        obligation
        for obligation in request.coverage_obligations
        if obligation.expected_claim_type == claim_type
    ]
    return bool(matching) and all(obligation.obligation_label == label for obligation in matching)


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


def _attempt_artifact_path(run_dir: Path, request: LLMWindowRequest, kind: str) -> Path:
    base = run_dir / "linkflow" / request.deal_slug / request.request_id
    existing = sorted(base.glob("attempt-*.json")) if base.exists() else []
    sequence = len(existing) + 1
    return base / f"attempt-{sequence:03d}_{kind}.json"


def _write_artifact(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(payload, indent=2, sort_keys=True)
    tmp = path.with_name(f".{path.name}.tmp")
    with tmp.open("w", encoding="utf-8") as handle:
        handle.write(encoded)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)


def _record_attempt_artifact(run_dir: Path, run_id: str, request: LLMWindowRequest, path: Path) -> None:
    record_artifact(
        run_dir,
        run_id=run_id,
        path=path,
        artifact_kind="linkflow_attempt",
        owning_stage="extract",
        deal_slug=request.deal_slug,
        created_by="run_linkflow_requests",
    )


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


def make_async_openai_client(config: LLMProviderConfig):
    """Build an ``AsyncOpenAI`` client using the api key declared by ``config``.

    Raises ``LLMContractError`` when the api key env var is missing or when the
    ``openai`` package cannot be imported. The returned client is an async
    context manager: callers must enter ``async with`` so the underlying HTTP
    session is closed exactly once after all region calls complete.
    """

    api_key = os.environ.get(config.api_key_env)
    if not api_key:
        raise LLMContractError(f"{config.api_key_env} is required for live Linkflow calls")
    try:
        from openai import AsyncOpenAI
    except ImportError as exc:
        raise LLMContractError("openai is required for live Linkflow calls") from exc
    return AsyncOpenAI(api_key=api_key, base_url=config.base_url, max_retries=0)


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


def _usage(final_response: Any) -> ProviderUsage:
    usage = _response_value(final_response, "usage")
    if usage is None:
        return ProviderUsage()
    input_tokens = _response_value(usage, "input_tokens")
    output_tokens = _response_value(usage, "output_tokens")
    if isinstance(input_tokens, int) and isinstance(output_tokens, int):
        return ProviderUsage(input_tokens=input_tokens, output_tokens=output_tokens, token_source="actual")
    return ProviderUsage()


class WindowBundle(BaseModel):
    """Per-window outcome from one fan-out attempt.

    Carries either the validated provider response or the captured error so the
    caller can decide whether to commit the whole filing attempt.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    sequence: int = Field(ge=1)
    request_id: str
    request: LLMWindowRequest
    response: LLMExtractionResponse | None = None
    error_type: str | None = None
    error_message: str | None = None
    http_status: int | None = None
    finish_status: str | None = None
    response_digest: str | None = None
    artifact_payload: dict[str, Any] | None = None
    artifact_kind: str | None = None  # "success" or "failure"

    @property
    def succeeded(self) -> bool:
        return self.response is not None and self.error_message is None


def _resolve_max_concurrency(value: int | None = None) -> int:
    if value is not None:
        if value < 1:
            raise ValueError(f"region max concurrency must be a positive integer; got {value!r}")
        return value
    raw = os.environ.get(_REGION_CONCURRENCY_ENV)
    if raw is None or raw == "":
        return _DEFAULT_REGION_CONCURRENCY
    try:
        parsed = int(raw)
    except ValueError as exc:
        raise ValueError(
            f"{_REGION_CONCURRENCY_ENV} must be a positive integer; got {raw!r}"
        ) from exc
    if parsed < 1:
        raise ValueError(
            f"{_REGION_CONCURRENCY_ENV} must be a positive integer; got {raw!r}"
        )
    return parsed


async def _extract_one_window(
    sequence: int,
    request: LLMWindowRequest,
    client: Any,
    semaphore: asyncio.Semaphore,
    config: LLMProviderConfig,
    run_id: str,
) -> WindowBundle:
    async with semaphore:
        try:
            output_text, _finish_reason, attempts, final_response, latency_ms = await _stream_with_retry(
                request, config, client
            )
        except BaseException as exc:  # noqa: BLE001 - we surface the captured error
            return _failure_bundle(sequence, request, config, exc)

    digest = hashlib.sha256(output_text.encode("utf-8")).hexdigest()
    try:
        payload = _parse_payload(output_text)
    except LLMContractError as exc:
        return _contract_failure_bundle(sequence, request, config, digest, str(exc))
    response = LLMExtractionResponse(
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
    return WindowBundle(
        sequence=sequence,
        request_id=request.request_id,
        request=request,
        response=response,
        finish_status="completed",
        response_digest=digest,
        artifact_kind="success",
        artifact_payload=_success_artifact_payload(request, config, run_id, response),
    )


def _failure_bundle(
    sequence: int,
    request: LLMWindowRequest,
    config: LLMProviderConfig,
    exc: BaseException,
) -> WindowBundle:
    status = _status_code(exc)
    finish_status = "provider_incomplete"
    if status is not None and 400 <= status < 500 and status not in {408, 409, 425, 429}:
        finish_status = "provider_rejected"
    if isinstance(exc, LLMContractError):
        finish_status = "contract_invalid"
    digest = hashlib.sha256(str(exc).encode("utf-8")).hexdigest()
    payload = {
        "request_id": request.request_id,
        "deal_slug": request.deal_slug,
        "window_id": request.window_id,
        "provider_name": config.provider_name,
        "provider_model": config.model,
        "reasoning_effort": config.reasoning_effort,
        "finish_status": finish_status,
        "http_status": status,
        "error_type": type(exc).__name__,
        "response_digest": digest,
        "error_message": str(exc),
    }
    return WindowBundle(
        sequence=sequence,
        request_id=request.request_id,
        request=request,
        response=None,
        error_type=type(exc).__name__,
        error_message=str(exc),
        http_status=status,
        finish_status=finish_status,
        response_digest=digest,
        artifact_kind="failure",
        artifact_payload=payload,
    )


def _contract_failure_bundle(
    sequence: int,
    request: LLMWindowRequest,
    config: LLMProviderConfig,
    digest: str,
    message: str,
) -> WindowBundle:
    payload = {
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
    }
    return WindowBundle(
        sequence=sequence,
        request_id=request.request_id,
        request=request,
        response=None,
        error_type="LLMContractError",
        error_message=message,
        finish_status="contract_invalid",
        response_digest=digest,
        artifact_kind="failure",
        artifact_payload=payload,
    )


def _success_artifact_payload(
    request: LLMWindowRequest,
    config: LLMProviderConfig,
    run_id: str,
    response: LLMExtractionResponse,
) -> dict[str, Any]:
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
    return {
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
        "coverage_obligation_count": len(request.coverage_obligations),
    }


async def extract_linkflow_windows(
    windows: Sequence[LLMWindowRequest],
    config: LLMProviderConfig,
    run_id: str,
    *,
    max_concurrency: int | None = None,
    client_factory: Any | None = None,
) -> list[WindowBundle]:
    """Run all ``windows`` for one filing under one event loop.

    Parameters
    ----------
    windows:
        Original-order sequence of provider requests for one filing.
    config:
        Provider config (api key env name + model + reasoning effort).
    run_id:
        Top-level run id; written into success/failure artifact payloads.
    max_concurrency:
        Overrides ``SEC_GRAPH_REGION_MAX_CONCURRENCY``. Default is 2.
    client_factory:
        Optional zero-arg factory returning an async-context-manager-friendly
        client. Tests inject a stub here. Production code uses the default
        ``AsyncOpenAI`` client wired through ``make_async_openai_client``.
    """

    bound = _resolve_max_concurrency(max_concurrency)
    semaphore = asyncio.Semaphore(bound)
    factory = client_factory if client_factory is not None else (lambda: make_async_openai_client(config))
    client = factory()
    try:
        async with client:
            tasks = [
                _extract_one_window(sequence, request, client, semaphore, config, run_id)
                for sequence, request in enumerate(windows, start=1)
            ]
            bundles = await asyncio.gather(*tasks)
    except TypeError:
        # Some clients are not async-context-managers; fall back to manual close.
        try:
            tasks = [
                _extract_one_window(sequence, request, client, semaphore, config, run_id)
                for sequence, request in enumerate(windows, start=1)
            ]
            bundles = await asyncio.gather(*tasks)
        finally:
            close = getattr(client, "close", None)
            if close is not None:
                result = close()
                if asyncio.iscoroutine(result):
                    await result
    return sorted(bundles, key=lambda bundle: bundle.sequence)


def run_linkflow_requests(
    conn: duckdb.DuckDBPyConnection,
    *,
    filing_id: str,
    run_id: str,
    run_dir: Path,
    config: LLMProviderConfig,
    request_mode: str = DEFAULT_REQUEST_MODE,
    max_concurrency: int | None = None,
    client_factory: Any | None = None,
) -> list[str]:
    """Fan out region requests for one filing, then sequentially insert.

    Provider artifacts land under ``{run_dir}/linkflow/{deal_slug}/{request_id}``
    and every artifact is recorded in ``stage_artifacts.jsonl``. If any window
    fails, the function writes failure artifacts and raises ``LLMContractError``;
    no claim is imported for the filing attempt.
    """

    windows = build_llm_windows(conn, filing_id=filing_id, request_mode=request_mode)
    if not windows:
        return []

    bundles = asyncio.run(
        extract_linkflow_windows(
            windows,
            config,
            run_id,
            max_concurrency=max_concurrency,
            client_factory=client_factory,
        )
    )

    failures = [bundle for bundle in bundles if not bundle.succeeded]
    if failures:
        # Write every bundle's artifact for audit, then raise. Successful bundles
        # in this attempt are kept on disk so an external reviewer can inspect
        # the partially-completed batch.
        for bundle in bundles:
            _persist_bundle_artifact(run_dir, run_id, bundle)
        first = failures[0]
        raise LLMContractError(
            f"Linkflow region request failed for {first.request_id}: {first.error_message}"
        )

    inserted: list[str] = []
    for bundle in bundles:
        assert bundle.response is not None
        try:
            claim_ids = insert_llm_response(conn, bundle.request, bundle.response, run_id=run_id)
        except LLMContractError as exc:
            failure = _contract_failure_bundle(
                bundle.sequence,
                bundle.request,
                config,
                bundle.response.raw_response_sha256,
                str(exc),
            )
            _persist_bundle_artifact(run_dir, run_id, failure)
            raise
        inserted.extend(claim_ids)
        # Augment the success payload with the inserted claim count, then write.
        if bundle.artifact_payload is not None:
            bundle.artifact_payload["inserted_claim_count"] = len(claim_ids)
        _persist_bundle_artifact(run_dir, run_id, bundle)
        _insert_cost_record(conn, bundle.request, run_id, config, bundle.response)
    return inserted


def _persist_bundle_artifact(run_dir: Path, run_id: str, bundle: WindowBundle) -> None:
    if bundle.artifact_payload is None or bundle.artifact_kind is None:
        return
    path = _attempt_artifact_path(run_dir, bundle.request, bundle.artifact_kind)
    payload = dict(bundle.artifact_payload)
    payload.setdefault("run_id", run_id)
    _write_artifact(path, payload)
    _record_attempt_artifact(run_dir, run_id, bundle.request, path)


def extract(request: LLMWindowRequest, config: LLMProviderConfig, *, run_id: str, run_dir: Path) -> LLMExtractionResponse:
    """Single-window adapter retained for legacy callers and tests.

    Production code should call ``run_linkflow_requests`` so all windows for a
    filing share one event loop and one shared client. This single-window path
    preserves the fan-out artifact contract so direct callers do not silently
    bypass the new artifact ledger.
    """

    bundles = asyncio.run(extract_linkflow_windows([request], config, run_id))
    bundle = bundles[0]
    _persist_bundle_artifact(run_dir, run_id, bundle)
    if not bundle.succeeded:
        raise LLMContractError(bundle.error_message or "Linkflow request failed")
    assert bundle.response is not None
    return bundle.response


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
