"""Python-owned derived judgments and review flags."""

from __future__ import annotations

from typing import Iterable, Literal

from pydantic import BaseModel, ConfigDict

JudgmentStatus = Literal["accepted", "review_required", "not_applicable"]
ReviewSeverity = Literal["blocking", "review", "info"]


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


class ReviewFlag(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    flag_id: str
    run_id: str
    deal_slug: str
    filing_id: str | None
    region_id: str | None
    obligation_id: str | None
    claim_id: str | None
    judgment_id: str | None
    canonical_table: str | None
    canonical_id: str | None
    flag_type: str
    severity: ReviewSeverity
    reason_code: str
    reason: str
    quote_text: str | None
    source_ref: str | None
    short_source_context: str | None
    recommended_review_question: str
    current: bool = True


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

CREATE TABLE review_flags (
  flag_id VARCHAR PRIMARY KEY,
  run_id VARCHAR NOT NULL,
  deal_slug VARCHAR NOT NULL,
  filing_id VARCHAR,
  region_id VARCHAR,
  obligation_id VARCHAR,
  claim_id VARCHAR,
  judgment_id VARCHAR,
  canonical_table VARCHAR,
  canonical_id VARCHAR,
  flag_type VARCHAR NOT NULL,
  severity VARCHAR NOT NULL CHECK (severity IN ('blocking', 'review', 'info')),
  reason_code VARCHAR NOT NULL,
  reason VARCHAR NOT NULL,
  quote_text VARCHAR,
  source_ref VARCHAR,
  short_source_context VARCHAR,
  recommended_review_question VARCHAR NOT NULL,
  current BOOLEAN NOT NULL
);
"""
