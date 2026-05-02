"""Append-only judgment model and helpers."""

from __future__ import annotations

from typing import Iterable, Literal

from pydantic import BaseModel, ConfigDict


class Judgment(BaseModel):
    model_config = ConfigDict(frozen=True)

    judgment_id: str
    run_id: str
    deal_id: str
    cycle_id: str | None
    actor_id: str | None
    event_id: str | None
    judgment_type: str
    judgment_value: str
    confidence: Literal["low", "medium", "high"]
    alternative_value: str | None
    supersedes_judgment_id: str | None
    evidence_ids: list[str]


def latest_judgments(judgments: Iterable[Judgment]) -> list[Judgment]:
    rows = list(judgments)
    superseded = {
        judgment.supersedes_judgment_id
        for judgment in rows
        if judgment.supersedes_judgment_id is not None
    }
    return [judgment for judgment in rows if judgment.judgment_id not in superseded]


JUDGMENTS_DDL = """
CREATE TABLE judgments (
  judgment_id VARCHAR PRIMARY KEY,
  run_id VARCHAR NOT NULL,
  deal_id VARCHAR NOT NULL,
  cycle_id VARCHAR,
  actor_id VARCHAR,
  event_id VARCHAR,
  judgment_type VARCHAR NOT NULL,
  judgment_value VARCHAR NOT NULL,
  confidence VARCHAR NOT NULL CHECK (confidence IN ('low', 'medium', 'high')),
  alternative_value VARCHAR,
  supersedes_judgment_id VARCHAR,
  evidence_ids VARCHAR[] NOT NULL,
  FOREIGN KEY (deal_id) REFERENCES deals(deal_id),
  FOREIGN KEY (cycle_id) REFERENCES process_cycles(cycle_id),
  FOREIGN KEY (actor_id) REFERENCES actors(actor_id),
  FOREIGN KEY (event_id) REFERENCES events(event_id),
  FOREIGN KEY (supersedes_judgment_id) REFERENCES judgments(judgment_id)
);
"""
