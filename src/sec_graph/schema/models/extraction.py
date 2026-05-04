"""Hard-reset extraction claims, evidence-map, and coverage schema."""

from __future__ import annotations

import datetime as dt
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Confidence = Literal["low", "medium", "high"]
ClaimType = Literal["actor", "event", "bid", "participation_count", "actor_relation"]
ClaimStage = Literal["linkflow", "rules"]
ClaimStatus = Literal["validated", "rejected", "disposed"]
Disposition = Literal[
    "canonicalized",
    "merged_duplicate",
    "rejected",
    "queued_ambiguity",
    "out_of_scope",
]
RegionKind = Literal[
    "sale_process_narrative",
    "bid_proposal_sequence",
    "participation_counts",
    "buyer_group_transaction_structure",
    "financing",
    "support_agreement",
    "rollover",
    "advisor_or_committee",
    "go_shop_or_amendment",
    "ambiguous_sale_process_material",
]
CoverageResultKind = Literal["claims_emitted", "no_supported_claim", "ambiguous", "missed"]
RelationType = Literal[
    "member_of",
    "affiliate_of",
    "controls",
    "acquisition_vehicle_of",
    "advises",
    "finances",
    "supports",
    "voting_support_for",
    "rollover_holder_for",
    "committee_member_of",
    "recused_from",
]
ActorKind = Literal["organization", "person", "group", "vehicle", "cohort", "committee"]
ActorObservability = Literal["named", "anonymous_handle", "count_only"]
EventType = Literal["process", "bid", "transaction"]
EventSubtype = Literal[
    "contact_initial",
    "nda_signed",
    "ioi_submitted",
    "first_round_bid",
    "final_round_bid",
    "exclusivity_grant",
    "merger_agreement_executed",
    "withdrawn_by_bidder",
    "excluded_by_target",
    "non_responsive",
    "cohort_closure",
    "advancement_admitted",
    "advancement_declined",
    "rollover_executed",
    "financing_committed",
]
EventActorRole = Literal[
    "target",
    "bid_submitter",
    "potential_buyer",
    "group_vehicle",
    "group_member",
    "advisor_for_target",
    "advisor_for_bidder",
    "equity_financing_source",
    "debt_financing_source",
    "support_shareholder",
    "rollover_holder",
    "offeror",
    "acquisition_sub",
    "sender",
    "recipient",
]
ProcessStage = Literal["contacted", "nda_signed", "ioi_submitted", "first_round", "final_round", "exclusivity"]
ActorClass = Literal["financial", "strategic", "mixed"]
CountQualifier = Literal["exact", "approximate", "lower_bound", "upper_bound", "range"]


class EvidenceRegion(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    region_id: str
    run_id: str
    filing_id: str
    deal_slug: str
    region_kind: RegionKind
    priority: int = Field(ge=1)
    start_paragraph_id: str
    end_paragraph_id: str
    paragraph_ids_json: str
    trigger_phrases_json: str
    expected_claim_types_json: str


Applicability = Literal["applicable", "not_applicable"]


class CoverageObligation(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    obligation_id: str
    run_id: str
    region_id: str
    filing_id: str
    deal_slug: str
    expected_claim_type: ClaimType
    obligation_kind: str
    obligation_label: str
    importance: Literal["required", "important", "optional"]
    applicability: Applicability
    applicability_reason_code: str
    applicability_basis_json: str
    current: bool = True


class CoverageResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    coverage_result_id: str
    run_id: str
    obligation_id: str
    result: CoverageResultKind
    reason_code: str
    reason: str
    claim_count: int = Field(ge=0)
    current: bool = True


class Claim(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    claim_id: str
    run_id: str
    filing_id: str
    deal_slug: str
    region_id: str
    provider_source_stage: ClaimStage
    claim_type: ClaimType
    confidence: Confidence
    raw_value: str
    normalized_value: str | None
    quote_text: str
    quote_text_hash: str
    status: ClaimStatus
    claim_sequence: int = Field(ge=1)


class ClaimCoverageLink(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    claim_id: str
    obligation_id: str
    run_id: str
    deal_slug: str
    claim_type: ClaimType
    current: bool = True


class ActorClaim(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    claim_id: str
    actor_label: str
    actor_kind: ActorKind
    observability: ActorObservability


class EventClaim(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    claim_id: str
    event_type: EventType
    event_subtype: EventSubtype
    event_date: dt.date | None
    description: str
    actor_label: str | None
    actor_role: EventActorRole | None


class BidClaim(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    claim_id: str
    bidder_label: str
    bid_date: dt.date | None
    bid_value: float | None
    bid_value_lower: float | None
    bid_value_upper: float | None
    bid_value_unit: str | None
    consideration_type: str | None
    bid_stage: Literal["initial", "revised", "final", "unspecified"]


class ParticipationCountClaim(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    claim_id: str
    process_stage: ProcessStage
    actor_class: ActorClass
    count_min: int = Field(ge=0)
    count_max: int | None = Field(default=None, ge=0)
    count_qualifier: CountQualifier


class ActorRelationClaim(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    claim_id: str
    subject_label: str
    object_label: str
    relation_type: RelationType
    role_detail: str | None
    effective_date_first: dt.date | None


class ClaimDisposition(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    disposition_id: str
    claim_id: str
    run_id: str
    disposition: Disposition
    reason_code: str
    reason: str
    canonical_table: str | None
    canonical_id: str | None
    surviving_claim_id: str | None
    created_stage: str
    current: bool = True


EXTRACTION_DDL = """
CREATE TABLE evidence_regions (
  region_id VARCHAR PRIMARY KEY,
  run_id VARCHAR NOT NULL,
  filing_id VARCHAR NOT NULL,
  deal_slug VARCHAR NOT NULL,
  region_kind VARCHAR NOT NULL CHECK (region_kind IN ('sale_process_narrative', 'bid_proposal_sequence', 'participation_counts', 'buyer_group_transaction_structure', 'financing', 'support_agreement', 'rollover', 'advisor_or_committee', 'go_shop_or_amendment', 'ambiguous_sale_process_material')),
  priority INTEGER NOT NULL,
  start_paragraph_id VARCHAR NOT NULL,
  end_paragraph_id VARCHAR NOT NULL,
  paragraph_ids_json VARCHAR NOT NULL,
  trigger_phrases_json VARCHAR NOT NULL,
  expected_claim_types_json VARCHAR NOT NULL,
  CHECK (priority >= 1),
  FOREIGN KEY (filing_id) REFERENCES filings(filing_id),
  FOREIGN KEY (start_paragraph_id) REFERENCES paragraphs(paragraph_id),
  FOREIGN KEY (end_paragraph_id) REFERENCES paragraphs(paragraph_id)
);

CREATE TABLE coverage_obligations (
  obligation_id VARCHAR PRIMARY KEY,
  run_id VARCHAR NOT NULL,
  region_id VARCHAR NOT NULL,
  filing_id VARCHAR NOT NULL,
  deal_slug VARCHAR NOT NULL,
  expected_claim_type VARCHAR NOT NULL CHECK (expected_claim_type IN ('actor', 'event', 'bid', 'participation_count', 'actor_relation')),
  obligation_kind VARCHAR NOT NULL,
  obligation_label VARCHAR NOT NULL,
  importance VARCHAR NOT NULL CHECK (importance IN ('required', 'important', 'optional')),
  applicability VARCHAR NOT NULL CHECK (applicability IN ('applicable', 'not_applicable')),
  applicability_reason_code VARCHAR NOT NULL,
  applicability_basis_json VARCHAR NOT NULL,
  current BOOLEAN NOT NULL,
  FOREIGN KEY (region_id) REFERENCES evidence_regions(region_id),
  FOREIGN KEY (filing_id) REFERENCES filings(filing_id)
);

CREATE TABLE coverage_results (
  coverage_result_id VARCHAR PRIMARY KEY,
  run_id VARCHAR NOT NULL,
  obligation_id VARCHAR NOT NULL,
  result VARCHAR NOT NULL CHECK (result IN ('claims_emitted', 'no_supported_claim', 'ambiguous', 'missed')),
  reason_code VARCHAR NOT NULL,
  reason VARCHAR NOT NULL,
  claim_count INTEGER NOT NULL,
  current BOOLEAN NOT NULL,
  CHECK (claim_count >= 0),
  FOREIGN KEY (obligation_id) REFERENCES coverage_obligations(obligation_id)
);

CREATE TABLE claims (
  claim_id VARCHAR PRIMARY KEY,
  run_id VARCHAR NOT NULL,
  filing_id VARCHAR NOT NULL,
  deal_slug VARCHAR NOT NULL,
  region_id VARCHAR NOT NULL,
  provider_source_stage VARCHAR NOT NULL CHECK (provider_source_stage IN ('linkflow', 'rules')),
  claim_type VARCHAR NOT NULL CHECK (claim_type IN ('actor', 'event', 'bid', 'participation_count', 'actor_relation')),
  confidence VARCHAR NOT NULL CHECK (confidence IN ('low', 'medium', 'high')),
  raw_value VARCHAR NOT NULL,
  normalized_value VARCHAR,
  quote_text VARCHAR NOT NULL,
  quote_text_hash VARCHAR NOT NULL,
  status VARCHAR NOT NULL CHECK (status IN ('validated', 'rejected', 'disposed')),
  claim_sequence INTEGER NOT NULL,
  CHECK (claim_sequence >= 1),
  FOREIGN KEY (filing_id) REFERENCES filings(filing_id),
  FOREIGN KEY (region_id) REFERENCES evidence_regions(region_id)
);

CREATE TABLE claim_coverage_links (
  claim_id VARCHAR PRIMARY KEY,
  obligation_id VARCHAR NOT NULL,
  run_id VARCHAR NOT NULL,
  deal_slug VARCHAR NOT NULL,
  claim_type VARCHAR NOT NULL CHECK (claim_type IN ('actor', 'event', 'bid', 'participation_count', 'actor_relation')),
  current BOOLEAN NOT NULL,
  FOREIGN KEY (claim_id) REFERENCES claims(claim_id),
  FOREIGN KEY (obligation_id) REFERENCES coverage_obligations(obligation_id)
);

CREATE TABLE actor_claims (
  claim_id VARCHAR PRIMARY KEY,
  actor_label VARCHAR NOT NULL,
  actor_kind VARCHAR NOT NULL CHECK (actor_kind IN ('organization', 'person', 'group', 'vehicle', 'cohort', 'committee')),
  observability VARCHAR NOT NULL CHECK (observability IN ('named', 'anonymous_handle', 'count_only')),
  FOREIGN KEY (claim_id) REFERENCES claims(claim_id)
);

CREATE TABLE event_claims (
  claim_id VARCHAR PRIMARY KEY,
  event_type VARCHAR NOT NULL CHECK (event_type IN ('process', 'bid', 'transaction')),
  event_subtype VARCHAR NOT NULL CHECK (event_subtype IN ('contact_initial', 'nda_signed', 'ioi_submitted', 'first_round_bid', 'final_round_bid', 'exclusivity_grant', 'merger_agreement_executed', 'withdrawn_by_bidder', 'excluded_by_target', 'non_responsive', 'cohort_closure', 'advancement_admitted', 'advancement_declined', 'rollover_executed', 'financing_committed')),
  event_date DATE,
  description VARCHAR NOT NULL,
  actor_label VARCHAR,
  actor_role VARCHAR CHECK (actor_role IS NULL OR actor_role IN ('target', 'bid_submitter', 'potential_buyer', 'group_vehicle', 'group_member', 'advisor_for_target', 'advisor_for_bidder', 'equity_financing_source', 'debt_financing_source', 'support_shareholder', 'rollover_holder', 'offeror', 'acquisition_sub', 'sender', 'recipient')),
  FOREIGN KEY (claim_id) REFERENCES claims(claim_id)
);

CREATE TABLE bid_claims (
  claim_id VARCHAR PRIMARY KEY,
  bidder_label VARCHAR NOT NULL,
  bid_date DATE,
  bid_value DOUBLE,
  bid_value_lower DOUBLE,
  bid_value_upper DOUBLE,
  bid_value_unit VARCHAR,
  consideration_type VARCHAR,
  bid_stage VARCHAR NOT NULL CHECK (bid_stage IN ('initial', 'revised', 'final', 'unspecified')),
  CHECK (bid_value_upper IS NULL OR bid_value_lower IS NULL OR bid_value_upper >= bid_value_lower),
  FOREIGN KEY (claim_id) REFERENCES claims(claim_id)
);

CREATE TABLE participation_count_claims (
  claim_id VARCHAR PRIMARY KEY,
  process_stage VARCHAR NOT NULL CHECK (process_stage IN ('contacted', 'nda_signed', 'ioi_submitted', 'first_round', 'final_round', 'exclusivity')),
  actor_class VARCHAR NOT NULL CHECK (actor_class IN ('financial', 'strategic', 'mixed')),
  count_min INTEGER NOT NULL,
  count_max INTEGER,
  count_qualifier VARCHAR NOT NULL CHECK (count_qualifier IN ('exact', 'approximate', 'lower_bound', 'upper_bound', 'range')),
  CHECK (count_min >= 0),
  CHECK (count_max IS NULL OR count_max >= count_min),
  FOREIGN KEY (claim_id) REFERENCES claims(claim_id)
);

CREATE TABLE actor_relation_claims (
  claim_id VARCHAR PRIMARY KEY,
  subject_label VARCHAR NOT NULL,
  object_label VARCHAR NOT NULL,
  relation_type VARCHAR NOT NULL CHECK (relation_type IN ('member_of', 'affiliate_of', 'controls', 'acquisition_vehicle_of', 'advises', 'finances', 'supports', 'voting_support_for', 'rollover_holder_for', 'committee_member_of', 'recused_from')),
  role_detail VARCHAR,
  effective_date_first DATE,
  FOREIGN KEY (claim_id) REFERENCES claims(claim_id)
);

CREATE TABLE claim_evidence (
  claim_id VARCHAR NOT NULL,
  evidence_id VARCHAR NOT NULL,
  ordinal INTEGER NOT NULL,
  PRIMARY KEY (claim_id, evidence_id, ordinal),
  CHECK (ordinal >= 1),
  FOREIGN KEY (claim_id) REFERENCES claims(claim_id),
  FOREIGN KEY (evidence_id) REFERENCES spans(evidence_id)
);

CREATE TABLE claim_dispositions (
  disposition_id VARCHAR PRIMARY KEY,
  claim_id VARCHAR NOT NULL,
  run_id VARCHAR NOT NULL,
  disposition VARCHAR NOT NULL CHECK (disposition IN ('canonicalized', 'merged_duplicate', 'rejected', 'queued_ambiguity', 'out_of_scope')),
  reason_code VARCHAR NOT NULL,
  reason VARCHAR NOT NULL,
  canonical_table VARCHAR,
  canonical_id VARCHAR,
  surviving_claim_id VARCHAR,
  created_stage VARCHAR NOT NULL,
  current BOOLEAN NOT NULL,
  FOREIGN KEY (claim_id) REFERENCES claims(claim_id),
  FOREIGN KEY (surviving_claim_id) REFERENCES claims(claim_id)
);
"""
