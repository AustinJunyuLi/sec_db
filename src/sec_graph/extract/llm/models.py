"""Provider-neutral typed semantic claim contracts."""

from __future__ import annotations

import datetime as dt
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from sec_graph.schema.models.extraction import (
    ActorClass,
    ActorKind,
    ActorObservability,
    ClaimType,
    Confidence,
    CountQualifier,
    EventActorRole,
    EventSubtype,
    EventType,
    ProcessStage,
    RegionKind,
    RelationType,
)

ReasoningEffort = Literal["low", "medium", "high", "xhigh"]
RequestMode = Literal["claim_only_p8_relation_v1"]
DEFAULT_REQUEST_MODE: RequestMode = "claim_only_p8_relation_v1"
FinishStatus = Literal["completed", "provider_rejected", "provider_incomplete", "contract_invalid"]


class LLMContractError(RuntimeError):
    """Raised when provider output violates the local semantic claim contract."""


class LinkflowProviderContractError(LLMContractError):
    """Raised when Linkflow violates the explicit Responses completion policy."""


class WindowParagraph(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    paragraph_id: str
    source_span_id: str
    char_start: int = Field(ge=0)
    char_end: int = Field(ge=0)
    paragraph_text: str


class WindowObligation(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    obligation_id: str
    expected_claim_type: ClaimType
    obligation_label: str
    importance: Literal["required", "important", "optional"]


class LLMWindowRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    request_id: str
    deal_slug: str
    deal_id: str
    filing_id: str
    region_id: str
    window_id: str
    region_kind: RegionKind
    ordered_paragraphs: list[WindowParagraph] = Field(min_length=1)
    coverage_obligations: list[WindowObligation] = Field(min_length=1)
    allowed_claim_types: list[ClaimType] = Field(min_length=1)
    schema_version: int
    extract_version: int
    request_mode: RequestMode


class ClaimAttribution(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    coverage_obligation_id: str = Field(
        min_length=1,
        description="Exact coverage obligation id this claim supports.",
    )


class ActorClaimPayload(ClaimAttribution):
    model_config = ConfigDict(frozen=True, extra="forbid")

    claim_type: Literal["actor"]
    actor_label: str
    actor_kind: ActorKind
    observability: ActorObservability
    confidence: Confidence
    quote_text: str


class EventClaimPayload(ClaimAttribution):
    model_config = ConfigDict(frozen=True, extra="forbid")

    claim_type: Literal["event"]
    event_type: EventType
    event_subtype: EventSubtype
    event_date: dt.date | None
    description: str
    actor_label: str | None
    actor_role: EventActorRole | None
    confidence: Confidence
    quote_text: str


class BidClaimPayload(ClaimAttribution):
    model_config = ConfigDict(frozen=True, extra="forbid")

    claim_type: Literal["bid"]
    bidder_label: str
    bid_date: dt.date | None
    bid_value: float | None
    bid_value_lower: float | None
    bid_value_upper: float | None
    bid_value_unit: str | None
    consideration_type: str | None
    bid_stage: Literal["initial", "revised", "final", "unspecified"]
    confidence: Confidence
    quote_text: str


class ParticipationCountClaimPayload(ClaimAttribution):
    model_config = ConfigDict(frozen=True, extra="forbid")

    claim_type: Literal["participation_count"]
    process_stage: ProcessStage
    actor_class: ActorClass
    count_min: int = Field(ge=0)
    count_max: int | None = Field(default=None, ge=0)
    count_qualifier: CountQualifier
    confidence: Confidence
    quote_text: str


class ActorRelationClaimPayload(ClaimAttribution):
    model_config = ConfigDict(frozen=True, extra="forbid")

    claim_type: Literal["actor_relation"]
    subject_label: str
    object_label: str
    relation_type: RelationType
    role_detail: str | None
    effective_date_first: dt.date | None
    confidence: Confidence
    quote_text: str


class SemanticClaimsPayload(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    actor_claims: list[ActorClaimPayload] = Field(default_factory=list)
    event_claims: list[EventClaimPayload] = Field(default_factory=list)
    bid_claims: list[BidClaimPayload] = Field(default_factory=list)
    participation_count_claims: list[ParticipationCountClaimPayload] = Field(default_factory=list)
    actor_relation_claims: list[ActorRelationClaimPayload] = Field(default_factory=list)


class ProviderUsage(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    input_tokens: int | None = None
    output_tokens: int | None = None
    token_source: Literal["actual", "estimated"] = "estimated"


class LLMExtractionResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    request_id: str
    provider_name: str
    provider_model: str
    reasoning_effort: ReasoningEffort
    payload: SemanticClaimsPayload
    raw_response_sha256: str
    finish_status: FinishStatus
    latency_ms: int | None = None
    attempt_count: int = Field(default=1, ge=1)
    usage: ProviderUsage = Field(default_factory=ProviderUsage)


class LLMProviderConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    provider_name: Literal["linkflow"]
    model: str = "gpt-5.5"
    reasoning_effort: ReasoningEffort = "medium"
    base_url: str = "https://www.linkflow.run/v1"
    api_key_env: str = "LINKFLOW_API_KEY"
    timeout_seconds: int = 3600
