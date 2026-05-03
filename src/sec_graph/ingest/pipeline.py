"""Ingest example filing markdown into DuckDB evidence tables."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import duckdb

from sec_graph.schema import CleanFiling, Paragraph, connect, init_schema, make_id, quote_hash
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


def filing_sources(slugs: list[str], filings_dir: Path | None = None) -> list[IngestSource]:
    base_dir = filings_dir or REPO_ROOT / "data" / "filings"
    sources: list[IngestSource] = []
    for slug in slugs:
        source_path = base_dir / slug / "raw.md"
        manifest_path = base_dir / slug / "manifest.json"
        if not source_path.exists() or not manifest_path.exists():
            raise FileNotFoundError(f"missing fetched filing artifacts for {slug} under {base_dir / slug}")
        sources.append(IngestSource(slug=slug, source_path=source_path, manifest_path=manifest_path))
    return sources


def _process_scope(source: IngestSource) -> str:
    if source.manifest_path is None:
        return "target_full_proxy"
    manifest = json.loads(source.manifest_path.read_text(encoding="utf-8"))
    form_type = str(
        manifest.get("source", {}).get("filing_form_type")
        or manifest.get("source", {}).get("form_type", "")
    ).upper()
    if form_type in {"DEFM14A", "PREM14A"}:
        return "target_full_proxy"
    if form_type in {"SC TO-T", "SC TO-T/A"}:
        return "bidder_partial_schedule_to"
    if form_type in {"DEFA14A", "DEFA14A/A"}:
        return "amendment_only"
    raise ValueError(f"cannot map form_type {form_type!r} to process_scope for {source.slug}")


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
        process_scope=_process_scope(source),
    )
    conn.execute("DELETE FROM spans WHERE filing_id = ?", [filing_id])
    conn.execute("DELETE FROM paragraphs WHERE filing_id = ?", [filing_id])
    conn.execute("DELETE FROM filings WHERE filing_id = ?", [filing_id])
    conn.execute("INSERT INTO filings VALUES (?, ?, ?, ?, ?, ?, ?, ?)", tuple(filing.model_dump().values()))
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
        conn.execute("INSERT INTO spans VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", tuple(span.model_dump().values()))
    return filing


def ingest_examples(conn: duckdb.DuckDBPyConnection, examples_dir: Path = DEFAULT_EXAMPLES_DIR) -> list[CleanFiling]:
    sources = example_sources(examples_dir)
    return ingest_sources(conn, sources, run_id="ingest-examples")


def ingest_sources(
    conn: duckdb.DuckDBPyConnection,
    sources: list[IngestSource],
    *,
    run_id: str = "ingest-sources",
) -> list[CleanFiling]:
    del run_id
    filings = [ingest_source(conn, source) for source in sources]
    return filings


def ingest_examples_to_db(db_path: Path, examples_dir: Path = DEFAULT_EXAMPLES_DIR, *, fresh: bool = False) -> list[CleanFiling]:
    if db_path.exists():
        if not fresh:
            raise FileExistsError(f"{db_path} exists; pass fresh=True to replace it")
        db_path.unlink()
    sources = example_sources(examples_dir)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = connect(db_path)
    init_schema(conn)
    return ingest_sources(conn, sources, run_id="ingest-examples")
