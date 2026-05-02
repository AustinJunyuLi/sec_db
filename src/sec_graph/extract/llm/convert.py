"""Convert validated LLM payloads to local candidate rows."""

from __future__ import annotations

import duckdb

from sec_graph.extract.llm.models import LLMContractError, LLMExtractionRequest, LLMExtractionResponse
from sec_graph.schema import ExtractionCandidate, SourceSpan, make_id, quote_hash


def _next_sequence(conn: duckdb.DuckDBPyConnection, table_name: str, id_col: str, slug: str, type_name: str) -> int:
    prefix = f"{slug}_{type_name}_"
    rows = conn.execute(
        f"SELECT {id_col} FROM {table_name} WHERE {id_col} LIKE ?",
        [f"{prefix}%"],
    ).fetchall()
    if not rows:
        return 1
    return max(int(row[0].rsplit("_", maxsplit=1)[1]) for row in rows) + 1


def _validate_response(request: LLMExtractionRequest, response: LLMExtractionResponse) -> None:
    if response.finish_status != "completed":
        raise LLMContractError(f"LLM response status is {response.finish_status}")
    if response.request_id != request.request_id:
        raise LLMContractError(f"response request_id {response.request_id} does not match {request.request_id}")


def _validate_payload(request: LLMExtractionRequest, quote_text: str, quote_start: int, quote_end: int, candidate_type: str) -> None:
    if candidate_type not in request.allowed_candidate_types:
        raise LLMContractError(f"candidate_type {candidate_type} is not allowed")
    if quote_start < 0 or quote_end > len(request.paragraph_text) or quote_start >= quote_end:
        raise LLMContractError("quote offsets are outside paragraph bounds")
    if request.paragraph_text[quote_start:quote_end] != quote_text:
        raise LLMContractError("quote_text does not match paragraph substring")


def insert_llm_response(
    conn: duckdb.DuckDBPyConnection,
    request: LLMExtractionRequest,
    response: LLMExtractionResponse,
    run_id: str,
) -> list[ExtractionCandidate]:
    _validate_response(request, response)
    span_sequence = _next_sequence(conn, "spans", "evidence_id", request.deal_slug, "llmspan")
    candidate_sequence = _next_sequence(conn, "candidates", "candidate_id", request.deal_slug, "llmcandidate")
    inserted: list[ExtractionCandidate] = []
    for payload in response.candidates:
        _validate_payload(
            request,
            payload.quote_text,
            payload.quote_start,
            payload.quote_end,
            payload.candidate_type,
        )
        evidence_id = make_id(request.deal_slug, "llmspan", span_sequence)
        candidate_id = make_id(request.deal_slug, "llmcandidate", candidate_sequence)
        span_sequence += 1
        candidate_sequence += 1
        span = SourceSpan(
            evidence_id=evidence_id,
            filing_id=request.filing_id,
            paragraph_id=request.paragraph_id,
            span_basis="raw_md",
            span_kind="phrase",
            parent_evidence_id=request.parent_evidence_id,
            created_by_stage="extract",
            char_start=request.char_start + payload.quote_start,
            char_end=request.char_start + payload.quote_end,
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
        conn.execute("INSERT INTO spans VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", tuple(span.model_dump().values()))
        conn.execute(
            "INSERT INTO candidates VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            tuple(candidate.model_dump().values()),
        )
        inserted.append(candidate)
    return inserted
