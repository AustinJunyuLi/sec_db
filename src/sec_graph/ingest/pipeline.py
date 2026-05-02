"""Ingest example filing markdown into DuckDB evidence tables."""

from __future__ import annotations

import datetime as dt
import json
from dataclasses import dataclass
from pathlib import Path

import duckdb

from sec_graph.schema import CleanFiling, Paragraph, RunMetadata, connect, init_schema, make_id, quote_hash
from sec_graph.schema import versions

from .cleaning import clean_markdown
from .paragraphs import split_paragraphs
from .sections import assign_sections
from .spans import paragraph_seed_span

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_EXAMPLES_DIR = REPO_ROOT / "data" / "examples"


@dataclass(frozen=True)
class IngestSource:
    slug: str
    source_path: Path
    manifest_path: Path | None = None


def example_sources(examples_dir: Path = DEFAULT_EXAMPLES_DIR) -> list[IngestSource]:
    paths = sorted(examples_dir.glob("*.md"))
    if not paths:
        raise FileNotFoundError(f"no example markdown files found under {examples_dir}")
    return [IngestSource(slug=path.stem, source_path=path) for path in paths if path.name != "README.md"]


def _insert_metadata(conn: duckdb.DuckDBPyConnection, run_id: str, input_hashes: dict[str, str]) -> None:
    metadata = RunMetadata(
        run_id=run_id,
        schema_version=versions.SCHEMA_VERSION,
        parser_version=versions.PARSER_VERSION,
        ingest_version=versions.INGEST_VERSION,
        extract_version=versions.EXTRACT_VERSION,
        reconcile_version=versions.RECONCILE_VERSION,
        validate_version=versions.VALIDATE_VERSION,
        project_version=versions.PROJECT_VERSION,
        input_hashes=input_hashes,
        created_at=dt.datetime.now(dt.UTC),
    )
    payload = metadata.model_dump()
    payload["input_hashes"] = json.dumps(payload["input_hashes"], sort_keys=True)
    payload["created_at"] = payload["created_at"].isoformat()
    conn.execute("INSERT INTO run_metadata VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", tuple(payload.values()))


def ingest_source(conn: duckdb.DuckDBPyConnection, source: IngestSource) -> CleanFiling:
    raw_text = source.source_path.read_text(encoding="utf-8")
    cleaned = clean_markdown(raw_text)
    blocks = split_paragraphs(cleaned)
    sections = assign_sections([block.text for block in blocks])
    filing_id = make_id(source.slug, "filing", 1)
    page_count = raw_text.count("<!-- PAGE ")
    filing = CleanFiling(
        filing_id=filing_id,
        deal_slug=source.slug,
        source_path=str(source.source_path),
        raw_sha256=quote_hash(raw_text),
        parser_version=versions.PARSER_VERSION,
        page_count=page_count,
        section_count=len({section for section in sections if section != "unknown_section"}),
    )
    conn.execute("DELETE FROM spans WHERE filing_id = ?", [filing_id])
    conn.execute("DELETE FROM paragraphs WHERE filing_id = ?", [filing_id])
    conn.execute("DELETE FROM filings WHERE filing_id = ?", [filing_id])
    conn.execute("INSERT INTO filings VALUES (?, ?, ?, ?, ?, ?, ?)", tuple(filing.model_dump().values()))
    for idx, (block, section) in enumerate(zip(blocks, sections, strict=True), start=1):
        paragraph = Paragraph(
            paragraph_id=make_id(source.slug, "para", idx),
            filing_id=filing_id,
            section=section,
            page_hint=block.page_hint,
            char_start=block.char_start,
            char_end=block.char_end,
            paragraph_text=block.text,
            paragraph_hash=quote_hash(block.text),
        )
        span = paragraph_seed_span(source.slug, filing_id, paragraph.paragraph_id, idx, block)
        conn.execute("INSERT INTO paragraphs VALUES (?, ?, ?, ?, ?, ?, ?, ?)", tuple(paragraph.model_dump().values()))
        conn.execute("INSERT INTO spans VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", tuple(span.model_dump().values()))
    return filing


def ingest_examples(conn: duckdb.DuckDBPyConnection, examples_dir: Path = DEFAULT_EXAMPLES_DIR) -> list[CleanFiling]:
    sources = example_sources(examples_dir)
    filings = [ingest_source(conn, source) for source in sources]
    conn.execute("DELETE FROM run_metadata WHERE run_id = ?", ["ingest-examples"])
    _insert_metadata(conn, "ingest-examples", {filing.deal_slug: filing.raw_sha256 for filing in filings})
    return filings


def ingest_examples_to_db(db_path: Path, examples_dir: Path = DEFAULT_EXAMPLES_DIR) -> list[CleanFiling]:
    if db_path.exists():
        db_path.unlink()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = connect(db_path)
    init_schema(conn)
    return ingest_examples(conn, examples_dir=examples_dir)
