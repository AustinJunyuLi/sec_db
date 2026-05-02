"""Build within-deal narrative window LLM extraction requests.

Window construction strategy: deterministic ordered-paragraph stride within a
single filing — paragraphs are partitioned by (section, fixed stride of N
paragraphs) and assigned a window_kind from a closed enum. No cross-deal
content. Earlier windows feed prior_deal_memory of later windows in the SAME
filing only.
"""

from __future__ import annotations

from dataclasses import dataclass

import duckdb

from sec_graph.extract.llm.models import (
    ActiveCycleCandidate,
    CandidateType,
    ExtractionTask,
    LLMWindowRequest,
    PriorActorAlias,
    PriorDealMemory,
    PriorEvent,
    UnresolvedReference,
    WindowKind,
    WindowParagraph,
)
from sec_graph.extract.rules.actors import actor_matches
from sec_graph.extract.rules.events import dated_event_matches
from sec_graph.schema import make_id, versions

_ALLOWED_CANDIDATE_TYPES: list[CandidateType] = [
    "actor_mention",
    "dated_event",
    "bid_value",
    "participation_count",
]
_DEFAULT_TASKS: list[ExtractionTask] = [
    "actor_aliases",
    "events",
    "participation_counts",
]
_TARGET_SECTIONS = ("Background of the Merger", "Financing", "unknown_section")
# Deterministic stride: N consecutive paragraphs per window. Chosen so a
# single window typically holds enough narrative context for cross-paragraph
# references (e.g., an actor introduced in paragraph i is still present when
# the model reads paragraph i+2).
_WINDOW_STRIDE = 3


@dataclass(frozen=True)
class _ParagraphRow:
    paragraph_id: str
    source_span_id: str
    char_start: int
    char_end: int
    section: str
    paragraph_text: str


def _paragraph_rows(
    conn: duckdb.DuckDBPyConnection, filing_id: str
) -> list[_ParagraphRow]:
    rows = conn.execute(
        """
        SELECT paragraphs.paragraph_id, spans.evidence_id,
               paragraphs.char_start, paragraphs.char_end,
               paragraphs.section, paragraphs.paragraph_text
        FROM paragraphs
        JOIN spans
          ON spans.paragraph_id = paragraphs.paragraph_id
         AND spans.span_kind = 'paragraph_seed'
        WHERE paragraphs.filing_id = ?
          AND paragraphs.section IN ('Background of the Merger', 'Financing', 'unknown_section')
          AND length(trim(paragraphs.paragraph_text)) > 0
        ORDER BY paragraphs.char_start, paragraphs.paragraph_id
        """,
        [filing_id],
    ).fetchall()
    return [
        _ParagraphRow(
            paragraph_id=row[0],
            source_span_id=row[1],
            char_start=row[2],
            char_end=row[3],
            section=row[4],
            paragraph_text=row[5],
        )
        for row in rows
    ]


def _slug_and_deal(
    conn: duckdb.DuckDBPyConnection, filing_id: str
) -> tuple[str, str]:
    row = conn.execute(
        "SELECT deal_slug FROM filings WHERE filing_id = ?", [filing_id]
    ).fetchone()
    if row is None:
        raise ValueError(f"filing_id {filing_id} does not exist")
    slug = row[0]
    # deal_id == slug at this stage; the canonical Deal table is keyed by slug too.
    return slug, slug


def _window_kind_for(section: str, sequence: int) -> WindowKind:
    if section == "Background of the Merger":
        # First background window introduces actors; subsequent background
        # windows are process-step clusters narrating the auction arc.
        return "actor_introduction" if sequence == 1 else "narrative_arc"
    if section == "Financing":
        return "process_step_cluster"
    # unknown_section: treat as narrative arc; the model is told it is one
    # ordered window from a single filing.
    return "narrative_arc"


def _chunk_by_stride(
    rows: list[_ParagraphRow], stride: int
) -> list[list[_ParagraphRow]]:
    chunks: list[list[_ParagraphRow]] = []
    current: list[_ParagraphRow] = []
    current_section: str | None = None
    for row in rows:
        if (
            current_section is not None
            and (row.section != current_section or len(current) >= stride)
        ):
            chunks.append(current)
            current = []
        current.append(row)
        current_section = row.section
    if current:
        chunks.append(current)
    return chunks


def _build_prior_memory(
    earlier_windows: list[LLMWindowRequest],
) -> PriorDealMemory:
    """Compact prior memory derived from earlier windows in the SAME filing.

    Python owns this — it is not echoed back from a model. We use the same
    deterministic regex passes that drive rules extraction so the memory is
    reproducible run-to-run.
    """

    aliases: list[PriorActorAlias] = []
    seen_aliases: set[tuple[str, str]] = set()
    events: list[PriorEvent] = []
    seen_events: set[tuple[str, str, str]] = set()

    for window in earlier_windows:
        for paragraph in window.ordered_paragraphs:
            text = paragraph.paragraph_text
            for match in actor_matches(text):
                key = (match.normalized_value, paragraph.paragraph_id)
                if key in seen_aliases:
                    continue
                seen_aliases.add(key)
                aliases.append(
                    PriorActorAlias(
                        alias=match.raw_value,
                        canonical_label=match.normalized_value,
                        source_paragraph_id=paragraph.paragraph_id,
                    )
                )
            for match in dated_event_matches(text):
                key = (
                    match.normalized_value,
                    match.raw_value,
                    paragraph.paragraph_id,
                )
                if key in seen_events:
                    continue
                seen_events.add(key)
                events.append(
                    PriorEvent(
                        event_kind="dated_event",
                        normalized_value=match.normalized_value,
                        quote_text=match.raw_value,
                        source_paragraph_id=paragraph.paragraph_id,
                    )
                )

    return PriorDealMemory(
        actor_aliases=aliases,
        prior_events=events,
        active_cycle_candidates=[] if not aliases else [
            ActiveCycleCandidate(
                cycle_label="primary_sale_process",
                source_paragraph_id=aliases[0].source_paragraph_id,
            )
        ],
        unresolved_references=[
            UnresolvedReference(
                reference_text=alias.alias,
                source_paragraph_id=alias.source_paragraph_id,
            )
            for alias in aliases
            if alias.alias.startswith(("Party ", "Bidder ", "Sponsor "))
        ],
    )


def build_llm_windows(
    conn: duckdb.DuckDBPyConnection,
    filing_id: str,
    *,
    stride: int = _WINDOW_STRIDE,
) -> list[LLMWindowRequest]:
    """Build deterministic within-deal narrative windows for a single filing.

    Strategy: ordered paragraphs from the requested filing are partitioned by
    (section, stride). Each window carries Python-derived prior_deal_memory
    summarizing earlier windows in the SAME filing. No cross-deal content.
    """

    slug, deal_id = _slug_and_deal(conn, filing_id)
    rows = _paragraph_rows(conn, filing_id)
    if not rows:
        return []

    chunks = _chunk_by_stride(rows, stride)
    windows: list[LLMWindowRequest] = []
    for sequence, chunk in enumerate(chunks, start=1):
        ordered_paragraphs = [
            WindowParagraph(
                paragraph_id=row.paragraph_id,
                source_span_id=row.source_span_id,
                char_start=row.char_start,
                char_end=row.char_end,
                paragraph_text=row.paragraph_text,
            )
            for row in chunk
        ]
        windows.append(
            LLMWindowRequest(
                request_id=make_id(slug, "llmrequest", sequence),
                deal_id=deal_id,
                filing_id=filing_id,
                window_id=make_id(slug, "window", sequence),
                window_kind=_window_kind_for(chunk[0].section, sequence),
                ordered_paragraphs=ordered_paragraphs,
                prior_deal_memory=_build_prior_memory(windows),
                extraction_tasks=list(_DEFAULT_TASKS),
                allowed_candidate_types=list(_ALLOWED_CANDIDATE_TYPES),
                schema_version=versions.SCHEMA_VERSION,
                extract_version=versions.EXTRACT_VERSION,
            )
        )
    return windows
