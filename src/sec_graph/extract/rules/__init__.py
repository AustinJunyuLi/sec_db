"""Deterministic extraction rule orchestration."""

from __future__ import annotations

import datetime as dt

import duckdb

from sec_graph.schema import ExtractionCandidate, SourceSpan, make_id, quote_hash

from .actors import Match, actor_matches
from .bids import bid_matches
from .counts import count_matches
from .events import dated_event_matches
from .relations import relation_aliases, relation_matches


def _utc_run_id(prefix: str) -> str:
    """Generic UTC timestamp run id used when the caller does not pass one.

    Format: `{prefix}_{YYYYMMDDTHHMMSSZ}`. The prefix names the stage so a
    pipeline grep can locate the call site.
    """
    timestamp = dt.datetime.now(dt.UTC).strftime("%Y%m%dT%H%M%SZ")
    return f"{prefix}_{timestamp}"


def _slug_for_filing(conn: duckdb.DuckDBPyConnection, filing_id: str) -> str:
    row = conn.execute("SELECT deal_slug FROM filings WHERE filing_id = ?", [filing_id]).fetchone()
    if row is None:
        raise ValueError(f"filing_id {filing_id} does not exist")
    return row[0]


def _paragraph_rows(conn: duckdb.DuckDBPyConnection, filing_id: str) -> list[dict[str, object]]:
    rows = conn.execute(
        """
        SELECT paragraphs.paragraph_id, paragraphs.char_start, paragraphs.paragraph_text,
               spans.evidence_id
        FROM paragraphs
        JOIN spans
          ON spans.paragraph_id = paragraphs.paragraph_id
         AND spans.span_kind = 'paragraph_seed'
        WHERE paragraphs.filing_id = ?
          AND paragraphs.section IN ('Background of the Merger', 'Financing', 'unknown_section')
        ORDER BY paragraphs.char_start, paragraphs.paragraph_id
        """,
        [filing_id],
    ).fetchall()
    return [
        {
            "paragraph_id": row[0],
            "char_start": row[1],
            "paragraph_text": row[2],
            "parent_evidence_id": row[3],
        }
        for row in rows
    ]


def _matches_for_text(text: str, aliases: dict[str, str] | None = None) -> list[Match]:
    matches: list[Match] = []
    matches.extend(actor_matches(text))
    matches.extend(dated_event_matches(text))
    matches.extend(bid_matches(text))
    matches.extend(count_matches(text))
    matches.extend(relation_matches(text, aliases))
    return matches


def _document_aliases(paragraphs: list[dict[str, object]]) -> dict[str, str]:
    aliases: dict[str, str] = {}
    for paragraph in paragraphs:
        aliases.update(relation_aliases(str(paragraph["paragraph_text"])))
    return aliases


def run_rules(
    conn: duckdb.DuckDBPyConnection,
    filing_id: str,
    run_id: str | None = None,
) -> list[ExtractionCandidate]:
    """Execute deterministic rule extraction for one filing.

    `run_id` is optional. When omitted, a UTC-timestamped id is generated
    on the spot so the produced candidates carry a generic stage stamp.
    Callers that need a stable id should pass one explicitly.
    """
    if run_id is None:
        run_id = _utc_run_id("extract")
    slug = _slug_for_filing(conn, filing_id)
    conn.execute(
        """
        DELETE FROM relation_candidates
        WHERE candidate_id IN (
            SELECT candidate_id FROM candidates WHERE filing_id = ?
        )
        """,
        [filing_id],
    )
    conn.execute("DELETE FROM candidates WHERE filing_id = ?", [filing_id])
    conn.execute("DELETE FROM spans WHERE filing_id = ? AND created_by_stage = 'extract'", [filing_id])
    candidates: list[ExtractionCandidate] = []
    sequence = 1
    paragraphs = _paragraph_rows(conn, filing_id)
    aliases = _document_aliases(paragraphs)
    for paragraph in paragraphs:
        text = str(paragraph["paragraph_text"])
        paragraph_start = int(paragraph["char_start"])
        for match in _matches_for_text(text, aliases):
            span_id = make_id(slug, "extractspan", sequence)
            candidate_id = make_id(slug, "candidate", sequence)
            char_start = paragraph_start + match.start
            char_end = paragraph_start + match.end
            quote_text = text[match.start:match.end]
            span = SourceSpan(
                evidence_id=span_id,
                filing_id=filing_id,
                paragraph_id=str(paragraph["paragraph_id"]),
                span_basis="raw_md",
                span_kind=match.span_kind,  # type: ignore[arg-type]
                parent_evidence_id=str(paragraph["parent_evidence_id"]),
                created_by_stage="extract",
                char_start=char_start,
                char_end=char_end,
                quote_text=quote_text,
                quote_hash=quote_hash(quote_text),
            )
            candidate = ExtractionCandidate(
                candidate_id=candidate_id,
                run_id=run_id,
                filing_id=filing_id,
                candidate_type=match.candidate_type,  # type: ignore[arg-type]
                raw_value=match.raw_value,
                normalized_value=match.normalized_value,
                confidence=match.confidence,  # type: ignore[arg-type]
                evidence_ids=[span.evidence_id],
                dependencies=[],
                status="active",
            )
            conn.execute("INSERT INTO spans VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", tuple(span.model_dump().values()))
            conn.execute(
                "INSERT INTO candidates VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                tuple(candidate.model_dump().values()),
            )
            if match.relation_payload is not None:
                relation_payload = match.relation_payload.model_copy(
                    update={"candidate_id": candidate_id}
                )
                conn.execute(
                    "INSERT INTO relation_candidates VALUES (?, ?, ?, ?, ?, ?)",
                    tuple(relation_payload.model_dump(mode="json").values()),
                )
            candidates.append(candidate)
            sequence += 1
    return candidates
