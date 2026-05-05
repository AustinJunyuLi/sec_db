from pathlib import Path

import duckdb

from sec_graph.project.summaries import proof_summary
from sec_graph.schema import evidence_fingerprint, init_schema, quote_hash


def test_review_flag_changes_verdict_to_review_required(tmp_path: Path) -> None:
    conn = duckdb.connect(":memory:")
    init_schema(conn)
    _seed_valid_minimal_run(conn, tmp_path)
    conn.execute(
        "INSERT INTO review_flags VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            "deal_reviewflag_1",
            "run-1",
            "deal",
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            "missed_supported_obligation",
            "review",
            "test_review",
            "review needed",
            None,
            None,
            None,
            "Review the missed supported obligation.",
            True,
        ],
    )

    proof = proof_summary(conn, run_id="run-1", projection_name="bidder_cycle_v1")

    assert proof["verdict"] == "REVIEW_REQUIRED"
    assert proof["review_flag_count"] == 1
    assert proof["blocking_flag_count"] == 0


def test_blocking_flag_changes_verdict_to_unsound(tmp_path: Path) -> None:
    conn = duckdb.connect(":memory:")
    init_schema(conn)
    _seed_valid_minimal_run(conn, tmp_path)
    conn.execute(
        "INSERT INTO review_flags VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            "deal_reviewflag_1",
            "run-1",
            "deal",
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            "unsupported_claim",
            "blocking",
            "test_blocking",
            "blocking issue",
            None,
            None,
            None,
            "Review the unsupported claim.",
            True,
        ],
    )

    proof = proof_summary(conn, run_id="run-1", projection_name="bidder_cycle_v1")

    assert proof["verdict"] == "UNSOUND"
    assert proof["blocking_flag_count"] == 1


def _seed_valid_minimal_run(conn: duckdb.DuckDBPyConnection, tmp_path: Path) -> None:
    text = "Target sale process source."
    source_path = tmp_path / "deal.md"
    source_path.write_text(text, encoding="utf-8")
    text_hash = quote_hash(text)
    conn.execute(
        "INSERT INTO filings VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        ["deal_filing_1", "deal", str(source_path), text_hash, 1, None, 1, "target_full_proxy"],
    )
    conn.execute(
        "INSERT INTO paragraphs VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        ["deal_para_1", "deal_filing_1", "Background of the Merger", None, 0, len(text), text, text_hash],
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
            len(text),
            text,
            text_hash,
            evidence_fingerprint("deal_filing_1", 0, len(text), text_hash),
        ],
    )
    conn.execute(
        "INSERT INTO deals VALUES (?, ?, ?, ?, ?)",
        ["deal_deal_1", "run-1", "deal", "deal_actor_1", "2024-01-01"],
    )
    conn.execute(
        "INSERT INTO actors VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ["deal_actor_1", "run-1", "deal_deal_1", "Target", "organization", "named", None, None, None, None],
    )
    conn.execute(
        "INSERT INTO process_cycles VALUES (?, ?, ?, ?, ?, ?, ?)",
        ["deal_cycle_1", "run-1", "deal_deal_1", 1, "primary sale process", "2024-01-01", "2024-01-02"],
    )
    for table, row_id in (
        ("deals", "deal_deal_1"),
        ("actors", "deal_actor_1"),
        ("process_cycles", "deal_cycle_1"),
    ):
        conn.execute("INSERT INTO row_evidence VALUES (?, ?, ?, ?)", [table, row_id, "deal_evidence_1", 1])
