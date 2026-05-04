"""Section-detection contract: heading variants, TOC rejection, and reset.

The Reference-9 filings use diverse markdown wrappers around sale-process
headings, embed table-of-contents rows that look superficially like headings,
and do not always close with a known canonical heading. The detector must be
permissive enough to find every variant in the vocabulary, strict enough to
reject TOC rows and body sentences, and robust enough to reset sticky
sale-process labels when a new heading-like paragraph appears.
"""

from __future__ import annotations

from sec_graph.ingest.section_vocabulary import (
    NON_CANONICAL_HEADING,
    SALE_PROCESS_HEADINGS,
)
from sec_graph.ingest.sections import assign_sections, detect_section


def test_plain_background_heading_detected() -> None:
    assert detect_section("Background of the Merger") == "Background of the Merger"


def test_bold_background_heading_detected() -> None:
    assert detect_section("**Background of the Merger**") == "Background of the Merger"


def test_bold_italic_background_offer_heading_detected() -> None:
    assert detect_section("***Background of the Offer***") == "Background of the Offer"


def test_styled_command_background_heading_detected() -> None:
    heading = (
        '**COMMAND=STYLE_ADDED,"margin-left:10.0pt;text-indent:-10.0pt;" '
        "Background of the Merger**"
    )
    assert detect_section(heading) == "Background of the Merger"


def test_past_contacts_heading_with_trailing_period_detected() -> None:
    heading = "***Past Contacts, Transactions, Negotiations and Agreements.***"
    assert (
        detect_section(heading)
        == "Past Contacts, Transactions, Negotiations and Agreements"
    )


def test_numbered_subsection_heading_detected() -> None:
    heading = "10. Background of the Offer"
    assert detect_section(heading) == "Background of the Offer"


def test_table_of_contents_row_is_not_promoted_to_heading() -> None:
    toc_row = "| Background of the Merger | 27 |"
    assert detect_section(toc_row) is None


def test_cross_reference_sentence_is_not_promoted_to_heading() -> None:
    sentence = (
        'See *"The Merger (Proposal 1)—Background of the Merger"* for '
        "information regarding the results of the go-shop process."
    )
    assert detect_section(sentence) is None


def test_body_sentence_starting_with_heading_words_is_not_promoted() -> None:
    # Even when a body sentence starts with the heading text, the detector
    # must not promote it because exact-match (after stripping markup,
    # trailing punctuation, and leading section numbers) requires the
    # paragraph's first line to BE the heading, not merely begin with it.
    sentence = (
        "Background of the Merger has been described above; the following "
        "narrative provides additional context."
    )
    assert detect_section(sentence) is None


def test_unknown_bold_heading_resets_sticky_section() -> None:
    sections = assign_sections(
        [
            "**Background of the Merger**",
            "The board contacted bidders.",
            "**sTec's Reasons for the Merger**",
            "The board considered fairness.",
        ]
    )
    assert sections == [
        "Background of the Merger",
        "Background of the Merger",
        "unknown_section",
        "unknown_section",
    ]


def test_unknown_numbered_heading_resets_past_contacts() -> None:
    sections = assign_sections(
        [
            "***Past Contacts, Transactions, Negotiations and Agreements.***",
            "For more information, see Section 11 — The Merger Agreement.",
            "11. The Merger Agreement.",
            "The following summary describes the merger agreement.",
        ]
    )
    assert sections == [
        "Past Contacts, Transactions, Negotiations and Agreements",
        "Past Contacts, Transactions, Negotiations and Agreements",
        "unknown_section",
        "unknown_section",
    ]


def test_page_marker_paragraph_does_not_change_section() -> None:
    sections = assign_sections(
        [
            "**Background of the Merger**",
            "The board began the sale process.",
            "<!-- PAGE 30 -->",
            "Discussions continued through November.",
        ]
    )
    assert sections == ["Background of the Merger"] * 4


def test_long_bold_paragraph_is_not_treated_as_heading() -> None:
    # Long bold paragraphs (e.g., regulatory disclosures) must not reset the
    # current section just because they happen to be wrapped in markdown
    # emphasis. The heading heuristic enforces a length bound.
    long_bold = "**" + ("This is a long disclosure paragraph. " * 10).strip() + "**"
    sections = assign_sections(
        [
            "**Background of the Merger**",
            long_bold,
            "The board met to discuss strategic alternatives.",
        ]
    )
    assert sections == ["Background of the Merger"] * 3


def test_sale_process_vocabulary_is_ordered_longest_first() -> None:
    # Prefix variants must come before their shorter counterparts so the
    # exact-match path returns the most specific heading available.
    background_offer_index = SALE_PROCESS_HEADINGS.index("Background of the Offer")
    background_offer_and_merger_index = SALE_PROCESS_HEADINGS.index(
        "Background of the Offer and Merger"
    )
    assert background_offer_and_merger_index < background_offer_index


def test_non_canonical_heading_sentinel_is_distinct() -> None:
    # The sentinel returned for unrecognized heading-like paragraphs must not
    # collide with any canonical section label.
    assert NON_CANONICAL_HEADING not in SALE_PROCESS_HEADINGS
