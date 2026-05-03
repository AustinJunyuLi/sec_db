"""Append-only semantic judgment model."""

from __future__ import annotations

import datetime as dt
from typing import Iterable, Literal

from pydantic import BaseModel, ConfigDict, model_validator

JudgmentKind = Literal["fact_correction", "semantic_validation"]


class Judgment(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    judgment_id: str
    run_id: str
    judgment_kind: JudgmentKind
    target_table: str
    target_id: str
    target_column: str | None
    prior_value: str | None
    new_value: str | None
    reason_code: str
    reason: str
    supersedes_judgment_id: str | None
    created_at: dt.datetime
    created_by: str

    @model_validator(mode="after")
    def _correction_shape(self) -> "Judgment":
        if self.judgment_kind == "fact_correction" and self.target_column is None:
            raise ValueError("fact_correction requires target_column")
        return self


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
  judgment_kind VARCHAR NOT NULL CHECK (judgment_kind IN ('fact_correction', 'semantic_validation')),
  target_table VARCHAR NOT NULL,
  target_id VARCHAR NOT NULL,
  target_column VARCHAR,
  prior_value VARCHAR,
  new_value VARCHAR,
  reason_code VARCHAR NOT NULL,
  reason VARCHAR NOT NULL,
  supersedes_judgment_id VARCHAR,
  created_at VARCHAR NOT NULL,
  created_by VARCHAR NOT NULL,
  CHECK (judgment_kind <> 'fact_correction' OR target_column IS NOT NULL),
  FOREIGN KEY (supersedes_judgment_id) REFERENCES judgments(judgment_id)
);
"""
