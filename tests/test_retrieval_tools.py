"""Phase 3 (US-004) — RetrievalIndex + deterministic agent tools."""

from __future__ import annotations

from decimal import Decimal

import pytest

from sec_review_compiler.filing import build_atlas
from sec_review_compiler.filing.examples import load_synthetic_filing
from sec_review_compiler.retrieval import (
    BM25Hit,
    QuoteVerification,
    RegexMatch,
    RetrievalIndex,
    TextPosition,
    normalize_actor_label,
    parse_count,
    parse_date,
    parse_money,
    verify_quote,
)


@pytest.fixture(scope="module")
def index() -> RetrievalIndex:
    pkg = load_synthetic_filing()
    atlas = build_atlas(pkg)
    return RetrievalIndex.from_atlas(atlas, raw_text=pkg.raw_text, filing_id=pkg.filing_id)


# ---------------------------------------------------------------- literal lookup

class TestLiteralLookup:
    def test_unique_quote_returns_one_position_with_paragraph_id(self, index: RetrievalIndex) -> None:
        positions = index.literal("On January 2, 2026, Buyer A")
        assert len(positions) == 1
        pos = positions[0]
        assert isinstance(pos, TextPosition)
        assert index.raw_text[pos.char_start:pos.char_end] == pos.quote_text
        assert pos.paragraph_id is not None

    def test_duplicate_phrase_returns_multiple_positions(self, index: RetrievalIndex) -> None:
        positions = index.literal("Background of the Merger")
        assert len(positions) >= 2
        # The two occurrences live in different paragraphs.
        paragraph_ids = {p.paragraph_id for p in positions}
        assert len(paragraph_ids) >= 2

    def test_absent_quote_returns_empty(self, index: RetrievalIndex) -> None:
        assert index.literal("this string is not in the filing") == []


# ---------------------------------------------------------------- regex

class TestRegex:
    def test_regex_returns_matches_with_groups(self, index: RetrievalIndex) -> None:
        results = index.regex(r"\$(\d{2}\.\d{2})\s+per\s+share")
        assert results, "expected at least one $X.XX per share match"
        match = results[0]
        assert isinstance(match, RegexMatch)
        assert match.matched_text.endswith("per share")
        assert match.groups[0] == "25.50"

    def test_regex_does_not_mutate_raw_text(self, index: RetrievalIndex) -> None:
        before = index.raw_text
        before_id = id(before)
        # Run regex with a destructive-looking pattern (substitution-style)
        index.regex(r"Buyer\s+A")
        index.regex(r".*")
        after = index.raw_text
        assert after == before
        assert id(after) == before_id  # exact same str object — nothing replaced


# ---------------------------------------------------------------- BM25

class TestBM25:
    def test_bm25_returns_hits_for_meaningful_query(self, index: RetrievalIndex) -> None:
        hits = index.bm25("confidentiality agreement Buyer", k=3)
        assert hits, "expected non-empty hits"
        for h in hits:
            assert isinstance(h, BM25Hit)
            assert h.score > 0
            assert h.paragraph.paragraph_id == h.paragraph_id
        # Top hit should mention the confidentiality agreement.
        assert "confidentiality" in hits[0].paragraph.text.lower()

    def test_bm25_empty_query_returns_empty(self, index: RetrievalIndex) -> None:
        assert index.bm25("", k=5) == []

    def test_bm25_unknown_terms_return_empty(self, index: RetrievalIndex) -> None:
        assert index.bm25("zzzzzzzz qqqqqqqq", k=5) == []


# ---------------------------------------------------------------- fetches

class TestFetches:
    def test_get_paragraph(self, index: RetrievalIndex) -> None:
        first = index.paragraphs[0]
        assert index.get_paragraph(first.paragraph_id) == first

    def test_get_section_round_trip(self, index: RetrievalIndex) -> None:
        # build_atlas guarantees at least one section in the synthetic fixture.
        pkg = load_synthetic_filing()
        atlas = build_atlas(pkg)
        any_section = atlas.sections[0]
        section = index.get_section(any_section.section_id)
        assert section.section_id == any_section.section_id

    def test_neighborhood_returns_window(self, index: RetrievalIndex) -> None:
        anchor = index.paragraphs[2]
        window = index.neighborhood(anchor.paragraph_id, before=1, after=1)
        assert len(window) == 3
        assert window[1].paragraph_id == anchor.paragraph_id

    def test_neighborhood_clips_at_edges(self, index: RetrievalIndex) -> None:
        first = index.paragraphs[0]
        window = index.neighborhood(first.paragraph_id, before=2, after=0)
        assert window == [first]

    def test_get_table_round_trip(self, index: RetrievalIndex) -> None:
        pkg = load_synthetic_filing()
        atlas = build_atlas(pkg)
        table = atlas.tables[0]
        assert index.get_table(table.table_id) == table

    def test_unknown_id_raises(self, index: RetrievalIndex) -> None:
        with pytest.raises(KeyError):
            index.get_paragraph("does-not-exist")


# ---------------------------------------------------------------- verify_quote

class TestVerifyQuote:
    def test_unique_quote(self, index: RetrievalIndex) -> None:
        v = verify_quote(index, "On January 2, 2026, Buyer A")
        assert isinstance(v, QuoteVerification)
        assert v.verbatim_present is True
        assert v.ambiguity == "unique"
        assert len(v.positions) == 1
        assert len(v.paragraph_ids) == 1

    def test_duplicate_quote_flagged_ambiguous(self, index: RetrievalIndex) -> None:
        v = verify_quote(index, "Background of the Merger")
        assert v.verbatim_present is True
        assert v.ambiguity == "ambiguous_multiple"
        assert len(v.positions) >= 2
        assert len(v.paragraph_ids) >= 2

    def test_absent_quote(self, index: RetrievalIndex) -> None:
        v = verify_quote(index, "this is not in the filing")
        assert v.verbatim_present is False
        assert v.ambiguity == "absent"
        assert v.positions == ()
        assert v.paragraph_ids == ()


# ---------------------------------------------------------------- parse_date

class TestParseDate:
    def test_exact_date(self) -> None:
        d = parse_date("January 2, 2026")
        assert d.iso_date == "2026-01-02"
        assert d.year == 2026 and d.month == 1 and d.day == 2
        assert d.granularity == "day"
        assert d.ambiguous is False

    def test_early_march_ambiguous(self) -> None:
        d = parse_date("early March 2026")
        assert d.ambiguous is True
        assert d.iso_date is None
        assert d.day is None
        assert d.month == 3
        assert d.year == 2026
        assert d.granularity == "month"
        assert d.ambiguity_reason is not None
        assert "early" in d.ambiguity_reason

    def test_late_month_ambiguous(self) -> None:
        d = parse_date("late November 2025")
        assert d.ambiguous is True
        assert d.month == 11 and d.year == 2025
        assert d.granularity == "month"

    def test_month_year_ambiguous(self) -> None:
        d = parse_date("March 2026")
        assert d.ambiguous is True
        assert d.month == 3 and d.year == 2026
        assert d.granularity == "month"

    def test_quarter_ambiguous(self) -> None:
        d = parse_date("Q1 2026")
        assert d.granularity == "quarter"
        assert d.quarter == 1 and d.year == 2026
        assert d.ambiguous is True

    def test_quarter_words(self) -> None:
        d = parse_date("first quarter of 2026")
        assert d.granularity == "quarter"
        assert d.quarter == 1 and d.year == 2026

    def test_year_only(self) -> None:
        d = parse_date("2026")
        assert d.granularity == "year"
        assert d.year == 2026
        assert d.month is None and d.day is None
        assert d.ambiguous is True

    def test_unrecognized(self) -> None:
        d = parse_date("sometime soon")
        assert d.granularity == "ambiguous"
        assert d.ambiguous is True
        assert d.year is None


# ---------------------------------------------------------------- parse_money

class TestParseMoney:
    def test_per_share_unit_preserved(self) -> None:
        m = parse_money("$14.00 per share")
        assert m.amount_decimal == Decimal("14.00")
        assert m.currency == "USD"
        assert m.unit == "per_share"
        assert m.ambiguous is False

    def test_absolute_with_commas(self) -> None:
        m = parse_money("$1,200,000,000")
        assert m.amount_decimal == Decimal("1200000000")
        assert m.unit == "absolute"

    def test_scale_word_billion(self) -> None:
        m = parse_money("$1.2 billion")
        assert m.amount_decimal == Decimal("1.2") * Decimal("1000000000")
        assert m.unit == "absolute"

    def test_approximate_flagged(self) -> None:
        m = parse_money("approximately $25 per share")
        assert m.unit == "per_share"
        assert m.ambiguous is True
        assert m.ambiguity_reason == "approximate"

    def test_no_money_in_text(self) -> None:
        m = parse_money("a fair value to the stockholders")
        assert m.amount_decimal is None
        assert m.unit == "unknown"
        assert m.ambiguous is True


# ---------------------------------------------------------------- parse_count

class TestParseCount:
    def test_between_range(self) -> None:
        c = parse_count("between 20 and 25 parties")
        assert c.min_count == 20
        assert c.max_count == 25
        assert c.exact is False
        assert c.ambiguous is False  # range is well-defined

    def test_dash_range(self) -> None:
        c = parse_count("contacted 30-40 strategic parties")
        assert c.min_count == 30 and c.max_count == 40

    def test_more_than_open_upper(self) -> None:
        c = parse_count("more than 50 parties")
        assert c.min_count == 51
        assert c.max_count is None
        assert c.ambiguous is True
        assert c.ambiguity_reason == "open_upper_bound"

    def test_fewer_than_open_lower(self) -> None:
        c = parse_count("fewer than 10 parties")
        assert c.min_count is None
        assert c.max_count == 9
        assert c.ambiguous is True

    def test_exact_count(self) -> None:
        c = parse_count("7 parties")
        assert c.min_count == 7 and c.max_count == 7
        assert c.exact is True

    def test_approximate(self) -> None:
        c = parse_count("approximately 45 parties")
        assert c.min_count == 45 and c.max_count == 45
        assert c.exact is False
        assert c.ambiguous is True
        assert c.ambiguity_reason == "approximate"


# ---------------------------------------------------------------- normalize_actor_label

class TestNormalizeActorLabel:
    def test_filing_local_locality(self) -> None:
        a = normalize_actor_label(label="Acme Corp.", filing_id="f:1")
        assert a.locality == "filing"
        assert a.filing_id == "f:1"

    def test_canonical_legal_suffix(self) -> None:
        a = normalize_actor_label(label="Acme Corporation", filing_id="f:1")
        assert a.canonical_local.endswith(" Corp")
        assert "Acme Corporation" in a.aliases

    def test_no_cross_filing_pooling(self) -> None:
        # Same raw label across different filings yields *different* ActorLabel
        # records with distinct filing_ids — no pooling, no shared id.
        a = normalize_actor_label(label="Buyer A", filing_id="f:1")
        b = normalize_actor_label(label="Buyer A", filing_id="f:2")
        assert a.canonical_local == b.canonical_local
        assert a.filing_id != b.filing_id
        # The contract is locality, not equality across filings.
        assert (a.canonical_local, a.filing_id) != (b.canonical_local, b.filing_id)

    def test_collapses_whitespace(self) -> None:
        a = normalize_actor_label(label="  Acme   Corp.  ", filing_id="f:1")
        assert a.canonical_local == "Acme Corp"

    def test_passthrough_when_no_suffix(self) -> None:
        a = normalize_actor_label(label="Buyer A", filing_id="f:1")
        assert a.canonical_local == "Buyer A"
        assert a.aliases == ()
