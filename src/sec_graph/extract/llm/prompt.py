"""Prompt construction for paragraph-scoped LLM extraction."""

from __future__ import annotations

from sec_graph.extract.llm.models import LLMExtractionRequest


def build_prompt(request: LLMExtractionRequest) -> str:
    allowed = ", ".join(request.allowed_candidate_types)
    return (
        "You extract evidence-bound candidate payloads from one SEC merger filing paragraph.\n"
        "Return JSON only, with a top-level object containing a candidates array.\n"
        "Do not emit canonical rows, actors, events, judgments, or projections.\n"
        f"Allowed candidate_type values: {allowed}.\n"
        "For every candidate, quote_text must be an exact substring of paragraph_text, "
        "and quote_start/quote_end must be paragraph-local character offsets for that substring.\n"
        "If no supported candidates exist, return {\"candidates\": []}.\n\n"
        f"deal_slug: {request.deal_slug}\n"
        f"paragraph_id: {request.paragraph_id}\n"
        f"section: {request.section}\n"
        "paragraph_text:\n"
        f"{request.paragraph_text}"
    )
