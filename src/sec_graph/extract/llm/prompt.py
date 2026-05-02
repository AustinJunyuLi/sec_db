"""Prompt construction for within-deal narrative window LLM extraction."""

from __future__ import annotations

from sec_graph.extract.llm.models import LLMWindowRequest


def _format_prior_memory(window: LLMWindowRequest) -> str:
    memory = window.prior_deal_memory
    if not (
        memory.actor_aliases
        or memory.prior_events
        or memory.active_cycle_candidates
        or memory.unresolved_references
    ):
        return "(empty - this is an early window in the filing)"
    parts: list[str] = []
    if memory.actor_aliases:
        parts.append(
            "actor_aliases: "
            + "; ".join(
                f"{alias.alias} -> {alias.canonical_label}"
                for alias in memory.actor_aliases
            )
        )
    if memory.prior_events:
        parts.append(
            "prior_events: "
            + "; ".join(
                f"{event.event_kind}={event.normalized_value} ({event.quote_text!r})"
                for event in memory.prior_events
            )
        )
    if memory.active_cycle_candidates:
        parts.append(
            "active_cycle_candidates: "
            + "; ".join(
                cycle.cycle_label for cycle in memory.active_cycle_candidates
            )
        )
    if memory.unresolved_references:
        parts.append(
            "unresolved_references: "
            + "; ".join(ref.reference_text for ref in memory.unresolved_references)
        )
    return "\n".join(parts)


def _format_paragraphs(window: LLMWindowRequest) -> str:
    blocks = []
    for index, paragraph in enumerate(window.ordered_paragraphs, start=1):
        blocks.append(
            f"[paragraph {index} | {paragraph.paragraph_id}]\n{paragraph.paragraph_text}"
        )
    return "\n\n".join(blocks)


def build_window_prompt(window: LLMWindowRequest) -> str:
    """Render the within-deal narrative window prompt.

    The prompt MUST:
    - tell the model the input is ordered paragraphs from a single filing;
    - surface prior_deal_memory derived from earlier paragraphs in the SAME filing;
    - instruct the model to emit quote_text only (Python derives offsets);
    - declare the closed candidate payload shape and forbid offset fields.
    """

    allowed = ", ".join(window.allowed_candidate_types)
    tasks = ", ".join(window.extraction_tasks)
    return (
        "You extract evidence-bound candidate payloads from ordered paragraphs "
        "from a single filing window. Earlier paragraphs in this window establish "
        "facts that may be referenced by later paragraphs. The window is one filing "
        "only - no other deals or filings are present.\n"
        "Return JSON only, with a top-level object containing a candidates array.\n"
        "Do not emit canonical rows, actors, events, judgments, or projections.\n"
        f"Allowed candidate_type values: {allowed}.\n"
        f"Extraction tasks for this window: {tasks}.\n"
        "Each candidate object must contain exactly these keys: candidate_type, "
        "raw_value, normalized_value, confidence, quote_text, dependencies.\n"
        "confidence must be one of low, medium, high. dependencies must be an array; "
        "use [] when no dependency applies.\n"
        "Set raw_value to the exact extracted text. Normalization is strict: "
        "dated_event normalized_value must be YYYY-MM-DD only; omit date ranges, "
        "relative dates, and times. bid_value normalized_value must be a numeric "
        "per-share amount like 20.75 or a numeric range like 18.00-19.00, with no "
        "currency symbols, inequalities, units, or words. participation_count "
        "normalized_value must be a positive integer string. For actor_mention, "
        "normalized_value should be the canonical actor label.\n"
        "For every candidate, quote_text must be an exact substring of the assembled "
        "window text and must appear exactly once across the window. Do not emit "
        "character offsets - Python derives them deterministically from quote_text. "
        "Omit any candidate whose quote_text you cannot copy exactly or whose "
        "quote_text appears more than once. If a label appears repeatedly, use a "
        "larger exact phrase that appears once and contains that label, or omit the "
        "candidate.\n"
        "If no supported candidates exist, return {\"candidates\": []}.\n\n"
        f"deal_id: {window.deal_id}\n"
        f"filing_id: {window.filing_id}\n"
        f"window_id: {window.window_id}\n"
        f"window_kind: {window.window_kind}\n"
        "prior_deal_memory (within this filing only):\n"
        f"{_format_prior_memory(window)}\n\n"
        "Ordered window paragraphs:\n"
        f"{_format_paragraphs(window)}\n"
    )
