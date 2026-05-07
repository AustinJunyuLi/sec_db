import json
from pathlib import Path

import duckdb

from sec_graph.extract.disposition import (
    dispose_claims_for_filing,
    finalize_coverage_after_disposition,
)
from sec_graph.extract.llm.convert import insert_llm_response
from sec_graph.extract.llm.models import (
    ActorClaimPayload,
    ActorRelationClaimPayload,
    BidClaimPayload,
    DEFAULT_REQUEST_MODE,
    EventClaimPayload,
    LLMContractError,
    LLMExtractionResponse,
    LLMWindowRequest,
    SemanticClaimsPayload,
    WindowObligation,
    WindowParagraph,
)
from sec_graph.schema import (
    CleanFiling,
    Paragraph,
    SourceSpan,
    connect,
    evidence_fingerprint,
    init_schema,
    make_id,
    quote_hash,
)
from sec_graph.validate.integrity import validate_database

RUN_ID = "2026-05-03T010203Z_coverage-deal_deadbeef"


def test_single_event_claim_does_not_satisfy_all_event_obligations(tmp_path: Path) -> None:
    conn = connect(":memory:")
    init_schema(conn)
    _insert_window_source(conn, tmp_path)

    window = LLMWindowRequest(
        request_id="coverage-deal_llmrequest_1",
        deal_slug="coverage-deal",
        deal_id="coverage-deal",
        filing_id="coverage-deal_filing_1",
        region_id="coverage-deal_region_1",
        window_id="coverage-deal_window_1",
        region_kind="sale_process_narrative",
        ordered_paragraphs=[
            WindowParagraph(
                paragraph_id="coverage-deal_para_1",
                source_span_id="coverage-deal_evidence_1",
                char_start=0,
                char_end=89,
                paragraph_text=(
                    "The Board began a sale process. "
                    "The Board later granted exclusivity to Buyer A."
                ),
            )
        ],
        coverage_obligations=[
            WindowObligation(
                obligation_id="coverage-deal_obligation_1",
                expected_claim_type="event",
                obligation_label="Sales process initiation",
                importance="required",
            ),
            WindowObligation(
                obligation_id="coverage-deal_obligation_2",
                expected_claim_type="event",
                obligation_label="Exclusivity grant",
                importance="required",
            ),
        ],
        allowed_claim_types=["event"],
        schema_version=1,
        extract_version=1,
        request_mode=DEFAULT_REQUEST_MODE,
    )
    payload = SemanticClaimsPayload(
        actor_claims=[],
        event_claims=[
            EventClaimPayload(
                claim_type="event",
                coverage_obligation_id="coverage-deal_obligation_1",
                event_type="process",
                event_subtype="contact_initial",
                event_date=None,
                description="The Board began a sale process.",
                actor_label=None,
                actor_role=None,
                confidence="high",
                quote_text="The Board began a sale process.",
            )
        ],
        bid_claims=[],
        participation_count_claims=[],
        actor_relation_claims=[],
    )
    response = LLMExtractionResponse(
        request_id=window.request_id,
        provider_name="linkflow",
        provider_model="gpt-5.5",
        reasoning_effort="medium",
        payload=payload,
        raw_response_sha256=quote_hash(json.dumps(payload.model_dump(mode="json"), sort_keys=True)),
        finish_status="completed",
    )

    insert_llm_response(conn, window, response, run_id=RUN_ID)
    dispose_claims_for_filing(conn, filing_id="coverage-deal_filing_1", run_id=RUN_ID)
    finalize_coverage_after_disposition(conn, run_id=RUN_ID, filing_id="coverage-deal_filing_1")

    rows = conn.execute(
        """
        SELECT obligation_id, result, claim_count
        FROM coverage_results
        ORDER BY obligation_id
        """
    ).fetchall()
    assert rows == [
        ("coverage-deal_obligation_1", "claims_emitted", 1),
        ("coverage-deal_obligation_2", "missed_supported_obligation", 0),
    ]


def test_unlinked_supported_obligation_becomes_missed_supported_obligation(tmp_path: Path) -> None:
    conn, request = _request_with_one_obligation(tmp_path, obligation_kind="ioi_count")
    response = _empty_completed_response(request)

    insert_llm_response(conn, request, response, run_id=RUN_ID)
    dispose_claims_for_filing(conn, filing_id=request.filing_id, run_id=RUN_ID)
    finalize_coverage_after_disposition(conn, run_id=RUN_ID, filing_id=request.filing_id)

    row = conn.execute(
        "SELECT result, reason_code FROM coverage_results WHERE obligation_id = ?",
        [request.coverage_obligations[0].obligation_id],
    ).fetchone()
    assert row == ("missed_supported_obligation", "missed_required_or_important_obligation")


def test_claims_emitted_requires_supported_linked_claim(tmp_path: Path) -> None:
    conn, request = _request_with_one_obligation(tmp_path, obligation_kind="final_consideration")
    response = _completed_response_with_bid_claim(request)

    claim_ids = insert_llm_response(conn, request, response, run_id=RUN_ID)
    # Force the linked claim to look unsupported, then run finalize_coverage to
    # publish a coverage row that asserts claims_emitted. The structural
    # validation should reject the inconsistency between coverage_results
    # claiming "claims_emitted" and the underlying disposition not being
    # supported. We bypass the normal disposition by setting the row directly.
    conn.execute("DELETE FROM claim_dispositions WHERE claim_id = ?", [claim_ids[0]])
    conn.execute(
        "INSERT INTO claim_dispositions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            "coverage-deal_disposition_1",
            claim_ids[0],
            RUN_ID,
            "rejected_unsupported",
            "test_rejection",
            "test",
            None,
            None,
            None,
            "test",
            True,
        ],
    )
    # Manually publish a claims_emitted coverage row that contradicts the
    # disposition; structural validation must catch the mismatch.
    obligation_id = request.coverage_obligations[0].obligation_id
    conn.execute("DELETE FROM coverage_results WHERE obligation_id = ?", [obligation_id])
    conn.execute(
        "INSERT INTO coverage_results VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        [
            "coverage-deal_coverageresult_1",
            RUN_ID,
            obligation_id,
            "claims_emitted",
            "claims_emitted",
            "Manually inserted to exercise structural validation.",
            1,
            True,
        ],
    )

    result = validate_database(conn)
    details = [finding.detail for finding in result.system_failures]
    assert any("claims_emitted requires supported linked claims" in item for item in details)


def test_inserted_claim_persists_coverage_obligation_link(tmp_path: Path) -> None:
    conn = connect(":memory:")
    init_schema(conn)
    _insert_window_source(conn, tmp_path)
    window = LLMWindowRequest(
        request_id="coverage-deal_llmrequest_1",
        deal_slug="coverage-deal",
        deal_id="coverage-deal",
        filing_id="coverage-deal_filing_1",
        region_id="coverage-deal_region_1",
        window_id="coverage-deal_window_1",
        region_kind="sale_process_narrative",
        ordered_paragraphs=[
            WindowParagraph(
                paragraph_id="coverage-deal_para_1",
                source_span_id="coverage-deal_evidence_1",
                char_start=0,
                char_end=89,
                paragraph_text=(
                    "The Board began a sale process. "
                    "The Board later granted exclusivity to Buyer A."
                ),
            )
        ],
        coverage_obligations=[
            WindowObligation(
                obligation_id="coverage-deal_obligation_1",
                expected_claim_type="event",
                obligation_label="Sales process initiation",
                importance="required",
            )
        ],
        allowed_claim_types=["event"],
        schema_version=1,
        extract_version=1,
        request_mode=DEFAULT_REQUEST_MODE,
    )
    payload = SemanticClaimsPayload(
        event_claims=[
            EventClaimPayload(
                claim_type="event",
                coverage_obligation_id="coverage-deal_obligation_1",
                event_type="process",
                event_subtype="contact_initial",
                event_date=None,
                description="The Board began a sale process.",
                actor_label=None,
                actor_role=None,
                confidence="high",
                quote_text="The Board began a sale process.",
            )
        ]
    )
    response = LLMExtractionResponse(
        request_id=window.request_id,
        provider_name="linkflow",
        provider_model="gpt-5.5",
        reasoning_effort="medium",
        payload=payload,
        raw_response_sha256=quote_hash(json.dumps(payload.model_dump(mode="json"), sort_keys=True)),
        finish_status="completed",
    )

    [claim_id] = insert_llm_response(conn, window, response, run_id=RUN_ID)

    assert conn.execute(
        """
        SELECT claim_id, obligation_id, run_id, current
        FROM claim_coverage_links
        """
    ).fetchall() == [
        (claim_id, "coverage-deal_obligation_1", RUN_ID, True)
    ]


def test_rejected_claim_obligation_link_rolls_back_partial_inserts(tmp_path: Path) -> None:
    conn = connect(":memory:")
    init_schema(conn)
    _insert_window_source(conn, tmp_path)

    window = LLMWindowRequest(
        request_id="coverage-deal_llmrequest_1",
        deal_slug="coverage-deal",
        deal_id="coverage-deal",
        filing_id="coverage-deal_filing_1",
        region_id="coverage-deal_region_1",
        window_id="coverage-deal_window_1",
        region_kind="sale_process_narrative",
        ordered_paragraphs=[
            WindowParagraph(
                paragraph_id="coverage-deal_para_1",
                source_span_id="coverage-deal_evidence_1",
                char_start=0,
                char_end=89,
                paragraph_text=(
                    "The Board began a sale process. "
                    "The Board later granted exclusivity to Buyer A."
                ),
            )
        ],
        coverage_obligations=[
            WindowObligation(
                obligation_id="coverage-deal_obligation_1",
                expected_claim_type="actor",
                obligation_label="Target board",
                importance="required",
            ),
            WindowObligation(
                obligation_id="coverage-deal_obligation_2",
                expected_claim_type="actor_relation",
                obligation_label="Buyer group composition",
                importance="important",
            ),
        ],
        allowed_claim_types=["actor", "actor_relation"],
        schema_version=1,
        extract_version=1,
        request_mode=DEFAULT_REQUEST_MODE,
    )
    payload = SemanticClaimsPayload(
        actor_claims=[
            ActorClaimPayload(
                claim_type="actor",
                coverage_obligation_id="coverage-deal_obligation_1",
                actor_label="The Board",
                actor_kind="committee",
                observability="named",
                confidence="high",
                quote_text="The Board began a sale process.",
            )
        ],
        actor_relation_claims=[
            ActorRelationClaimPayload(
                claim_type="actor_relation",
                coverage_obligation_id="coverage-deal_obligation_1",
                subject_label="Buyer A",
                object_label="The Board",
                relation_type="member_of",
                role_detail=None,
                effective_date_first=None,
                confidence="medium",
                quote_text="The Board later granted exclusivity to Buyer A.",
            )
        ],
    )
    response = LLMExtractionResponse(
        request_id=window.request_id,
        provider_name="linkflow",
        provider_model="gpt-5.5",
        reasoning_effort="medium",
        payload=payload,
        raw_response_sha256=quote_hash(json.dumps(payload.model_dump(mode="json"), sort_keys=True)),
        finish_status="completed",
    )

    try:
        insert_llm_response(conn, window, response, run_id=RUN_ID)
    except LLMContractError as exc:
        assert "does not match expected_claim_type" in str(exc)
    else:
        raise AssertionError("expected wrong obligation family to fail")

    for table in (
        "claims",
        "actor_claims",
        "actor_relation_claims",
        "claim_coverage_links",
        "claim_evidence",
        "coverage_results",
    ):
        assert conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0] == 0


def test_unlinked_applicable_obligations_get_all_python_coverage_states(tmp_path: Path) -> None:
    conn = connect(":memory:")
    init_schema(conn)
    _insert_window_source(conn, tmp_path)

    _replace_obligations(
        conn,
        [
            (
                "process_initiation",
                "event",
                "Sales process initiation",
                "required",
                "universal_sale_process",
                [],
            ),
            (
                "exclusivity_grant",
                "event",
                "Exclusivity grant",
                "important",
                "positive_source_support",
                ["exclusivity"],
            ),
            (
                "target_legal_advisor",
                "actor",
                "Legal advisor for target",
                "required",
                "universal_sale_process",
                [],
            ),
            (
                "tender_offer_prior_contacts",
                "event",
                "Tender-offer prior contacts",
                "important",
                "process_scope:bidder_partial_schedule_to",
                ["bidder_partial_schedule_to"],
            ),
        ],
    )
    window = LLMWindowRequest(
        request_id="coverage-deal_llmrequest_1",
        deal_slug="coverage-deal",
        deal_id="coverage-deal",
        filing_id="coverage-deal_filing_1",
        region_id="coverage-deal_region_1",
        window_id="coverage-deal_window_1",
        region_kind="sale_process_narrative",
        ordered_paragraphs=[
            WindowParagraph(
                paragraph_id="coverage-deal_para_1",
                source_span_id="coverage-deal_evidence_1",
                char_start=0,
                char_end=89,
                paragraph_text=(
                    "The Board began a sale process. "
                    "The Board later granted exclusivity to Buyer A."
                ),
            )
        ],
        coverage_obligations=[
            WindowObligation(
                obligation_id="coverage-deal_obligation_1",
                expected_claim_type="event",
                obligation_label="Sales process initiation",
                importance="required",
            ),
            WindowObligation(
                obligation_id="coverage-deal_obligation_2",
                expected_claim_type="event",
                obligation_label="Exclusivity grant",
                importance="important",
            ),
            WindowObligation(
                obligation_id="coverage-deal_obligation_3",
                expected_claim_type="actor",
                obligation_label="Legal advisor for target",
                importance="required",
            ),
            WindowObligation(
                obligation_id="coverage-deal_obligation_4",
                expected_claim_type="event",
                obligation_label="Tender-offer prior contacts",
                importance="important",
            ),
        ],
        allowed_claim_types=["event", "actor"],
        schema_version=1,
        extract_version=1,
        request_mode=DEFAULT_REQUEST_MODE,
    )
    payload = SemanticClaimsPayload(
        event_claims=[
            EventClaimPayload(
                claim_type="event",
                coverage_obligation_id="coverage-deal_obligation_1",
                event_type="process",
                event_subtype="contact_initial",
                event_date=None,
                description="The Board began a sale process.",
                actor_label=None,
                actor_role=None,
                confidence="high",
                quote_text="The Board began a sale process.",
            )
        ]
    )
    response = LLMExtractionResponse(
        request_id=window.request_id,
        provider_name="linkflow",
        provider_model="gpt-5.5",
        reasoning_effort="medium",
        payload=payload,
        raw_response_sha256=quote_hash(json.dumps(payload.model_dump(mode="json"), sort_keys=True)),
        finish_status="completed",
    )

    insert_llm_response(conn, window, response, run_id=RUN_ID)
    dispose_claims_for_filing(conn, filing_id="coverage-deal_filing_1", run_id=RUN_ID)
    finalize_coverage_after_disposition(conn, run_id=RUN_ID, filing_id="coverage-deal_filing_1")

    rows = conn.execute(
        """
        SELECT obligation_id, result, reason_code, claim_count
        FROM coverage_results
        ORDER BY obligation_id
        """
    ).fetchall()
    assert rows == [
        ("coverage-deal_obligation_1", "claims_emitted", "claims_emitted", 1),
        ("coverage-deal_obligation_2", "missed_supported_obligation", "missed_required_or_important_obligation", 0),
        ("coverage-deal_obligation_3", "missed_supported_obligation", "missed_required_or_important_obligation", 0),
        ("coverage-deal_obligation_4", "missed_supported_obligation", "missed_required_or_important_obligation", 0),
    ]


def _request_with_one_obligation(tmp_path: Path, *, obligation_kind: str) -> tuple[duckdb.DuckDBPyConnection, LLMWindowRequest]:
    conn = connect(":memory:")
    init_schema(conn)
    _insert_window_source(conn, tmp_path)
    _replace_obligations(
        conn,
        [
            (
                obligation_kind,
                "bid" if obligation_kind == "final_consideration" else "participation_count",
                "Final consideration" if obligation_kind == "final_consideration" else "IOI count",
                "required",
                "positive_source_support",
                ["exclusivity"] if obligation_kind == "final_consideration" else ["sale process"],
            )
        ],
    )
    request = LLMWindowRequest(
        request_id="coverage-deal_llmrequest_1",
        deal_slug="coverage-deal",
        deal_id="coverage-deal",
        filing_id="coverage-deal_filing_1",
        region_id="coverage-deal_region_1",
        window_id="coverage-deal_window_1",
        region_kind="sale_process_narrative",
        ordered_paragraphs=[
            WindowParagraph(
                paragraph_id="coverage-deal_para_1",
                source_span_id="coverage-deal_evidence_1",
                char_start=0,
                char_end=89,
                paragraph_text=(
                    "The Board began a sale process. "
                    "The Board later granted exclusivity to Buyer A."
                ),
            )
        ],
        coverage_obligations=[
            WindowObligation(
                obligation_id="coverage-deal_obligation_1",
                expected_claim_type="bid" if obligation_kind == "final_consideration" else "participation_count",
                obligation_label="Final consideration" if obligation_kind == "final_consideration" else "IOI count",
                importance="required",
            )
        ],
        allowed_claim_types=["bid"] if obligation_kind == "final_consideration" else ["participation_count"],
        schema_version=1,
        extract_version=1,
        request_mode=DEFAULT_REQUEST_MODE,
    )
    return conn, request


def _empty_completed_response(request: LLMWindowRequest) -> LLMExtractionResponse:
    payload = SemanticClaimsPayload()
    return LLMExtractionResponse(
        request_id=request.request_id,
        provider_name="linkflow",
        provider_model="gpt-5.5",
        reasoning_effort="medium",
        payload=payload,
        raw_response_sha256=quote_hash(json.dumps(payload.model_dump(mode="json"), sort_keys=True)),
        finish_status="completed",
    )


def _completed_response_with_bid_claim(request: LLMWindowRequest) -> LLMExtractionResponse:
    payload = SemanticClaimsPayload(
        bid_claims=[
            BidClaimPayload(
                claim_type="bid",
                coverage_obligation_id=request.coverage_obligations[0].obligation_id,
                bidder_label="Buyer A",
                bid_date=None,
                bid_value=10.0,
                bid_value_lower=None,
                bid_value_upper=None,
                bid_value_unit="USD_per_share",
                consideration_type="cash",
                bid_stage="final",
                confidence="high",
                quote_text="The Board later granted exclusivity to Buyer A.",
            )
        ]
    )
    return LLMExtractionResponse(
        request_id=request.request_id,
        provider_name="linkflow",
        provider_model="gpt-5.5",
        reasoning_effort="medium",
        payload=payload,
        raw_response_sha256=quote_hash(json.dumps(payload.model_dump(mode="json"), sort_keys=True)),
        finish_status="completed",
    )


def _insert_window_source(conn, tmp_path: Path) -> None:
    text = "The Board began a sale process. The Board later granted exclusivity to Buyer A."
    source_path = tmp_path / "coverage-deal.md"
    source_path.write_text(text, encoding="utf-8")
    filing = CleanFiling(
        filing_id=make_id("coverage-deal", "filing", 1),
        deal_slug="coverage-deal",
        source_path=str(source_path),
        raw_sha256=quote_hash(text),
        parser_version=1,
        page_count=None,
        section_count=1,
        process_scope="target_full_proxy",
    )
    paragraph = Paragraph(
        paragraph_id=make_id("coverage-deal", "para", 1),
        filing_id=filing.filing_id,
        section="Background of the Merger",
        page_hint=None,
        char_start=0,
        char_end=len(text),
        paragraph_text=text,
        paragraph_hash=quote_hash(text),
    )
    text_hash = quote_hash(text)
    span = SourceSpan(
        evidence_id=make_id("coverage-deal", "evidence", 1),
        filing_id=filing.filing_id,
        paragraph_id=paragraph.paragraph_id,
        span_basis="raw_md",
        span_kind="paragraph_seed",
        parent_evidence_id=None,
        created_by_stage="ingest",
        char_start=0,
        char_end=len(text),
        quote_text=text,
        quote_text_hash=text_hash,
        evidence_fingerprint=evidence_fingerprint(filing.filing_id, 0, len(text), text_hash),
    )
    conn.execute("INSERT INTO filings VALUES (?, ?, ?, ?, ?, ?, ?, ?)", tuple(filing.model_dump().values()))
    conn.execute("INSERT INTO paragraphs VALUES (?, ?, ?, ?, ?, ?, ?, ?)", tuple(paragraph.model_dump().values()))
    conn.execute("INSERT INTO spans VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", tuple(span.model_dump().values()))
    conn.execute(
        "INSERT INTO evidence_regions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            make_id("coverage-deal", "region", 1),
            RUN_ID,
            filing.filing_id,
            filing.deal_slug,
            "sale_process_narrative",
            1,
            paragraph.paragraph_id,
            paragraph.paragraph_id,
            json.dumps([paragraph.paragraph_id]),
            json.dumps(["began a sale process", "granted exclusivity"]),
            json.dumps(["event"]),
        ],
    )
    obligation_kinds = (
        ("process_initiation", "Sales process initiation"),
        ("exclusivity_grant", "Exclusivity grant"),
    )
    for sequence, (kind, label) in enumerate(obligation_kinds, start=1):
        conn.execute(
            "INSERT INTO coverage_obligations VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                make_id("coverage-deal", "obligation", sequence),
                RUN_ID,
                make_id("coverage-deal", "region", 1),
                filing.filing_id,
                filing.deal_slug,
                "event",
                kind,
                label,
                "required",
                "applicable",
                "universal_sale_process",
                "[]",
                True,
            ],
        )


def _replace_obligations(conn, rows: list[tuple[str, str, str, str, str, list[str]]]) -> None:
    conn.execute("DELETE FROM coverage_results")
    conn.execute("DELETE FROM coverage_obligations")
    for sequence, (kind, claim_type, label, importance, reason_code, basis) in enumerate(rows, start=1):
        conn.execute(
            "INSERT INTO coverage_obligations VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                make_id("coverage-deal", "obligation", sequence),
                RUN_ID,
                make_id("coverage-deal", "region", 1),
                make_id("coverage-deal", "filing", 1),
                "coverage-deal",
                claim_type,
                kind,
                label,
                importance,
                "applicable",
                reason_code,
                json.dumps(basis),
                True,
            ],
        )
