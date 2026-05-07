import json
from pathlib import Path

from sec_graph.extract.llm.convert import insert_llm_response
from sec_graph.extract.llm.models import (
    ActorClaimPayload,
    ActorRelationClaimPayload,
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

    rows = conn.execute(
        """
        SELECT obligation_id, result, claim_count
        FROM coverage_results
        ORDER BY obligation_id
        """
    ).fetchall()
    assert rows == [
        ("coverage-deal_obligation_1", "claims_emitted", 1),
        ("coverage-deal_obligation_2", "missed", 0),
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
        "claim_evidence",
        "coverage_results",
    ):
        assert conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0] == 0


def test_event_claim_accepts_go_shop_and_amendment_subtypes(tmp_path: Path) -> None:
    """A go-shop / amendment event claim must round-trip through the schema."""

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
                obligation_label="Go-shop period",
                importance="optional",
            ),
            WindowObligation(
                obligation_id="coverage-deal_obligation_2",
                expected_claim_type="event",
                obligation_label="Amendment to merger agreement",
                importance="optional",
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
                event_subtype="go_shop_period",
                event_date=None,
                description="The Board began a sale process.",
                actor_label=None,
                actor_role=None,
                confidence="high",
                quote_text="The Board began a sale process.",
            ),
            EventClaimPayload(
                claim_type="event",
                coverage_obligation_id="coverage-deal_obligation_2",
                event_type="transaction",
                event_subtype="amendment",
                event_date=None,
                description="The Board later granted exclusivity to Buyer A.",
                actor_label=None,
                actor_role=None,
                confidence="high",
                quote_text="The Board later granted exclusivity to Buyer A.",
            ),
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

    subtypes = conn.execute(
        "SELECT event_subtype FROM event_claims ORDER BY event_subtype"
    ).fetchall()
    assert subtypes == [("amendment",), ("go_shop_period",)]


def test_participation_count_claim_accepts_unknown_actor_class(tmp_path: Path) -> None:
    """A count claim with actor_class='unknown' must round-trip through the schema."""

    from sec_graph.extract.llm.models import ParticipationCountClaimPayload

    conn = connect(":memory:")
    init_schema(conn)
    _insert_window_source(conn, tmp_path)
    # Replace the event obligations with a participation_count obligation so
    # the LLM payload can target it cleanly.
    conn.execute("DELETE FROM coverage_obligations WHERE filing_id = ?", ["coverage-deal_filing_1"])
    conn.execute(
        "INSERT INTO coverage_obligations VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            "coverage-deal_obligation_count",
            RUN_ID,
            "coverage-deal_region_1",
            "coverage-deal_filing_1",
            "coverage-deal",
            "participation_count",
            "Bidder count at IOI stage",
            "required",
            True,
        ],
    )

    window = LLMWindowRequest(
        request_id="coverage-deal_llmrequest_1",
        deal_slug="coverage-deal",
        deal_id="coverage-deal",
        filing_id="coverage-deal_filing_1",
        region_id="coverage-deal_region_1",
        window_id="coverage-deal_window_1",
        region_kind="participation_counts",
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
                obligation_id="coverage-deal_obligation_count",
                expected_claim_type="participation_count",
                obligation_label="Bidder count at IOI stage",
                importance="required",
            ),
        ],
        allowed_claim_types=["participation_count"],
        schema_version=1,
        extract_version=1,
        request_mode=DEFAULT_REQUEST_MODE,
    )
    payload = SemanticClaimsPayload(
        actor_claims=[],
        event_claims=[],
        bid_claims=[],
        participation_count_claims=[
            ParticipationCountClaimPayload(
                claim_type="participation_count",
                coverage_obligation_id="coverage-deal_obligation_count",
                process_stage="ioi_submitted",
                actor_class="unknown",
                count_min=4,
                count_max=None,
                count_qualifier="exact",
                confidence="high",
                quote_text="The Board began a sale process.",
            )
        ],
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

    rows = conn.execute(
        "SELECT actor_class, count_min FROM participation_count_claims"
    ).fetchall()
    assert rows == [("unknown", 4)]


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
    for sequence, label in enumerate(("Sales process initiation", "Exclusivity grant"), start=1):
        conn.execute(
            "INSERT INTO coverage_obligations VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                make_id("coverage-deal", "obligation", sequence),
                RUN_ID,
                make_id("coverage-deal", "region", 1),
                filing.filing_id,
                filing.deal_slug,
                "event",
                label,
                "required",
                True,
            ],
        )
