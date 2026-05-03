import json
from pathlib import Path

from sec_graph.extract.evidence_map import build_evidence_map
from sec_graph.extract.llm.convert import insert_llm_response
from sec_graph.extract.llm.models import (
    ActorClaimPayload,
    ActorRelationClaimPayload,
    BidClaimPayload,
    EventClaimPayload,
    LLMExtractionResponse,
    ParticipationCountClaimPayload,
    SemanticClaimsPayload,
)
from sec_graph.extract.llm.requests import build_llm_windows
from sec_graph.project.summaries import write_projection_outputs
from sec_graph.reconcile.pipeline import reconcile_all
from sec_graph.schema import CleanFiling, Paragraph, SourceSpan, connect, evidence_fingerprint, init_schema, make_id, quote_hash
from sec_graph.validate.integrity import HardCheck, validate_database


RUN_ID = "2026-05-03T111213Z_semantics-deal_deadbeef"


def test_bid_claim_quote_must_support_bidder_date_and_context(tmp_path: Path) -> None:
    conn, source_path = _semantic_db(
        tmp_path,
        bid_quote="$10.00 per share",
        relation_quote="Parent was an acquisition vehicle of Buyer Group",
    )

    validation = validate_database(conn, raw_source_root=source_path.parent)

    assert any(
        failure.check == HardCheck.SEMANTIC_CLAIM_EVIDENCE
        and failure.table_name == "bid_claims"
        and "bidder_label" in failure.detail
        for failure in validation.hard_failures
    )

    proof = write_projection_outputs(
        conn,
        tmp_path / "thin-bid-proof",
        run_id=RUN_ID,
        projection_name="bidder_cycle_baseline_v1",
    )
    assert proof["verdict"] != "SOUND"
    assert proof["semantic_validation_failures"] >= 1


def test_actor_relation_quote_must_support_subject_object_and_relation(tmp_path: Path) -> None:
    conn, source_path = _semantic_db(
        tmp_path,
        bid_quote="On January 1, 2020, Party A submitted a final proposal of $10.00 per share",
        relation_quote="Buyer Group",
    )

    validation = validate_database(conn, raw_source_root=source_path.parent)

    assert any(
        failure.check == HardCheck.SEMANTIC_CLAIM_EVIDENCE
        and failure.table_name == "actor_relation_claims"
        and "subject_label" in failure.detail
        for failure in validation.hard_failures
    )


def test_required_important_ambiguous_or_no_supported_coverage_blocks_sound(tmp_path: Path) -> None:
    conn, _source_path = _semantic_db(
        tmp_path,
        bid_quote="On January 1, 2020, Party A submitted a final proposal of $10.00 per share",
        relation_quote="Parent was an acquisition vehicle of Buyer Group",
    )
    required_id = conn.execute(
        """
        SELECT obligation_id
        FROM coverage_obligations
        WHERE importance = 'required'
        ORDER BY obligation_id
        LIMIT 1
        """
    ).fetchone()[0]
    important_id = conn.execute(
        """
        SELECT obligation_id
        FROM coverage_obligations
        WHERE importance = 'important'
        ORDER BY obligation_id
        LIMIT 1
        """
    ).fetchone()[0]
    conn.execute("UPDATE coverage_results SET result = 'ambiguous', claim_count = 0 WHERE obligation_id = ?", [required_id])
    conn.execute("UPDATE coverage_results SET result = 'no_supported_claim', claim_count = 0 WHERE obligation_id = ?", [important_id])

    proof = write_projection_outputs(
        conn,
        tmp_path / "coverage-proof",
        run_id=RUN_ID,
        projection_name="bidder_cycle_baseline_v1",
    )

    assert proof["verdict"] != "SOUND"
    assert proof["insufficient_required_or_important_obligations"] == 2


def _semantic_db(tmp_path: Path, *, bid_quote: str, relation_quote: str):
    conn = connect(":memory:")
    init_schema(conn)
    source_path = _insert_filing(conn, tmp_path)
    build_evidence_map(conn, filing_id="semantics-deal_filing_1", run_id=RUN_ID)
    for window in build_llm_windows(conn, filing_id="semantics-deal_filing_1"):
        insert_llm_response(conn, window, _response_for_window(window, bid_quote=bid_quote, relation_quote=relation_quote), RUN_ID)
    reconcile_all(conn, run_id=RUN_ID)
    return conn, source_path


def _insert_filing(conn, tmp_path: Path) -> Path:
    text = (
        "Background of the Merger\n\n"
        "On January 1, 2020, Party A submitted a final proposal of $10.00 per share. "
        "The Company contacted 10 financial buyers. "
        "Parent was an acquisition vehicle of Buyer Group. "
        "The parties executed the merger agreement on January 5, 2020.\n"
    )
    source_path = tmp_path / "semantics-deal.md"
    source_path.write_text(text, encoding="utf-8")
    filing = CleanFiling(
        filing_id=make_id("semantics-deal", "filing", 1),
        deal_slug="semantics-deal",
        source_path=str(source_path),
        raw_sha256=quote_hash(text),
        parser_version=1,
        page_count=None,
        section_count=1,
        process_scope="target_full_proxy",
    )
    paragraph = Paragraph(
        paragraph_id=make_id("semantics-deal", "para", 1),
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
        evidence_id=make_id("semantics-deal", "evidence", 1),
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
    return source_path


def _response_for_window(window, *, bid_quote: str, relation_quote: str) -> LLMExtractionResponse:
    allowed = set(window.allowed_claim_types)
    obligation_ids = {
        claim_type: [
            obligation.obligation_id
            for obligation in window.coverage_obligations
            if obligation.expected_claim_type == claim_type
        ]
        for claim_type in allowed
    }
    payload = SemanticClaimsPayload(
        actor_claims=[
            ActorClaimPayload(
                coverage_obligation_ids=obligation_ids["actor"],
                claim_type="actor",
                actor_label="Party A",
                actor_kind="organization",
                observability="named",
                confidence="high",
                quote_text="Party A submitted a final proposal",
            )
        ]
        if "actor" in allowed
        else [],
        event_claims=[
            EventClaimPayload(
                coverage_obligation_ids=obligation_ids["event"],
                claim_type="event",
                event_type="transaction",
                event_subtype="merger_agreement_executed",
                event_date="2020-01-05",
                description="The parties executed the merger agreement.",
                actor_label="Party A",
                actor_role="bid_submitter",
                confidence="high",
                quote_text="executed the merger agreement on January 5, 2020",
            )
        ]
        if "event" in allowed
        else [],
        bid_claims=[
            BidClaimPayload(
                coverage_obligation_ids=obligation_ids["bid"],
                claim_type="bid",
                bidder_label="Party A",
                bid_date="2020-01-01",
                bid_value=10.0,
                bid_value_lower=None,
                bid_value_upper=None,
                bid_value_unit="per_share",
                consideration_type="cash",
                bid_stage="final",
                confidence="high",
                quote_text=bid_quote,
            )
        ]
        if "bid" in allowed
        else [],
        participation_count_claims=[
            ParticipationCountClaimPayload(
                coverage_obligation_ids=obligation_ids["participation_count"],
                claim_type="participation_count",
                process_stage="contacted",
                actor_class="financial",
                count_min=10,
                count_max=None,
                count_qualifier="exact",
                confidence="high",
                quote_text="contacted 10 financial buyers",
            )
        ]
        if "participation_count" in allowed
        else [],
        actor_relation_claims=[
            ActorRelationClaimPayload(
                coverage_obligation_ids=obligation_ids["actor_relation"],
                claim_type="actor_relation",
                subject_label="Parent",
                object_label="Buyer Group",
                relation_type="acquisition_vehicle_of",
                role_detail="acquisition vehicle",
                effective_date_first=None,
                confidence="high",
                quote_text=relation_quote,
            )
        ]
        if "actor_relation" in allowed
        else [],
    )
    return LLMExtractionResponse(
        request_id=window.request_id,
        provider_name="linkflow",
        provider_model="gpt-5.5",
        reasoning_effort="high",
        payload=payload,
        raw_response_sha256=quote_hash(json.dumps(payload.model_dump(mode="json"), sort_keys=True)),
        finish_status="completed",
    )
