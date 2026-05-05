"""Prompt construction for typed semantic claim extraction."""

from __future__ import annotations

from sec_graph.extract.llm.models import LLMWindowRequest

_FINAL_PRICE_OBLIGATION_LABEL = "Final transaction price"


def build_system_prompt() -> str:
    return (
        "You extract relation-revised claim-only P8 sale-process semantic claims from SEC merger filing text.\n"
        "Extract every supported sale-process semantic claim that answers one listed coverage obligation.\n"
        "Exact quote copying is required for every claim.\n"
        "Quote_text must be contiguous text from one bracketed paragraph, copied character-for-character as shown.\n"
        "Preserve punctuation, capitalization, spacing, line breaks, dashes, and symbols; do not paraphrase, repair, or use ellipses.\n"
        "A quote must be unique in the input. If the quote is too short or ambiguous, choose a longer unique quote or omit the claim.\n"
        "Same quote across different claims is fine.\n"
        "One sentence may support actor, event, bid, count, and relation claims.\n"
        "Each claim must set coverage_obligation_id to exactly one obligation id from the same claim type. Do not use [], null, or another claim type's obligation id.\n"
        "Do not use an obligation as a catch-all for nearby but different facts.\n"
        "For actor_relation claims, use the shortest exact clause or sentence that directly states the relation.\n"
        "For actor_relation claims, prefer the most specific source-backed relation label. "
        "Use voting_support_for for voting/support agreements requiring a party to vote shares or support adoption. "
        "Use rollover_holder_for for equity rollover or retained-equity facts. "
        "Use committee_member_of for board or special committee membership. "
        "Use recused_from for recusal or exclusion from a process, meeting, negotiation, evaluation, or committee context. "
        "Use supports only when the source states support but does not support a more specific relation label.\n"
        "For bid claims, quote_text must contain the bidder, bid date, bid value, and bid/offer/proposal context in one contiguous quote.\n"
        "Do not emit scalar research labels for formality, initiation side, dropout agency, dropout reason, proposal scope, or actor class. "
        "Instead preserve the exact source language in ordinary actor, event, bid, count, or relation claims. "
        "Important source indicators include written, oral, non-binding, preliminary, revised, final, best and final, definitive, "
        "withdrew, did not respond, was not advanced, was excluded, contacted at board direction, unsolicited approach, "
        "financial buyer, strategic buyer, private equity, industry participant, and whole-company or asset proposal language.\n"
        "Dates use YYYY-MM-DD only when explicit; otherwise null. Never return an empty string for a date.\n"
        "Never emit char_start, char_end, canonical ids, projection rows, or provider offsets.\n"
        "If an obligation has no supported positive claim in the window, emit no claim for that obligation. Python will mark missing coverage.\n"
        "Return strict JSON only."
    )


def build_window_prompt(window: LLMWindowRequest) -> str:
    allowed = ", ".join(window.allowed_claim_types)
    obligations = _format_obligations_by_claim_type(window)
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
        "Every claim must set coverage_obligation_id to exactly one obligation id from the same claim type. "
        "Do not use [], null, an empty string, or an obligation id from another claim type.\n"
        "If an obligation has no supported positive claim in the window, emit no claim for that obligation. "
        "Python will mark missing coverage.\n\n"
        f"deal_slug: {window.deal_slug}\n"
        f"filing_id: {window.filing_id}\n"
        f"region_id: {window.region_id}\n"
        f"region_kind: {window.region_kind}\n"
        f"request_mode: {window.request_mode}\n\n"
        "Coverage obligations:\n"
        f"{obligations}\n\n"
        "Obligation acceptance rules:\n"
        f"{_format_acceptance_rules(window)}\n\n"
        "Window paragraphs:\n"
        f"{paragraphs}\n\n"
        "Extract every supported claim. Reuse quotes across distinct claims when warranted. "
        "Use exactly one same-type coverage_obligation_id on every claim. "
        "Return strict JSON only."
    )


def build_window_messages(window: LLMWindowRequest) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": build_system_prompt()},
        {"role": "user", "content": build_window_prompt(window)},
    ]


def _format_obligations_by_claim_type(window: LLMWindowRequest) -> str:
    lines: list[str] = []
    for claim_type in window.allowed_claim_types:
        matching = [item for item in window.coverage_obligations if item.expected_claim_type == claim_type]
        if not matching:
            continue
        lines.append(f"{claim_type}:")
        for item in matching:
            lines.append(f"- {item.obligation_id}: {item.importance} | {item.obligation_label}")
    return "\n".join(lines)


def _format_acceptance_rules(window: LLMWindowRequest) -> str:
    lines: list[str] = []
    labels = {item.obligation_label for item in window.coverage_obligations}
    if _FINAL_PRICE_OBLIGATION_LABEL in labels:
        lines.append(
            "- Final transaction price: emit only the final, winning, accepted, or best-and-final price claim; "
            "not preliminary, rejected, superseded, financing, or advisory facts. The quote must include bidder, date, value, and offer/proposal context."
        )
    if "Buyer group composition" in labels:
        lines.append(
            "- Buyer group composition: emit only buyer group membership, affiliate/control, or acquisition-vehicle relations; "
            "not financing, support, legal advisor, financial advisor, or negotiation-counterparty relations."
        )
    if "Final round bid receipt" in labels:
        lines.append(
            "- Final round bid receipt: emit event claims for receipt/submission of final or best-and-final bids, not every earlier bid."
        )
    if "Exclusivity grant" in labels:
        lines.append(
            "- Exclusivity grant: emit only if the target or committee grants exclusivity; bidder requests for exclusivity are not enough."
        )
    if "Financial advisor for target" in labels:
        lines.append(
            "- Financial advisor for target: emit an advises relation from the advisor to the target, company, board, or committee named in the quote. "
            "Do not emit bidder advisors for this obligation."
        )
    if "Legal advisor for target" in labels:
        lines.append(
            "- Legal advisor for target: emit an advises relation from counsel to the target, company, board, or committee named in the quote. "
            "Do not treat counsel as a bidder."
        )
    return "\n".join(lines) if lines else "- Use only the listed obligation labels as acceptance criteria."
