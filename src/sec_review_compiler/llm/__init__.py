"""Linkflow adapter, strict schemas, and the agent tool loop.

This package is the only place compiler agents touch the model boundary.
All Linkflow calls go through `LinkflowClientConfig` + the explicit
`ToolLoop`; agents never construct OpenAI/Linkflow clients directly.
"""

from .linkflow import (
    DEFAULT_BASE_URL,
    DEFAULT_MAX_CONCURRENCY,
    DEFAULT_MODEL,
    DEFAULT_REASONING_EFFORT,
    SUPPORTED_REASONING_EFFORTS,
    LinkflowClientConfig,
    build_responses_client,
)
from .schemas import (
    consistency_finding_schema,
    extractor_claim_schema,
    scout_region_map_schema,
    strict_response_format,
    verifier_verdict_schema,
)
from .tool_loop import (
    FakeLinkflowResponse,
    FakeResponsesClient,
    ToolDefinition,
    ToolLoop,
    ToolLoopResult,
    ToolRegistry,
)

__all__ = [
    "DEFAULT_BASE_URL",
    "DEFAULT_MAX_CONCURRENCY",
    "DEFAULT_MODEL",
    "DEFAULT_REASONING_EFFORT",
    "FakeLinkflowResponse",
    "FakeResponsesClient",
    "LinkflowClientConfig",
    "SUPPORTED_REASONING_EFFORTS",
    "ToolDefinition",
    "ToolLoop",
    "ToolLoopResult",
    "ToolRegistry",
    "build_responses_client",
    "consistency_finding_schema",
    "extractor_claim_schema",
    "scout_region_map_schema",
    "strict_response_format",
    "verifier_verdict_schema",
]
