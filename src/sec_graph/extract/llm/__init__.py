"""Provider-neutral LLM extraction interface (within-deal narrative windows)."""

from .convert import insert_llm_response
from .models import (
    LinkflowProviderContractError,
    LLMCandidatePayload,
    LLMContractError,
    LLMExtractionResponse,
    LLMProviderConfig,
    LLMWindowRequest,
    PriorActorAlias,
    PriorDealMemory,
    PriorEvent,
    WindowKind,
    WindowParagraph,
)
from .requests import build_llm_windows

__all__ = [
    "LLMCandidatePayload",
    "LLMContractError",
    "LLMExtractionResponse",
    "LLMProviderConfig",
    "LLMWindowRequest",
    "LinkflowProviderContractError",
    "PriorActorAlias",
    "PriorDealMemory",
    "PriorEvent",
    "WindowKind",
    "WindowParagraph",
    "build_llm_windows",
    "insert_llm_response",
]
