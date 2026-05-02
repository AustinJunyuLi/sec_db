import datetime as dt
import hashlib
import json
from pathlib import Path

from sec_graph.extract.rules import run_rules
from sec_graph.schema import CleanFiling, Paragraph, RunMetadata, SourceSpan, connect, init_schema, make_id, quote_hash, validate_quote
from sec_graph.schema import versions


def _row_hashes(conn, table_name: str, where: str = "") -> list[str]:
    rows = conn.execute(f"SELECT * FROM {table_name} {where} ORDER BY 1").fetchall()
    payloads = [json.dumps(row, sort_keys=True, default=str) for row in rows]
    return [hashlib.sha256(payload.encode("utf-8")).hexdigest() for payload in payloads]


def _seed_smoke_paragraphs(conn) -> None:
    text = Path("tests/fixtures/smoke_filing.md").read_text(encoding="utf-8")
    filing = CleanFiling(
        filing_id="smoke_filing",
        deal_slug="smoke",
        source_path="tests/fixtures/smoke_filing.md",
        raw_sha256=quote_hash(text),
        parser_version=versions.PARSER_VERSION,
        page_count=2,
        section_count=1,
    )
    conn.execute("INSERT INTO filings VALUES (?, ?, ?, ?, ?, ?, ?)", tuple(filing.model_dump().values()))
    paragraph_texts = [
        "On January 5, 2024, Party A submitted an indication of interest.",
        "On January 12, 2024, Party B proposed $12.50 per share in cash.",
        "The board also contacted 15 financial buyers during the process.",
    ]
    cursor = 0
    for idx, paragraph_text in enumerate(paragraph_texts, start=1):
        start = text.index(paragraph_text, cursor)
        end = start + len(paragraph_text)
        cursor = end
        paragraph = Paragraph(
            paragraph_id=make_id("smoke", "para", idx),
            filing_id=filing.filing_id,
            section="Background of the Merger",
            page_hint=1 if idx < 3 else 2,
            char_start=start,
            char_end=end,
            paragraph_text=paragraph_text,
            paragraph_hash=quote_hash(paragraph_text),
        )
        span = SourceSpan(
            evidence_id=make_id("smoke", "evidence", idx),
            filing_id=filing.filing_id,
            paragraph_id=paragraph.paragraph_id,
            span_basis="raw_md",
            span_kind="paragraph_seed",
            parent_evidence_id=None,
            created_by_stage="ingest",
            char_start=start,
            char_end=end,
            quote_text=paragraph_text,
            quote_hash=quote_hash(paragraph_text),
        )
        conn.execute("INSERT INTO paragraphs VALUES (?, ?, ?, ?, ?, ?, ?, ?)", tuple(paragraph.model_dump().values()))
        conn.execute("INSERT INTO spans VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", tuple(span.model_dump().values()))
    metadata = RunMetadata(
        run_id="extract-smoke",
        schema_version=versions.SCHEMA_VERSION,
        parser_version=versions.PARSER_VERSION,
        ingest_version=versions.INGEST_VERSION,
        extract_version=versions.EXTRACT_VERSION,
        reconcile_version=versions.RECONCILE_VERSION,
        validate_version=versions.VALIDATE_VERSION,
        project_version=versions.PROJECT_VERSION,
        input_hashes={"smoke": filing.raw_sha256},
        created_at=dt.datetime(2026, 5, 2, 15, 0, tzinfo=dt.UTC),
    )
    payload = metadata.model_dump()
    payload["input_hashes"] = json.dumps(payload["input_hashes"], sort_keys=True)
    payload["created_at"] = payload["created_at"].isoformat()
    conn.execute("INSERT INTO run_metadata VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", tuple(payload.values()))


def _loaded_conn():
    conn = connect(":memory:")
    init_schema(conn)
    _seed_smoke_paragraphs(conn)
    return conn


def _candidate_projection(conn) -> list[dict[str, object]]:
    rows = conn.execute(
        """
        SELECT candidate_type, raw_value, normalized_value, confidence, status
        FROM candidates
        ORDER BY candidate_id
        """
    ).fetchall()
    return [
        {
            "candidate_type": row[0],
            "raw_value": row[1],
            "normalized_value": row[2],
            "confidence": row[3],
            "status": row[4],
        }
        for row in rows
    ]


def test_smoke_rules_match_golden_candidates() -> None:
    conn = _loaded_conn()
    run_rules(conn, filing_id="smoke_filing")

    expected = json.loads(Path("tests/fixtures/extract/smoke_candidates.json").read_text(encoding="utf-8"))
    assert _candidate_projection(conn) == expected


def test_candidates_are_evidence_bound_to_extract_spans_inside_parent_paragraphs() -> None:
    conn = _loaded_conn()
    run_rules(conn, filing_id="smoke_filing")
    smoke_text = Path("tests/fixtures/smoke_filing.md").read_text(encoding="utf-8")

    for candidate_id, evidence_ids in conn.execute("SELECT candidate_id, evidence_ids FROM candidates").fetchall():
        assert evidence_ids, candidate_id
        for evidence_id in evidence_ids:
            span = conn.execute(
                """
                SELECT child.char_start, child.char_end, child.quote_hash, child.parent_evidence_id,
                       parent.char_start, parent.char_end
                FROM spans AS child
                JOIN spans AS parent ON child.parent_evidence_id = parent.evidence_id
                WHERE child.evidence_id = ?
                """,
                [evidence_id],
            ).fetchone()
            assert span is not None
            child_start, child_end, quote_hash_value, parent_id, parent_start, parent_end = span
            assert parent_id is not None
            assert parent_start <= child_start <= child_end <= parent_end
            assert validate_quote(smoke_text, child_start, child_end, quote_hash_value)


def test_rule_extraction_is_deterministic() -> None:
    first = _loaded_conn()
    second = _loaded_conn()
    for conn in (first, second):
        run_rules(conn, filing_id="smoke_filing")

    assert _row_hashes(first, "candidates") == _row_hashes(second, "candidates")
    assert _row_hashes(first, "spans", "WHERE created_by_stage = 'extract'") == _row_hashes(
        second,
        "spans",
        "WHERE created_by_stage = 'extract'",
    )
