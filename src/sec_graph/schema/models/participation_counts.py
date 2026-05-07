"""Closed cohort participation-count canonical model and DDL."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

ProcessStage = Literal["contacted", "nda_signed", "ioi_submitted", "first_round", "final_round", "exclusivity"]
ActorClass = Literal["financial", "strategic", "mixed", "unknown"]
CountQualifier = Literal["exact", "approximate", "lower_bound", "upper_bound", "range"]


class ParticipationCount(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    participation_count_id: str
    run_id: str
    deal_id: str
    cycle_id: str
    event_id: str | None
    process_stage: ProcessStage
    actor_class: ActorClass
    count_min: int = Field(ge=0)
    count_max: int | None = Field(default=None, ge=0)
    count_qualifier: CountQualifier
    named_subset_actor_ids_json: str
    anonymous_remainder_count: int = Field(ge=0)

    @model_validator(mode="after")
    def _count_range_is_ordered(self) -> "ParticipationCount":
        if self.count_max is not None and self.count_max < self.count_min:
            raise ValueError("count_max must be greater than or equal to count_min")
        return self


PARTICIPATION_COUNTS_DDL = """
CREATE TABLE participation_counts (
  participation_count_id VARCHAR PRIMARY KEY,
  run_id VARCHAR NOT NULL,
  deal_id VARCHAR NOT NULL,
  cycle_id VARCHAR NOT NULL,
  event_id VARCHAR,
  process_stage VARCHAR NOT NULL CHECK (process_stage IN ('contacted', 'nda_signed', 'ioi_submitted', 'first_round', 'final_round', 'exclusivity')),
  actor_class VARCHAR NOT NULL CHECK (actor_class IN ('financial', 'strategic', 'mixed', 'unknown')),
  count_min INTEGER NOT NULL,
  count_max INTEGER,
  count_qualifier VARCHAR NOT NULL CHECK (count_qualifier IN ('exact', 'approximate', 'lower_bound', 'upper_bound', 'range')),
  named_subset_actor_ids_json VARCHAR NOT NULL,
  anonymous_remainder_count INTEGER NOT NULL,
  CHECK (count_min >= 0),
  CHECK (count_max IS NULL OR count_max >= count_min),
  CHECK (anonymous_remainder_count >= 0),
  FOREIGN KEY (deal_id) REFERENCES deals(deal_id),
  FOREIGN KEY (cycle_id) REFERENCES process_cycles(cycle_id),
  FOREIGN KEY (event_id) REFERENCES events(event_id)
);
"""
