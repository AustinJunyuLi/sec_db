"""Pydantic mirrors of the strict JSON schemas in `llm.schemas`.

Linkflow returns the structured payload as a JSON string; the
orchestrator parses it through these models for client-side validation
before committing anything to the deal-room. The models share the same
`extra="forbid"` discipline as the API-side strict schemas.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class EvidenceCitation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    paragraph_id: str
    quote: str


class ScoutRegion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    paragraph_ids: list[str]
    search_keywords: list[str]
    confidence: Literal["high", "medium", "low"]


class ScoutMap(BaseModel):
    model_config = ConfigDict(extra="forbid")

    regions: list[ScoutRegion]


class ClaimAttemptOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claim_type: str
    claim_fingerprint: str
    payload_json: str
    evidence: list[EvidenceCitation] = Field(default_factory=list)


class ProposedCorrection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    payload_json: str
    rationale: str


class VerifierVerdict(BaseModel):
    model_config = ConfigDict(extra="forbid")

    verdict: Literal["confirm", "partial", "reject", "ambiguous"]
    reasoning_summary: str
    supporting_evidence: list[EvidenceCitation]
    proposed_correction_json: str | None
    confidence: float


class ConsistencyFinding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    finding_type: Literal[
        "contradictory_dates",
        "incompatible_bids",
        "actor_identity_mismatch",
        "duplicate_claim",
        "graph_invariant",
    ]
    attempt_ids: list[str]
    description: str
    severity: Literal["info", "warning", "blocking"]
