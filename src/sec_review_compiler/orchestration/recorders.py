"""Recorders for provider + tool calls.

Records are JSON-serialisable summaries — never raw prompts or full
responses. The orchestrator hands them to the existing
`exports.review.export_provider_calls` / `export_tool_calls` writers.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class ProviderCallRecorder:
    records: list[dict] = field(default_factory=list)

    def record(
        self,
        *,
        role: str,
        model: str,
        n_input_items: int,
        n_tools_offered: int,
        reasoning_effort: str | None,
        n_output_items: int,
        final_text_length: int,
        function_call_count: int,
        latency_ms: int,
    ) -> None:
        self.records.append({
            "role": role,
            "model": model,
            "n_input_items": n_input_items,
            "n_tools_offered": n_tools_offered,
            "reasoning_effort": reasoning_effort,
            "n_output_items": n_output_items,
            "final_text_length": final_text_length,
            "function_call_count": function_call_count,
            "latency_ms": latency_ms,
        })


@dataclass(slots=True)
class ToolCallRecorder:
    records: list[dict] = field(default_factory=list)

    def record(
        self,
        *,
        role: str,
        tool_name: str,
        arg_keys: list[str],
        result_summary: dict,
        latency_ms: int,
    ) -> None:
        self.records.append({
            "role": role,
            "tool_name": tool_name,
            "arg_keys": list(arg_keys),
            "result_summary": result_summary,
            "latency_ms": latency_ms,
        })
