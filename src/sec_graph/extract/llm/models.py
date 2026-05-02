"""Provider-neutral LLM extraction contracts."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

CandidateType = Literal["actor_mention", "dated_event", "bid_value", "participation_count"]
Confidence = Literal["low", "medium", "high"]
FinishStatus = Literal["completed", "provider_rejected", "provider_incomplete", "contract_invalid"]
ReasoningEffort = Literal["low", "medium", "high", "xhigh"]


class LLMContractError(RuntimeError):
    """Raised when provider output violates the local candidate contract."""


class LLMExtractionRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    request_id: str
    filing_id: str
    deal_slug: str
    paragraph_id: str
    parent_evidence_id: str
    section: str
    paragraph_text: str
    char_start: int
    char_end: int
    allowed_candidate_types: list[CandidateType] = Field(default_factory=list)
    schema_version: int
    extract_version: int


class LLMCandidatePayload(BaseModel):
    model_config = ConfigDict(frozen=True)

    candidate_type: CandidateType
    raw_value: str
    normalized_value: str
    confidence: Confidence
    quote_text: str
    quote_start: int
    quote_end: int
    dependencies: list[str]


class LLMExtractionResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    request_id: str
    provider_name: str
    provider_model: str
    reasoning_effort: ReasoningEffort
    candidates: list[LLMCandidatePayload]
    raw_response_sha256: str
    finish_status: FinishStatus


class LLMProviderConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    provider_name: Literal["linkflow"]
    model: str
    reasoning_effort: ReasoningEffort
    base_url: str = "https://www.linkflow.run/v1"
    api_key_env: str = "LINKFLOW_API_KEY"
    timeout_seconds: int = 120
