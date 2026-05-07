"""Python-owned derived judgments."""

from __future__ import annotations

from typing import Iterable, Literal

from pydantic import BaseModel, ConfigDict

JudgmentStatus = Literal["accepted", "review_required", "not_applicable"]


class Judgment(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    judgment_id: str
    run_id: str
    deal_id: str
    cycle_id: str | None
    target_table: str
    target_id: str
    judgment_key: str
    judgment_value: str | None
    judgment_status: JudgmentStatus
    rule_id: str
    reason_code: str
    reason: str
    basis_json: str
    current: bool = True
    supersedes_judgment_id: str | None = None


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
  target_table VARCHAR NOT NULL,
  target_id VARCHAR NOT NULL,
  judgment_key VARCHAR NOT NULL,
  judgment_value VARCHAR,
  judgment_status VARCHAR NOT NULL CHECK (judgment_status IN ('accepted', 'review_required', 'not_applicable')),
  rule_id VARCHAR NOT NULL,
  reason_code VARCHAR NOT NULL,
  reason VARCHAR NOT NULL,
  basis_json VARCHAR NOT NULL,
  current BOOLEAN NOT NULL,
  supersedes_judgment_id VARCHAR,
  FOREIGN KEY (supersedes_judgment_id) REFERENCES judgments(judgment_id)
);
"""
