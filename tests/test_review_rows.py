"""Red tests for the consolidated review_rows table and run-status helper."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from sec_graph.project.review_rows import ReviewRow, next_review_row_id
from sec_graph.schema import (
    TRUSTED_STATUSES,
    connect,
    init_schema,
    status_from_open_review_count,
)


def test_review_rows_table_has_expected_columns_and_check_constraints() -> None:
    conn = connect(":memory:")
    init_schema(conn)

    table_names = {
        row[0]
        for row in conn.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'main'"
        ).fetchall()
    }
    assert "review_rows" in table_names
    assert "review_flags" not in table_names

    columns = {row[1] for row in conn.execute("PRAGMA table_info('review_rows')").fetchall()}
    for column in (
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
    ):
        assert column in columns

    constraint_text = "\n".join(
        row[0]
        for row in conn.execute(
            """
            SELECT constraint_text
            FROM duckdb_constraints()
            WHERE table_name = 'review_rows'
            ORDER BY constraint_text
            """
        ).fetchall()
    )
    assert "open" in constraint_text
    assert "accepted" in constraint_text
    assert "rejected" in constraint_text
    assert "deferred" in constraint_text
    assert "coverage" in constraint_text
    assert "claim_disposition" in constraint_text
    assert "judgment" in constraint_text
    assert "projection" in constraint_text
    assert "validation" in constraint_text
    assert "review" in constraint_text
    assert "info" in constraint_text


def test_status_from_open_review_count() -> None:
    assert status_from_open_review_count(0) == "passed_clean"
    assert status_from_open_review_count(1) == "needs_review"
    assert status_from_open_review_count(10) == "needs_review"
    assert status_from_open_review_count(11) == "high_burden"
    assert status_from_open_review_count(100) == "high_burden"


def test_trusted_statuses_constant_excludes_failed_system() -> None:
    assert TRUSTED_STATUSES == frozenset({"passed_clean", "needs_review", "high_burden"})
    assert "failed_system" not in TRUSTED_STATUSES
    assert "stale_after_failure" not in TRUSTED_STATUSES


def test_review_row_pydantic_accepts_minimal_open_review_row() -> None:
    row = ReviewRow(
        review_row_id="deal_reviewrow_1",
        run_id="run-1",
        deal_slug="deal",
        review_status="open",
        review_type="coverage",
        source_table="coverage_results",
        source_id="deal_coverage_1",
        severity="review",
        reason_code="missed_supported_obligation",
        message="Required obligation has no supported claim.",
        review_question="Does the source support this obligation?",
        created_at="2026-05-07T00:00:00Z",
    )
    assert row.review_row_id == "deal_reviewrow_1"
    assert row.review_status == "open"
    assert row.review_type == "coverage"
    assert row.severity == "review"


def test_review_row_pydantic_rejects_unknown_review_status() -> None:
    with pytest.raises(ValidationError):
        ReviewRow(
            review_row_id="deal_reviewrow_1",
            run_id="run-1",
            deal_slug="deal",
            review_status="blocked",  # type: ignore[arg-type]
            review_type="coverage",
            source_table="coverage_results",
            source_id="deal_coverage_1",
            severity="review",
            reason_code="x",
            message="x",
            review_question="x",
            created_at="2026-05-07T00:00:00Z",
        )


def test_review_row_pydantic_rejects_unknown_severity() -> None:
    with pytest.raises(ValidationError):
        ReviewRow(
            review_row_id="deal_reviewrow_1",
            run_id="run-1",
            deal_slug="deal",
            review_status="open",
            review_type="coverage",
            source_table="coverage_results",
            source_id="deal_coverage_1",
            severity="blocking",  # type: ignore[arg-type]
            reason_code="x",
            message="x",
            review_question="x",
            created_at="2026-05-07T00:00:00Z",
        )


def test_review_row_pydantic_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError):
        ReviewRow(
            review_row_id="deal_reviewrow_1",
            run_id="run-1",
            deal_slug="deal",
            review_status="open",
            review_type="coverage",
            source_table="coverage_results",
            source_id="deal_coverage_1",
            severity="review",
            reason_code="x",
            message="x",
            review_question="x",
            created_at="2026-05-07T00:00:00Z",
            current=True,  # type: ignore[call-arg]
        )


def test_review_row_db_check_constraint_rejects_bad_severity() -> None:
    conn = connect(":memory:")
    init_schema(conn)
    with pytest.raises(Exception):
        conn.execute(
            "INSERT INTO review_rows VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                "deal_reviewrow_1",
                "run-1",
                "deal",
                "open",
                "coverage",
                "coverage_results",
                "deal_coverage_1",
                "blocking",  # bad severity
                "x",
                "x",
                "x",
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                "2026-05-07T00:00:00Z",
            ],
        )


def test_next_review_row_id_allocates_sequentially() -> None:
    conn = connect(":memory:")
    init_schema(conn)
    first = next_review_row_id(conn, "deal")
    assert first == "deal_reviewrow_1"

    conn.execute(
        "INSERT INTO review_rows VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            first,
            "run-1",
            "deal",
            "open",
            "coverage",
            "coverage_results",
            "deal_coverage_1",
            "review",
            "x",
            "x",
            "x",
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            "2026-05-07T00:00:00Z",
        ],
    )
    second = next_review_row_id(conn, "deal")
    assert second == "deal_reviewrow_2"


def test_status_from_open_review_count_zero_is_passed_clean() -> None:
    assert status_from_open_review_count(0) == "passed_clean"


def test_status_from_open_review_count_one_is_needs_review() -> None:
    assert status_from_open_review_count(1) == "needs_review"


def test_status_from_open_review_count_eleven_is_high_burden() -> None:
    assert status_from_open_review_count(11) == "high_burden"
