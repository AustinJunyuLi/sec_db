"""Extraction candidate model and DDL."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict


class ExtractionCandidate(BaseModel):
    model_config = ConfigDict(frozen=True)

    candidate_id: str
    run_id: str
    filing_id: str
    candidate_type: Literal["actor_mention", "dated_event", "bid_value", "participation_count"]
    raw_value: str
    normalized_value: str
    confidence: Literal["low", "medium", "high"]
    evidence_ids: list[str]
    dependencies: list[str]
    status: Literal["active", "rejected"]


EXTRACTION_DDL = """
CREATE TABLE candidates (
  candidate_id VARCHAR PRIMARY KEY,
  run_id VARCHAR NOT NULL,
  filing_id VARCHAR NOT NULL,
  candidate_type VARCHAR NOT NULL CHECK (candidate_type IN ('actor_mention', 'dated_event', 'bid_value', 'participation_count')),
  raw_value VARCHAR NOT NULL,
  normalized_value VARCHAR NOT NULL,
  confidence VARCHAR NOT NULL CHECK (confidence IN ('low', 'medium', 'high')),
  evidence_ids VARCHAR[] NOT NULL,
  dependencies VARCHAR[] NOT NULL,
  status VARCHAR NOT NULL CHECK (status IN ('active', 'rejected')),
  FOREIGN KEY (filing_id) REFERENCES filings(filing_id)
);
"""
