"""Tests for the single semantic gate in extract.disposition."""

from __future__ import annotations

from pathlib import Path

import duckdb

from sec_graph.extract.disposition import (
    dispose_claims_for_filing,
    finalize_coverage_after_disposition,
)
from sec_graph.reconcile.pipeline import reconcile_filing
from sec_graph.schema import evidence_fingerprint, init_schema, quote_hash


def _conn() -> duckdb.DuckDBPyConnection:
    conn = duckdb.connect(":memory:")
    init_schema(conn)
    return conn


def test_unsupported_bid_claim_is_rejected_and_recorded_as_review_row() -> None:
    conn = _conn()
    _seed_minimal_bid_claim(
        conn,
        quote_text="Party A submitted a proposal.",
        bidder_label="Party A",
        bid_date="2024-01-02",
        bid_value=10.0,
    )

    dispose_claims_for_filing(conn, filing_id="deal_filing_1", run_id="run-1")

    disposition = conn.execute(
        "SELECT disposition, reason_code FROM claim_dispositions WHERE claim_id = 'deal_claim_1'"
    ).fetchone()
    assert disposition[0] == "rejected_unsupported"
    assert "bid_quote_missing" in disposition[1]

    rows = conn.execute(
        "SELECT review_status, review_type, severity FROM review_rows"
    ).fetchall()
    assert rows == [("open", "claim_disposition", "review")]


def test_relation_quote_must_name_subject_actor() -> None:
    """A relation quote that does not name the subject actor is quarantined."""

    conn = _conn()
    _seed_minimal_relation_claim(
        conn,
        # The subject is "Parent" but the quote does not name it.
        quote_text="Buyer Group was a member of an acquisition vehicle.",
        subject_label="Parent",
        object_label="Buyer Group",
        relation_type="acquisition_vehicle_of",
    )

    dispose_claims_for_filing(conn, filing_id="deal_filing_1", run_id="run-1")

    disposition = conn.execute(
        "SELECT disposition, reason_code FROM claim_dispositions WHERE claim_id = 'deal_claim_2'"
    ).fetchone()
    assert disposition[0] == "rejected_unsupported"
    assert "subject_label" in disposition[1]

    review = conn.execute(
        "SELECT review_status, review_type, severity FROM review_rows WHERE claim_id = 'deal_claim_2'"
    ).fetchone()
    assert review == ("open", "claim_disposition", "review")


def test_bid_quote_with_only_later_that_same_day_does_not_support_explicit_bid_date() -> None:
    """A bid quote saying only "later that same day" cannot support an
    explicit ``bid_date`` unless the evidence includes the date."""

    conn = _conn()
    _seed_minimal_bid_claim(
        conn,
        quote_text="Party A submitted a proposal of $10.00 per share later that same day.",
        bidder_label="Party A",
        bid_date="2024-01-02",
        bid_value=10.0,
    )

    dispose_claims_for_filing(conn, filing_id="deal_filing_1", run_id="run-1")

    disposition = conn.execute(
        "SELECT disposition, reason_code FROM claim_dispositions WHERE claim_id = 'deal_claim_1'"
    ).fetchone()
    assert disposition[0] == "rejected_unsupported"
    assert "date" in disposition[1]


def test_count_obligation_does_not_become_covered_through_unsupported_count_claim() -> None:
    conn = _conn()
    _seed_minimal_count_claim(
        conn,
        quote_text="The board met on January 5.",  # no count language
        process_stage="contacted",
        actor_class="financial",
        count_min=10,
    )

    dispose_claims_for_filing(conn, filing_id="deal_filing_1", run_id="run-1")
    finalize_coverage_after_disposition(
        conn, run_id="run-1", filing_id="deal_filing_1"
    )

    coverage = conn.execute(
        "SELECT result, claim_count FROM coverage_results WHERE obligation_id = 'deal_obligation_1'"
    ).fetchone()
    # Not claims_emitted because the count claim is not supported.
    assert coverage[0] != "claims_emitted"
    assert coverage[1] == 0


def test_reconcile_refuses_undisposed_claims() -> None:
    conn = _conn()
    _seed_minimal_bid_claim(
        conn,
        quote_text="On January 2, 2024, Party A submitted a proposal of $10.00 per share.",
        bidder_label="Party A",
        bid_date="2024-01-02",
        bid_value=10.0,
    )

    try:
        reconcile_filing(conn, filing_id="deal_filing_1", run_id="run-1")
    except ValueError as exc:
        assert "undisposed supported claims" in str(exc)
    else:
        raise AssertionError("reconcile must reject undisposed claims")


# --------------------------------------------------------------------------- #
# Seeding helpers                                                             #
# --------------------------------------------------------------------------- #


def _seed_filing(
    conn: duckdb.DuckDBPyConnection, *, quote_text: str
) -> tuple[str, str]:
    raw_hash = quote_hash(quote_text)
    fingerprint = evidence_fingerprint("deal_filing_1", 0, len(quote_text), raw_hash)
    conn.execute(
        "INSERT INTO filings VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        [
            "deal_filing_1",
            "deal",
            str(Path("example.md")),
            raw_hash,
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
            "Background of the Merger",
            None,
            0,
            len(quote_text),
            quote_text,
            raw_hash,
        ],
    )
    conn.execute(
        "INSERT INTO spans VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            "deal_evidence_1",
            "deal_filing_1",
            "deal_para_1",
            "raw_md",
            "paragraph_seed",
            None,
            "ingest",
            0,
            len(quote_text),
            quote_text,
            raw_hash,
            fingerprint,
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
    return raw_hash, fingerprint


def _seed_minimal_bid_claim(
    conn: duckdb.DuckDBPyConnection,
    *,
    quote_text: str,
    bidder_label: str,
    bid_date: str,
    bid_value: float,
) -> None:
    raw_hash, _ = _seed_filing(conn, quote_text=quote_text)
    conn.execute(
        "INSERT INTO claims VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            "deal_claim_1",
            "run-1",
            "deal_filing_1",
            "deal",
            "deal_region_1",
            "linkflow",
            "bid",
            "high",
            quote_text,
            None,
            quote_text,
            raw_hash,
            "validated",
            1,
        ],
    )
    conn.execute("INSERT INTO claim_evidence VALUES (?, ?, ?)", ["deal_claim_1", "deal_evidence_1", 1])
    conn.execute(
        "INSERT INTO bid_claims VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            "deal_claim_1",
            bidder_label,
            bid_date,
            bid_value,
            None,
            None,
            "USD_per_share",
            "cash",
            "initial",
        ],
    )


def _seed_minimal_relation_claim(
    conn: duckdb.DuckDBPyConnection,
    *,
    quote_text: str,
    subject_label: str,
    object_label: str,
    relation_type: str,
) -> None:
    raw_hash, _ = _seed_filing(conn, quote_text=quote_text)
    conn.execute(
        "INSERT INTO claims VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            "deal_claim_2",
            "run-1",
            "deal_filing_1",
            "deal",
            "deal_region_1",
            "linkflow",
            "actor_relation",
            "high",
            quote_text,
            None,
            quote_text,
            raw_hash,
            "validated",
            2,
        ],
    )
    conn.execute(
        "INSERT INTO claim_evidence VALUES (?, ?, ?)", ["deal_claim_2", "deal_evidence_1", 1]
    )
    conn.execute(
        "INSERT INTO actor_relation_claims VALUES (?, ?, ?, ?, ?, ?)",
        ["deal_claim_2", subject_label, object_label, relation_type, None, None],
    )


def _seed_minimal_count_claim(
    conn: duckdb.DuckDBPyConnection,
    *,
    quote_text: str,
    process_stage: str,
    actor_class: str,
    count_min: int,
) -> None:
    raw_hash, _ = _seed_filing(conn, quote_text=quote_text)
    # Add a count obligation so finalize_coverage_after_disposition has work to do.
    conn.execute(
        "INSERT INTO coverage_obligations VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            "deal_obligation_1",
            "run-1",
            "deal_region_1",
            "deal_filing_1",
            "deal",
            "participation_count",
            "contacted_count",
            "Number of parties contacted.",
            "important",
            "applicable",
            "process_scope:contacted",
            "[]",
            True,
        ],
    )
    conn.execute(
        "INSERT INTO claims VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            "deal_claim_3",
            "run-1",
            "deal_filing_1",
            "deal",
            "deal_region_1",
            "linkflow",
            "participation_count",
            "high",
            quote_text,
            None,
            quote_text,
            raw_hash,
            "validated",
            3,
        ],
    )
    conn.execute(
        "INSERT INTO claim_coverage_links VALUES (?, ?, ?, ?, ?, ?)",
        [
            "deal_claim_3",
            "deal_obligation_1",
            "run-1",
            "deal",
            "participation_count",
            True,
        ],
    )
    conn.execute("INSERT INTO claim_evidence VALUES (?, ?, ?)", ["deal_claim_3", "deal_evidence_1", 1])
    conn.execute(
        "INSERT INTO participation_count_claims VALUES (?, ?, ?, ?, ?, ?)",
        ["deal_claim_3", process_stage, actor_class, count_min, None, "exact"],
    )
