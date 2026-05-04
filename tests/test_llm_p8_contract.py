import json

from sec_graph.extract.llm.linkflow import _parse_payload, _response_payload
from sec_graph.extract.llm.models import (
    ActorRelationClaimPayload,
    DEFAULT_REQUEST_MODE,
    LLMContractError,
    LLMProviderConfig,
    LLMWindowRequest,
    WindowObligation,
    WindowParagraph,
)
from sec_graph.extract.llm.prompt import build_system_prompt, build_window_prompt


def _window_request() -> LLMWindowRequest:
    return LLMWindowRequest(
        request_id="smoke_llmrequest_1",
        deal_slug="smoke-deal",
        deal_id="smoke-deal",
        filing_id="smoke-deal_filing_1",
        region_id="smoke-deal_region_1",
        window_id="smoke-deal_window_1",
        region_kind="sale_process_narrative",
        ordered_paragraphs=[
            WindowParagraph(
                paragraph_id="p1",
                source_span_id="span1",
                char_start=0,
                char_end=96,
                paragraph_text=(
                    "The Board retained Example Advisors and began a sale process with "
                    "five potential bidders."
                ),
            )
        ],
        coverage_obligations=[
            WindowObligation(
                obligation_id="obl_event_1",
                expected_claim_type="event",
                obligation_label="Sales process initiation",
                importance="required",
            ),
            WindowObligation(
                obligation_id="obl_count_1",
                expected_claim_type="participation_count",
                obligation_label="Bidder count at IOI stage",
                importance="required",
            ),
        ],
        allowed_claim_types=["event", "participation_count"],
        schema_version=1,
        extract_version=1,
        request_mode=DEFAULT_REQUEST_MODE,
    )


def _all_claim_type_window_request() -> LLMWindowRequest:
    return LLMWindowRequest(
        request_id="smoke_llmrequest_1",
        deal_slug="smoke-deal",
        deal_id="smoke-deal",
        filing_id="smoke-deal_filing_1",
        region_id="smoke-deal_region_1",
        window_id="smoke-deal_window_1",
        region_kind="sale_process_narrative",
        ordered_paragraphs=[
            WindowParagraph(
                paragraph_id="p1",
                source_span_id="span1",
                char_start=0,
                char_end=120,
                paragraph_text="The Board retained advisors, contacted bidders, received a final bid, and Buyer Group formed Parent.",
            )
        ],
        coverage_obligations=[
            WindowObligation(
                obligation_id="obl_actor_1",
                expected_claim_type="actor",
                obligation_label="Target board",
                importance="required",
            ),
            WindowObligation(
                obligation_id="obl_event_1",
                expected_claim_type="event",
                obligation_label="Sales process initiation",
                importance="required",
            ),
            WindowObligation(
                obligation_id="obl_bid_1",
                expected_claim_type="bid",
                obligation_label="Final transaction price",
                importance="required",
            ),
            WindowObligation(
                obligation_id="obl_count_1",
                expected_claim_type="participation_count",
                obligation_label="Bidder count at IOI stage",
                importance="required",
            ),
            WindowObligation(
                obligation_id="obl_relation_1",
                expected_claim_type="actor_relation",
                obligation_label="Buyer group composition",
                importance="important",
            ),
        ],
        allowed_claim_types=["actor", "event", "bid", "participation_count", "actor_relation"],
        schema_version=1,
        extract_version=1,
        request_mode=DEFAULT_REQUEST_MODE,
    )


def _committee_recusal_relation_window_request() -> LLMWindowRequest:
    return LLMWindowRequest(
        request_id="smoke_llmrequest_relation_1",
        deal_slug="smoke-deal",
        deal_id="smoke-deal",
        filing_id="smoke-deal_filing_1",
        region_id="smoke-deal_region_1",
        window_id="smoke-deal_window_relation_1",
        region_kind="support_agreement",
        ordered_paragraphs=[
            WindowParagraph(
                paragraph_id="p1",
                source_span_id="span1",
                char_start=0,
                char_end=120,
                paragraph_text="Shareholder agreed to vote shares for the merger and Director A was added to the special committee.",
            )
        ],
        coverage_obligations=[
            WindowObligation(
                obligation_id="obl_relation_1",
                expected_claim_type="actor_relation",
                obligation_label="Special committee membership",
                importance="required",
            ),
            WindowObligation(
                obligation_id="obl_relation_2",
                expected_claim_type="actor_relation",
                obligation_label="Recusal from sale process",
                importance="required",
            ),
        ],
        allowed_claim_types=["actor_relation"],
        schema_version=1,
        extract_version=1,
        request_mode=DEFAULT_REQUEST_MODE,
    )


def _specific_relation_window_request() -> LLMWindowRequest:
    return LLMWindowRequest(
        request_id="smoke_llmrequest_relation_specific_1",
        deal_slug="smoke-deal",
        deal_id="smoke-deal",
        filing_id="smoke-deal_filing_1",
        region_id="smoke-deal_region_1",
        window_id="smoke-deal_window_relation_specific_1",
        region_kind="sale_process_narrative",
        ordered_paragraphs=[
            WindowParagraph(
                paragraph_id="p1",
                source_span_id="span1",
                char_start=0,
                char_end=180,
                paragraph_text=(
                    "Shareholder agreed to vote for the merger and Holder agreed "
                    "to rollover equity in Parent."
                ),
            )
        ],
        coverage_obligations=[
            WindowObligation(
                obligation_id="obl_relation_1",
                expected_claim_type="actor_relation",
                obligation_label="Voting support agreement",
                importance="important",
            ),
            WindowObligation(
                obligation_id="obl_relation_2",
                expected_claim_type="actor_relation",
                obligation_label="Rollover holder",
                importance="important",
            ),
        ],
        allowed_claim_types=["actor_relation"],
        schema_version=1,
        extract_version=1,
        request_mode=DEFAULT_REQUEST_MODE,
    )


def _unknown_relation_window_request() -> LLMWindowRequest:
    return LLMWindowRequest(
        request_id="smoke_llmrequest_relation_unknown_1",
        deal_slug="smoke-deal",
        deal_id="smoke-deal",
        filing_id="smoke-deal_filing_1",
        region_id="smoke-deal_region_1",
        window_id="smoke-deal_window_relation_unknown_1",
        region_kind="sale_process_narrative",
        ordered_paragraphs=[
            WindowParagraph(
                paragraph_id="p1",
                source_span_id="span1",
                char_start=0,
                char_end=120,
                paragraph_text="Shareholder agreed to vote shares for the merger.",
            )
        ],
        coverage_obligations=[
            WindowObligation(
                obligation_id="obl_relation_1",
                expected_claim_type="actor_relation",
                obligation_label="Voting support relation",
                importance="important",
            ),
        ],
        allowed_claim_types=["actor_relation"],
        schema_version=1,
        extract_version=1,
        request_mode=DEFAULT_REQUEST_MODE,
    )


def test_default_linkflow_reasoning_effort_is_medium() -> None:
    assert LLMProviderConfig(provider_name="linkflow").reasoning_effort == "medium"


def test_prompt_allows_cross_claim_quote_reuse() -> None:
    text = build_system_prompt() + "\n" + build_window_prompt(_window_request())

    assert "Same quote across different claims is fine" in text
    assert "copied character-for-character" in text
    assert "one bracketed paragraph" in text
    assert "appearing exactly once" not in text


def test_prompt_requires_one_matching_obligation_per_claim() -> None:
    text = build_system_prompt() + "\n" + build_window_prompt(_all_claim_type_window_request())

    assert "coverage_obligation_id" in text
    assert "exactly one obligation id from the same claim type" in text
    assert "Do not use []" in text
    assert "Python will mark missing coverage" in text


def test_provider_schema_top_level_properties_are_claim_arrays_only() -> None:
    payload = _response_payload(_all_claim_type_window_request(), LLMProviderConfig(provider_name="linkflow"))
    schema = payload["text"]["format"]["schema"]

    assert set(schema["properties"]) == {
        "actor_claims",
        "event_claims",
        "bid_claims",
        "participation_count_claims",
        "actor_relation_claims",
    }
    assert "coverage_results" not in schema["properties"]


def test_linkflow_payload_uses_system_and_user_messages() -> None:
    payload = _response_payload(_window_request(), LLMProviderConfig(provider_name="linkflow"))

    assert payload["input"][0]["role"] == "system"
    assert payload["input"][1]["role"] == "user"


def test_linkflow_payload_constrains_obligation_id_by_claim_family() -> None:
    payload = _response_payload(_all_claim_type_window_request(), LLMProviderConfig(provider_name="linkflow"))
    schema = payload["text"]["format"]["schema"]

    assert schema["properties"]["actor_claims"]["items"]["properties"]["coverage_obligation_id"]["enum"] == ["obl_actor_1"]
    assert schema["properties"]["event_claims"]["items"]["properties"]["coverage_obligation_id"]["enum"] == ["obl_event_1"]
    assert schema["properties"]["bid_claims"]["items"]["properties"]["coverage_obligation_id"]["enum"] == ["obl_bid_1"]
    assert schema["properties"]["participation_count_claims"]["items"]["properties"]["coverage_obligation_id"]["enum"] == ["obl_count_1"]
    assert schema["properties"]["actor_relation_claims"]["items"]["properties"]["coverage_obligation_id"]["enum"] == [
        "obl_relation_1"
    ]
    assert schema["properties"]["actor_relation_claims"]["items"]["properties"]["relation_type"]["enum"] == [
        "member_of",
        "affiliate_of",
        "controls",
        "acquisition_vehicle_of",
    ]
    assert schema["properties"]["bid_claims"]["items"]["properties"]["bid_stage"]["enum"] == ["final"]


def test_linkflow_payload_constrains_committee_and_recusal_relation_enums() -> None:
    payload = _response_payload(
        _committee_recusal_relation_window_request(),
        LLMProviderConfig(provider_name="linkflow"),
    )
    relation_enum = payload["text"]["format"]["schema"]["properties"]["actor_relation_claims"]["items"]["properties"][
        "relation_type"
    ]["enum"]

    assert relation_enum == [
        "committee_member_of",
        "recused_from",
    ]


def test_unmapped_relation_obligation_label_fails_loudly() -> None:
    try:
        _response_payload(
            _unknown_relation_window_request(),
            LLMProviderConfig(provider_name="linkflow"),
        )
    except LLMContractError as exc:
        assert "unmapped actor-relation obligation label" in str(exc)
        assert "Voting support relation" in str(exc)
    else:
        raise AssertionError("unmapped actor-relation obligation labels must not widen the schema")


def test_linkflow_payload_constrains_relation_enum_from_relation_obligations() -> None:
    payload = _response_payload(_specific_relation_window_request(), LLMProviderConfig(provider_name="linkflow"))
    relation_enum = payload["text"]["format"]["schema"]["properties"]["actor_relation_claims"]["items"]["properties"][
        "relation_type"
    ]["enum"]

    assert relation_enum == [
        "voting_support_for",
        "rollover_holder_for",
    ]


def test_old_rollover_holder_relation_is_rejected_by_pydantic() -> None:
    old_relation = "rollover_holder" + "_of"
    try:
        ActorRelationClaimPayload(
            claim_type="actor_relation",
            coverage_obligation_id="obl_relation_1",
            subject_label="Holder",
            object_label="Buyer",
            relation_type=old_relation,
            role_detail=None,
            effective_date_first=None,
            confidence="high",
            quote_text="Holder rolled equity into Buyer.",
        )
    except Exception as exc:
        assert old_relation in str(exc)
    else:
        raise AssertionError("old rollover holder relation must be rejected")


def test_claim_payload_requires_scalar_coverage_obligation_id() -> None:
    try:
        ActorRelationClaimPayload(
            claim_type="actor_relation",
            coverage_obligation_ids=[],
            subject_label="Parent",
            object_label="Buyer Group",
            relation_type="acquisition_vehicle_of",
            role_detail=None,
            effective_date_first=None,
            confidence="high",
            quote_text="Parent was an acquisition vehicle of Buyer Group.",
        )
    except Exception as exc:
        assert "coverage_obligation_id" in str(exc)
    else:
        raise AssertionError("legacy coverage_obligation_ids list must be rejected")


def test_parse_payload_rejects_provider_coverage_results() -> None:
    payload = {
        "actor_claims": [],
        "event_claims": [],
        "bid_claims": [],
        "participation_count_claims": [],
        "actor_relation_claims": [],
        "coverage_results": [],
    }

    try:
        _parse_payload(json.dumps(payload))
    except LLMContractError as exc:
        assert "coverage_results" in str(exc)
    else:
        raise AssertionError("provider-owned coverage_results must be rejected")


def test_parse_payload_rejects_legacy_scalar_research_fields() -> None:
    payload = {
        "actor_claims": [
            {
                "coverage_obligation_id": "obl_actor_1",
                "claim_type": "actor",
                "actor_label": "Party A",
                "actor_kind": "organization",
                "observability": "named",
                "confidence": "high",
                "quote_text": "Party A submitted a proposal.",
                "actor_class": "financial",
            }
        ],
        "event_claims": [
            {
                "coverage_obligation_id": "obl_event_1",
                "claim_type": "event",
                "event_type": "process",
                "event_subtype": "contact_initial",
                "event_date": None,
                "description": "The process began.",
                "actor_label": None,
                "actor_role": None,
                "confidence": "high",
                "quote_text": "The process began.",
                "drop_agency": "bidder",
                "drop_reason": "price",
                "initiation_side": "target",
            }
        ],
        "bid_claims": [
            {
                "coverage_obligation_id": "obl_bid_1",
                "claim_type": "bid",
                "bidder_label": "Party A",
                "bid_date": None,
                "bid_value": 10.0,
                "bid_value_lower": None,
                "bid_value_upper": None,
                "bid_value_unit": "per_share",
                "consideration_type": "cash",
                "bid_stage": "final",
                "confidence": "high",
                "quote_text": "$10.00 per share",
                "bid_formality": "formal",
                "proposal_scope": "whole_company",
            }
        ],
        "participation_count_claims": [],
        "actor_relation_claims": [],
    }

    try:
        _parse_payload(json.dumps(payload))
    except LLMContractError as exc:
        message = str(exc)
        assert "actor_class" in message
        assert "drop_agency" in message
        assert "bid_formality" in message
    else:
        raise AssertionError("legacy scalar research fields must be rejected")


def test_prompt_limits_claims_to_listed_obligations() -> None:
    text = build_system_prompt() + "\n" + build_window_prompt(_all_claim_type_window_request())

    assert "that answers one listed coverage obligation" in text
    assert "Final transaction price" in text
    assert "not preliminary, rejected, superseded, financing, or advisory facts" in text
    assert "Buyer group composition" in text
