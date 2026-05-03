"""Prompt construction for typed semantic claim extraction."""

from __future__ import annotations

from sec_graph.extract.llm.models import LLMWindowRequest


def build_system_prompt() -> str:
    return (
        "You extract V0 sale-process semantic claims from SEC merger filing text.\n"
        "Extract every supported sale-process semantic claim.\n"
        "Exact quote copying is required for every claim.\n"
        "Quote_text must be contiguous text from one bracketed paragraph, copied character-for-character as shown.\n"
        "Preserve punctuation, capitalization, spacing, line breaks, dashes, and symbols; do not paraphrase, repair, or use ellipses.\n"
        "A quote must be unique in the input. If the quote is too short or ambiguous, choose a longer unique quote or omit the claim.\n"
        "Same quote across different claims is fine.\n"
        "One sentence may support actor, event, bid, count, and relation claims.\n"
        "For actor_relation claims, use the shortest exact clause or sentence that directly states the relation.\n"
        "Dates use YYYY-MM-DD only when explicit; otherwise null. Never return an empty string for a date.\n"
        "Never emit char_start, char_end, canonical ids, projection rows, or provider offsets.\n"
        "Emit one coverage_result per obligation; never emit missed.\n"
        "Return strict JSON only."
    )


def build_window_prompt(window: LLMWindowRequest) -> str:
    allowed = ", ".join(window.allowed_claim_types)
    obligations = "\n".join(
        f"- {item.obligation_id}: {item.expected_claim_type} | {item.importance} | {item.obligation_label}"
        for item in window.coverage_obligations
    )
    paragraphs = "\n\n".join(
        f"[{paragraph.paragraph_id}]\n{paragraph.paragraph_text}"
        for paragraph in window.ordered_paragraphs
    )
    return (
        "You propose meaning; Python proves quotes, coordinates, IDs, canonical rows, and projection rows.\n"
        "Use closed enum values only.\n"
        "For optional date fields, return YYYY-MM-DD only when the date is explicit; otherwise return null. "
        "Never return an empty string for a date.\n"
        f"Allowed claim types for this request: {allowed}.\n"
        "For each coverage obligation, either emit one or more supported claims or add a coverage result "
        "of no_supported_claim or ambiguous.\n\n"
        f"deal_slug: {window.deal_slug}\n"
        f"filing_id: {window.filing_id}\n"
        f"region_id: {window.region_id}\n"
        f"region_kind: {window.region_kind}\n"
        f"request_mode: {window.request_mode}\n\n"
        "Coverage obligations:\n"
        f"{obligations}\n\n"
        "Window paragraphs:\n"
        f"{paragraphs}\n\n"
        "Extract every supported claim. Reuse quotes across distinct claims when warranted. "
        "Emit one coverage_result per obligation. Return strict JSON only."
    )


def build_window_messages(window: LLMWindowRequest) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": build_system_prompt()},
        {"role": "user", "content": build_window_prompt(window)},
    ]
