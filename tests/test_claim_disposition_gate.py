from pathlib import Path

import duckdb

from sec_graph.extract.disposition import dispose_claims_for_filing
from sec_graph.reconcile.pipeline import reconcile_filing
from sec_graph.schema import evidence_fingerprint, init_schema, quote_hash


def _conn() -> duckdb.DuckDBPyConnection:
    conn = duckdb.connect(":memory:")
    init_schema(conn)
    return conn


def test_unsupported_bid_claim_is_rejected_before_reconcile() -> None:
    conn = _conn()
    _seed_minimal_bid_claim(
        conn,
        quote_text="Party A submitted a proposal.",
        bidder_label="Party A",
        bid_date="2024-01-02",
        bid_value=10.0,
    )

    dispose_claims_for_filing(conn, filing_id="deal_filing_1", run_id="run-1")

    row = conn.execute(
        "SELECT disposition, reason_code FROM claim_dispositions WHERE claim_id = 'deal_claim_1'"
    ).fetchone()
    assert row == ("rejected_unsupported", "bid_quote_missing_date_or_value")

    flags = conn.execute("SELECT flag_type, severity FROM review_flags").fetchall()
    assert flags == [("unsupported_claim", "blocking")]


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


def _seed_minimal_bid_claim(
    conn: duckdb.DuckDBPyConnection,
    *,
    quote_text: str,
    bidder_label: str,
    bid_date: str,
    bid_value: float,
) -> None:
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
        ["deal_claim_1", bidder_label, bid_date, bid_value, None, None, "USD_per_share", "cash", "initial"],
    )
