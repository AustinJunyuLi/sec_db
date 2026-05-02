"""Participation-count model and DDL."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ParticipationCount(BaseModel):
    model_config = ConfigDict(frozen=True)

    participation_count_id: str
    run_id: str
    deal_id: str
    cycle_id: str
    count_type: str
    count_value: int = Field(ge=0)
    count_unit: str
    process_stage: str
    bidder_subtype_split: dict[str, int] | None
    actor_creation_required: Literal["required", "deferred", "projection_only"]
    evidence_ids: list[str]


PARTICIPATION_COUNTS_DDL = """
CREATE TABLE participation_counts (
  participation_count_id VARCHAR PRIMARY KEY,
  run_id VARCHAR NOT NULL,
  deal_id VARCHAR NOT NULL,
  cycle_id VARCHAR NOT NULL,
  count_type VARCHAR NOT NULL,
  count_value INTEGER NOT NULL,
  count_unit VARCHAR NOT NULL,
  process_stage VARCHAR NOT NULL,
  bidder_subtype_split VARCHAR,
  actor_creation_required VARCHAR NOT NULL CHECK (actor_creation_required IN ('required', 'deferred', 'projection_only')),
  evidence_ids VARCHAR[] NOT NULL,
  CHECK (count_value >= 0),
  FOREIGN KEY (deal_id) REFERENCES deals(deal_id),
  FOREIGN KEY (cycle_id) REFERENCES process_cycles(cycle_id)
);
"""
