"""Provider-neutral LLM extraction contracts.

Within-deal narrative window contract:
- requests are LLMWindowRequest payloads (ordered paragraphs from one filing);
- candidates emit quote_text only — Python owns char_start/char_end resolution;
- actor_relation candidates use the typed LLMActorRelationCandidate payload,
  not JSON-in-string smuggled through the flat candidate type.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# Flat candidate types deliberately exclude actor_relation. Relations use the
# typed LLMActorRelationCandidate payload below.
CandidateType = Literal[
    "actor_mention",
    "dated_event",
    "bid_value",
    "participation_count",
]
Confidence = Literal["low", "medium", "high"]
FinishStatus = Literal[
    "completed",
    "provider_rejected",
    "provider_incomplete",
    "contract_invalid",
]
ReasoningEffort = Literal["low", "medium", "high", "xhigh"]
WindowKind = Literal[
    "narrative_arc",
    "process_step_cluster",
    "actor_introduction",
]
ExtractionTask = Literal[
    "actor_aliases",
    "events",
    "participation_counts",
    "actor_relations",
]
RelationPredicate = Literal[
    "member_of",
    "affiliate_of",
    "controls",
    "acquisition_vehicle_of",
    "advises",
    "finances",
    "supports",
    "rollover_holder_of",
]


class LLMContractError(RuntimeError):
    """Raised when provider output violates the local candidate contract."""


class LinkflowProviderContractError(LLMContractError):
    """Raised when the Linkflow stream violates the provider completion policy.

    Distinct subclass so callers can react to provider-side contract failures
    (e.g., missing response.completed) separately from local payload contract
    violations, while still being caught by handlers that match LLMContractError.
    """


class WindowParagraph(BaseModel):
    """One ordered paragraph reference inside a within-deal window."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    paragraph_id: str
    source_span_id: str  # the paragraph_seed evidence_id
    char_start: int = Field(ge=0)
    char_end: int = Field(ge=0)
    paragraph_text: str


class PriorActorAlias(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    alias: str
    canonical_label: str
    source_paragraph_id: str


class PriorEvent(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    event_kind: str
    normalized_value: str  # e.g. ISO date or short phrase
    quote_text: str
    source_paragraph_id: str


class ActiveCycleCandidate(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    cycle_label: str
    source_paragraph_id: str


class UnresolvedReference(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    reference_text: str
    source_paragraph_id: str


class PriorDealMemory(BaseModel):
    """Compact within-filing memory carried into a window prompt.

    All entries are derived by Python from earlier paragraphs in the SAME
    filing. No cross-deal content. Empty lists are valid.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    actor_aliases: list[PriorActorAlias] = Field(default_factory=list)
    prior_events: list[PriorEvent] = Field(default_factory=list)
    active_cycle_candidates: list[ActiveCycleCandidate] = Field(default_factory=list)
    unresolved_references: list[UnresolvedReference] = Field(default_factory=list)


class LLMWindowRequest(BaseModel):
    """A within-deal narrative window request to the LLM extractor.

    Construction strategy: deterministic ordered-paragraph stride within one
    filing (see requests.build_llm_windows). No cross-deal content.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    request_id: str  # deterministic {slug}_llmrequest_{sequence}
    deal_id: str
    filing_id: str
    window_id: str  # deterministic {slug}_window_{sequence}
    window_kind: WindowKind
    ordered_paragraphs: list[WindowParagraph] = Field(min_length=1)
    prior_deal_memory: PriorDealMemory
    extraction_tasks: list[ExtractionTask] = Field(min_length=1)
    allowed_candidate_types: list[CandidateType] = Field(default_factory=list)
    schema_version: int
    extract_version: int


class LLMCandidatePayload(BaseModel):
    """Flat candidate payload. Used for actor_mention, dated_event, bid_value,
    participation_count. Relations use LLMActorRelationCandidate."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    candidate_type: CandidateType
    raw_value: str
    normalized_value: str
    confidence: Confidence
    quote_text: str
    dependencies: list[str]


class LLMActorRelationCandidate(BaseModel):
    """Typed first-class relation candidate payload.

    JSON-in-string smuggling through the flat candidate payload is forbidden.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    subject_actor_ref: str
    predicate: RelationPredicate
    object_actor_ref: str
    evidence_quote: str
    confidence: Confidence
    role_detail: str | None = None
    effective_date_first: str | None = None
    dependencies: list[str] = Field(default_factory=list)


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
    timeout_seconds: int = 240
