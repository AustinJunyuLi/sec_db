"""Convert validated LLM payloads to local candidate rows.

Quote resolution policy: providers emit quote_text only. Python finds the
unique exact match against the underlying paragraph source-span text within
the window, derives char_start/char_end against the underlying paragraph
seed coordinates, and rejects the candidate if no unique match exists.
"""

from __future__ import annotations

import datetime as dt
import re

import duckdb

from sec_graph.extract.llm.models import (
    LLMCandidatePayload,
    LLMContractError,
    LLMExtractionResponse,
    LLMWindowRequest,
    WindowParagraph,
)
from sec_graph.schema import ExtractionCandidate, SourceSpan, make_id, quote_hash

_BID_NORMALIZED_RE = re.compile(r"^\d+(?:\.\d+)?(?:-\d+(?:\.\d+)?)?$")
_COUNT_NORMALIZED_RE = re.compile(r"^[1-9]\d*$")


def _next_sequence(
    conn: duckdb.DuckDBPyConnection,
    table_name: str,
    id_col: str,
    slug: str,
    type_name: str,
) -> int:
    prefix = f"{slug}_{type_name}_"
    rows = conn.execute(
        f"SELECT {id_col} FROM {table_name} WHERE {id_col} LIKE ?",
        [f"{prefix}%"],
    ).fetchall()
    if not rows:
        return 1
    return max(int(row[0].rsplit("_", maxsplit=1)[1]) for row in rows) + 1


def _validate_response(
    request: LLMWindowRequest, response: LLMExtractionResponse
) -> None:
    if response.finish_status != "completed":
        raise LLMContractError(
            f"LLM response status is {response.finish_status}"
        )
    if response.request_id != request.request_id:
        raise LLMContractError(
            f"response request_id {response.request_id} does not match {request.request_id}"
        )


def _resolve_quote(
    window: LLMWindowRequest, quote_text: str
) -> tuple[WindowParagraph, int, int]:
    """Resolve a provider quote to the unique paragraph and offsets.

    Re-derives offsets against the underlying paragraph source-span text.
    """

    if not quote_text:
        raise LLMContractError("quote_text is empty")

    matches: list[tuple[WindowParagraph, int]] = []
    for paragraph in window.ordered_paragraphs:
        text = paragraph.paragraph_text
        start = text.find(quote_text)
        while start != -1:
            matches.append((paragraph, start))
            start = text.find(quote_text, start + 1)
    if not matches:
        raise LLMContractError("quote_text is not an exact window substring")
    if len(matches) > 1:
        raise LLMContractError("quote_text is ambiguous within window")

    paragraph, paragraph_offset = matches[0]
    return (
        paragraph,
        paragraph_offset,
        paragraph_offset + len(quote_text),
    )


def _validate_payload_type_allowed(
    request: LLMWindowRequest, candidate_type: str
) -> None:
    if candidate_type not in request.allowed_candidate_types:
        raise LLMContractError(
            f"candidate_type {candidate_type} is not allowed"
        )


def _validate_normalized_value(payload: LLMCandidatePayload) -> None:
    if payload.candidate_type == "dated_event":
        try:
            parsed = dt.date.fromisoformat(payload.normalized_value)
        except ValueError as exc:
            raise LLMContractError(
                "dated_event normalized_value must be YYYY-MM-DD"
            ) from exc
        if payload.normalized_value != parsed.isoformat():
            raise LLMContractError(
                "dated_event normalized_value must be canonical YYYY-MM-DD"
            )
    elif payload.candidate_type == "bid_value":
        if not _BID_NORMALIZED_RE.match(payload.normalized_value):
            raise LLMContractError(
                "bid_value normalized_value must be a numeric amount or lower-upper range"
            )
        if "-" in payload.normalized_value:
            lower, upper = (
                float(part)
                for part in payload.normalized_value.split("-", maxsplit=1)
            )
            if lower > upper:
                raise LLMContractError(
                    "bid_value normalized range lower bound exceeds upper bound"
                )
    elif payload.candidate_type == "participation_count":
        if not _COUNT_NORMALIZED_RE.match(payload.normalized_value):
            raise LLMContractError(
                "participation_count normalized_value must be a positive integer"
            )
    # actor_mention: normalized_value is opaque label.


def insert_llm_response(
    conn: duckdb.DuckDBPyConnection,
    request: LLMWindowRequest,
    response: LLMExtractionResponse,
    run_id: str,
) -> list[ExtractionCandidate]:
    _validate_response(request, response)

    slug = request.deal_id
    span_sequence = _next_sequence(conn, "spans", "evidence_id", slug, "llmspan")
    candidate_sequence = _next_sequence(
        conn, "candidates", "candidate_id", slug, "llmcandidate"
    )

    validated: list[
        tuple[LLMCandidatePayload, WindowParagraph, int, int]
    ] = []
    for payload in response.candidates:
        _validate_payload_type_allowed(request, payload.candidate_type)
        _validate_normalized_value(payload)
        paragraph, quote_start, quote_end = _resolve_quote(
            request, payload.quote_text
        )
        validated.append((payload, paragraph, quote_start, quote_end))

    inserted: list[ExtractionCandidate] = []
    for payload, paragraph, quote_start, quote_end in validated:
        evidence_id = make_id(slug, "llmspan", span_sequence)
        candidate_id = make_id(slug, "llmcandidate", candidate_sequence)
        span_sequence += 1
        candidate_sequence += 1
        span = SourceSpan(
            evidence_id=evidence_id,
            filing_id=request.filing_id,
            paragraph_id=paragraph.paragraph_id,
            span_basis="raw_md",
            span_kind="phrase",
            parent_evidence_id=paragraph.source_span_id,
            created_by_stage="extract",
            char_start=paragraph.char_start + quote_start,
            char_end=paragraph.char_start + quote_end,
            quote_text=payload.quote_text,
            quote_hash=quote_hash(payload.quote_text),
        )
        candidate = ExtractionCandidate(
            candidate_id=candidate_id,
            run_id=run_id,
            filing_id=request.filing_id,
            candidate_type=payload.candidate_type,
            raw_value=payload.raw_value,
            normalized_value=payload.normalized_value,
            confidence=payload.confidence,
            evidence_ids=[span.evidence_id],
            dependencies=payload.dependencies,
            status="active",
        )
        conn.execute(
            "INSERT INTO spans VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            tuple(span.model_dump().values()),
        )
        conn.execute(
            "INSERT INTO candidates VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            tuple(candidate.model_dump().values()),
        )
        inserted.append(candidate)
    return inserted
