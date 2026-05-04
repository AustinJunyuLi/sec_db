"""Convert validated Linkflow semantic payloads into claim tables."""

from __future__ import annotations

import json
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

_NO_LINKED_CLAIM_REASON = (
    "Python marked this obligation missed because Linkflow returned no validated "
    "claim linked to this obligation."
)
_NO_SUPPORTED_CLAIM_REASON = (
    "Python found no source support for this applicable obligation in the "
    "request window after applicability review."
)
_AMBIGUOUS_SUPPORT_REASON = (
    "Python could not safely classify source support for this applicable "
    "obligation after region and applicability review."
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
    coverage_sequence = _next_sequence(conn, "coverage_results", "coverage_result_id", request.deal_slug, "coverage")
    inserted_claim_ids: list[str] = []
    obligations_by_id = {obligation.obligation_id: obligation for obligation in request.coverage_obligations}
    if len(obligations_by_id) != len(request.coverage_obligations):
        raise LLMContractError("request contains duplicate coverage obligation ids")
    obligation_metadata = _obligation_metadata(conn, obligations_by_id.keys())
    coverage_claim_counts = {obligation_id: 0 for obligation_id in obligations_by_id}

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
        coverage_claim_counts[payload.coverage_obligation_id] += 1
        inserted_claim_ids.append(claim_id)

    for obligation in request.coverage_obligations:
        count = coverage_claim_counts[obligation.obligation_id]
        if count:
            result = "claims_emitted"
            reason_code = "linkflow_claims_linked"
            reason = "Linkflow emitted at least one validated claim explicitly linked to this obligation."
        else:
            result, reason_code, reason = _classify_unlinked_obligation(
                obligation,
                obligation_metadata[obligation.obligation_id],
                request,
            )
        coverage_result_id = make_id(request.deal_slug, "coverage", coverage_sequence)
        coverage_sequence += 1
        conn.execute(
            "INSERT INTO coverage_results VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [coverage_result_id, run_id, obligation.obligation_id, result, reason_code, reason, count, True],
        )
    return inserted_claim_ids


def _obligation_metadata(
    conn: duckdb.DuckDBPyConnection,
    obligation_ids: Iterable[str],
) -> dict[str, dict[str, str]]:
    ids = list(obligation_ids)
    if not ids:
        return {}
    placeholders = ", ".join("?" for _ in ids)
    rows = conn.execute(
        f"""
        SELECT obligation_id, obligation_kind, applicability_reason_code,
               applicability_basis_json
        FROM coverage_obligations
        WHERE obligation_id IN ({placeholders})
        """,
        ids,
    ).fetchall()
    metadata = {
        obligation_id: {
            "obligation_kind": obligation_kind,
            "applicability_reason_code": applicability_reason_code,
            "applicability_basis_json": applicability_basis_json,
        }
        for obligation_id, obligation_kind, applicability_reason_code, applicability_basis_json in rows
    }
    missing = sorted(set(ids) - set(metadata))
    if missing:
        raise LLMContractError(
            "request references coverage obligations absent from DuckDB: "
            + ", ".join(missing)
        )
    return metadata


def _classify_unlinked_obligation(
    obligation: WindowObligation,
    metadata: dict[str, str],
    request: LLMWindowRequest,
) -> tuple[str, str, str]:
    reason_code = metadata["applicability_reason_code"]
    if reason_code.startswith("process_scope:"):
        return "ambiguous", "python_support_ambiguous", _AMBIGUOUS_SUPPORT_REASON
    if _window_supports_obligation(obligation, metadata, request):
        return "missed", "linkflow_no_linked_claim", _NO_LINKED_CLAIM_REASON
    return "no_supported_claim", "python_no_source_support", _NO_SUPPORTED_CLAIM_REASON


def _window_supports_obligation(
    obligation: WindowObligation,
    metadata: dict[str, str],
    request: LLMWindowRequest,
) -> bool:
    text = _folded_window_text(request)
    for basis in _metadata_basis(metadata):
        if basis.casefold() in text:
            return True
    kind = metadata["obligation_kind"]
    label = obligation.obligation_label.casefold()
    support_terms = {
        "process_initiation": ("sale process", "strategic alternatives", "initiated", "began"),
        "target_board": ("board", "directors"),
        "target_financial_advisor": ("financial advisor", "financial adviser", "advisor", "adviser"),
        "target_legal_advisor": ("legal advisor", "legal adviser", "counsel", "law firm"),
        "final_consideration": ("per share", "$", "consideration", "purchase price"),
        "final_approval_event": ("merger agreement", "approved", "executed", "signed"),
        "contacted_count": ("contacted", "potential buyers", "potential bidders", "potential parties"),
        "ioi_count": ("indication of interest", "indications of interest", "ioi", "proposal"),
        "first_round_count": ("first round", "first-round", "first phase"),
        "final_round_count": ("final round", "final-round", "best and final"),
        "final_round_bid_event": ("final bid", "final proposal", "best and final"),
        "exclusivity_grant": ("exclusivity", "exclusive negotiations"),
        "go_shop_period": ("go-shop", "go shop"),
        "buyer_group_composition": ("buyer group", "consortium", "acquisition vehicle"),
        "rollover_holder": ("rollover", "roll-over", "rolled over", "retain equity"),
        "voting_support": ("voting agreement", "support agreement", "agreed to vote"),
        "special_committee": ("special committee", "transaction committee"),
        "recusal": ("recused", "did not participate", "abstained"),
        "financing_committed": ("debt commitment", "equity commitment", "financing commitment"),
        "amendment": ("amendment", "amended merger agreement"),
    }.get(kind, ())
    if any(term in text for term in support_terms):
        return True
    return label and label in text


def _metadata_basis(metadata: dict[str, str]) -> tuple[str, ...]:
    raw = metadata["applicability_basis_json"]
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise LLMContractError("coverage obligation applicability_basis_json is invalid JSON") from exc
    if not isinstance(parsed, list) or not all(isinstance(item, str) for item in parsed):
        raise LLMContractError("coverage obligation applicability_basis_json must be a JSON string list")
    return tuple(parsed)


def _folded_window_text(request: LLMWindowRequest) -> str:
    return "\n".join(
        paragraph.paragraph_text for paragraph in request.ordered_paragraphs
    ).casefold()


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
