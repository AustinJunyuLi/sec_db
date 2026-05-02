import datetime as dt
import hashlib
import json
from pathlib import Path

from pydantic import ValidationError

from sec_graph.schema import (
    CleanFiling,
    Paragraph,
    RunMetadata,
    Section,
    SourceSpan,
    SequenceAllocator,
    apply_ddl,
    connect,
    init_schema,
    make_id,
    quote_hash,
    validate_quote,
)
from sec_graph.schema import versions


def _table_names(conn) -> set[str]:
    return {
        row[0]
        for row in conn.execute(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'main'
            ORDER BY table_name
            """
        ).fetchall()
    }


def _row_hashes(conn, table_name: str) -> list[str]:
    rows = conn.execute(f"SELECT * FROM {table_name} ORDER BY 1").fetchall()
    payloads = [json.dumps(row, sort_keys=True, default=str) for row in rows]
    return [hashlib.sha256(payload.encode("utf-8")).hexdigest() for payload in payloads]


def _insert_smoke_evidence(conn) -> dict[str, list[object]]:
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
    section = Section(
        section_id="smoke_section_001",
        filing_id=filing.filing_id,
        section_name="Background of the Merger",
        char_start=text.index("Background of the Merger"),
        char_end=text.index("Reasons for the Merger"),
    )
    paragraph_texts = [
        "On January 5, 2024, Party A submitted an indication of interest.",
        "On January 12, 2024, Party B proposed $12.50 per share in cash.",
        "The board also contacted 15 financial buyers during the process.",
    ]
    cursor = 0
    paragraphs: list[Paragraph] = []
    spans: list[SourceSpan] = []
    for idx, paragraph_text in enumerate(paragraph_texts, start=1):
        char_start = text.index(paragraph_text, cursor)
        char_end = char_start + len(paragraph_text)
        cursor = char_end
        paragraph = Paragraph(
            paragraph_id=make_id("smoke", "para", idx),
            filing_id=filing.filing_id,
            section=section.section_name,
            page_hint=1 if idx < 3 else 2,
            char_start=char_start,
            char_end=char_end,
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
            char_start=char_start,
            char_end=char_end,
            quote_text=paragraph_text,
            quote_hash=quote_hash(paragraph_text),
        )
        paragraphs.append(paragraph)
        spans.append(span)

    metadata = RunMetadata(
        run_id="stage1a-smoke",
        schema_version=versions.SCHEMA_VERSION,
        parser_version=versions.PARSER_VERSION,
        ingest_version=versions.INGEST_VERSION,
        extract_version=versions.EXTRACT_VERSION,
        reconcile_version=versions.RECONCILE_VERSION,
        validate_version=versions.VALIDATE_VERSION,
        project_version=versions.PROJECT_VERSION,
        input_hashes={"smoke_filing.md": filing.raw_sha256},
        created_at=dt.datetime(2026, 5, 2, 12, 0, tzinfo=dt.UTC),
    )

    conn.execute(
        "INSERT INTO filings VALUES (?, ?, ?, ?, ?, ?, ?)",
        tuple(filing.model_dump().values()),
    )
    for paragraph in paragraphs:
        conn.execute(
            "INSERT INTO paragraphs VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            tuple(paragraph.model_dump().values()),
        )
    for span in spans:
        conn.execute(
            "INSERT INTO spans VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            tuple(span.model_dump().values()),
        )
    metadata_row = metadata.model_dump()
    metadata_row["input_hashes"] = json.dumps(metadata_row["input_hashes"], sort_keys=True)
    metadata_row["created_at"] = metadata_row["created_at"].isoformat()
    conn.execute(
        "INSERT INTO run_metadata VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        tuple(metadata_row.values()),
    )
    return {"filing": [filing], "section": [section], "paragraphs": paragraphs, "spans": spans}


def test_stage_versions_are_declared_integers() -> None:
    for name in (
        "PARSER_VERSION",
        "INGEST_VERSION",
        "EXTRACT_VERSION",
        "RECONCILE_VERSION",
        "VALIDATE_VERSION",
        "PROJECT_VERSION",
        "SCHEMA_VERSION",
    ):
        assert isinstance(getattr(versions, name), int)


def test_deterministic_id_helpers_are_stable() -> None:
    assert make_id("petsmart", "actor", 3) == "petsmart_actor_3"

    allocator = SequenceAllocator()
    assert allocator.next("petsmart", "actor") == "petsmart_actor_1"
    assert allocator.next("petsmart", "actor") == "petsmart_actor_2"
    assert allocator.next("petsmart", "event") == "petsmart_event_1"

    replay = SequenceAllocator()
    assert [replay.next("petsmart", "actor") for _ in range(2)] == [
        "petsmart_actor_1",
        "petsmart_actor_2",
    ]


def test_quote_hash_and_validation_handle_unicode_and_empty_spans() -> None:
    text = "Alpha\nParty A paid £12.50 per share.\nΩ"
    quote = "Party A paid £12.50 per share."
    start = text.index(quote)
    end = start + len(quote)

    assert quote_hash(quote) == hashlib.sha256(quote.encode("utf-8")).hexdigest()
    assert quote_hash("") == hashlib.sha256(b"").hexdigest()
    assert validate_quote(text, start, end, quote_hash(quote))
    assert not validate_quote(text, start, end, quote_hash("different"))


def test_source_span_requires_non_negotiable_stage1a_fields() -> None:
    payload = {
        "evidence_id": "smoke_evidence_1",
        "filing_id": "smoke_filing",
        "paragraph_id": "smoke_para_001",
        "char_start": 0,
        "char_end": 4,
        "quote_text": "test",
        "quote_hash": quote_hash("test"),
    }

    try:
        SourceSpan(**payload)
    except ValidationError as exc:
        missing = {error["loc"][0] for error in exc.errors()}
    else:  # pragma: no cover - this would mean the contract is not enforced.
        missing = set()

    assert {
        "span_basis",
        "span_kind",
        "parent_evidence_id",
        "created_by_stage",
    } <= missing


def test_init_schema_creates_only_stage1a_tables() -> None:
    conn = connect(":memory:")
    apply_ddl(conn, "CREATE TABLE ddl_probe (id INTEGER);")
    assert _table_names(conn) == {"ddl_probe"}

    conn = connect(":memory:")
    init_schema(conn)

    assert _table_names(conn) == {"filings", "paragraphs", "spans", "run_metadata"}


def test_models_round_trip_through_duckdb_and_validate_quote_hashes() -> None:
    conn = connect(":memory:")
    init_schema(conn)
    inserted = _insert_smoke_evidence(conn)
    text = Path("tests/fixtures/smoke_filing.md").read_text(encoding="utf-8")

    row = conn.execute("SELECT * FROM filings WHERE filing_id = ?", ["smoke_filing"]).fetchone()
    filing = CleanFiling.model_validate(dict(zip(CleanFiling.model_fields, row, strict=True)))
    assert filing == inserted["filing"][0]

    paragraph_row = conn.execute(
        "SELECT * FROM paragraphs WHERE paragraph_id = ?",
        [inserted["paragraphs"][0].paragraph_id],
    ).fetchone()
    paragraph = Paragraph.model_validate(dict(zip(Paragraph.model_fields, paragraph_row, strict=True)))
    assert paragraph == inserted["paragraphs"][0]

    span_row = conn.execute(
        "SELECT * FROM spans WHERE evidence_id = ?",
        [inserted["spans"][0].evidence_id],
    ).fetchone()
    span = SourceSpan.model_validate(dict(zip(SourceSpan.model_fields, span_row, strict=True)))
    assert span == inserted["spans"][0]

    metadata_row = conn.execute(
        "SELECT * FROM run_metadata WHERE run_id = ?",
        ["stage1a-smoke"],
    ).fetchone()
    metadata_payload = dict(zip(RunMetadata.model_fields, metadata_row, strict=True))
    metadata_payload["input_hashes"] = json.loads(metadata_payload["input_hashes"])
    metadata = RunMetadata.model_validate(metadata_payload)
    assert metadata.run_id == "stage1a-smoke"
    assert metadata.input_hashes["smoke_filing.md"] == inserted["filing"][0].raw_sha256

    paragraph_count = conn.execute("SELECT count(*) FROM paragraphs").fetchone()[0]
    span_count = conn.execute("SELECT count(*) FROM spans").fetchone()[0]
    assert paragraph_count == 3
    assert span_count == 3

    for span in inserted["spans"]:
        assert quote_hash(span.quote_text) == span.quote_hash
        assert validate_quote(text, span.char_start, span.char_end, span.quote_hash)


def test_smoke_fixture_exercises_page_markers_and_stage1a_determinism() -> None:
    smoke_text = Path("tests/fixtures/smoke_filing.md").read_text(encoding="utf-8")
    assert smoke_text.count("<!-- PAGE ") >= 2

    first = connect(":memory:")
    second = connect(":memory:")
    for conn in (first, second):
        init_schema(conn)
        _insert_smoke_evidence(conn)

    for table_name in ("filings", "paragraphs", "spans", "run_metadata"):
        assert _row_hashes(first, table_name) == _row_hashes(second, table_name)
