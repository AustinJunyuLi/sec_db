"""Source-span construction for ingested paragraph seeds.

Paragraph seed spans are the only span_kind allowed to have
``parent_evidence_id is None``. Every downstream extract span (sentence,
clause, phrase, llm_extract) MUST chain to a seed via ``parent_evidence_id``;
this is enforced both by the ``SourceSpan`` Pydantic model
(``schema/models/filings.py``) and by the ``spans`` table CHECK constraint
(``FILINGS_DDL``). Coordinates here are raw-source coordinates: the
``ParagraphBlock`` invariant set by ``split_paragraphs`` guarantees that
``raw_text[block.char_start:block.char_end] == block.text``, so the seed
span passes the Phase 4 source-truth validation.
"""

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
