"""Tests for obligation applicability heuristics.

Count obligations only apply when the evidence window contains explicit count
language (numeric digits or written counts) bound to a participation noun.
Stage words alone (e.g. ``preliminary proposal``, ``first round``,
``best and final``) must not be enough.
"""

from __future__ import annotations

import pytest

from sec_graph.extract.applicability import (
    COUNT_WORD_OR_NUMBER_RE,
    PARTICIPATION_NOUN_RE,
    has_count_language,
)


@pytest.mark.parametrize(
    "text",
    [
        "The Company contacted 10 financial buyers in the first round.",
        "Twelve potential buyers signed confidentiality agreements.",
        "Three parties submitted indications of interest.",
        "Two bidders advanced to the final round.",
        "Five potential acquirors remained active in the process.",
        "twenty-four parties were contacted",
        "fifty bidders were excluded after the preliminary round",
    ],
)
def test_has_count_language_accepts_count_plus_participation_noun(text: str) -> None:
    assert has_count_language(text)


@pytest.mark.parametrize(
    "text",
    [
        "first round",
        "preliminary proposal",
        "best and final",
        "the Company received a preliminary proposal",
        "the parties advanced to the first round",
        "the best and final offer was received",
        "submission of preliminary proposal in the first round",
    ],
)
def test_has_count_language_rejects_stage_words_alone(text: str) -> None:
    assert not has_count_language(text), text


def test_has_count_language_rejects_count_without_participation_noun() -> None:
    # 10 dollars per share is a value, not a participant count.
    assert not has_count_language("the bid was $10.00 per share")
    # Date-like numbers without participants do not satisfy the rule.
    assert not has_count_language("on January 1, 2020 the Board met")


def test_has_count_language_rejects_participation_noun_without_count() -> None:
    assert not has_count_language("the Company contacted potential buyers")
    assert not has_count_language("multiple parties submitted indications of interest")


def test_has_count_language_rejects_empty_input() -> None:
    assert not has_count_language("")


def test_count_pattern_matches_digits_and_written_words() -> None:
    assert COUNT_WORD_OR_NUMBER_RE.search("contacted 10 parties")
    assert COUNT_WORD_OR_NUMBER_RE.search("contacted twelve parties")
    assert COUNT_WORD_OR_NUMBER_RE.search("contacted twenty-four parties")
    # Word boundaries: standalone digits match, glued ordinals like '10th' do not.
    assert COUNT_WORD_OR_NUMBER_RE.search("the 10 parties") is not None
    assert not COUNT_WORD_OR_NUMBER_RE.search("on the 10th day")
    assert not COUNT_WORD_OR_NUMBER_RE.search("preliminary proposal")
    assert not COUNT_WORD_OR_NUMBER_RE.search("first round")


def test_participation_noun_pattern_excludes_stage_nouns() -> None:
    assert PARTICIPATION_NOUN_RE.search("financial buyers")
    assert PARTICIPATION_NOUN_RE.search("potential acquirors")
    assert PARTICIPATION_NOUN_RE.search("interested parties")
    # Stage / process nouns are not participation nouns.
    assert not PARTICIPATION_NOUN_RE.search("first round")
    assert not PARTICIPATION_NOUN_RE.search("preliminary proposal")
    assert not PARTICIPATION_NOUN_RE.search("best and final")
    assert not PARTICIPATION_NOUN_RE.search("the sale process")
