"""Linkflow-driven extractor for the live vertical slice.

Wires the TIMELINE_BID_EXTRACTOR role: prompt + extractor_batch schema +
read tool surface. Returns the extracted claims as `ExtractedClaim`
records the orchestrator already understands.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass

from ..agents.outputs import ExtractorBatchOutput
from ..agents.prompts import role_prompt
from ..agents.roles import AgentRole
from ..agents.tool_surface import tools_for_role
from ..filing.package import FilingPackage
from ..llm.linkflow import LinkflowClientConfig
from ..llm.schemas import role_response_format
from ..llm.tool_loop import ToolLoop, ToolLoopResult, ToolRegistry
from ..retrieval.index import RetrievalIndex
from .recorders import ProviderCallRecorder, ToolCallRecorder
from .tool_handlers import build_tool_definitions


@dataclass(frozen=True, slots=True)
class LiveExtractorConfig:
    role: AgentRole = AgentRole.TIMELINE_BID_EXTRACTOR
    max_turns: int = 16
    reasoning_effort: str = "low"


class LiveLinkflowExtractor:
    """Use Linkflow + the timeline-bid extractor role to propose claims."""

    def __init__(
        self,
        *,
        client,
        config: LinkflowClientConfig,
        provider_recorder: ProviderCallRecorder,
        tool_recorder: ToolCallRecorder,
        extractor_config: LiveExtractorConfig | None = None,
    ) -> None:
        self._client = client
        self._config = config
        self._provider_recorder = provider_recorder
        self._tool_recorder = tool_recorder
        self._extractor_config = extractor_config or LiveExtractorConfig()

    def extract(
        self,
        *,
        package: FilingPackage,
        index: RetrievalIndex,
    ):
        from .orchestrator import ExtractedClaim  # local import — avoid cycle

        role = self._extractor_config.role
        tool_names = sorted(tools_for_role(role))
        tools = ToolRegistry(
            build_tool_definitions(
                role=role,
                tool_names=tool_names,
                index=index,
                recorder=self._tool_recorder,
            )
        )

        history = [
            {"role": "developer", "content": role_prompt(role)},
            {
                "role": "user",
                "content": (
                    f"Filing {package.filing_id} ({package.filing_type}) has "
                    f"{len(package.paragraphs)} paragraphs. Identify timeline "
                    "events: NDAs, indications of interest, proposals, final "
                    "bids, withdrawals. Cite verbatim quotes only."
                ),
            },
        ]
        loop = ToolLoop(
            client=self._client,
            model=self._config.model,
            tools=tools,
            response_format=role_response_format(role, name_prefix="agent"),
            reasoning_effort=self._extractor_config.reasoning_effort,
            max_turns=self._extractor_config.max_turns,
        )

        started = time.perf_counter()
        result: ToolLoopResult = loop.run(history)
        elapsed = int((time.perf_counter() - started) * 1000)
        self._provider_recorder.record(
            role=role.value,
            model=self._config.model,
            n_input_items=len(history),
            n_tools_offered=len(tool_names),
            reasoning_effort=self._extractor_config.reasoning_effort,
            n_output_items=len(result.history) - len(history),
            final_text_length=len(result.final_text),
            function_call_count=len(result.tool_results),
            latency_ms=elapsed,
        )

        if result.final_output is None:
            return []
        parsed = ExtractorBatchOutput.model_validate(result.final_output)
        claims: list = []
        for claim in parsed.claims:
            cited_quotes = tuple(c.quote for c in claim.evidence)
            cited_paragraph_ids = tuple(c.paragraph_id for c in claim.evidence)
            if not cited_quotes:
                # Refuse uncited claims — agents must propose with evidence.
                continue
            claims.append(
                ExtractedClaim(
                    claim_type=claim.claim_type,
                    claim_fingerprint=claim.claim_fingerprint,
                    payload_json=claim.payload_json,
                    cited_quotes=cited_quotes,
                    cited_paragraph_ids=cited_paragraph_ids,
                )
            )
        return claims
