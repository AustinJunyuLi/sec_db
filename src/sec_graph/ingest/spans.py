"""Source-span construction for ingested paragraph seeds."""

from __future__ import annotations

from sec_graph.schema import SourceSpan, make_id, quote_hash

from .paragraphs import ParagraphBlock


def paragraph_seed_span(slug: str, filing_id: str, paragraph_id: str, sequence: int, block: ParagraphBlock) -> SourceSpan:
    return SourceSpan(
        evidence_id=make_id(slug, "evidence", sequence),
        filing_id=filing_id,
        paragraph_id=paragraph_id,
        span_basis="raw_md",
        span_kind="paragraph_seed",
        parent_evidence_id=None,
        created_by_stage="ingest",
        char_start=block.char_start,
        char_end=block.char_end,
        quote_text=block.text,
        quote_hash=quote_hash(block.text),
    )
