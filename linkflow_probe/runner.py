"""Tier 1 Linkflow capability probes."""

from __future__ import annotations

import argparse
import asyncio
import json
import platform
import sys
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import openai

from linkflow_probe import __version__
from linkflow_probe.client import DEFAULT_BASE_URL, build_client, load_env
from linkflow_probe.sanitize import append_jsonl, sanitize, to_jsonable, write_json
from linkflow_probe.schemas import minimal_schema, nested_claim_schema, strict_json_schema, verdict_schema


@dataclass
class ProbeContext:
    run_dir: Path
    model: str
    matrix: list[dict[str, Any]] = field(default_factory=list)

    @property
    def sanitized_calls_path(self) -> Path:
        return self.run_dir / "sanitized_calls.jsonl"

    @property
    def raw_shape_path(self) -> Path:
        return self.run_dir / "raw_shape_samples.jsonl"

    @property
    def failures_path(self) -> Path:
        return self.run_dir / "failures.jsonl"

    def record_matrix(self, capability: str, tier: int, status: str, artifacts: list[str], notes: str) -> None:
        self.matrix.append(
            {
                "capability": capability,
                "tier": tier,
                "status": status,
                "evidence_artifacts": artifacts,
                "notes": notes,
            }
        )


def _response_text(response: Any) -> str:
    text = getattr(response, "output_text", None)
    if isinstance(text, str):
        return text
    chunks: list[str] = []
    for item in getattr(response, "output", []) or []:
        data = to_jsonable(item)
        if data.get("type") == "message":
            for content in data.get("content", []):
                if isinstance(content, dict):
                    value = content.get("text") or content.get("output_text")
                    if isinstance(value, str):
                        chunks.append(value)
    return "".join(chunks)


def _output_items(response: Any) -> list[dict[str, Any]]:
    return [to_jsonable(item) for item in (getattr(response, "output", []) or [])]


def _function_calls(response: Any) -> list[dict[str, Any]]:
    calls = []
    for item in _output_items(response):
        if item.get("type") == "function_call":
            calls.append(item)
    return calls


def _call_id(call: dict[str, Any]) -> str:
    value = call.get("call_id") or call.get("id")
    if not isinstance(value, str):
        raise RuntimeError(f"function call missing call_id/id: {call}")
    return value


def _call_name(call: dict[str, Any]) -> str:
    value = call.get("name")
    if not isinstance(value, str):
        raise RuntimeError(f"function call missing name: {call}")
    return value


def _call_args(call: dict[str, Any]) -> dict[str, Any]:
    raw = call.get("arguments", "{}")
    if isinstance(raw, str):
        return json.loads(raw or "{}")
    if isinstance(raw, dict):
        return raw
    raise RuntimeError(f"unsupported function call arguments: {raw!r}")


async def _recorded_create(ctx: ProbeContext, probe_id: str, **payload: Any) -> Any:
    started = time.perf_counter()
    request_line = append_jsonl(
        ctx.sanitized_calls_path,
        {
            "probe_id": probe_id,
            "event": "request",
            "payload": _request_summary(payload),
        },
    )
    try:
        client = build_client()
        response = await client.responses.create(**payload)
    except Exception as exc:  # noqa: BLE001 - probe must classify provider failures
        duration_ms = int((time.perf_counter() - started) * 1000)
        failure_line = append_jsonl(
            ctx.failures_path,
            {
                "probe_id": probe_id,
                "request_ref": f"sanitized_calls.jsonl:{request_line}",
                "duration_ms": duration_ms,
                "error_type": type(exc).__name__,
                "error_message": str(exc),
                "status_code": getattr(exc, "status_code", None),
            },
        )
        raise ProbeFailure(f"{type(exc).__name__}: {exc}", f"failures.jsonl:{failure_line}") from exc
    duration_ms = int((time.perf_counter() - started) * 1000)
    response_line = append_jsonl(
        ctx.sanitized_calls_path,
        {
            "probe_id": probe_id,
            "event": "response",
            "request_ref": f"sanitized_calls.jsonl:{request_line}",
            "duration_ms": duration_ms,
            "status": getattr(response, "status", None),
            "id": getattr(response, "id", None),
            "output_item_types": [item.get("type") for item in _output_items(response)],
            "text": _response_text(response),
            "usage": to_jsonable(getattr(response, "usage", None)),
        },
    )
    shape_line = append_jsonl(
        ctx.raw_shape_path,
        {
            "probe_id": probe_id,
            "response_ref": f"sanitized_calls.jsonl:{response_line}",
            "response_shape": sanitize(response),
        },
    )
    setattr(response, "_probe_artifact_refs", [f"sanitized_calls.jsonl:{response_line}", f"raw_shape_samples.jsonl:{shape_line}"])
    return response


def _request_summary(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "model": payload.get("model"),
        "has_input": "input" in payload,
        "input_item_count": len(payload.get("input", [])) if isinstance(payload.get("input"), list) else None,
        "has_tools": bool(payload.get("tools")),
        "tool_names": [tool.get("name") for tool in payload.get("tools", []) if isinstance(tool, dict)],
        "has_text_format": bool(payload.get("text")),
        "reasoning": payload.get("reasoning"),
    }


class ProbeFailure(RuntimeError):
    def __init__(self, message: str, artifact_ref: str) -> None:
        super().__init__(message)
        self.artifact_ref = artifact_ref


async def probe_connectivity(ctx: ProbeContext) -> None:
    response = await _recorded_create(
        ctx,
        "P1.01",
        model=ctx.model,
        input="Reply with exactly: OK",
    )
    text = _response_text(response).strip()
    status = getattr(response, "status", None)
    if status == "completed" and "OK" in text:
        ctx.record_matrix("sdk_connectivity", 1, "supported", response._probe_artifact_refs, f"completed with text={text!r}")
    else:
        ctx.record_matrix("sdk_connectivity", 1, "unsupported", response._probe_artifact_refs, f"status={status!r}; text={text!r}")


async def probe_reasoning(ctx: ProbeContext) -> None:
    artifacts: list[str] = []
    supported: list[str] = []
    failures: list[str] = []
    for effort in ("low", "medium", "high"):
        try:
            response = await _recorded_create(
                ctx,
                f"P1.02-{effort}",
                model=ctx.model,
                input=f"Reply with exactly: effort-{effort}",
                reasoning={"effort": effort},
            )
            artifacts.extend(response._probe_artifact_refs)
            if getattr(response, "status", None) == "completed":
                supported.append(effort)
        except ProbeFailure as exc:
            artifacts.append(exc.artifact_ref)
            failures.append(f"{effort}:{exc}")
    if supported:
        status = "supported" if len(supported) == 3 else "partial"
        ctx.record_matrix("model_and_reasoning_acceptance", 1, status, artifacts, f"supported={supported}; failures={failures}")
    else:
        ctx.record_matrix("model_and_reasoning_acceptance", 1, "unsupported", artifacts, f"failures={failures}")


async def probe_minimal_schema(ctx: ProbeContext) -> None:
    try:
        response = await _recorded_create(
            ctx,
            "P1.03",
            model=ctx.model,
            input="Return JSON: label yes, confidence 0.95, reason synthetic pass.",
            text={"format": strict_json_schema("minimal_payload", minimal_schema())},
        )
        payload = json.loads(_response_text(response))
        ok = set(payload) == {"label", "confidence", "reason"} and payload["label"] in {"yes", "no"}
        ctx.record_matrix(
            "strict_structured_output_minimal",
            1,
            "supported" if ok else "unsupported",
            response._probe_artifact_refs,
            f"validated={ok}; keys={sorted(payload)}",
        )
    except (json.JSONDecodeError, ProbeFailure) as exc:
        ref = getattr(exc, "artifact_ref", "failures.jsonl")
        ctx.record_matrix("strict_structured_output_minimal", 1, "unsupported", [ref], str(exc))


async def probe_nested_schema(ctx: ProbeContext) -> None:
    artifacts: list[str] = []
    notes: list[str] = []
    for label, schema in (
        ("nullable", nested_claim_schema(nullable=True)),
        ("nonnullable", nested_claim_schema(nullable=False)),
    ):
        try:
            response = await _recorded_create(
                ctx,
                f"P1.04-{label}",
                model=ctx.model,
                input=(
                    "Return one event claim. Use claim_type event, event_subtype nda_signed, "
                    "event_date 2026-01-02, actor_label Buyer A, paragraph p1, quote Synthetic quote."
                ),
                text={"format": strict_json_schema(f"nested_claim_{label}", schema)},
            )
            artifacts.extend(response._probe_artifact_refs)
            payload = json.loads(_response_text(response))
            if payload.get("claim_type") == "event" and payload.get("evidence"):
                notes.append(f"{label}:supported")
            else:
                notes.append(f"{label}:invalid_payload")
        except (json.JSONDecodeError, ProbeFailure) as exc:
            artifacts.append(getattr(exc, "artifact_ref", "failures.jsonl"))
            notes.append(f"{label}:{exc}")
    if any(note == "nullable:supported" for note in notes):
        status = "supported"
    elif any(note == "nonnullable:supported" for note in notes):
        status = "partial"
    else:
        status = "unsupported"
    ctx.record_matrix("strict_structured_output_nested", 1, status, artifacts, "; ".join(notes))


def lookup_tools() -> list[dict[str, Any]]:
    return [
        {
            "type": "function",
            "name": "lookup_case",
            "description": "Return a synthetic fact for a synthetic case id.",
            "parameters": {
                "type": "object",
                "additionalProperties": False,
                "properties": {"case_id": {"type": "string"}},
                "required": ["case_id"],
            },
            "strict": True,
        }
    ]


def filing_tools() -> list[dict[str, Any]]:
    parameters = {
        "type": "object",
        "additionalProperties": False,
        "properties": {"query": {"type": "string"}},
        "required": ["query"],
    }
    paragraph_parameters = {
        "type": "object",
        "additionalProperties": False,
        "properties": {"paragraph_id": {"type": "string"}},
        "required": ["paragraph_id"],
    }
    verify_parameters = {
        "type": "object",
        "additionalProperties": False,
        "properties": {"paragraph_id": {"type": "string"}, "quote": {"type": "string"}},
        "required": ["paragraph_id", "quote"],
    }
    return [
        {"type": "function", "name": "search_text", "description": "Search synthetic filing text.", "parameters": parameters, "strict": True},
        {"type": "function", "name": "get_paragraph", "description": "Fetch a synthetic paragraph.", "parameters": paragraph_parameters, "strict": True},
        {"type": "function", "name": "verify_quote", "description": "Verify a quote in a paragraph.", "parameters": verify_parameters, "strict": True},
    ]


async def probe_single_tool(ctx: ProbeContext) -> None:
    artifacts: list[str] = []
    try:
        turn1 = await _recorded_create(
            ctx,
            "P1.05-turn1",
            model=ctx.model,
            input="Use lookup_case for case_id A1, then answer with the returned fact.",
            tools=lookup_tools(),
        )
        artifacts.extend(turn1._probe_artifact_refs)
        calls = _function_calls(turn1)
        if not calls:
            ctx.record_matrix("tool_call_single_round", 1, "unsupported", artifacts, "no function_call output item")
            return
        call = calls[0]
        tool_output = {"case_id": _call_args(call).get("case_id", "A1"), "fact": "Synthetic target signed an NDA on 2026-01-02."}
        history = [
            {"role": "user", "content": "Use lookup_case for case_id A1, then answer with the returned fact."},
            *[sanitize(item) for item in _output_items(turn1)],
            {"type": "function_call_output", "call_id": _call_id(call), "output": json.dumps(tool_output)},
        ]
        turn2 = await _recorded_create(ctx, "P1.05-turn2", model=ctx.model, input=history, tools=lookup_tools())
        artifacts.extend(turn2._probe_artifact_refs)
        text = _response_text(turn2)
        ok = "2026-01-02" in text or "NDA" in text
        ctx.record_matrix("tool_call_single_round", 1, "supported" if ok else "partial", artifacts, f"final_text={text!r}")
    except ProbeFailure as exc:
        artifacts.append(exc.artifact_ref)
        ctx.record_matrix("tool_call_single_round", 1, "unsupported", artifacts, str(exc))


def execute_synthetic_tool(name: str, args: dict[str, Any]) -> dict[str, Any]:
    paragraphs = {
        "p1": "On January 2, 2026, Buyer A entered into a confidentiality agreement with Target Co.",
        "p2": "On February 5, 2026, Buyer A submitted a final proposal to acquire Target Co.",
    }
    if name == "search_text":
        return {"matches": [{"paragraph_id": "p1", "snippet": paragraphs["p1"]}]}
    if name == "get_paragraph":
        paragraph_id = str(args.get("paragraph_id", "p1"))
        return {"paragraph_id": paragraph_id, "text": paragraphs.get(paragraph_id, "")}
    if name == "verify_quote":
        paragraph_id = str(args.get("paragraph_id", "p1"))
        quote = str(args.get("quote", ""))
        text = paragraphs.get(paragraph_id, "")
        return {"paragraph_id": paragraph_id, "verbatim_present": quote in text, "quote": quote}
    if name == "lookup_case":
        return {"case_id": args.get("case_id", "A1"), "fact": "Synthetic target signed an NDA on 2026-01-02."}
    raise RuntimeError(f"unknown synthetic tool {name}")


async def run_tool_loop(ctx: ProbeContext, final_schema: bool) -> tuple[str, list[str], int]:
    artifacts: list[str] = []
    tools = filing_tools()
    instruction = (
        "Use tools to find the paragraph about Buyer A's confidentiality agreement. "
        "You must search_text, then get_paragraph, then verify_quote before finalizing. "
    )
    if final_schema:
        instruction += "Return final JSON matching the requested schema."
    history: list[dict[str, Any]] = [{"role": "user", "content": instruction}]
    tool_result_count = 0
    for round_index in range(1, 11):
        payload: dict[str, Any] = {
            "model": ctx.model,
            "input": history,
            "tools": tools,
        }
        if final_schema:
            payload["text"] = {"format": strict_json_schema("verdict_payload", verdict_schema())}
        response = await _recorded_create(ctx, f"P1.06-07-round{round_index}", **payload)
        artifacts.extend(response._probe_artifact_refs)
        calls = _function_calls(response)
        if not calls:
            return _response_text(response), artifacts, tool_result_count
        history.extend([sanitize(item) for item in _output_items(response)])
        for call in calls:
            name = _call_name(call)
            result = execute_synthetic_tool(name, _call_args(call))
            tool_result_count += 1
            history.append({"type": "function_call_output", "call_id": _call_id(call), "output": json.dumps(result)})
    raise ProbeFailure("tool loop exceeded 10 rounds", artifacts[-1] if artifacts else "sanitized_calls.jsonl")


async def probe_tool_loop(ctx: ProbeContext) -> None:
    try:
        text, artifacts, tool_count = await run_tool_loop(ctx, final_schema=False)
        ok = tool_count >= 2 and ("p1" in text or "confidentiality" in text.lower() or "NDA" in text)
        ctx.record_matrix("tool_call_multi_turn_loop", 1, "supported" if ok else "partial", artifacts, f"tool_results={tool_count}; final_text={text!r}")
    except ProbeFailure as exc:
        ctx.record_matrix("tool_call_multi_turn_loop", 1, "unsupported", [exc.artifact_ref], str(exc))


async def probe_tool_loop_structured(ctx: ProbeContext) -> None:
    try:
        text, artifacts, tool_count = await run_tool_loop(ctx, final_schema=True)
        payload = json.loads(text)
        ok = tool_count >= 2 and set(payload) == {"verdict", "paragraph_id", "quote", "reason"}
        ctx.record_matrix("tool_use_plus_final_structured_output", 1, "supported" if ok else "partial", artifacts, f"tool_results={tool_count}; payload={payload}")
    except (json.JSONDecodeError, ProbeFailure) as exc:
        ctx.record_matrix("tool_use_plus_final_structured_output", 1, "unsupported", [getattr(exc, "artifact_ref", "failures.jsonl")], str(exc))


async def probe_error_taxonomy(ctx: ProbeContext) -> None:
    artifacts: list[str] = []
    classifications: list[str] = []
    invalid_cases = [
        ("invalid_model", {"model": "definitely-not-a-real-linkflow-model", "input": "Reply OK"}),
        (
            "invalid_schema",
            {
                "model": ctx.model,
                "input": "Return JSON.",
                "text": {"format": {"type": "json_schema", "name": "bad_schema", "strict": True, "schema": {"type": "object", "required": ["missing"]}}},
            },
        ),
    ]
    for probe_id, payload in invalid_cases:
        try:
            await _recorded_create(ctx, f"P1.08-{probe_id}", **payload)
            classifications.append(f"{probe_id}:unexpected_success")
        except ProbeFailure as exc:
            artifacts.append(exc.artifact_ref)
            classifications.append(f"{probe_id}:classified")
    try:
        timeout_client = build_client(timeout=0.001)
        started = time.perf_counter()
        await timeout_client.responses.create(model=ctx.model, input="Reply OK")
        classifications.append("timeout:unexpected_success")
    except Exception as exc:  # noqa: BLE001
        line = append_jsonl(
            ctx.failures_path,
            {
                "probe_id": "P1.08-timeout",
                "duration_ms": int((time.perf_counter() - started) * 1000),
                "error_type": type(exc).__name__,
                "error_message": str(exc),
                "status_code": getattr(exc, "status_code", None),
            },
        )
        artifacts.append(f"failures.jsonl:{line}")
        classifications.append("timeout:classified")
    ok = all(item.endswith(":classified") for item in classifications)
    ctx.record_matrix("error_and_retry_taxonomy", 1, "supported" if ok else "partial", artifacts, "; ".join(classifications))


async def probe_concurrency(ctx: ProbeContext) -> None:
    artifacts: list[str] = []
    notes: list[str] = []
    max_supported = 0
    for level in (1, 2, 4, 8):
        async def one_call(index: int) -> bool:
            response = await _recorded_create(ctx, f"P1.09-c{level}-{index}", model=ctx.model, input=f"Reply with exactly: C{level}-{index}")
            artifacts.extend(response._probe_artifact_refs)
            return getattr(response, "status", None) == "completed"

        try:
            results = await asyncio.gather(*(one_call(index) for index in range(level)))
            success_count = sum(1 for item in results if item)
            notes.append(f"concurrency_{level}:{success_count}/{level}")
            if success_count == level:
                max_supported = level
        except ProbeFailure as exc:
            artifacts.append(exc.artifact_ref)
            notes.append(f"concurrency_{level}:failed:{exc}")
            break
    if max_supported >= 2:
        status = "supported"
    elif max_supported == 1:
        status = "partial"
    else:
        status = "unsupported"
    ctx.record_matrix("bounded_concurrency", 1, status, artifacts, f"max_supported={max_supported}; {'; '.join(notes)}")


async def probe_streaming(ctx: ProbeContext) -> None:
    started = time.perf_counter()
    events: list[str] = []
    try:
        client = build_client()
        async with client.responses.stream(model=ctx.model, input="Reply with exactly: STREAM_OK") as stream:
            async for event in stream:
                events.append(type(event).__name__)
            final = await stream.get_final_response()
        line = append_jsonl(
            ctx.sanitized_calls_path,
            {
                "probe_id": "P2.01-streaming",
                "event": "streaming_response",
                "duration_ms": int((time.perf_counter() - started) * 1000),
                "event_types": events,
                "status": getattr(final, "status", None),
                "text": _response_text(final),
            },
        )
        ctx.record_matrix("streaming_event_shapes", 2, "supported", [f"sanitized_calls.jsonl:{line}"], f"event_types={sorted(set(events))}")
    except Exception as exc:  # noqa: BLE001
        line = append_jsonl(
            ctx.failures_path,
            {
                "probe_id": "P2.01-streaming",
                "duration_ms": int((time.perf_counter() - started) * 1000),
                "error_type": type(exc).__name__,
                "error_message": str(exc),
                "status_code": getattr(exc, "status_code", None),
            },
        )
        ctx.record_matrix("streaming_event_shapes", 2, "unsupported", [f"failures.jsonl:{line}"], str(exc))


def gate_status(matrix: list[dict[str, Any]]) -> str:
    statuses = {entry["capability"]: entry["status"] for entry in matrix if entry["tier"] == 1}
    hard_required = [
        "sdk_connectivity",
        "strict_structured_output_minimal",
        "strict_structured_output_nested",
        "tool_call_single_round",
        "tool_call_multi_turn_loop",
        "tool_use_plus_final_structured_output",
        "error_and_retry_taxonomy",
    ]
    if any(statuses.get(item) == "unsupported" for item in hard_required):
        return "NO_GO"
    if any(statuses.get(item) in {"partial", "inconclusive", "not_tested"} for item in statuses):
        return "GO_WITH_LIMITATIONS"
    return "GO"


async def run_tier1(args: argparse.Namespace) -> Path:
    env = load_env()
    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    run_dir = Path("runs") / "linkflow-probe" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    ctx = ProbeContext(run_dir=run_dir, model=args.model or env.model)
    manifest = {
        "probe_run_id": run_id,
        "started_at": datetime.now(UTC).isoformat(),
        "probe_suite_version": __version__,
        "python_version": sys.version,
        "platform": platform.platform(),
        "openai_version": openai.__version__,
        "linkflow_base_url": env.base_url or DEFAULT_BASE_URL,
        "models_tested": [ctx.model],
        "environment": {
            "LINKFLOW_API_KEY_present": env.api_key_present,
            "LINKFLOW_BASE_URL_present": bool(env.base_url),
        },
    }
    write_json(run_dir / "probe_manifest.json", manifest)
    probes = [
        probe_connectivity,
        probe_reasoning,
        probe_minimal_schema,
        probe_nested_schema,
        probe_single_tool,
        probe_tool_loop,
        probe_tool_loop_structured,
        probe_error_taxonomy,
        probe_concurrency,
    ]
    if args.include_streaming:
        probes.append(probe_streaming)
    for probe in probes:
        await probe(ctx)
        write_json(run_dir / "capability_matrix.json", {"entries": ctx.matrix, "gate": gate_status(ctx.matrix)})
    gate = gate_status(ctx.matrix)
    write_json(run_dir / "capability_matrix.json", {"entries": ctx.matrix, "gate": gate})
    readme_lines = [
        "# Linkflow probe run",
        "",
        f"- Probe run id: `{run_id}`",
        f"- Model: `{ctx.model}`",
        f"- Gate: `{gate}`",
        "",
        "## Tier 1 matrix",
        "",
    ]
    for entry in ctx.matrix:
        readme_lines.append(f"- P{entry['tier']} `{entry['capability']}`: `{entry['status']}` - {entry['notes']}")
    (run_dir / "README.md").write_text("\n".join(readme_lines) + "\n", encoding="utf-8")
    return run_dir


def summarize(run_dir: Path) -> None:
    matrix_path = run_dir / "capability_matrix.json"
    data = json.loads(matrix_path.read_text(encoding="utf-8"))
    print(f"Gate: {data.get('gate')}")
    for entry in data.get("entries", []):
        print(f"{entry['capability']}: {entry['status']} - {entry['notes']}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run Linkflow capability probes.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    run = subparsers.add_parser("run", help="Run probe suite.")
    run.add_argument("--tier", choices=["1", "all"], default="1")
    run.add_argument("--model", default=None)
    run.add_argument("--include-streaming", action="store_true")
    summarize_parser = subparsers.add_parser("summarize", help="Summarize a probe run.")
    summarize_parser.add_argument("run_dir", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "run":
        try:
            run_dir = asyncio.run(run_tier1(args))
        except RuntimeError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 2
        summarize(run_dir)
        print(f"Artifacts: {run_dir}")
        return 0
    if args.command == "summarize":
        summarize(args.run_dir)
        return 0
    raise AssertionError(args.command)
