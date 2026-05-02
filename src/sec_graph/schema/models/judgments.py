"""Two-axis append-only judgment model and helpers.

The `judgments` table is APPEND-ONLY. The pipeline must never silently delete
rows here. Reviewer overrides emit a NEW judgment whose
`supersedes_judgment_id` points at the prior row (see `latest_judgments`
below). Reconcile-owned admission judgments may be replaced as derived
    artifacts of the reconcile stage; later reconcile passes append fresh rows
    rather than deleting the previous ones.

The two axes are intentionally narrow:

- `fact_correction` patches a stored canonical value. It is also used to
  record explicit rejection of unresolved candidates by patching
  `candidates.status` from `active` to a tagged rejection (e.g.
  `rejected:unresolved_actor_relation`). This stays inside the two-axis
  surface and avoids inventing an open `kind` enum.
- `projection_eligibility` admits or excludes an actor under a named
  projection rule.

See `docs/spec.md` §1A "Judgments" and §10.2.
"""

from __future__ import annotations

import datetime as dt
from typing import Iterable, Literal

from pydantic import BaseModel, ConfigDict, model_validator

# Closed two-axis enum. Do NOT add `rejected`, `unknown`, or any open value
# here — rejections are encoded as `fact_correction` rows whose `new_value`
# carries a `rejected:<reason>` tag. See module docstring.
JudgmentKind = Literal["fact_correction", "projection_eligibility"]


class Judgment(BaseModel):
    """Append-only judgment row.

    Validators below enforce per-kind required fields. Pydantic refuses any
    cross-axis row (e.g. a `projection_eligibility` row that also sets
    `target_table`).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    judgment_id: str
    run_id: str
    judgment_kind: JudgmentKind
    target_table: str | None
    target_id: str | None
    target_column: str | None
    prior_value: str | None
    new_value: str | None
    projection_name: str | None
    actor_id: str | None
    included: bool | None
    rule_id: str | None
    evidence_ids: list[str]
    supersedes_judgment_id: str | None
    created_at: dt.datetime
    created_by: str

    @model_validator(mode="after")
    def _axis_shape_is_exclusive(self) -> "Judgment":
        correction_values = (
            self.target_table,
            self.target_id,
            self.target_column,
            self.prior_value,
            self.new_value,
        )
        projection_values = (self.projection_name, self.actor_id, self.included, self.rule_id)
        if self.judgment_kind == "fact_correction":
            if any(value is None for value in correction_values):
                raise ValueError("fact_correction requires target_table, target_id, target_column, prior_value, and new_value")
            if any(value is not None for value in projection_values):
                raise ValueError("fact_correction cannot populate projection fields")
        if self.judgment_kind == "projection_eligibility":
            if any(value is not None for value in correction_values):
                raise ValueError("projection_eligibility cannot populate fact-correction fields")
            if any(value is None for value in projection_values):
                raise ValueError("projection_eligibility requires projection_name, actor_id, included, and rule_id")
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
  judgment_kind VARCHAR NOT NULL CHECK (judgment_kind IN ('fact_correction', 'projection_eligibility')),
  target_table VARCHAR,
  target_id VARCHAR,
  target_column VARCHAR,
  prior_value VARCHAR,
  new_value VARCHAR,
  projection_name VARCHAR,
  actor_id VARCHAR,
  included BOOLEAN,
  rule_id VARCHAR,
  evidence_ids VARCHAR[] NOT NULL,
  supersedes_judgment_id VARCHAR,
  created_at VARCHAR NOT NULL,
  created_by VARCHAR NOT NULL,
  CHECK (
    (
      judgment_kind = 'fact_correction'
      AND target_table IS NOT NULL
      AND target_id IS NOT NULL
      AND target_column IS NOT NULL
      AND prior_value IS NOT NULL
      AND new_value IS NOT NULL
      AND projection_name IS NULL
      AND actor_id IS NULL
      AND included IS NULL
      AND rule_id IS NULL
    )
    OR
    (
      judgment_kind = 'projection_eligibility'
      AND target_table IS NULL
      AND target_id IS NULL
      AND target_column IS NULL
      AND prior_value IS NULL
      AND new_value IS NULL
      AND projection_name IS NOT NULL
      AND actor_id IS NOT NULL
      AND included IS NOT NULL
      AND rule_id IS NOT NULL
    )
  ),
  FOREIGN KEY (supersedes_judgment_id) REFERENCES judgments(judgment_id)
);
"""
