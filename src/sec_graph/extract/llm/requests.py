"""Build paragraph-scoped LLM extraction requests."""

from __future__ import annotations

import duckdb

from sec_graph.extract.llm.models import CandidateType, LLMExtractionRequest
from sec_graph.schema import make_id
from sec_graph.schema import versions

_ALLOWED_TYPES: list[CandidateType] = ["actor_mention", "dated_event", "bid_value", "participation_count"]


def build_llm_requests(conn: duckdb.DuckDBPyConnection, filing_id: str, limit: int | None = None) -> list[LLMExtractionRequest]:
    rows = conn.execute(
        """
        SELECT filings.deal_slug, paragraphs.paragraph_id, paragraphs.section,
               paragraphs.paragraph_text, paragraphs.char_start, paragraphs.char_end,
               spans.evidence_id
        FROM paragraphs
        JOIN filings USING (filing_id)
        JOIN spans
          ON spans.paragraph_id = paragraphs.paragraph_id
         AND spans.span_kind = 'paragraph_seed'
        WHERE paragraphs.filing_id = ?
          AND paragraphs.section IN ('Background of the Merger', 'unknown_section')
          AND length(trim(paragraphs.paragraph_text)) > 0
        ORDER BY paragraphs.char_start, paragraphs.paragraph_id
        """,
        [filing_id],
    ).fetchall()
    if limit is not None:
        rows = rows[:limit]
    requests: list[LLMExtractionRequest] = []
    for sequence, row in enumerate(rows, start=1):
        slug, paragraph_id, section, paragraph_text, char_start, char_end, evidence_id = row
        requests.append(
            LLMExtractionRequest(
                request_id=make_id(slug, "llmrequest", sequence),
                filing_id=filing_id,
                deal_slug=slug,
                paragraph_id=paragraph_id,
                parent_evidence_id=evidence_id,
                section=section,
                paragraph_text=paragraph_text,
                char_start=char_start,
                char_end=char_end,
                allowed_candidate_types=_ALLOWED_TYPES,
                schema_version=versions.SCHEMA_VERSION,
                extract_version=versions.EXTRACT_VERSION,
            )
        )
    return requests
