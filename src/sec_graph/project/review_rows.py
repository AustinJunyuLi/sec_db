"""Consolidated review-row artifact and helpers."""

from __future__ import annotations

from typing import Literal

import duckdb
from pydantic import BaseModel, ConfigDict

from sec_graph.schema import make_id

ReviewStatus = Literal["open", "accepted", "rejected", "deferred"]
ReviewType = Literal[
    "coverage",
    "claim_disposition",
    "judgment",
    "projection",
    "validation",
]
ReviewSeverity = Literal["review", "info"]


class ReviewRow(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    review_row_id: str
    run_id: str
    deal_slug: str
    review_status: ReviewStatus
    review_type: ReviewType
    source_table: str
    source_id: str
    severity: ReviewSeverity
    reason_code: str
    message: str
    review_question: str
    claim_id: str | None = None
    obligation_id: str | None = None
    judgment_id: str | None = None
    canonical_table: str | None = None
    canonical_id: str | None = None
    evidence_json: str | None = None
    resolution_notes: str | None = None
    resolved_by: str | None = None
    resolved_at: str | None = None
    created_at: str


def next_review_row_id(conn: duckdb.DuckDBPyConnection, deal_slug: str) -> str:
    """Allocate a deterministic review_row_id for ``deal_slug``."""

    prefix = f"{deal_slug}_reviewrow_"
    rows = conn.execute(
        "SELECT review_row_id FROM review_rows WHERE review_row_id LIKE ?",
        [f"{prefix}%"],
    ).fetchall()
    if not rows:
        sequence = 1
    else:
        sequence = max(int(row[0].rsplit("_", maxsplit=1)[1]) for row in rows) + 1
    return make_id(deal_slug, "reviewrow", sequence)


def write_review_rows_jsonl(*args, **kwargs) -> None:
    """Reserved for Task 7; currently unimplemented."""

    raise NotImplementedError("write_review_rows_jsonl is implemented in Task 7")


def write_review_rows_csv(*args, **kwargs) -> None:
    """Reserved for Task 7; currently unimplemented."""

    raise NotImplementedError("write_review_rows_csv is implemented in Task 7")
