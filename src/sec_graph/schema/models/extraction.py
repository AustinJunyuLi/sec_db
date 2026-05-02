"""Extraction candidate model and DDL."""

from __future__ import annotations

import datetime as dt
from typing import Literal

from pydantic import BaseModel, ConfigDict


class ExtractionCandidate(BaseModel):
    model_config = ConfigDict(frozen=True)

    candidate_id: str
    run_id: str
    filing_id: str
    candidate_type: Literal["actor_mention", "dated_event", "bid_value", "participation_count", "actor_relation"]
    raw_value: str
    normalized_value: str
    confidence: Literal["low", "medium", "high"]
    evidence_ids: list[str]
    dependencies: list[str]
    status: Literal["active", "rejected"]


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


class RelationCandidate(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    candidate_id: str
    subject_label: str
    object_label: str
    relation_type: RelationType
    role_detail: str | None
    effective_date_first: dt.date | None


EXTRACTION_DDL = """
CREATE TABLE candidates (
  candidate_id VARCHAR PRIMARY KEY,
  run_id VARCHAR NOT NULL,
  filing_id VARCHAR NOT NULL,
  candidate_type VARCHAR NOT NULL CHECK (candidate_type IN ('actor_mention', 'dated_event', 'bid_value', 'participation_count', 'actor_relation')),
  raw_value VARCHAR NOT NULL,
  normalized_value VARCHAR NOT NULL,
  confidence VARCHAR NOT NULL CHECK (confidence IN ('low', 'medium', 'high')),
  evidence_ids VARCHAR[] NOT NULL,
  dependencies VARCHAR[] NOT NULL,
  status VARCHAR NOT NULL CHECK (status IN ('active', 'rejected')),
  FOREIGN KEY (filing_id) REFERENCES filings(filing_id)
);

CREATE TABLE relation_candidates (
  candidate_id VARCHAR PRIMARY KEY,
  subject_label VARCHAR NOT NULL,
  object_label VARCHAR NOT NULL,
  relation_type VARCHAR NOT NULL CHECK (relation_type IN ('member_of', 'affiliate_of', 'controls', 'acquisition_vehicle_of', 'advises', 'finances', 'supports', 'rollover_holder_of')),
  role_detail VARCHAR,
  effective_date_first DATE,
  FOREIGN KEY (candidate_id) REFERENCES candidates(candidate_id)
);
"""
