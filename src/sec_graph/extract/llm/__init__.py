"""Provider-neutral LLM extraction interface (within-deal narrative windows)."""

from .convert import insert_llm_response
from .models import (
    LinkflowProviderContractError,
    LLMActorRelationCandidate,
    LLMCandidatePayload,
    LLMContractError,
    LLMExtractionResponse,
    LLMProviderConfig,
    LLMWindowRequest,
    PriorActorAlias,
    PriorDealMemory,
    PriorEvent,
    RelationPredicate,
    WindowKind,
    WindowParagraph,
)
from .requests import build_llm_windows

__all__ = [
    "LLMActorRelationCandidate",
    "LLMCandidatePayload",
    "LLMContractError",
    "LLMExtractionResponse",
    "LLMProviderConfig",
    "LLMWindowRequest",
    "LinkflowProviderContractError",
    "PriorActorAlias",
    "PriorDealMemory",
    "PriorEvent",
    "RelationPredicate",
    "WindowKind",
    "WindowParagraph",
    "build_llm_windows",
    "insert_llm_response",
]
