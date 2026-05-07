"""Convert validated Linkflow semantic payloads into claim tables.

Coverage finalization is owned by ``extract/disposition.py``; this module
only writes spans, claims, claim_coverage_links, claim_evidence, and the
typed claim row.
"""

from __future__ import annotations

from typing import Iterable

import duckdb

from sec_graph.extract.llm.models import (
    ActorClaimPayload,
    ActorRelationClaimPayload,
    BidClaimPayload,
    EventClaimPayload,
    LLMContractError,
    LLMExtractionResponse,
    LLMWindowRequest,
    ParticipationCountClaimPayload,
    WindowObligation,
    WindowParagraph,
)
from sec_graph.schema import SourceSpan, evidence_fingerprint, make_id, quote_hash

ClaimPayload = (
    ActorClaimPayload
    | EventClaimPayload
    | BidClaimPayload
    | ParticipationCountClaimPayload
    | ActorRelationClaimPayload
)


def insert_llm_response(
    conn: duckdb.DuckDBPyConnection,
    request: LLMWindowRequest,
    response: LLMExtractionResponse,
    run_id: str,
) -> list[str]:
    conn.begin()
    try:
        inserted = _insert_llm_response_rows(conn, request, response, run_id)
    except Exception:
        conn.rollback()
        raise
    conn.commit()
    return inserted


def _insert_llm_response_rows(
    conn: duckdb.DuckDBPyConnection,
    request: LLMWindowRequest,
    response: LLMExtractionResponse,
    run_id: str,
) -> list[str]:
    if response.finish_status != "completed":
        raise LLMContractError(f"LLM response status is {response.finish_status}")
    if response.request_id != request.request_id:
        raise LLMContractError("response request_id does not match request")

    payloads = list(_iter_claim_payloads(response.payload))
    span_sequence = _next_sequence(conn, "spans", "evidence_id", request.deal_slug, "llmspan")
    claim_sequence = _next_sequence(conn, "claims", "claim_id", request.deal_slug, "claim")
    inserted_claim_ids: list[str] = []
    obligations_by_id = {obligation.obligation_id: obligation for obligation in request.coverage_obligations}
    if len(obligations_by_id) != len(request.coverage_obligations):
        raise LLMContractError("request contains duplicate coverage obligation ids")
    _verify_obligations_exist(conn, obligations_by_id.keys())

    for payload in payloads:
        if payload.claim_type not in request.allowed_claim_types:
            raise LLMContractError(f"claim_type {payload.claim_type} is not allowed for request")
        _validate_claim_obligation_links(payload, obligations_by_id)
        paragraph, quote_start, quote_end = _resolve_quote(request, payload.quote_text)
        quote_text_hash = quote_hash(payload.quote_text)
        span = SourceSpan(
            evidence_id=make_id(request.deal_slug, "llmspan", span_sequence),
            filing_id=request.filing_id,
            paragraph_id=paragraph.paragraph_id,
            span_basis="raw_md",
            span_kind="llm_extract",
            parent_evidence_id=paragraph.source_span_id,
            created_by_stage="extract",
            char_start=paragraph.char_start + quote_start,
            char_end=paragraph.char_start + quote_end,
            quote_text=payload.quote_text,
            quote_text_hash=quote_text_hash,
            evidence_fingerprint=evidence_fingerprint(
                request.filing_id,
                paragraph.char_start + quote_start,
                paragraph.char_start + quote_end,
                quote_text_hash,
            ),
        )
        claim_id = make_id(request.deal_slug, "claim", claim_sequence)
        span_sequence += 1
        claim_sequence += 1
        conn.execute(
            "INSERT INTO spans VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            tuple(span.model_dump().values()),
        )
        conn.execute(
            "INSERT INTO claims VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                claim_id,
                run_id,
                request.filing_id,
                request.deal_slug,
                request.region_id,
                "linkflow",
                payload.claim_type,
                payload.confidence,
                _raw_value(payload),
                _normalized_value(payload),
                payload.quote_text,
                quote_text_hash,
                "validated",
                claim_sequence - 1,
            ],
        )
        conn.execute(
            "INSERT INTO claim_coverage_links VALUES (?, ?, ?, ?, ?, ?)",
            [
                claim_id,
                payload.coverage_obligation_id,
                run_id,
                request.deal_slug,
                payload.claim_type,
                True,
            ],
        )
        conn.execute("INSERT INTO claim_evidence VALUES (?, ?, ?)", [claim_id, span.evidence_id, 1])
        _insert_typed_claim(conn, claim_id, payload)
        inserted_claim_ids.append(claim_id)

    return inserted_claim_ids


def _verify_obligations_exist(
    conn: duckdb.DuckDBPyConnection,
    obligation_ids: Iterable[str],
) -> None:
    ids = list(obligation_ids)
    if not ids:
        return
    placeholders = ", ".join("?" for _ in ids)
    rows = conn.execute(
        f"""
        SELECT obligation_id
        FROM coverage_obligations
        WHERE obligation_id IN ({placeholders})
        """,
        ids,
    ).fetchall()
    found = {row[0] for row in rows}
    missing = sorted(set(ids) - found)
    if missing:
        raise LLMContractError(
            "request references coverage obligations absent from DuckDB: "
            + ", ".join(missing)
        )


def _validate_claim_obligation_links(payload: ClaimPayload, obligations_by_id: dict[str, WindowObligation]) -> None:
    obligation_id = payload.coverage_obligation_id
    obligation = obligations_by_id.get(obligation_id)
    if obligation is None:
        raise LLMContractError(f"claim references unknown coverage obligation {obligation_id}")
    if obligation.expected_claim_type != payload.claim_type:
        raise LLMContractError(
            f"claim_type {payload.claim_type} does not match expected_claim_type "
            f"{obligation.expected_claim_type} for obligation {obligation_id}"
        )


def _iter_claim_payloads(payload) -> Iterable[ClaimPayload]:
    yield from payload.actor_claims
    yield from payload.event_claims
    yield from payload.bid_claims
    yield from payload.participation_count_claims
    yield from payload.actor_relation_claims


def _resolve_quote(
    window: LLMWindowRequest,
    quote_text: str,
) -> tuple[WindowParagraph, int, int]:
    if not quote_text:
        raise LLMContractError("quote_text is empty")
    matches: list[tuple[WindowParagraph, int]] = []
    for paragraph in window.ordered_paragraphs:
        start = paragraph.paragraph_text.find(quote_text)
        while start != -1:
            matches.append((paragraph, start))
            start = paragraph.paragraph_text.find(quote_text, start + 1)
    if not matches:
        raise LLMContractError("quote_text is not an exact window substring")
    if len(matches) > 1:
        raise LLMContractError("quote_text is ambiguous within window")
    paragraph, start = matches[0]
    return paragraph, start, start + len(quote_text)


def _next_sequence(
    conn: duckdb.DuckDBPyConnection,
    table_name: str,
    id_col: str,
    slug: str,
    type_name: str,
) -> int:
    prefix = f"{slug}_{type_name}_"
    rows = conn.execute(f"SELECT {id_col} FROM {table_name} WHERE {id_col} LIKE ?", [f"{prefix}%"]).fetchall()
    if not rows:
        return 1
    return max(int(row[0].rsplit("_", maxsplit=1)[1]) for row in rows) + 1


def _raw_value(payload: ClaimPayload) -> str:
    if isinstance(payload, ActorClaimPayload):
        return payload.actor_label
    if isinstance(payload, EventClaimPayload):
        return payload.description
    if isinstance(payload, BidClaimPayload):
        value = payload.bid_value if payload.bid_value is not None else payload.bid_value_lower
        return f"{payload.bidder_label}:{value}"
    if isinstance(payload, ParticipationCountClaimPayload):
        return f"{payload.process_stage}:{payload.actor_class}:{payload.count_min}"
    return f"{payload.subject_label}:{payload.relation_type}:{payload.object_label}"


def _normalized_value(payload: ClaimPayload) -> str | None:
    if isinstance(payload, EventClaimPayload) and payload.event_date is not None:
        return payload.event_date.isoformat()
    if isinstance(payload, BidClaimPayload):
        if payload.bid_value is not None:
            return str(payload.bid_value)
        if payload.bid_value_lower is not None or payload.bid_value_upper is not None:
            return f"{payload.bid_value_lower}-{payload.bid_value_upper}"
    if isinstance(payload, ParticipationCountClaimPayload):
        return str(payload.count_min)
    return None


def _insert_typed_claim(conn: duckdb.DuckDBPyConnection, claim_id: str, payload: ClaimPayload) -> None:
    if isinstance(payload, ActorClaimPayload):
        conn.execute(
            "INSERT INTO actor_claims VALUES (?, ?, ?, ?)",
            [claim_id, payload.actor_label, payload.actor_kind, payload.observability],
        )
    elif isinstance(payload, EventClaimPayload):
        conn.execute(
            "INSERT INTO event_claims VALUES (?, ?, ?, ?, ?, ?, ?)",
            [
                claim_id,
                payload.event_type,
                payload.event_subtype,
                payload.event_date,
                payload.description,
                payload.actor_label,
                payload.actor_role,
            ],
        )
    elif isinstance(payload, BidClaimPayload):
        conn.execute(
            "INSERT INTO bid_claims VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                claim_id,
                payload.bidder_label,
                payload.bid_date,
                payload.bid_value,
                payload.bid_value_lower,
                payload.bid_value_upper,
                payload.bid_value_unit,
                payload.consideration_type,
                payload.bid_stage,
            ],
        )
    elif isinstance(payload, ParticipationCountClaimPayload):
        conn.execute(
            "INSERT INTO participation_count_claims VALUES (?, ?, ?, ?, ?, ?)",
            [
                claim_id,
                payload.process_stage,
                payload.actor_class,
                payload.count_min,
                payload.count_max,
                payload.count_qualifier,
            ],
        )
    elif isinstance(payload, ActorRelationClaimPayload):
        conn.execute(
            "INSERT INTO actor_relation_claims VALUES (?, ?, ?, ?, ?, ?)",
            [
                claim_id,
                payload.subject_label,
                payload.object_label,
                payload.relation_type,
                payload.role_detail,
                payload.effective_date_first,
            ],
        )
    else:
        raise TypeError(f"unsupported claim payload {type(payload).__name__}")
