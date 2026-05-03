from sec_graph.extract.llm.linkflow import _response_payload
from sec_graph.extract.llm.models import (
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
        request_mode="semantic_claims_v1",
    )


def test_default_linkflow_reasoning_effort_is_high() -> None:
    assert LLMProviderConfig(provider_name="linkflow").reasoning_effort == "high"


def test_prompt_allows_cross_claim_quote_reuse() -> None:
    text = build_system_prompt() + "\n" + build_window_prompt(_window_request())

    assert "Same quote across different claims is fine" in text
    assert "copied character-for-character" in text
    assert "one bracketed paragraph" in text
    assert "appearing exactly once" not in text


def test_linkflow_payload_uses_system_and_user_messages() -> None:
    payload = _response_payload(_window_request(), LLMProviderConfig(provider_name="linkflow"))

    assert payload["input"][0]["role"] == "system"
    assert payload["input"][1]["role"] == "user"
