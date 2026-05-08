"""Linkflow-driven verifier for the live vertical slice.

One ToolLoop call per bound claim attempt. The verifier sees the
attempt's cited paragraph snippets and a restricted tool surface; it
does NOT see the extractor's reasoning or any baseline answers.
"""

from __future__ import annotations

import json
import time
from typing import Sequence

from ..agents.outputs import VerifierVerdict as VerifierVerdictModel
from ..agents.prompts import role_prompt
from ..agents.roles import AgentRole
from ..agents.tool_surface import tools_for_role
from ..llm.linkflow import LinkflowClientConfig
from ..llm.schemas import role_response_format
from ..llm.tool_loop import ToolLoop, ToolLoopResult, ToolRegistry
from ..retrieval.index import RetrievalIndex
from .recorders import ProviderCallRecorder, ToolCallRecorder
from .tool_handlers import build_tool_definitions
from .verifier import VerifierProposal


class LiveLinkflowVerifier:
    def __init__(
        self,
        *,
        client,
        config: LinkflowClientConfig,
        provider_recorder: ProviderCallRecorder,
        tool_recorder: ToolCallRecorder,
        reasoning_effort: str = "high",
        max_turns: int = 4,
    ) -> None:
        self._client = client
        self._config = config
        self._provider_recorder = provider_recorder
        self._tool_recorder = tool_recorder
        self._reasoning_effort = reasoning_effort
        self._max_turns = max_turns
        self._index: RetrievalIndex | None = None

    def bind_index(self, index: RetrievalIndex) -> None:
        """Called once by the orchestrator before any verify()."""
        self._index = index

    def verify(
        self,
        *,
        attempt_id: str,
        cited_quotes: Sequence[str],
        cited_paragraph_ids: Sequence[str],
        raw_text: str,
    ) -> VerifierProposal:
        if self._index is None:
            raise RuntimeError(
                "LiveLinkflowVerifier.bind_index must be called before verify()"
            )
        role = AgentRole.VERIFIER
        tool_names = sorted(tools_for_role(role))
        tools = ToolRegistry(
            build_tool_definitions(
                role=role,
                tool_names=tool_names,
                index=self._index,
                recorder=self._tool_recorder,
            )
        )
        evidence_block = "\n\n".join(
            f"PARAGRAPH {pid}:\n{quote}" for pid, quote in zip(cited_paragraph_ids, cited_quotes)
        )
        history = [
            {"role": "developer", "content": role_prompt(role)},
            {
                "role": "user",
                "content": (
                    f"Verify the cited evidence for attempt {attempt_id}.\n\n"
                    f"{evidence_block}\n\n"
                    "Decide: confirm, partial, reject, or ambiguous. Cite "
                    "verbatim quotes."
                ),
            },
        ]
        loop = ToolLoop(
            client=self._client,
            model=self._config.model,
            tools=tools,
            response_format=role_response_format(role, name_prefix="agent"),
            reasoning_effort=self._reasoning_effort,
            max_turns=self._max_turns,
        )

        started = time.perf_counter()
        result: ToolLoopResult = loop.run(history)
        elapsed = int((time.perf_counter() - started) * 1000)
        self._provider_recorder.record(
            role=role.value,
            model=self._config.model,
            n_input_items=len(history),
            n_tools_offered=len(tool_names),
            reasoning_effort=self._reasoning_effort,
            n_output_items=len(result.history) - len(history),
            final_text_length=len(result.final_text),
            function_call_count=len(result.tool_results),
            latency_ms=elapsed,
        )

        if result.final_output is None:
            # Refuse to fabricate a verdict; mark malformed and let aggregation handle it.
            return VerifierProposal(
                verdict="ambiguous",
                reasoning_summary="verifier produced no final structured output",
                supporting_evidence_paragraph_ids=tuple(cited_paragraph_ids),
                proposed_correction_json=None,
                confidence=0.0,
            )
        verdict = VerifierVerdictModel.model_validate(result.final_output)
        return VerifierProposal(
            verdict=verdict.verdict,
            reasoning_summary=verdict.reasoning_summary,
            supporting_evidence_paragraph_ids=tuple(
                ev.paragraph_id for ev in verdict.supporting_evidence
            ),
            proposed_correction_json=verdict.proposed_correction_json,
            confidence=verdict.confidence,
        )
