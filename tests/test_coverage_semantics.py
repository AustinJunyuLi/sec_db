import json
from pathlib import Path

from sec_graph.extract.llm.convert import insert_llm_response
from sec_graph.extract.llm.models import (
    CoverageResultPayload,
    EventClaimPayload,
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
        request_mode="semantic_claims_v1",
    )
    payload = SemanticClaimsPayload(
        actor_claims=[],
        event_claims=[
            EventClaimPayload(
                claim_type="event",
                coverage_obligation_ids=["coverage-deal_obligation_1"],
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
        coverage_results=[
            CoverageResultPayload(
                obligation_id="coverage-deal_obligation_2",
                result="no_supported_claim",
                reason_code="not_in_source_window",
                reason="The window does not support an exclusivity event claim.",
            )
        ],
    )
    response = LLMExtractionResponse(
        request_id=window.request_id,
        provider_name="linkflow",
        provider_model="gpt-5.5",
        reasoning_effort="high",
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
        ("coverage-deal_obligation_2", "no_supported_claim", 0),
    ]


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
