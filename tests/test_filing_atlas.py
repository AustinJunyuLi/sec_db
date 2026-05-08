"""Phase 2 (US-003) — FilingPackage, SourceSpan, and Atlas."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from sec_review_compiler.errors import MissingTenderOfferExhibitError
from sec_review_compiler.filing import (
    Atlas,
    AtlasWarning,
    FilingPackage,
    Paragraph,
    SectionRecord,
    SourceSpan,
    build_atlas,
    build_filing_package,
)
from sec_review_compiler.filing.examples import (
    SYNTHETIC_FILING_PATH,
    load_synthetic_filing,
)


# ---------------------------------------------------------------- fixture

class TestSyntheticFixtureContent:
    def test_fixture_has_required_elements(self) -> None:
        text = SYNTHETIC_FILING_PATH.read_text(encoding="utf-8")
        assert "Item 1.01 Entry Into Material Definitive Agreement" in text  # transaction heading
        assert "Background of the Merger" in text  # background section
        assert text.count("Background of the Merger") >= 2  # ambiguous duplicate
        assert "On January 2, 2026, Buyer A" in text  # dated paragraph 1
        assert "On February 14, 2026, Buyer A" in text  # dated paragraph 2
        # Table-like block: a header row and rows with multi-space columns
        assert "Buyer A       $24.00      $25.00      $25.50" in text
        # Exhibit marker
        assert "Exhibit 99.1" in text


# ---------------------------------------------------------------- FilingPackage

class TestFilingPackage:
    def test_basic_fields(self) -> None:
        pkg = load_synthetic_filing()
        assert pkg.filing_id == "synthetic-demo:0001"
        assert pkg.filing_type == "8-K"
        assert pkg.raw_text  # non-empty
        assert pkg.raw_sha256 == hashlib.sha256(pkg.raw_text.encode("utf-8")).hexdigest()
        assert pkg.normalized_text  # non-empty
        assert pkg.normalized_sha256 == hashlib.sha256(
            pkg.normalized_text.encode("utf-8")
        ).hexdigest()
        assert len(pkg.paragraphs) >= 6
        assert all(isinstance(p, Paragraph) for p in pkg.paragraphs)

    def test_paragraphs_preserve_offsets_exact_slice(self) -> None:
        pkg = load_synthetic_filing()
        for p in pkg.paragraphs:
            assert pkg.raw_text[p.char_start:p.char_end] == p.text

    def test_paragraphs_are_in_source_order(self) -> None:
        pkg = load_synthetic_filing()
        ordinals = [p.ordinal for p in pkg.paragraphs]
        assert ordinals == sorted(ordinals)
        assert ordinals == list(range(len(ordinals)))
        starts = [p.char_start for p in pkg.paragraphs]
        assert starts == sorted(starts)

    def test_raw_text_is_not_mutated(self) -> None:
        original = SYNTHETIC_FILING_PATH.read_text(encoding="utf-8")
        pkg = build_filing_package(
            filing_id="x", filing_type="8-K", raw_text=original
        )
        assert pkg.raw_text == original

    def test_empty_text_raises(self) -> None:
        with pytest.raises(ValueError):
            build_filing_package(filing_id="x", filing_type="8-K", raw_text="")


# ---------------------------------------------------------------- Tender-offer

class TestTenderOfferExhibitGate:
    def test_missing_substantive_exhibit_raises_typed_error(self) -> None:
        # Tender-offer cover document only — no Offer to Purchase exhibit.
        text = (
            "SC TO-T cover document.\n\n"
            "This Schedule TO is filed solely as a cover.\n\n"
            "Exhibit 99.1\n"
            "Press release.\n"
        )
        with pytest.raises(MissingTenderOfferExhibitError):
            build_filing_package(
                filing_id="tender-no-offer:0001",
                filing_type="SC TO-T",
                raw_text=text,
            )

    def test_substantive_offer_exhibit_satisfies_gate(self) -> None:
        text = (
            "SC TO-T cover.\n\n"
            "Exhibit (a)(1)(A)\n"
            "Offer to Purchase dated April 1, 2026.\n\n"
            "All shares of Target Co. are being sought ...\n"
        )
        pkg = build_filing_package(
            filing_id="tender-with-offer:0001",
            filing_type="SC TO-T",
            raw_text=text,
        )
        assert any(ex.substantive_offer for ex in pkg.exhibits)

    def test_declared_substantive_exhibit_satisfies_gate(self) -> None:
        text = (
            "SC TO-T cover.\n\n"
            "Exhibit (a)(1)(A)\n"
            "Tender materials filed under cover.\n"
        )
        pkg = build_filing_package(
            filing_id="tender-declared:0001",
            filing_type="SC TO-T",
            raw_text=text,
            declared_substantive_exhibits=["(a)(1)(A)"],
        )
        assert any(ex.substantive_offer for ex in pkg.exhibits)

    def test_non_tender_offer_does_not_require_offer_exhibit(self) -> None:
        # 8-K filings have no tender-offer gate — no exhibits is fine.
        pkg = build_filing_package(
            filing_id="8k-noexh:0001", filing_type="8-K", raw_text="A short filing.\n"
        )
        assert pkg.exhibits == ()


# ---------------------------------------------------------------- SourceSpan

class TestSourceSpanIdentity:
    def test_identity_is_sha256_of_components(self) -> None:
        span = SourceSpan(
            filing_id="f:1",
            char_start=10,
            char_end=20,
            quote_text="hello",
        )
        expected_quote_hash = hashlib.sha256(b"hello").hexdigest()
        expected_evidence = hashlib.sha256(
            f"f:11020{expected_quote_hash}".encode("utf-8")
        ).hexdigest()
        assert span.quote_text_hash == expected_quote_hash
        assert span.identity() == expected_evidence
        assert span.evidence_id == expected_evidence

    def test_text_only_duplicate_quotes_have_distinct_evidence_ids(self) -> None:
        # Same quote text, different coordinates → different evidence ids.
        span_a = SourceSpan(filing_id="f:1", char_start=0, char_end=5, quote_text="ALPHA")
        span_b = SourceSpan(filing_id="f:1", char_start=100, char_end=105, quote_text="ALPHA")
        assert span_a.quote_text_hash == span_b.quote_text_hash
        assert span_a.identity() != span_b.identity()

    def test_inverted_offsets_rejected(self) -> None:
        with pytest.raises(ValueError):
            SourceSpan(filing_id="f:1", char_start=10, char_end=5, quote_text="x")


# ---------------------------------------------------------------- Atlas

class TestAtlas:
    def test_atlas_has_all_record_collections(self) -> None:
        pkg = load_synthetic_filing()
        atlas = build_atlas(pkg)
        assert isinstance(atlas, Atlas)
        assert len(atlas.filings) == 1
        assert atlas.filings[0].filing_id == pkg.filing_id
        assert len(atlas.paragraphs) == len(pkg.paragraphs)
        assert len(atlas.source_spans) == len(pkg.paragraphs)
        assert len(atlas.section_candidates) >= 2
        assert len(atlas.sections) >= 2
        assert len(atlas.tables) >= 1
        assert len(atlas.exhibits) >= 1

    def test_atlas_source_spans_slice_back_to_text(self) -> None:
        pkg = load_synthetic_filing()
        atlas = build_atlas(pkg)
        for span in atlas.source_spans:
            assert pkg.raw_text[span.char_start:span.char_end] == span.quote_text

    def test_ambiguous_section_label_emits_warning(self) -> None:
        pkg = load_synthetic_filing()
        atlas = build_atlas(pkg)
        ambiguous = [w for w in atlas.atlas_warnings if w.code == "ambiguous_section_label"]
        assert ambiguous, "duplicate 'Background of the Merger' should warn"
        message = ambiguous[0].message.lower()
        assert "background of the merger" in message
        assert "occurs 2 times" in message or "occurs 2" in message

    def test_ambiguous_sections_are_recorded_not_skipped(self) -> None:
        pkg = load_synthetic_filing()
        atlas = build_atlas(pkg)
        background_sections = [
            s for s in atlas.sections
            if s.label_normalised == "background of the merger"
        ]
        assert len(background_sections) == 2
        assert all(s.is_ambiguous_label for s in background_sections)
        # Each section spans a non-empty range and points to a unique heading paragraph.
        heading_ids = {s.heading_paragraph_id for s in background_sections}
        assert len(heading_ids) == 2

    def test_tables_have_columns_and_rows(self) -> None:
        pkg = load_synthetic_filing()
        atlas = build_atlas(pkg)
        assert atlas.tables, "the bidding-activity block should be detected as a table"
        bid_table = atlas.tables[0]
        assert bid_table.column_count >= 3
        assert bid_table.row_count >= 3

    def test_exhibits_recorded_with_substantive_flag(self) -> None:
        pkg = load_synthetic_filing()
        atlas = build_atlas(pkg)
        exhibit = atlas.exhibits[0]
        assert exhibit.designation == "99.1"
        assert exhibit.label == "Form of Confidentiality Agreement"
        # The synthetic exhibit is not the substantive offer — substantive_offer = False.
        assert exhibit.substantive_offer is False

    def test_section_evidence_ids_are_distinct_for_duplicated_label(self) -> None:
        pkg = load_synthetic_filing()
        atlas = build_atlas(pkg)
        # Build SourceSpans for the two duplicate-label headings and confirm
        # text-only duplicate quotes get distinct evidence ids.
        background_paragraph_ids = [
            s.heading_paragraph_id for s in atlas.sections
            if s.label_normalised == "background of the merger"
        ]
        spans = [
            sp for sp in atlas.source_spans
            if sp.paragraph_id in background_paragraph_ids
        ]
        assert len(spans) == 2
        assert spans[0].quote_text == spans[1].quote_text
        assert spans[0].identity() != spans[1].identity()
