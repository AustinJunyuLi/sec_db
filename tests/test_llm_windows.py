"""Within-deal narrative window contract for the LLM extraction interface."""

from pathlib import Path

import pytest

from sec_graph.extract.llm.convert import insert_llm_response
from sec_graph.extract.llm.models import (
    LLMCandidatePayload,
    LLMContractError,
    LLMExtractionResponse,
    LLMWindowRequest,
    WindowParagraph,
)
from sec_graph.extract.llm.prompt import build_window_prompt
from sec_graph.extract.llm.requests import build_llm_windows
from sec_graph.ingest.pipeline import ingest_examples
from sec_graph.schema import connect, init_schema


def _conn():
    conn = connect(":memory:")
    init_schema(conn)
    ingest_examples(conn, examples_dir=Path("data/examples"))
    return conn


def _windows_for_filing(conn, filing_id: str) -> list[LLMWindowRequest]:
    return build_llm_windows(conn, filing_id=filing_id)


def test_llm_requests_are_deal_windows_not_single_paragraphs() -> None:
    conn = _conn()
    windows = _windows_for_filing(conn, "petsmart-inc_filing_1")

    # The contract has changed: paragraph-only build_llm_requests must be gone.
    from sec_graph.extract.llm import requests as requests_module

    assert not hasattr(requests_module, "build_llm_requests"), (
        "build_llm_requests (paragraph-only) must be deleted; use build_llm_windows"
    )

    assert windows, "expected at least one within-deal window"
    multi_paragraph_windows = [w for w in windows if len(w.ordered_paragraphs) > 1]
    assert multi_paragraph_windows, (
        "at least one window must aggregate multiple paragraphs to honor within-deal memory"
    )
    assert all(isinstance(w, LLMWindowRequest) for w in windows)
    # Closed enum window_kind
    allowed_kinds = {"narrative_arc", "process_step_cluster", "actor_introduction"}
    assert {w.window_kind for w in windows} <= allowed_kinds


def test_window_contains_ordered_paragraph_refs_and_source_span_refs() -> None:
    conn = _conn()
    windows = _windows_for_filing(conn, "petsmart-inc_filing_1")
    window = next(w for w in windows if len(w.ordered_paragraphs) > 1)

    # Ordered: char_start strictly non-decreasing.
    starts = [p.char_start for p in window.ordered_paragraphs]
    assert starts == sorted(starts), "window paragraphs must be ordered by char_start"

    for p in window.ordered_paragraphs:
        assert isinstance(p, WindowParagraph)
        assert p.paragraph_id
        assert p.source_span_id  # underlying paragraph_seed evidence_id
        assert p.char_end >= p.char_start

    # Verify source spans actually exist in the DB and are paragraph seeds.
    span_ids = [p.source_span_id for p in window.ordered_paragraphs]
    placeholders = ",".join(["?"] * len(span_ids))
    rows = conn.execute(
        f"SELECT evidence_id, span_kind FROM spans WHERE evidence_id IN ({placeholders})",
        span_ids,
    ).fetchall()
    assert len(rows) == len(span_ids)
    assert all(row[1] == "paragraph_seed" for row in rows)


def test_window_carries_prior_actor_alias_and_event_memory() -> None:
    conn = _conn()
    windows = _windows_for_filing(conn, "petsmart-inc_filing_1")
    # The first window has empty prior memory; later windows must carry memory.
    later_windows = [w for w in windows if int(w.window_id.rsplit("_", 1)[1]) > 1]
    assert later_windows, "expected more than one window for the petsmart filing"

    has_memory = False
    for window in later_windows:
        memory = window.prior_deal_memory
        # prior_deal_memory must be a dict with the four required compact lists.
        assert set(memory.model_fields_set) >= {
            "actor_aliases",
            "prior_events",
            "active_cycle_candidates",
            "unresolved_references",
        } or set(memory.__class__.model_fields.keys()) >= {
            "actor_aliases",
            "prior_events",
            "active_cycle_candidates",
            "unresolved_references",
        }
        if memory.actor_aliases or memory.prior_events:
            has_memory = True
    assert has_memory, "later windows must surface prior actor aliases or prior events"

    # The prompt must surface the prior_deal_memory so the model can use it.
    sample = next(w for w in later_windows if w.prior_deal_memory.actor_aliases)
    prompt = build_window_prompt(sample)
    assert "prior_deal_memory" in prompt or "Prior deal memory" in prompt
    # And the prompt must instruct quote_text only, no offsets.
    assert "quote_text" in prompt
    assert "char_start" not in prompt
    assert "char_end" not in prompt
    assert "quote_start" not in prompt
    assert "quote_end" not in prompt


def test_quotes_from_window_candidates_validate_against_source_spans() -> None:
    conn = _conn()
    windows = _windows_for_filing(conn, "petsmart-inc_filing_1")
    # Pick a window that includes a known dated event paragraph from petsmart.
    target_quote = "On May 21, 2014,"
    window = next(
        w for w in windows
        if any(target_quote in p.paragraph_text for p in w.ordered_paragraphs)
    )

    response = LLMExtractionResponse(
        request_id=window.request_id,
        provider_name="offline",
        provider_model="mock",
        reasoning_effort="low",
        candidates=[
            LLMCandidatePayload(
                candidate_type="dated_event",
                raw_value=target_quote,
                normalized_value="2014-05-21",
                confidence="medium",
                quote_text=target_quote,
                dependencies=[],
            )
        ],
        raw_response_sha256="0" * 64,
        finish_status="completed",
    )
    inserted = insert_llm_response(conn, window, response, run_id="window-offline")

    assert len(inserted) == 1
    evidence_id = inserted[0].evidence_ids[0]
    row = conn.execute(
        "SELECT char_start, char_end, paragraph_id, parent_evidence_id, quote_text "
        "FROM spans WHERE evidence_id = ?",
        [evidence_id],
    ).fetchone()
    char_start, char_end, paragraph_id, parent_evidence_id, quote_text = row

    # The recorded coordinates must agree with the underlying paragraph seed:
    # - parent must be the paragraph seed evidence_id of the paragraph that contains the quote
    # - char_start/char_end must reproduce the exact quote against the raw markdown
    matched_para = next(
        p for p in window.ordered_paragraphs if target_quote in p.paragraph_text
    )
    assert paragraph_id == matched_para.paragraph_id
    assert parent_evidence_id == matched_para.source_span_id
    assert quote_text == target_quote
    raw_text = Path("data/examples/petsmart-inc.md").read_text(encoding="utf-8")
    assert raw_text[char_start:char_end] == target_quote


def test_no_cross_deal_context_is_included() -> None:
    conn = _conn()
    petsmart_windows = _windows_for_filing(conn, "petsmart-inc_filing_1")
    saks_windows = _windows_for_filing(conn, "saks_filing_1")

    # Each window must reference exactly one filing_id and that must be the requested one.
    for window in petsmart_windows:
        assert window.filing_id == "petsmart-inc_filing_1"
        assert window.deal_id == "petsmart-inc"
    for window in saks_windows:
        assert window.filing_id == "saks_filing_1"
        assert window.deal_id == "saks"

    # No saks paragraph_text content may appear inside any petsmart window's assembled text,
    # and vice versa. Use a deterministic distinctive token from each filing if present.
    saks_first_para = saks_windows[0].ordered_paragraphs[0].paragraph_text[:80]
    petsmart_first_para = petsmart_windows[0].ordered_paragraphs[0].paragraph_text[:80]

    for window in petsmart_windows:
        assembled = "\n".join(p.paragraph_text for p in window.ordered_paragraphs)
        assert saks_first_para not in assembled
    for window in saks_windows:
        assembled = "\n".join(p.paragraph_text for p in window.ordered_paragraphs)
        assert petsmart_first_para not in assembled

    # prior_deal_memory in each window must also be filing-scoped.
    for window in petsmart_windows:
        for alias in window.prior_deal_memory.actor_aliases:
            assert alias.source_paragraph_id.startswith("petsmart-inc_")
        for event in window.prior_deal_memory.prior_events:
            assert event.source_paragraph_id.startswith("petsmart-inc_")
