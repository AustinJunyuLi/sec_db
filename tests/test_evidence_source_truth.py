"""Phase 4 source-truth contract tests.

Validation must prove that every span maps back to actual raw source bytes,
not just internally consistent stored quote text. Non-paragraph spans must
chain to a parent paragraph seed.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from sec_graph.ingest.cleaning import clean_markdown
from sec_graph.ingest.paragraphs import split_paragraphs
from sec_graph.schema import (
    CleanFiling,
    Paragraph,
    RunMetadata,
    SourceSpan,
    connect,
    init_schema,
    make_id,
    quote_hash,
)
from sec_graph.schema import versions
from sec_graph.validate.integrity import validate_database


def _seed_filing(
    conn,
    *,
    raw_text: str,
    source_path: str,
    slug: str = "srctruth",
) -> tuple[str, str]:
    filing_id = make_id(slug, "filing", 1)
    filing = CleanFiling(
        filing_id=filing_id,
        deal_slug=slug,
        source_path=source_path,
        raw_sha256=quote_hash(raw_text),
        parser_version=versions.PARSER_VERSION,
        page_count=None,
        section_count=1,
        process_scope="target_full_proxy",
    )
    metadata = RunMetadata(
        run_id="srctruth-run",
        schema_version=versions.SCHEMA_VERSION,
        parser_version=versions.PARSER_VERSION,
        ingest_version=versions.INGEST_VERSION,
        extract_version=versions.EXTRACT_VERSION,
        reconcile_version=versions.RECONCILE_VERSION,
        validate_version=versions.VALIDATE_VERSION,
        project_version=versions.PROJECT_VERSION,
        input_hashes={slug: filing.raw_sha256},
        created_at=dt.datetime(2026, 5, 2, 12, 0, tzinfo=dt.UTC),
    )
    conn.execute(
        "INSERT INTO filings VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        tuple(filing.model_dump().values()),
    )
    payload = metadata.model_dump()
    payload["input_hashes"] = json.dumps(payload["input_hashes"], sort_keys=True)
    payload["created_at"] = payload["created_at"].isoformat()
    conn.execute(
        "INSERT INTO run_metadata VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        tuple(payload.values()),
    )
    return filing_id, slug


def test_validate_database_rejects_span_coordinates_that_do_not_match_raw_source(
    tmp_path: Path,
) -> None:
    raw_text = (
        "On January 5, 2024, Party A submitted an indication of interest.\n\n"
        "On January 12, 2024, Party B proposed $12.50 per share.\n"
    )
    raw_root = tmp_path / "raw_root"
    raw_root.mkdir()
    source_file = raw_root / "srctruth.md"
    source_file.write_text(raw_text, encoding="utf-8")

    conn = connect(":memory:")
    init_schema(conn)
    filing_id, slug = _seed_filing(
        conn, raw_text=raw_text, source_path=str(source_file)
    )

    para_text = "On January 5, 2024, Party A submitted an indication of interest."
    para_start = raw_text.index(para_text)
    para_end = para_start + len(para_text)
    paragraph = Paragraph(
        paragraph_id=make_id(slug, "para", 1),
        filing_id=filing_id,
        section="Background of the Merger",
        page_hint=None,
        char_start=para_start,
        char_end=para_end,
        paragraph_text=para_text,
        paragraph_hash=quote_hash(para_text),
    )
    seed_span = SourceSpan(
        evidence_id=make_id(slug, "evidence", 1),
        filing_id=filing_id,
        paragraph_id=paragraph.paragraph_id,
        span_basis="raw_md",
        span_kind="paragraph_seed",
        parent_evidence_id=None,
        created_by_stage="ingest",
        char_start=para_start,
        char_end=para_end,
        quote_text=para_text,
        quote_hash=quote_hash(para_text),
    )

    # Forge an extract span: stored quote and hash agree with each other but
    # do NOT match the slice of raw_text at the recorded coordinates.
    forged_text = "Party Z paid $99.00 per share."
    forged_start = para_start
    forged_end = para_start + 5  # Clearly < len(forged_text)
    forged_span = SourceSpan(
        evidence_id=make_id(slug, "evidence", 2),
        filing_id=filing_id,
        paragraph_id=paragraph.paragraph_id,
        span_basis="raw_md",
        span_kind="phrase",
        parent_evidence_id=seed_span.evidence_id,
        created_by_stage="extract",
        char_start=forged_start,
        char_end=forged_end,
        quote_text=forged_text,
        quote_hash=quote_hash(forged_text),
    )

    conn.execute(
        "INSERT INTO paragraphs VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        tuple(paragraph.model_dump().values()),
    )
    for span in (seed_span, forged_span):
        conn.execute(
            "INSERT INTO spans VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            tuple(span.model_dump().values()),
        )

    result = validate_database(conn, raw_source_root=raw_root)

    matched = [
        failure
        for failure in result.hard_failures
        if failure.row_id == forged_span.evidence_id
    ]
    assert matched, (
        "validate_database must report the forged span as a source-truth failure; "
        f"failures={result.hard_failures}"
    )
    assert filing_id in matched[0].detail or "source slice" in matched[0].detail
    assert "source slice" in matched[0].detail or "does not equal" in matched[0].detail


def test_split_paragraphs_does_not_mark_cleaned_noncontiguous_text_as_raw_md() -> None:
    raw = (
        "Background of the Merger\n\n"
        "Party X met with the board.\n"
        "COMMAND=ADD_BASECOLOR,\"Black\"\n"
        "Party X then submitted an indication.\n\n"
    )

    cleaned = clean_markdown(raw)
    blocks = split_paragraphs(cleaned)

    offending: list[tuple[int, str, str]] = []
    for idx, block in enumerate(blocks):
        raw_slice = raw[block.char_start:block.char_end]
        if block.text != raw_slice:
            offending.append((idx, block.text, raw_slice))

    assert not offending, (
        "split_paragraphs returned blocks whose text does not equal the raw "
        f"source slice at the recorded coordinates: {offending}"
    )


def test_extract_spans_require_parent_paragraph_seed() -> None:
    base_kwargs = dict(
        evidence_id="srctruth_evidence_5",
        filing_id="srctruth_filing_1",
        paragraph_id="srctruth_para_1",
        created_by_stage="extract",
        char_start=0,
        char_end=4,
        quote_text="test",
        quote_hash=quote_hash("test"),
    )

    for span_kind in ("sentence", "clause", "phrase"):
        with pytest.raises(ValidationError) as exc_info:
            SourceSpan(
                **base_kwargs,
                span_basis="raw_md",
                span_kind=span_kind,
                parent_evidence_id=None,
            )
        message = str(exc_info.value)
        assert "parent_evidence_id" in message, (
            f"span_kind={span_kind} must reject missing parent_evidence_id; "
            f"got: {message}"
        )

    # Paragraph seeds are still allowed to have no parent.
    SourceSpan(
        **base_kwargs,
        span_basis="raw_md",
        span_kind="paragraph_seed",
        parent_evidence_id=None,
    )
