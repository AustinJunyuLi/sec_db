"""Deployable canonical models and DDL."""

from __future__ import annotations

import datetime as dt
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

ActorKind = Literal["organization", "person", "group", "vehicle", "cohort", "committee"]
ActorObservability = Literal["named", "anonymous_handle", "count_only"]
RelationType = Literal[
    "member_of",
    "affiliate_of",
    "controls",
    "acquisition_vehicle_of",
    "advises",
    "finances",
    "supports",
    "rollover_holder_of",
]
Confidence = Literal["low", "medium", "high"]
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


class Deal(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    deal_id: str
    run_id: str
    deal_slug: str
    target_actor_id: str
    announcement_date: dt.date | None
    evidence_ids: list[str]


class ProcessCycle(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    cycle_id: str
    run_id: str
    deal_id: str
    cycle_sequence: int = Field(ge=1)
    cycle_label: str
    start_date: dt.date | None
    end_date: dt.date | None
    evidence_ids: list[str]


class Actor(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    actor_id: str
    run_id: str
    deal_id: str
    actor_label: str
    actor_kind: ActorKind
    observability: ActorObservability
    evidence_ids: list[str]
    lead_arranger_label: str | None
    member_count_known: int | None = Field(default=None, ge=0)
    has_strategic_member: bool | None
    has_sovereign_wealth_member: bool | None

    @model_validator(mode="after")
    def _group_only_fields_are_group_only(self) -> "Actor":
        if self.actor_kind == "group":
            return self
        group_values = (
            self.lead_arranger_label,
            self.member_count_known,
            self.has_strategic_member,
            self.has_sovereign_wealth_member,
        )
        if any(value is not None for value in group_values):
            raise ValueError("group-only actor fields require actor_kind='group'")
        return self


class ActorRelation(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    relation_id: str
    run_id: str
    deal_id: str
    subject_actor_id: str
    object_actor_id: str
    relation_type: RelationType
    role_detail: str | None
    cycle_id_first_observed: str | None
    cycle_id_last_observed: str | None
    effective_date_first: dt.date | None
    effective_date_last: dt.date | None
    confidence: Confidence | None
    evidence_ids: list[str]

    @model_validator(mode="after")
    def _temporal_frame_is_present(self) -> "ActorRelation":
        if self.cycle_id_first_observed is None and self.effective_date_first is None:
            raise ValueError("actor relation needs cycle_id_first_observed or effective_date_first")
        if (
            self.effective_date_last is not None
            and self.effective_date_first is not None
            and self.effective_date_last < self.effective_date_first
        ):
            raise ValueError("effective_date_last must be on or after effective_date_first")
        return self


class Event(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    event_id: str
    run_id: str
    deal_id: str
    cycle_id: str
    event_type: EventType
    event_subtype: EventSubtype
    event_date: dt.date | None
    description: str
    bid_value: float | None
    bid_value_lower: float | None
    bid_value_upper: float | None
    bid_value_unit: str | None
    consideration_type: str | None
    evidence_ids: list[str]


class EventActorLink(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    link_id: str
    run_id: str
    event_id: str
    actor_id: str
    role: EventActorRole
    role_detail: str | None
    evidence_ids: list[str]


CANONICAL_DDL = """
CREATE TABLE deals (
  deal_id VARCHAR PRIMARY KEY,
  run_id VARCHAR NOT NULL,
  deal_slug VARCHAR NOT NULL,
  target_actor_id VARCHAR NOT NULL,
  announcement_date DATE,
  evidence_ids VARCHAR[] NOT NULL
);

CREATE TABLE actors (
  actor_id VARCHAR PRIMARY KEY,
  run_id VARCHAR NOT NULL,
  deal_id VARCHAR NOT NULL,
  actor_label VARCHAR NOT NULL,
  actor_kind VARCHAR NOT NULL CHECK (actor_kind IN ('organization', 'person', 'group', 'vehicle', 'cohort', 'committee')),
  observability VARCHAR NOT NULL CHECK (observability IN ('named', 'anonymous_handle', 'count_only')),
  evidence_ids VARCHAR[] NOT NULL,
  lead_arranger_label VARCHAR,
  member_count_known INTEGER,
  has_strategic_member BOOLEAN,
  has_sovereign_wealth_member BOOLEAN,
  CHECK (member_count_known IS NULL OR member_count_known >= 0),
  CHECK (
    actor_kind = 'group'
    OR (
      lead_arranger_label IS NULL
      AND member_count_known IS NULL
      AND has_strategic_member IS NULL
      AND has_sovereign_wealth_member IS NULL
    )
  ),
  FOREIGN KEY (deal_id) REFERENCES deals(deal_id)
);

CREATE TABLE process_cycles (
  cycle_id VARCHAR PRIMARY KEY,
  run_id VARCHAR NOT NULL,
  deal_id VARCHAR NOT NULL,
  cycle_sequence INTEGER NOT NULL,
  cycle_label VARCHAR NOT NULL,
  start_date DATE,
  end_date DATE,
  evidence_ids VARCHAR[] NOT NULL,
  CHECK (cycle_sequence >= 1),
  CHECK (end_date IS NULL OR start_date IS NULL OR end_date >= start_date),
  FOREIGN KEY (deal_id) REFERENCES deals(deal_id)
);

CREATE TABLE actor_relations (
  relation_id VARCHAR PRIMARY KEY,
  run_id VARCHAR NOT NULL,
  deal_id VARCHAR NOT NULL,
  subject_actor_id VARCHAR NOT NULL,
  object_actor_id VARCHAR NOT NULL,
  relation_type VARCHAR NOT NULL CHECK (relation_type IN ('member_of', 'affiliate_of', 'controls', 'acquisition_vehicle_of', 'advises', 'finances', 'supports', 'rollover_holder_of')),
  role_detail VARCHAR,
  cycle_id_first_observed VARCHAR,
  cycle_id_last_observed VARCHAR,
  effective_date_first DATE,
  effective_date_last DATE,
  confidence VARCHAR CHECK (confidence IS NULL OR confidence IN ('low', 'medium', 'high')),
  evidence_ids VARCHAR[] NOT NULL,
  CHECK (cycle_id_first_observed IS NOT NULL OR effective_date_first IS NOT NULL),
  CHECK (effective_date_last IS NULL OR effective_date_first IS NULL OR effective_date_last >= effective_date_first),
  FOREIGN KEY (deal_id) REFERENCES deals(deal_id),
  FOREIGN KEY (subject_actor_id) REFERENCES actors(actor_id),
  FOREIGN KEY (object_actor_id) REFERENCES actors(actor_id),
  FOREIGN KEY (cycle_id_first_observed) REFERENCES process_cycles(cycle_id),
  FOREIGN KEY (cycle_id_last_observed) REFERENCES process_cycles(cycle_id)
);

CREATE TABLE events (
  event_id VARCHAR PRIMARY KEY,
  run_id VARCHAR NOT NULL,
  deal_id VARCHAR NOT NULL,
  cycle_id VARCHAR NOT NULL,
  event_type VARCHAR NOT NULL CHECK (event_type IN ('process', 'bid', 'transaction')),
  event_subtype VARCHAR NOT NULL CHECK (event_subtype IN ('contact_initial', 'nda_signed', 'ioi_submitted', 'first_round_bid', 'final_round_bid', 'exclusivity_grant', 'merger_agreement_executed', 'withdrawn_by_bidder', 'excluded_by_target', 'non_responsive', 'cohort_closure', 'advancement_admitted', 'advancement_declined', 'rollover_executed', 'financing_committed')),
  event_date DATE,
  description VARCHAR NOT NULL,
  bid_value DOUBLE,
  bid_value_lower DOUBLE,
  bid_value_upper DOUBLE,
  bid_value_unit VARCHAR,
  consideration_type VARCHAR,
  evidence_ids VARCHAR[] NOT NULL,
  CHECK (bid_value_upper IS NULL OR bid_value_lower IS NULL OR bid_value_upper >= bid_value_lower),
  FOREIGN KEY (deal_id) REFERENCES deals(deal_id),
  FOREIGN KEY (cycle_id) REFERENCES process_cycles(cycle_id)
);

CREATE TABLE event_actor_links (
  link_id VARCHAR PRIMARY KEY,
  run_id VARCHAR NOT NULL,
  event_id VARCHAR NOT NULL,
  actor_id VARCHAR NOT NULL,
  role VARCHAR NOT NULL CHECK (role IN ('target', 'bid_submitter', 'potential_buyer', 'group_vehicle', 'group_member', 'advisor_for_target', 'advisor_for_bidder', 'equity_financing_source', 'debt_financing_source', 'support_shareholder', 'rollover_holder', 'offeror', 'acquisition_sub', 'sender', 'recipient')),
  role_detail VARCHAR,
  evidence_ids VARCHAR[] NOT NULL,
  FOREIGN KEY (event_id) REFERENCES events(event_id),
  FOREIGN KEY (actor_id) REFERENCES actors(actor_id)
);
"""
