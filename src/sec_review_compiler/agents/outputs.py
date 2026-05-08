"""Pydantic mirrors of the strict JSON schemas in `llm.schemas`.

Every role has a designated output model. The orchestrator validates
agent JSON through the matching pydantic model before any deal-room
write. Models are frozen+`extra='forbid'` so a stray field from the
provider is caught client-side too.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .roles import AgentRole


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EvidenceCitation(_Base):
    paragraph_id: str
    quote: str


# ---------------------------------------------------------------- Scout

class ScoutRegion(_Base):
    name: str
    paragraph_ids: list[str]
    search_keywords: list[str]
    confidence: Literal["high", "medium", "low"]


class ScoutMap(_Base):
    regions: list[ScoutRegion]


# ---------------------------------------------------------------- Extractor

class ClaimAttemptOutput(_Base):
    claim_type: str
    claim_fingerprint: str
    payload_json: str
    evidence: list[EvidenceCitation] = Field(default_factory=list)


class ExtractorBatchOutput(_Base):
    claims: list[ClaimAttemptOutput]


# ---------------------------------------------------------------- Verifier

class ProposedCorrection(_Base):
    payload_json: str
    rationale: str


class VerifierVerdict(_Base):
    verdict: Literal["confirm", "partial", "reject", "ambiguous"]
    reasoning_summary: str
    supporting_evidence: list[EvidenceCitation]
    proposed_correction_json: str | None
    confidence: float


# ---------------------------------------------------------------- Consistency

class ConsistencyFinding(_Base):
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


class ConsistencyFindings(_Base):
    findings: list[ConsistencyFinding]


# ---------------------------------------------------------------- Omission inspector

class OmissionCoverageProposal(_Base):
    """A coverage ledger record proposed by the omission inspector.

    The model has *no* free-form prose field — only structured coverage
    fields. The orchestrator rejects any payload that does not validate
    here, which prevents free-form speculation from sneaking in via a
    notes string.
    """

    category: str
    subcategory: str | None
    check_state: Literal[
        "checked_found",
        "checked_absent",
        "ambiguous",
        "not_applicable",
        "failed_to_check",
    ]
    required: bool
    evidence_paragraph_id: str | None


class OmissionInspectorOutput(_Base):
    coverage_checks: list[OmissionCoverageProposal]


# ---------------------------------------------------------------- role mapping

ROLE_OUTPUT_MODEL: dict[AgentRole, type[BaseModel]] = {
    AgentRole.SCOUT: ScoutMap,
    AgentRole.PARTY_RELATION_EXTRACTOR: ExtractorBatchOutput,
    AgentRole.TIMELINE_BID_EXTRACTOR: ExtractorBatchOutput,
    AgentRole.COUNT_COVERAGE_EXTRACTOR: ExtractorBatchOutput,
    AgentRole.OMISSION_INSPECTOR: OmissionInspectorOutput,
    AgentRole.VERIFIER: VerifierVerdict,
    AgentRole.CONSISTENCY_CHECKER: ConsistencyFindings,
}


def role_output_model(role: AgentRole) -> type[BaseModel]:
    return ROLE_OUTPUT_MODEL[role]
