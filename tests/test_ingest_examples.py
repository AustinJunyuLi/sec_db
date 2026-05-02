import hashlib
import json
from pathlib import Path

from sec_graph.ingest.cleaning import clean_markdown
from sec_graph.ingest.pipeline import ingest_examples
from sec_graph.schema import connect, init_schema


def _paragraph_text(conn, slug: str) -> str:
    rows = conn.execute(
        """
        SELECT paragraph_text
        FROM paragraphs
        JOIN filings USING (filing_id)
        WHERE deal_slug = ?
        ORDER BY paragraph_id
        """,
        [slug],
    ).fetchall()
    return "\n".join(row[0] for row in rows)


def _row_hashes(conn, table_name: str) -> list[str]:
    rows = conn.execute(f"SELECT * FROM {table_name} ORDER BY 1").fetchall()
    payloads = [json.dumps(row, sort_keys=True, default=str) for row in rows]
    return [hashlib.sha256(payload.encode("utf-8")).hexdigest() for payload in payloads]


def test_cleaning_removes_only_explicit_noise_and_logs_offsets() -> None:
    raw = (
        "Background of the Merger\n\n"
        "COMMAND=ADD_BASECOLOR,\"Black\"\n"
        "Party X remained in the process.\n"
        "ZEQ.=5,SEQ=34,EFW=\"2224840\",CP=\"ZEP INC.\"\n"
        "Table of Contents\n"
        "27\n"
        "<!-- PAGE 35 -->\n"
    )

    cleaned = clean_markdown(raw)

    assert "Party X remained in the process." in cleaned.text
    assert "<!-- PAGE 35 -->" in cleaned.text
    assert "COMMAND=ADD_BASECOLOR" not in cleaned.text
    assert "ZEQ.=5" not in cleaned.text
    assert "Table of Contents" not in cleaned.text
    assert [removal.rule_id for removal in cleaned.removals] == [
        "printer_command",
        "zeq_banner",
        "table_of_contents",
        "isolated_folio",
    ]
    assert all(raw[removal.char_start:removal.char_end] == removal.text for removal in cleaned.removals)


def test_ingest_all_examples_preserves_page_markers_aliases_and_counts() -> None:
    conn = connect(":memory:")
    init_schema(conn)
    ingest_examples(conn, examples_dir=Path("data/examples"))

    expected_markers = {
        "petsmart-inc": range(29, 34),
        "providence-worcester": range(35, 44),
        "zep": range(35, 43),
        "saks": range(31, 37),
    }
    for slug, pages in expected_markers.items():
        text = _paragraph_text(conn, slug)
        for page in pages:
            assert f"<!-- PAGE {page} -->" in text

    combined = "\n".join(_paragraph_text(conn, slug) for slug in expected_markers)
    for alias in ("Industry Participant", "Party A", "G&W", "Party X", "Sponsor A", "Company H"):
        assert alias in combined

    assert (
        "fifty potential buyers (comprising twenty-eight strategic buyers and "
        "twenty-two financial buyers"
    ) in _paragraph_text(conn, "zep")

    span_count = conn.execute("SELECT count(*) FROM spans").fetchone()[0]
    paragraph_count = conn.execute("SELECT count(*) FROM paragraphs").fetchone()[0]
    assert span_count == paragraph_count


def test_ingest_examples_is_deterministic() -> None:
    first = connect(":memory:")
    second = connect(":memory:")
    for conn in (first, second):
        init_schema(conn)
        ingest_examples(conn, examples_dir=Path("data/examples"))

    for table_name in ("filings", "paragraphs", "spans"):
        assert _row_hashes(first, table_name) == _row_hashes(second, table_name)


def test_ingest_cli_writes_duckdb_to_explicit_path(tmp_path) -> None:
    from sec_graph.cli.ingest_cmd import main

    db_path = tmp_path / "pipeline.duckdb"
    assert main(["--all", "--db", str(db_path)]) == 0

    conn = connect(db_path)
    slugs = {
        row[0]
        for row in conn.execute("SELECT deal_slug FROM filings ORDER BY deal_slug").fetchall()
    }
    assert slugs == {"petsmart-inc", "providence-worcester", "saks", "zep"}
