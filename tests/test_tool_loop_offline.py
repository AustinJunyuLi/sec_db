"""Phase 5 (US-006) — Plain-Python tool loop, offline."""

from __future__ import annotations

import json

import pytest

from sec_review_compiler.errors import (
    LinkflowError,
    MalformedToolArgumentsError,
    ToolDispatchError,
)
from sec_review_compiler.llm import (
    FakeLinkflowResponse,
    FakeResponsesClient,
    ToolDefinition,
    ToolLoop,
    ToolLoopResult,
    ToolRegistry,
    extractor_claim_schema,
    strict_response_format,
)


# ---------------------------------------------------------------- helpers

def _tools_with_search(handler) -> ToolRegistry:
    return ToolRegistry(
        [
            ToolDefinition(
                name="search_filing",
                description="Find paragraphs containing a phrase.",
                parameters={
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {"query": {"type": "string"}},
                    "required": ["query"],
                },
                handler=handler,
            ),
        ]
    )


def _function_call_item(*, name: str, args: dict, call_id: str = "call_1") -> dict:
    return {
        "type": "function_call",
        "name": name,
        "call_id": call_id,
        "arguments": json.dumps(args),
    }


def _final_message_response(payload: dict) -> FakeLinkflowResponse:
    text = json.dumps(payload)
    return FakeLinkflowResponse(
        output_text=text,
        output=[
            {
                "type": "message",
                "role": "assistant",
                "content": [{"type": "output_text", "text": text}],
            }
        ],
    )


# ---------------------------------------------------------------- happy path

class TestToolLoopHappyPath:
    def test_two_turn_loop_returns_final_structured_output(self) -> None:
        tool_calls: list[dict] = []

        def handler(args: dict) -> dict:
            tool_calls.append(args)
            return {
                "paragraph_id": "p:1",
                "quote": "On January 2, 2026, Buyer A entered into a confidentiality agreement.",
            }

        tools = _tools_with_search(handler)
        final_payload = {
            "claim_type": "timeline_event",
            "claim_fingerprint": "fp:nda-2026-01-02",
            "payload_json": json.dumps({"event": "nda", "date": "2026-01-02"}),
            "evidence": [
                {
                    "paragraph_id": "p:1",
                    "quote": "On January 2, 2026, Buyer A entered into a confidentiality agreement.",
                }
            ],
        }

        # Turn 1: function_call. Turn 2: final structured output.
        client = FakeResponsesClient([
            FakeLinkflowResponse(
                output=[_function_call_item(name="search_filing", args={"query": "NDA"})],
            ),
            _final_message_response(final_payload),
        ])
        loop = ToolLoop(
            client=client,
            model="gpt-5.5",
            tools=tools,
            response_format=strict_response_format(
                "extractor_claim", extractor_claim_schema()
            ),
            reasoning_effort="medium",
            max_turns=4,
        )
        result = loop.run([
            {"role": "developer", "content": "extract NDA events"},
        ])
        assert isinstance(result, ToolLoopResult)
        assert result.turns_used == 2
        assert result.final_output == final_payload
        assert tool_calls == [{"query": "NDA"}]
        # The history records the function_call and its function_call_output.
        types = [item.get("type") for item in result.history]
        assert "function_call" in types
        assert "function_call_output" in types

    def test_no_tool_calls_returns_immediately(self) -> None:
        client = FakeResponsesClient([
            _final_message_response({"regions": []}),
        ])
        tools = ToolRegistry()
        loop = ToolLoop(
            client=client,
            model="gpt-5.5",
            tools=tools,
            response_format=strict_response_format(
                "scout_map",
                {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {"regions": {"type": "array", "items": {"type": "string"}}},
                    "required": ["regions"],
                },
            ),
            max_turns=2,
        )
        result = loop.run([{"role": "developer", "content": "scout"}])
        assert result.turns_used == 1
        assert result.final_output == {"regions": []}


# ---------------------------------------------------------------- malformed

class TestMalformedToolArguments:
    def test_invalid_json_arguments_raise_loudly(self) -> None:
        called = []

        def handler(args: dict) -> dict:
            called.append(args)
            return {}

        tools = _tools_with_search(handler)
        bad_call = {
            "type": "function_call",
            "name": "search_filing",
            "call_id": "call_xyz",
            "arguments": "{not valid json",
        }
        client = FakeResponsesClient([FakeLinkflowResponse(output=[bad_call])])
        loop = ToolLoop(client=client, model="gpt-5.5", tools=tools, max_turns=2)
        with pytest.raises(MalformedToolArgumentsError):
            loop.run([{"role": "developer", "content": "go"}])
        assert called == []  # handler never invoked

    def test_arguments_must_decode_to_object(self) -> None:
        def handler(args: dict) -> dict:
            return {}

        tools = _tools_with_search(handler)
        bad_call = {
            "type": "function_call",
            "name": "search_filing",
            "call_id": "call_xyz",
            "arguments": json.dumps([1, 2, 3]),  # array, not object
        }
        client = FakeResponsesClient([FakeLinkflowResponse(output=[bad_call])])
        loop = ToolLoop(client=client, model="gpt-5.5", tools=tools, max_turns=2)
        with pytest.raises(MalformedToolArgumentsError):
            loop.run([{"role": "developer", "content": "go"}])

    def test_unregistered_tool_raises_dispatch_error(self) -> None:
        client = FakeResponsesClient([
            FakeLinkflowResponse(output=[
                _function_call_item(name="never_registered", args={"x": 1}),
            ]),
        ])
        loop = ToolLoop(
            client=client,
            model="gpt-5.5",
            tools=ToolRegistry(),
            max_turns=2,
        )
        with pytest.raises(ToolDispatchError):
            loop.run([{"role": "developer", "content": "go"}])


# ---------------------------------------------------------------- caps

class TestToolLoopCaps:
    def test_max_turns_exhausted_raises(self) -> None:
        def handler(args: dict) -> dict:
            return {"hit": True}

        tools = _tools_with_search(handler)
        client = FakeResponsesClient([
            FakeLinkflowResponse(
                output=[_function_call_item(name="search_filing", args={"query": "q"}, call_id=f"c{i}")],
            )
            for i in range(3)
        ])
        loop = ToolLoop(client=client, model="gpt-5.5", tools=tools, max_turns=2)
        with pytest.raises(LinkflowError):
            loop.run([{"role": "developer", "content": "go"}])


# ---------------------------------------------------------------- request shape

class TestRequestShape:
    def test_reasoning_and_response_format_are_attached(self) -> None:
        client = FakeResponsesClient([
            _final_message_response({"regions": []}),
        ])
        tools = ToolRegistry()
        loop = ToolLoop(
            client=client,
            model="gpt-5.5",
            tools=tools,
            response_format=strict_response_format(
                "scout_map",
                {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {"regions": {"type": "array", "items": {"type": "string"}}},
                    "required": ["regions"],
                },
            ),
            reasoning_effort="low",
            max_turns=2,
        )
        loop.run([{"role": "developer", "content": "go"}])
        first_request = client.responses.requests[0]
        assert first_request["model"] == "gpt-5.5"
        assert first_request["response_format"]["strict"] is True
        assert first_request["reasoning"] == {"effort": "low"}
        assert first_request["tools"] == []
