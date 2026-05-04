"""Phase 2: applicability decisions and obligation generation.

These tests prove the per-region applicability engine is deterministic,
that universal/conditional/scope-driven families behave correctly, and that
the evidence-map writes the audit columns Linkflow never sees.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from sec_graph.extract.applicability import (
    ALL_OBLIGATION_KINDS,
    CONDITIONAL_OBLIGATIONS,
    SCOPE_OBLIGATIONS,
    UNIVERSAL_OBLIGATIONS,
    decide_applicability,
)
from sec_graph.extract.evidence_map import build_evidence_map
from sec_graph.extract.llm.requests import build_llm_windows
from sec_graph.ingest.pipeline import filing_sources, ingest_source
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

REPO_ROOT = Path(__file__).resolve().parents[1]
RUN_ID = "2026-05-04T010203Z_applicability-deal_deadbeef"


def test_universal_obligations_are_always_applicable() -> None:
    decisions = decide_applicability(region_text="", process_scope="target_full_proxy")
    universal_kinds = {kind.kind for kind in UNIVERSAL_OBLIGATIONS}
    universal_decisions = [
        decision for decision in decisions if decision.obligation_kind.kind in universal_kinds
    ]
    assert len(universal_decisions) == len(UNIVERSAL_OBLIGATIONS)
    for decision in universal_decisions:
        assert decision.applicability == "applicable"
        assert decision.reason_code == "universal_sale_process"
        assert decision.basis == ()


def test_conditional_obligation_is_applicable_only_with_trigger() -> None:
    text_with_exclusivity = "The parties granted exclusivity to Buyer A."
    text_without = "The board met to discuss strategic alternatives."

    with_decision = next(
        d
        for d in decide_applicability(
            region_text=text_with_exclusivity, process_scope="target_full_proxy"
        )
        if d.obligation_kind.kind == "exclusivity_grant"
    )
    assert with_decision.applicability == "applicable"
    assert with_decision.reason_code == "trigger_phrase_match"
    assert with_decision.basis  # at least one trigger captured

    without_decision = next(
        d
        for d in decide_applicability(
            region_text=text_without, process_scope="target_full_proxy"
        )
        if d.obligation_kind.kind == "exclusivity_grant"
    )
    assert without_decision.applicability == "not_applicable"
    assert without_decision.reason_code == "trigger_phrase_absent"
    assert without_decision.basis == ()


@pytest.mark.parametrize(
    ("text", "kind"),
    [
        (
            "Buyer A requested exclusivity, but the board declined exclusivity.",
            "exclusivity_grant",
        ),
        ("The board determined not to form a transaction committee.", "special_committee"),
        ("Company F did not participate in a buyer offer.", "recusal"),
    ],
)
def test_negative_or_unrelated_mentions_do_not_trigger_conditional_applicability(
    text: str, kind: str
) -> None:
    decision = next(
        item
        for item in decide_applicability(region_text=text, process_scope="target_full_proxy")
        if item.obligation_kind.kind == kind
    )
    assert decision.applicability == "not_applicable"
    assert decision.reason_code in {
        "negative_or_requested_only",
        "negative_or_not_formed",
        "unrelated_bidder_nonparticipation",
        "trigger_phrase_absent",
    }


def test_scope_obligation_only_applies_to_listed_scope() -> None:
    proxy_decisions = decide_applicability(
        region_text="Some text.", process_scope="target_full_proxy"
    )
    tender_decisions = decide_applicability(
        region_text="Some text.", process_scope="bidder_partial_schedule_to"
    )
    proxy_tender = next(
        d for d in proxy_decisions if d.obligation_kind.kind == "tender_offer_prior_contacts"
    )
    tender_tender = next(
        d for d in tender_decisions if d.obligation_kind.kind == "tender_offer_prior_contacts"
    )
    assert proxy_tender.applicability == "not_applicable"
    assert proxy_tender.reason_code == "process_scope_mismatch"
    assert tender_tender.applicability == "applicable"
    assert tender_tender.reason_code == "process_scope:bidder_partial_schedule_to"


def test_decide_applicability_is_deterministic_and_complete() -> None:
    text = "On January 1 the board began a sale process."
    one = decide_applicability(region_text=text, process_scope="target_full_proxy")
    two = decide_applicability(region_text=text, process_scope="target_full_proxy")
    assert [d.obligation_kind.kind for d in one] == [d.obligation_kind.kind for d in two]
    assert [d.applicability for d in one] == [d.applicability for d in two]
    assert [d.obligation_kind.kind for d in one] == [k.kind for k in ALL_OBLIGATION_KINDS]


def test_inapplicable_obligations_are_recorded_and_excluded_from_window() -> None:
    conn = connect(":memory:")
    init_schema(conn)
    filing_id = _insert_minimal_filing(conn)

    build_evidence_map(conn, filing_id=filing_id, run_id=RUN_ID)

    rows = conn.execute(
        """
        SELECT obligation_kind, applicability, applicability_reason_code,
               applicability_basis_json
        FROM coverage_obligations
        WHERE filing_id = ?
        ORDER BY CAST(regexp_extract(obligation_id, '_(\\d+)$', 1) AS INTEGER)
        """,
        [filing_id],
    ).fetchall()

    # Every taxonomy entry is materialized for the audit ledger.
    assert {row[0] for row in rows} == {kind.kind for kind in ALL_OBLIGATION_KINDS}
    applicable = [row for row in rows if row[1] == "applicable"]
    inapplicable = [row for row in rows if row[1] == "not_applicable"]
    assert len(applicable) >= len(UNIVERSAL_OBLIGATIONS)
    assert inapplicable, "expected at least one inapplicable obligation in this minimal text"

    for row in inapplicable:
        basis = json.loads(row[3])
        assert isinstance(basis, list)
        assert row[2] in {"trigger_phrase_absent", "process_scope_mismatch"}

    [window] = build_llm_windows(conn, filing_id=filing_id)
    window_kinds = {obligation.obligation_label for obligation in window.coverage_obligations}
    assert len(window_kinds) == len(applicable)


def test_window_allowed_claim_types_are_derived_from_applicable_obligations() -> None:
    conn = connect(":memory:")
    init_schema(conn)
    filing_id = _insert_minimal_filing(conn)
    build_evidence_map(conn, filing_id=filing_id, run_id=RUN_ID)

    conn.execute(
        """
        UPDATE evidence_regions
        SET expected_claim_types_json = ?
        WHERE filing_id = ?
        """,
        [json.dumps(["actor_relation"]), filing_id],
    )
    conn.execute(
        """
        UPDATE coverage_obligations
        SET applicability = 'not_applicable'
        WHERE filing_id = ? AND expected_claim_type = 'actor_relation'
        """,
        [filing_id],
    )

    [window] = build_llm_windows(conn, filing_id=filing_id)

    assert "actor_relation" not in window.allowed_claim_types
    assert window.allowed_claim_types == [
        "event",
        "actor",
        "bid",
    ]


def test_medivation_tender_offer_scope_drives_applicability() -> None:
    """The tender-offer-only obligation applies to medivation but no others.

    Reading the local Medivation filing also exercises the multi-region path
    (Background of the Offer + Past Contacts) that Phase 1 introduced.
    """
    if not (REPO_ROOT / "data" / "filings" / "medivation" / "raw.md").exists():
        pytest.skip("medivation filing not present locally")

    conn = connect(":memory:")
    init_schema(conn)
    [source] = filing_sources(["medivation"], filings_dir=REPO_ROOT / "data" / "filings")
    filing = ingest_source(conn, source)
    region_ids = build_evidence_map(conn, filing_id=filing.filing_id, run_id=RUN_ID)
    assert len(region_ids) == 2

    rows = conn.execute(
        """
        SELECT region_id, applicability, applicability_reason_code
        FROM coverage_obligations
        WHERE filing_id = ? AND obligation_kind = 'tender_offer_prior_contacts'
        """,
        [filing.filing_id],
    ).fetchall()
    assert len(rows) == 2
    for region_id, applicability, reason in rows:
        assert applicability == "applicable"
        assert reason == "process_scope:bidder_partial_schedule_to"


def test_full_proxy_scope_marks_tender_offer_obligation_inapplicable() -> None:
    if not (REPO_ROOT / "data" / "filings" / "petsmart-inc" / "raw.md").exists():
        pytest.skip("petsmart-inc filing not present locally")

    conn = connect(":memory:")
    init_schema(conn)
    [source] = filing_sources(["petsmart-inc"], filings_dir=REPO_ROOT / "data" / "filings")
    filing = ingest_source(conn, source)
    build_evidence_map(conn, filing_id=filing.filing_id, run_id=RUN_ID)

    rows = conn.execute(
        """
        SELECT applicability, applicability_reason_code
        FROM coverage_obligations
        WHERE filing_id = ? AND obligation_kind = 'tender_offer_prior_contacts'
        """,
        [filing.filing_id],
    ).fetchall()
    assert rows
    for applicability, reason in rows:
        assert applicability == "not_applicable"
        assert reason == "process_scope_mismatch"


def test_obligation_kind_unique_in_taxonomy() -> None:
    kinds = [kind.kind for kind in ALL_OBLIGATION_KINDS]
    assert len(kinds) == len(set(kinds)), "obligation kinds must be unique"
    families = {
        kind.family for kind in ALL_OBLIGATION_KINDS
    }
    assert families == {"universal", "conditional", "scope"}


def test_conditional_obligations_have_at_least_one_trigger() -> None:
    for kind in CONDITIONAL_OBLIGATIONS:
        assert kind.triggers, f"conditional obligation {kind.kind!r} has no triggers"


def test_scope_obligations_declare_their_scopes() -> None:
    for kind in SCOPE_OBLIGATIONS:
        assert kind.scopes, f"scope obligation {kind.kind!r} declares no scopes"


def _insert_minimal_filing(conn) -> str:
    text = (
        "Background of the Merger\n\n"
        "The board met to discuss alternatives. The board signed the merger agreement."
    )
    slug = "applicability-min-deal"
    filing_id = make_id(slug, "filing", 1)
    paragraph_id = make_id(slug, "para", 1)
    evidence_id = make_id(slug, "evidence", 1)

    filing = CleanFiling(
        filing_id=filing_id,
        deal_slug=slug,
        source_path=str(filing_id),
        raw_sha256=quote_hash(text),
        parser_version=1,
        page_count=None,
        section_count=1,
        process_scope="target_full_proxy",
    )
    paragraph = Paragraph(
        paragraph_id=paragraph_id,
        filing_id=filing_id,
        section="Background of the Merger",
        page_hint=None,
        char_start=0,
        char_end=len(text),
        paragraph_text=text,
        paragraph_hash=quote_hash(text),
    )
    text_hash = quote_hash(text)
    span = SourceSpan(
        evidence_id=evidence_id,
        filing_id=filing_id,
        paragraph_id=paragraph_id,
        span_basis="raw_md",
        span_kind="paragraph_seed",
        parent_evidence_id=None,
        created_by_stage="ingest",
        char_start=0,
        char_end=len(text),
        quote_text=text,
        quote_text_hash=text_hash,
        evidence_fingerprint=evidence_fingerprint(filing_id, 0, len(text), text_hash),
    )
    conn.execute("INSERT INTO filings VALUES (?, ?, ?, ?, ?, ?, ?, ?)", tuple(filing.model_dump().values()))
    conn.execute("INSERT INTO paragraphs VALUES (?, ?, ?, ?, ?, ?, ?, ?)", tuple(paragraph.model_dump().values()))
    conn.execute("INSERT INTO spans VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", tuple(span.model_dump().values()))
    return filing_id
