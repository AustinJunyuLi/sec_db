"""Red tests for the consolidated review_rows table and run-status helper."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from sec_graph.project.review_rows import (
    ReviewRow,
    next_review_row_id,
    project_review_rows,
    write_review_rows,
)
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


# --------------------------------------------------------------------------- #
# project_review_rows synthesis                                               #
# --------------------------------------------------------------------------- #


def _seed_minimal_filing(conn: Any) -> None:
    """Seed minimal filing/region/obligation rows that referential queries need."""
    conn.execute(
        "INSERT INTO filings VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        [
            "deal_filing_1",
            "deal",
            "example.md",
            "0" * 64,
            1,
            None,
            1,
            "target_full_proxy",
        ],
    )
    conn.execute(
        "INSERT INTO paragraphs VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        [
            "deal_para_1",
            "deal_filing_1",
            "Background",
            None,
            0,
            10,
            "..........",
            "0" * 64,
        ],
    )
    conn.execute(
        "INSERT INTO evidence_regions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            "deal_region_1",
            "run-1",
            "deal_filing_1",
            "deal",
            "sale_process_narrative",
            1,
            "deal_para_1",
            "deal_para_1",
            '["deal_para_1"]',
            "[]",
            '["bid"]',
        ],
    )


def _insert_applicable_obligation_with_missed_result(
    conn: Any, obligation_id: str
) -> None:
    conn.execute(
        "INSERT INTO coverage_obligations VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            obligation_id,
            "run-1",
            "deal_region_1",
            "deal_filing_1",
            "deal",
            "bid",
            "first_round_bid_count",
            "First-round bid",
            "required",
            "applicable",
            "narrative_says_first_round_bids",
            "{}",
            True,
        ],
    )
    conn.execute(
        "INSERT INTO coverage_results VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        [
            "deal_coverage_1",
            "run-1",
            obligation_id,
            "missed_supported_obligation",
            "supported_count_zero",
            "no supported claim covers this obligation",
            0,
            True,
        ],
    )


def test_project_review_rows_synthesizes_coverage_review_items() -> None:
    conn = connect(":memory:")
    init_schema(conn)
    conn.execute(
        "INSERT INTO deals VALUES (?, ?, ?, ?, ?)",
        ["deal_deal_1", "run-1", "deal", "deal_actor_target", "2024-01-01"],
    )
    _seed_minimal_filing(conn)
    _insert_applicable_obligation_with_missed_result(conn, "deal_obligation_1")

    rows = project_review_rows(conn, run_id="run-1")
    coverage_rows = [row for row in rows if row.review_type == "coverage"]
    assert coverage_rows, "expected synthesized coverage review row"
    coverage = coverage_rows[0]
    assert coverage.review_status == "open"
    assert coverage.source_table == "coverage_results"
    assert coverage.reason_code == "missed_supported_obligation"
    assert coverage.obligation_id == "deal_obligation_1"


def test_project_review_rows_synthesizes_validation_review_items(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conn = connect(":memory:")
    init_schema(conn)
    conn.execute(
        "INSERT INTO deals VALUES (?, ?, ?, ?, ?)",
        ["deal_deal_1", "run-1", "deal", "deal_actor_target", "2024-01-01"],
    )

    from sec_graph.validate import integrity as integrity_module

    class _FakeFinding:
        def __init__(self, check: str, table_name: str, row_id: str, detail: str) -> None:
            self.check = check
            self.table_name = table_name
            self.row_id = row_id
            self.detail = detail

    class _FakeResult:
        def __init__(self) -> None:
            self.system_failures: list[_FakeFinding] = []
            self.review_items = [
                _FakeFinding(
                    "coverage_review",
                    "coverage_obligations",
                    "deal_obligation_1",
                    "review burden detected",
                )
            ]

        @property
        def passed(self) -> bool:
            return not self.system_failures

    def _fake_validate(_conn: Any, *, raw_source_root: Any = None) -> _FakeResult:
        return _FakeResult()

    monkeypatch.setattr(integrity_module, "validate_database", _fake_validate)

    rows = project_review_rows(conn, run_id="run-1")
    validation_rows = [row for row in rows if row.review_type == "validation"]
    assert validation_rows, "expected synthesized validation review row"
    finding_row = validation_rows[0]
    assert finding_row.review_status == "open"
    assert finding_row.source_table == "coverage_obligations"
    assert finding_row.reason_code == "coverage_review"


def test_project_review_rows_is_idempotent() -> None:
    conn = connect(":memory:")
    init_schema(conn)
    conn.execute(
        "INSERT INTO deals VALUES (?, ?, ?, ?, ?)",
        ["deal_deal_1", "run-1", "deal", "deal_actor_target", "2024-01-01"],
    )
    _seed_minimal_filing(conn)
    _insert_applicable_obligation_with_missed_result(conn, "deal_obligation_1")

    project_review_rows(conn, run_id="run-1")
    first_count = int(
        conn.execute(
            """
            SELECT count(*)
            FROM review_rows
            WHERE run_id = ?
              AND review_type IN ('coverage', 'validation')
            """,
            ["run-1"],
        ).fetchone()[0]
    )

    project_review_rows(conn, run_id="run-1")
    second_count = int(
        conn.execute(
            """
            SELECT count(*)
            FROM review_rows
            WHERE run_id = ?
              AND review_type IN ('coverage', 'validation')
            """,
            ["run-1"],
        ).fetchone()[0]
    )
    assert first_count == second_count


def test_write_review_rows_emits_jsonl_and_csv(tmp_path: Path) -> None:
    conn = connect(":memory:")
    init_schema(conn)
    conn.execute(
        "INSERT INTO deals VALUES (?, ?, ?, ?, ?)",
        ["deal_deal_1", "run-1", "deal", "deal_actor_target", "2024-01-01"],
    )
    _seed_minimal_filing(conn)
    _insert_applicable_obligation_with_missed_result(conn, "deal_obligation_1")

    rows = project_review_rows(conn, run_id="run-1")
    assert rows, "expected at least one review row"

    write_review_rows(tmp_path, rows)

    jsonl_path = tmp_path / "review_rows.jsonl"
    csv_path = tmp_path / "review_rows.csv"
    assert jsonl_path.exists()
    assert csv_path.exists()

    parsed = [json.loads(line) for line in jsonl_path.read_text().splitlines() if line]
    assert parsed
    assert "review_row_id" in parsed[0]
    assert "review_type" in parsed[0]
    assert "review_status" in parsed[0]

    with csv_path.open(encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        rows_csv = list(reader)
    assert rows_csv
    assert {"review_row_id", "review_type", "review_status"} <= set(rows_csv[0].keys())


# --------------------------------------------------------------------------- #
# Bidder projection: review-row substrate                                     #
# --------------------------------------------------------------------------- #


def _seed_bidder_projection_substrate_missing_formality(conn: Any) -> None:
    """Seed a deal with a bid event whose formality cannot be determined."""
    conn.execute(
        "INSERT INTO deals VALUES (?, ?, ?, ?, ?)",
        ["deal_deal_1", "run-1", "deal", "deal_actor_1", "2024-01-01"],
    )
    conn.execute(
        "INSERT INTO actors VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ["deal_actor_1", "run-1", "deal_deal_1", "Target", "organization", "named", None, None, None, None],
    )
    conn.execute(
        "INSERT INTO actors VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ["deal_actor_2", "run-1", "deal_deal_1", "Party A", "organization", "named", None, None, None, None],
    )
    conn.execute(
        "INSERT INTO process_cycles VALUES (?, ?, ?, ?, ?, ?, ?)",
        ["deal_cycle_1", "run-1", "deal_deal_1", 1, "primary sale process", "2024-01-01", "2024-01-03"],
    )
    # Promote cycle to final-round boundary so that an IOI without value
    # cannot be resolved to a formal/informal judgment.
    conn.execute(
        "INSERT INTO participation_counts VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            "deal_pc_1",
            "run-1",
            "deal_deal_1",
            "deal_cycle_1",
            None,
            "final_round",
            "unknown",
            1,
            None,
            "exact",
            "[]",
            0,
        ],
    )
    conn.execute(
        "INSERT INTO events VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            "deal_event_1",
            "run-1",
            "deal_deal_1",
            "deal_cycle_1",
            "bid",
            "ioi_submitted",
            "2024-01-02",
            "ioi event",
            None,
            None,
            None,
            None,
            None,
        ],
    )
    conn.execute(
        "INSERT INTO event_actor_links VALUES (?, ?, ?, ?, ?, ?)",
        ["deal_link_1", "run-1", "deal_event_1", "deal_actor_2", "bid_submitter", None],
    )


def test_bidder_projection_emits_review_row_when_formality_substrate_missing() -> None:
    from sec_graph.judgments.derive import derive_judgments
    from sec_graph.project.bidder_rows import build_bidder_rows

    conn = connect(":memory:")
    init_schema(conn)
    _seed_bidder_projection_substrate_missing_formality(conn)

    derive_judgments(conn, run_id="run-1")
    rows = build_bidder_rows(conn, run_id="run-1", projection_name="bidder_cycle_baseline_v1")
    assert rows == [], "no bidder rows should project when formality substrate is missing"

    projection_review_rows = conn.execute(
        """
        SELECT reason_code FROM review_rows
        WHERE run_id = ?
          AND review_type = 'projection'
        """,
        ["run-1"],
    ).fetchall()
    reason_codes = {row[0] for row in projection_review_rows}
    assert "missing_formality_judgment" in reason_codes
