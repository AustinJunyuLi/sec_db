"""Validation semantics under the system_failures / review_items split."""

from __future__ import annotations

import json
from pathlib import Path

from sec_graph.extract.disposition import (
    dispose_claims_for_filing,
    finalize_coverage_after_disposition,
)
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
from sec_graph.validate.integrity import HardCheck, validate_database


RUN_ID = "2026-05-03T111213Z_semantics-deal_deadbeef"


def test_required_important_unresolved_coverage_is_review_not_system_failure(
    tmp_path: Path,
) -> None:
    conn, _source_path = _semantic_db(
        tmp_path,
        bid_quote="On January 1, 2020, Party A submitted a final proposal of $10.00 per share",
        relation_quote="Parent was an acquisition vehicle of Buyer Group",
    )
    required_id = conn.execute(
        """
        SELECT coverage_obligations.obligation_id
        FROM coverage_obligations
        JOIN coverage_results USING (obligation_id)
        WHERE importance = 'required'
          AND coverage_results.result = 'claims_emitted'
        ORDER BY obligation_id
        LIMIT 1
        """
    ).fetchone()[0]
    important_id = conn.execute(
        """
        SELECT coverage_obligations.obligation_id
        FROM coverage_obligations
        JOIN coverage_results USING (obligation_id)
        WHERE importance = 'important'
          AND coverage_results.result = 'claims_emitted'
        ORDER BY obligation_id
        LIMIT 1
        """
    ).fetchone()[0]
    conn.execute(
        "UPDATE coverage_results SET result = 'ambiguous_support', claim_count = 0 WHERE obligation_id = ?",
        [required_id],
    )
    conn.execute(
        "UPDATE coverage_results SET result = 'no_supported_claim', claim_count = 0 WHERE obligation_id = ?",
        [important_id],
    )

    validation = validate_database(conn)
    review_ids = {finding.row_id for finding in validation.review_items}
    assert required_id in review_ids
    assert important_id in review_ids
    # The same obligations must NOT appear as system failures.
    system_ids = {finding.row_id for finding in validation.system_failures}
    assert required_id not in system_ids
    assert important_id not in system_ids


def test_not_applicable_obligation_with_current_coverage_result_is_system_failure(
    tmp_path: Path,
) -> None:
    conn, _source_path = _semantic_db(
        tmp_path,
        bid_quote="On January 1, 2020, Party A submitted a final proposal of $10.00 per share",
        relation_quote="Parent was an acquisition vehicle of Buyer Group",
    )
    obligation_id = conn.execute(
        """
        SELECT obligation_id
        FROM coverage_obligations
        WHERE applicability = 'not_applicable'
        ORDER BY obligation_id
        LIMIT 1
        """
    ).fetchone()[0]
    conn.execute(
        "INSERT INTO coverage_results VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        [
            "bad_coverage_result",
            RUN_ID,
            obligation_id,
            "missed_supported_obligation",
            "bad_not_applicable_result",
            "not_applicable obligations must not carry coverage results",
            0,
            True,
        ],
    )

    validation = validate_database(conn)

    assert any(
        finding.check == HardCheck.COVERAGE_RESULT
        and finding.row_id == obligation_id
        and "not_applicable" in finding.detail
        for finding in validation.system_failures
    )


def test_projection_dependent_on_review_required_judgment_is_review_item(
    tmp_path: Path,
) -> None:
    conn, _source_path = _semantic_db(
        tmp_path,
        bid_quote="On January 1, 2020, Party A submitted a final proposal of $10.00 per share",
        relation_quote="Parent was an acquisition vehicle of Buyer Group",
    )
    event_id = conn.execute("SELECT event_id FROM events ORDER BY event_id LIMIT 1").fetchone()[0]
    conn.execute(
        "INSERT INTO review_rows VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            "semantics-deal_reviewrow_999",
            RUN_ID,
            "semantics-deal",
            "open",
            "judgment",
            "events",
            event_id,
            "review",
            "missing_projected_fate",
            "Projected fate cannot be derived.",
            "Review projected fate for this bidder-cycle row.",
            None,
            None,
            None,
            "events",
            event_id,
            None,
            None,
            None,
            None,
            "2026-05-07T00:00:00Z",
        ],
    )

    result = validate_database(conn)

    assert any(
        finding.check == HardCheck.PROJECTION_REVIEW
        and finding.detail.startswith("projection depends on review-required judgment")
        for finding in result.review_items
    )
    # Not a system failure.
    assert not any(
        finding.check == HardCheck.PROJECTION_REVIEW
        for finding in result.system_failures
    )


def test_claims_emitted_without_coverage_link_is_system_failure(tmp_path: Path) -> None:
    conn, _source_path = _semantic_db(
        tmp_path,
        bid_quote="On January 1, 2020, Party A submitted a final proposal of $10.00 per share",
        relation_quote="Parent was an acquisition vehicle of Buyer Group",
    )
    obligation_id = conn.execute(
        """
        SELECT obligation_id
        FROM coverage_results
        WHERE result = 'claims_emitted'
        ORDER BY obligation_id
        LIMIT 1
        """
    ).fetchone()[0]
    conn.execute("DELETE FROM claim_coverage_links WHERE obligation_id = ?", [obligation_id])

    validation = validate_database(conn)

    assert any(
        finding.check == HardCheck.COVERAGE_RESULT
        and finding.row_id == obligation_id
        and "claims_emitted has no linked claims" in finding.detail
        for finding in validation.system_failures
    )


def test_coverage_link_with_mismatched_claim_type_is_system_failure(tmp_path: Path) -> None:
    conn, _source_path = _semantic_db(
        tmp_path,
        bid_quote="On January 1, 2020, Party A submitted a final proposal of $10.00 per share",
        relation_quote="Parent was an acquisition vehicle of Buyer Group",
    )
    obligation_id, claim_id = _claims_emitted_link(conn)
    conn.execute(
        """
        UPDATE claims
        SET claim_type = CASE WHEN claim_type = 'event' THEN 'actor' ELSE 'event' END
        WHERE claim_id = ?
        """,
        [claim_id],
    )

    validation = validate_database(conn)

    assert any(
        finding.check == HardCheck.COVERAGE_RESULT
        and finding.row_id == obligation_id
        and claim_id in finding.detail
        for finding in validation.system_failures
    )


def test_coverage_link_with_mismatched_claim_run_is_system_failure(tmp_path: Path) -> None:
    conn, _source_path = _semantic_db(
        tmp_path,
        bid_quote="On January 1, 2020, Party A submitted a final proposal of $10.00 per share",
        relation_quote="Parent was an acquisition vehicle of Buyer Group",
    )
    obligation_id, claim_id = _claims_emitted_link(conn)
    conn.execute(
        "UPDATE claims SET run_id = '2026-05-03T111213Z_other-run_badf00d' WHERE claim_id = ?",
        [claim_id],
    )

    validation = validate_database(conn)

    assert any(
        finding.check == HardCheck.COVERAGE_RESULT
        and finding.row_id == obligation_id
        and claim_id in finding.detail
        for finding in validation.system_failures
    )


def test_coverage_link_with_mismatched_claim_deal_is_system_failure(tmp_path: Path) -> None:
    conn, _source_path = _semantic_db(
        tmp_path,
        bid_quote="On January 1, 2020, Party A submitted a final proposal of $10.00 per share",
        relation_quote="Parent was an acquisition vehicle of Buyer Group",
    )
    obligation_id, claim_id = _claims_emitted_link(conn)
    conn.execute("UPDATE claims SET deal_slug = 'other-deal' WHERE claim_id = ?", [claim_id])

    validation = validate_database(conn)

    assert any(
        finding.check == HardCheck.COVERAGE_RESULT
        and finding.row_id == obligation_id
        and claim_id in finding.detail
        for finding in validation.system_failures
    )


def test_unsupported_claim_in_canonical_tables_is_system_failure(tmp_path: Path) -> None:
    """If a claim_coverage_link exists for an unsupported claim under
    ``claims_emitted``, validation must flag it as a system failure."""

    conn, _source_path = _semantic_db(
        tmp_path,
        bid_quote="On January 1, 2020, Party A submitted a final proposal of $10.00 per share",
        relation_quote="Parent was an acquisition vehicle of Buyer Group",
    )
    obligation_id, claim_id = _claims_emitted_link(conn)
    conn.execute(
        "UPDATE claim_dispositions SET disposition = 'rejected_unsupported' WHERE claim_id = ?",
        [claim_id],
    )

    validation = validate_database(conn)

    assert any(
        finding.check == HardCheck.COVERAGE_RESULT
        and "claims_emitted requires supported linked claims" in finding.detail
        for finding in validation.system_failures
    )


def test_validation_result_passed_property_reflects_only_system_failures(
    tmp_path: Path,
) -> None:
    conn, _source_path = _semantic_db(
        tmp_path,
        bid_quote="On January 1, 2020, Party A submitted a final proposal of $10.00 per share",
        relation_quote="Parent was an acquisition vehicle of Buyer Group",
    )
    # A green run.
    validation = validate_database(conn)
    assert validation.passed
    assert validation.system_failures == []


def _semantic_db(tmp_path: Path, *, bid_quote: str, relation_quote: str):
    conn = connect(":memory:")
    init_schema(conn)
    source_path = _insert_filing(conn, tmp_path)
    build_evidence_map(conn, filing_id="semantics-deal_filing_1", run_id=RUN_ID)
    for window in build_llm_windows(conn, filing_id="semantics-deal_filing_1"):
        insert_llm_response(
            conn,
            window,
            _response_for_window(window, bid_quote=bid_quote, relation_quote=relation_quote),
            RUN_ID,
        )
    dispose_claims_for_filing(conn, filing_id="semantics-deal_filing_1", run_id=RUN_ID)
    finalize_coverage_after_disposition(
        conn, run_id=RUN_ID, filing_id="semantics-deal_filing_1"
    )
    reconcile_all(conn, run_id=RUN_ID)
    return conn, source_path


def _claims_emitted_link(conn) -> tuple[str, str]:
    return conn.execute(
        """
        SELECT coverage_results.obligation_id, claim_coverage_links.claim_id
        FROM coverage_results
        JOIN claim_coverage_links USING (obligation_id)
        WHERE coverage_results.result = 'claims_emitted'
        ORDER BY coverage_results.obligation_id, claim_coverage_links.claim_id
        LIMIT 1
        """
    ).fetchone()


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
        claim_type: next(
            obligation.obligation_id
            for obligation in window.coverage_obligations
            if obligation.expected_claim_type == claim_type
        )
        for claim_type in allowed
    }
    payload = SemanticClaimsPayload(
        actor_claims=[
            ActorClaimPayload(
                coverage_obligation_id=obligation_ids["actor"],
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
                coverage_obligation_id=obligation_ids["event"],
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
                coverage_obligation_id=obligation_ids["bid"],
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
                coverage_obligation_id=obligation_ids["participation_count"],
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
                coverage_obligation_id=obligation_ids["actor_relation"],
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
        reasoning_effort="medium",
        payload=payload,
        raw_response_sha256=quote_hash(json.dumps(payload.model_dump(mode="json"), sort_keys=True)),
        finish_status="completed",
    )


def test_participation_count_actor_class_accepts_unknown(tmp_path: Path) -> None:
    """Filings often say 'parties' or 'potential acquirors' without class.

    The participation_count_claims schema and the canonical participation_counts
    table must both admit ``actor_class='unknown'``.
    """

    from sec_graph.schema.models.extraction import ActorClass as ClaimActorClass
    from sec_graph.schema.models.participation_counts import ActorClass as CanonicalActorClass

    assert "unknown" in ClaimActorClass.__args__
    assert "unknown" in CanonicalActorClass.__args__

    payload = ParticipationCountClaimPayload(
        coverage_obligation_id="any_obligation",
        claim_type="participation_count",
        process_stage="contacted",
        actor_class="unknown",
        count_min=4,
        count_max=None,
        count_qualifier="exact",
        confidence="high",
        quote_text="contacted four parties",
    )
    assert payload.actor_class == "unknown"

    conn = connect(":memory:")
    init_schema(conn)
    # Confirm the DDL CHECK constraint accepts 'unknown'. We can't insert a
    # full claim row without all FK rows, so probe the CHECK directly with a
    # transient table containing the same constraint.
    conn.execute(
        "CREATE TABLE _probe (actor_class VARCHAR CHECK (actor_class IN ('financial', 'strategic', 'mixed', 'unknown')))"
    )
    conn.execute("INSERT INTO _probe VALUES ('unknown')")
    conn.execute("INSERT INTO _probe VALUES ('financial')")
    rows = conn.execute("SELECT actor_class FROM _probe ORDER BY actor_class").fetchall()
    assert rows == [("financial",), ("unknown",)]


def test_event_subtype_taxonomy_includes_go_shop_and_amendment() -> None:
    """Event obligations need go-shop and amendment subtypes; the closed enum must cover them."""

    from sec_graph.schema.models.canonical import EventSubtype as CanonicalEventSubtype
    from sec_graph.schema.models.extraction import EventSubtype as ExtractionEventSubtype

    extraction_args = set(ExtractionEventSubtype.__args__)
    canonical_args = set(CanonicalEventSubtype.__args__)
    assert "go_shop_period" in extraction_args
    assert "amendment" in extraction_args
    assert "go_shop_period" in canonical_args
    assert "amendment" in canonical_args


def test_event_subtype_check_constraint_accepts_new_values() -> None:
    """The real canonical events CHECK constraint must include the new values."""

    conn = connect(":memory:")
    init_schema(conn)
    conn.execute(
        "INSERT INTO deals VALUES ('deal_1', 'run_1', 'slug', 'actor_1', NULL)"
    )
    conn.execute(
        "INSERT INTO process_cycles VALUES ('cycle_1', 'run_1', 'deal_1', 1, 'primary', NULL, NULL)"
    )
    conn.execute(
        """
        INSERT INTO events
        VALUES
          ('event_1', 'run_1', 'deal_1', 'cycle_1', 'process', 'go_shop_period', NULL, 'go-shop period', NULL, NULL, NULL, NULL, NULL),
          ('event_2', 'run_1', 'deal_1', 'cycle_1', 'transaction', 'amendment', NULL, 'amendment', NULL, NULL, NULL, NULL, NULL)
        """
    )
    rows = conn.execute(
        "SELECT event_subtype FROM events ORDER BY event_subtype"
    ).fetchall()
    assert rows == [("amendment",), ("go_shop_period",)]
