"""Plain-Python tool loop over Linkflow's Responses API.

The loop maintains an explicit conversation history (a list of input
items the OpenAI Responses API understands) and dispatches every
function-call item to a registered tool. Each tool result is appended
back as a `function_call_output` item, and the loop re-issues
`responses.create` until the model emits a final structured output —
or the configured turn cap is reached.

There is **no fallback path**. Malformed tool arguments raise loudly;
unregistered tool calls raise; structured output that fails to parse
propagates straight up.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Protocol

from ..errors import (
    LinkflowError,
    MalformedToolArgumentsError,
    ToolDispatchError,
)


# ---------------------------------------------------------------- protocols

class ResponsesClient(Protocol):
    """Subset of `openai.OpenAI` used by the loop. The real `OpenAI`
    object satisfies this protocol via duck typing."""

    @property
    def responses(self) -> "ResponsesEndpoint": ...  # pragma: no cover


class ResponsesEndpoint(Protocol):
    def create(self, **kwargs: Any) -> Any: ...  # pragma: no cover


# ---------------------------------------------------------------- tools

ToolHandler = Callable[[dict[str, Any]], Any]


@dataclass(frozen=True, slots=True)
class ToolDefinition:
    """A function tool exposed to the agent.

    The `parameters` schema is forwarded verbatim to the API; the handler
    receives a parsed-args dict and returns a JSON-serialisable result
    that becomes the body of `function_call_output`.
    """

    name: str
    description: str
    parameters: dict[str, Any]
    handler: ToolHandler

    def to_api_tool(self) -> dict[str, Any]:
        return {
            "type": "function",
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
        }


class ToolRegistry:
    def __init__(self, tools: Iterable[ToolDefinition] = ()) -> None:
        self._tools: dict[str, ToolDefinition] = {}
        for tool in tools:
            self.register(tool)

    def register(self, tool: ToolDefinition) -> None:
        if tool.name in self._tools:
            raise ValueError(f"tool {tool.name!r} already registered")
        self._tools[tool.name] = tool

    def get(self, name: str) -> ToolDefinition:
        if name not in self._tools:
            raise ToolDispatchError(
                f"agent attempted to call unregistered tool {name!r}; "
                f"registered tools: {sorted(self._tools)}"
            )
        return self._tools[name]

    def api_tool_definitions(self) -> list[dict[str, Any]]:
        return [t.to_api_tool() for t in self._tools.values()]

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(self._tools.keys())


# ---------------------------------------------------------------- result

@dataclass(frozen=True, slots=True)
class ToolLoopResult:
    final_output: dict[str, Any] | None
    final_text: str
    tool_results: tuple[dict[str, Any], ...]
    history: tuple[dict[str, Any], ...]
    turns_used: int


# ---------------------------------------------------------------- helpers

def _to_jsonable(item: Any) -> Any:
    if isinstance(item, dict):
        return {k: _to_jsonable(v) for k, v in item.items()}
    if isinstance(item, (list, tuple)):
        return [_to_jsonable(v) for v in item]
    if hasattr(item, "model_dump"):
        return item.model_dump()
    if hasattr(item, "__dict__"):
        return {k: _to_jsonable(v) for k, v in item.__dict__.items() if not k.startswith("_")}
    return item


def _output_items(response: Any) -> list[dict[str, Any]]:
    items = getattr(response, "output", None)
    if items is None and isinstance(response, dict):
        items = response.get("output", [])
    return [_to_jsonable(item) for item in (items or [])]


def _final_text(response: Any) -> str:
    direct = getattr(response, "output_text", None)
    if isinstance(direct, str) and direct:
        return direct
    if isinstance(response, dict):
        ot = response.get("output_text")
        if isinstance(ot, str) and ot:
            return ot
    chunks: list[str] = []
    for item in _output_items(response):
        if item.get("type") == "message":
            for content in item.get("content", []):
                if isinstance(content, dict):
                    text = content.get("text") or content.get("output_text")
                    if isinstance(text, str):
                        chunks.append(text)
    return "".join(chunks)


def _function_calls(response: Any) -> list[dict[str, Any]]:
    return [item for item in _output_items(response) if item.get("type") == "function_call"]


def _parse_tool_args(call: dict[str, Any]) -> dict[str, Any]:
    raw = call.get("arguments", "{}")
    if isinstance(raw, dict):
        return raw
    if not isinstance(raw, str):
        raise MalformedToolArgumentsError(
            f"function call {call.get('name')!r} arguments must be a JSON string or dict, "
            f"got {type(raw).__name__}"
        )
    try:
        parsed = json.loads(raw or "{}")
    except json.JSONDecodeError as exc:
        raise MalformedToolArgumentsError(
            f"function call {call.get('name')!r} emitted invalid JSON arguments: {exc}"
        ) from exc
    if not isinstance(parsed, dict):
        raise MalformedToolArgumentsError(
            f"function call {call.get('name')!r} arguments must decode to an object, "
            f"got {type(parsed).__name__}"
        )
    return parsed


def _call_id(call: dict[str, Any]) -> str:
    value = call.get("call_id") or call.get("id")
    if not isinstance(value, str):
        raise LinkflowError(f"function call missing call_id/id: {call!r}")
    return value


# ---------------------------------------------------------------- loop

class ToolLoop:
    """Drive a Linkflow Responses API conversation with explicit history.

    The loop is sync. Concurrency lives at the orchestrator (see
    `LinkflowClientConfig.max_concurrency`).
    """

    def __init__(
        self,
        *,
        client: ResponsesClient,
        model: str,
        tools: ToolRegistry,
        response_format: dict[str, Any] | None = None,
        reasoning_effort: str | None = None,
        max_turns: int = 6,
    ) -> None:
        if max_turns < 1:
            raise ValueError("max_turns must be >= 1")
        self._client = client
        self._model = model
        self._tools = tools
        self._response_format = response_format
        self._reasoning_effort = reasoning_effort
        self._max_turns = max_turns

    def run(
        self,
        initial_history: list[dict[str, Any]],
    ) -> ToolLoopResult:
        history: list[dict[str, Any]] = list(initial_history)
        tool_results: list[dict[str, Any]] = []

        for turn in range(1, self._max_turns + 1):
            payload: dict[str, Any] = {
                "model": self._model,
                "input": history,
                "tools": self._tools.api_tool_definitions(),
            }
            if self._response_format is not None:
                payload["response_format"] = self._response_format
            if self._reasoning_effort is not None:
                payload["reasoning"] = {"effort": self._reasoning_effort}

            response = self._client.responses.create(**payload)
            calls = _function_calls(response)

            if not calls:
                final_text = _final_text(response)
                final_output = self._parse_final_output(final_text)
                return ToolLoopResult(
                    final_output=final_output,
                    final_text=final_text,
                    tool_results=tuple(tool_results),
                    history=tuple(history),
                    turns_used=turn,
                )

            for call in calls:
                history.append(call)  # echo the function_call into history
                args = _parse_tool_args(call)
                handler = self._tools.get(call["name"]).handler
                result = handler(args)
                tool_results.append(
                    {"name": call["name"], "args": args, "result": result}
                )
                history.append(
                    {
                        "type": "function_call_output",
                        "call_id": _call_id(call),
                        "output": json.dumps(result, default=str),
                    }
                )

        # Hit max_turns without a final answer — refuse to fabricate.
        raise LinkflowError(
            f"tool loop exhausted max_turns={self._max_turns} without a final response"
        )

    def _parse_final_output(self, final_text: str) -> dict[str, Any] | None:
        if self._response_format is None:
            return None
        text = final_text.strip()
        if not text:
            return None
        return json.loads(text)


# ---------------------------------------------------------------- offline fakes

@dataclass(frozen=True, slots=True)
class FakeLinkflowResponse:
    """A canned response shaped like an OpenAI Responses API response."""

    output: list[dict[str, Any]] = field(default_factory=list)
    output_text: str = ""


class _FakeResponsesEndpoint:
    def __init__(self, responses: list[FakeLinkflowResponse]) -> None:
        self._responses = list(responses)
        self._cursor = 0
        self.requests: list[dict[str, Any]] = []

    def create(self, **kwargs: Any) -> FakeLinkflowResponse:
        self.requests.append(kwargs)
        if self._cursor >= len(self._responses):
            raise AssertionError(
                "FakeResponsesClient ran out of canned responses; "
                f"received {len(self.requests)} requests"
            )
        response = self._responses[self._cursor]
        self._cursor += 1
        return response


class FakeResponsesClient:
    """Drop-in replacement for `openai.OpenAI` in tests.

    Construct with a list of `FakeLinkflowResponse` items; each call to
    `client.responses.create(...)` consumes the next one. The instance
    records every request payload on `.responses.requests`.
    """

    def __init__(self, responses: list[FakeLinkflowResponse]) -> None:
        self.responses = _FakeResponsesEndpoint(responses)
