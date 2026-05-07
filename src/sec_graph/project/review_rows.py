"""Consolidated review-row artifact and helpers."""

from __future__ import annotations

import csv
import datetime as dt
import io
import json
from pathlib import Path
from typing import Literal

import duckdb
from pydantic import BaseModel, ConfigDict

from sec_graph.run.io import atomic_write_text
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


_FIELD_ORDER: tuple[str, ...] = (
    "review_row_id",
    "run_id",
    "deal_slug",
    "review_status",
    "review_type",
    "source_table",
    "source_id",
    "severity",
    "reason_code",
    "message",
    "review_question",
    "claim_id",
    "obligation_id",
    "judgment_id",
    "canonical_table",
    "canonical_id",
    "evidence_json",
    "resolution_notes",
    "resolved_by",
    "resolved_at",
    "created_at",
)


def next_review_row_id(conn: duckdb.DuckDBPyConnection, deal_slug: str) -> str:
    """Allocate a deterministic review_row_id for ``deal_slug``."""

    sequence = _next_review_row_sequence(conn, deal_slug)
    return make_id(deal_slug, "reviewrow", sequence)


def project_review_rows(
    conn: duckdb.DuckDBPyConnection,
    *,
    run_id: str,
) -> list[ReviewRow]:
    """Synthesize coverage and validation review rows, then read all rows.

    The function inserts review rows into the ``review_rows`` table for:

    - Unresolved applicable coverage results (any
      ``coverage_results.result IN ('missed_supported_obligation',
      'no_supported_claim', 'ambiguous_support')`` for ``applicable``
      obligations) — ``review_type='coverage'``.
    - Non-system validation review items (the
      ``ValidationResult.review_items`` finding list) — ``review_type='validation'``.

    Disposition / judgment / projection review rows are produced by their
    writers and are read as-is. The function is idempotent: it deletes the
    rows it owns (``review_type IN ('coverage', 'validation')`` for the
    given ``run_id``) before re-inserting.
    """
    # Idempotent reset for synthesized review rows.
    conn.execute(
        """
        DELETE FROM review_rows
        WHERE run_id = ?
          AND review_type IN ('coverage', 'validation')
        """,
        [run_id],
    )

    _synthesize_coverage_rows(conn, run_id=run_id)
    _synthesize_validation_rows(conn, run_id=run_id)

    return _read_review_rows(conn, run_id=run_id)


def write_review_rows(run_dir: Path, rows: list[ReviewRow]) -> None:
    """Write ``review_rows.jsonl`` and ``review_rows.csv`` under ``run_dir``."""

    run_dir.mkdir(parents=True, exist_ok=True)

    jsonl_lines: list[str] = []
    for row in rows:
        payload = row.model_dump(mode="json")
        jsonl_lines.append(json.dumps(payload, sort_keys=True))
    jsonl_text = "\n".join(jsonl_lines) + ("\n" if jsonl_lines else "")
    atomic_write_text(run_dir / "review_rows.jsonl", jsonl_text)

    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=list(_FIELD_ORDER))
    writer.writeheader()
    for row in rows:
        payload = row.model_dump(mode="json")
        writer.writerow({field: payload.get(field) for field in _FIELD_ORDER})
    atomic_write_text(run_dir / "review_rows.csv", buf.getvalue())


# --------------------------------------------------------------------------- #
# Synthesizers                                                                #
# --------------------------------------------------------------------------- #


def _synthesize_coverage_rows(
    conn: duckdb.DuckDBPyConnection,
    *,
    run_id: str,
) -> None:
    rows = conn.execute(
        """
        SELECT coverage_results.coverage_result_id,
               coverage_results.obligation_id,
               coverage_results.result,
               coverage_results.reason,
               coverage_obligations.deal_slug,
               coverage_obligations.obligation_label,
               coverage_obligations.expected_claim_type,
               coverage_obligations.importance
        FROM coverage_results
        JOIN coverage_obligations
          ON coverage_obligations.obligation_id = coverage_results.obligation_id
         AND coverage_obligations.current = true
        WHERE coverage_results.current = true
          AND coverage_obligations.applicability = 'applicable'
          AND coverage_results.result IN (
              'missed_supported_obligation',
              'no_supported_claim',
              'ambiguous_support'
          )
        ORDER BY coverage_obligations.deal_slug, coverage_results.coverage_result_id
        """
    ).fetchall()
    for (
        coverage_result_id,
        obligation_id,
        result,
        reason,
        deal_slug,
        obligation_label,
        expected_claim_type,
        importance,
    ) in rows:
        review_row_id = next_review_row_id(conn, deal_slug)
        message = (
            f"Applicable {importance} obligation {obligation_label!r} "
            f"({expected_claim_type}): {reason}"
        )
        review_question = (
            f"Does the source support a {expected_claim_type} claim for "
            f"{obligation_label!r}? Reviewer should resolve coverage gap."
        )
        conn.execute(
            "INSERT INTO review_rows VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                review_row_id,
                run_id,
                deal_slug,
                "open",
                "coverage",
                "coverage_results",
                coverage_result_id,
                "review",
                str(result),
                message,
                review_question,
                None,
                obligation_id,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                _now_iso(),
            ],
        )


def _synthesize_validation_rows(
    conn: duckdb.DuckDBPyConnection,
    *,
    run_id: str,
) -> None:
    # Local import to avoid a hard import cycle with project.summaries.
    from sec_graph.validate.integrity import validate_database

    result = validate_database(conn)
    if not result.review_items:
        return

    deal_slug = _default_deal_slug(conn)
    for finding in result.review_items:
        review_row_id = next_review_row_id(conn, deal_slug)
        reason_code = str(finding.check.value if hasattr(finding.check, "value") else finding.check)
        review_question = (
            "Validation flagged this row as review burden. Confirm whether the "
            "source supports the canonical fact."
        )
        conn.execute(
            "INSERT INTO review_rows VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                review_row_id,
                run_id,
                deal_slug,
                "open",
                "validation",
                finding.table_name,
                finding.row_id,
                "review",
                reason_code,
                finding.detail,
                review_question,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                _now_iso(),
            ],
        )


# --------------------------------------------------------------------------- #
# Helpers                                                                     #
# --------------------------------------------------------------------------- #


def _read_review_rows(
    conn: duckdb.DuckDBPyConnection,
    *,
    run_id: str,
) -> list[ReviewRow]:
    rows = conn.execute(
        f"""
        SELECT {", ".join(_FIELD_ORDER)}
        FROM review_rows
        WHERE run_id = ?
        ORDER BY deal_slug, review_type, review_row_id
        """,
        [run_id],
    ).fetchall()
    out: list[ReviewRow] = []
    for row in rows:
        payload = dict(zip(_FIELD_ORDER, row, strict=True))
        out.append(ReviewRow(**payload))
    return out


def _default_deal_slug(conn: duckdb.DuckDBPyConnection) -> str:
    """Pick a deterministic deal_slug for synthesized validation rows.

    Validation findings are not always tied to a specific deal_slug; use the
    first deal_slug present in the schema, or fall back to ``"global"``.
    """
    row = conn.execute(
        "SELECT deal_slug FROM deals ORDER BY deal_slug LIMIT 1"
    ).fetchone()
    if row is not None:
        return str(row[0])
    return "global"


def _next_review_row_sequence(conn: duckdb.DuckDBPyConnection, deal_slug: str) -> int:
    prefix = f"{deal_slug}_reviewrow_"
    rows = conn.execute(
        "SELECT review_row_id FROM review_rows WHERE review_row_id LIKE ?",
        [f"{prefix}%"],
    ).fetchall()
    if not rows:
        return 1
    return max(int(row[0].rsplit("_", maxsplit=1)[1]) for row in rows) + 1


def _now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
