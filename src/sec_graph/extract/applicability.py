"""Obligation applicability heuristics.

Applicability determines whether a count or event obligation is *expected* to
be satisfied by claims drawn from a given evidence window. Stage words alone
(``preliminary proposal``, ``best and final``, ``first round``) are not enough
to create a count obligation. The window must include explicit count language
(numeric digits or written counts such as ``two`` or ``twelve``) bound to a
participation noun (``buyers``, ``parties``, ``bidders``, ``acquirors``).

This module is intentionally narrow. It does not interpret meaning; it only
filters out windows that obviously lack the surface cues required by a count
obligation.
"""

from __future__ import annotations

import re

# Numeric digits or written counts. Hyphenated counts (twenty-four) appear
# alongside their bare forms so the pattern matches either spelling.
_COUNT_WORDS = (
    "one",
    "two",
    "three",
    "four",
    "five",
    "six",
    "seven",
    "eight",
    "nine",
    "ten",
    "eleven",
    "twelve",
    "thirteen",
    "fourteen",
    "fifteen",
    "sixteen",
    "seventeen",
    "eighteen",
    "nineteen",
    "twenty",
    "twenty-one",
    "twenty-two",
    "twenty-three",
    "twenty-four",
    "twenty-five",
    "twenty-six",
    "twenty-seven",
    "twenty-eight",
    "twenty-nine",
    "thirty",
    "thirty-five",
    "forty",
    "fifty",
    "sixty",
    "seventy",
    "eighty",
    "ninety",
    "hundred",
)

_count_word_pattern = "|".join(
    sorted((re.escape(word) for word in _COUNT_WORDS), key=len, reverse=True)
)
COUNT_WORD_OR_NUMBER_RE = re.compile(
    rf"(?:\b\d+\b|\b(?:{_count_word_pattern})\b)",
    re.IGNORECASE,
)

# Participation nouns. These are deliberately restricted to *people-or-firm*
# nouns that the filing uses to describe sale-process participants. Stage
# nouns like "round", "proposal", or "process" are excluded so that
# ``preliminary proposal`` does not create a count obligation on its own.
PARTICIPATION_NOUN_RE = re.compile(
    r"\b(?:"
    r"buyers"
    r"|bidders"
    r"|parties"
    r"|participants"
    r"|acquir(?:ors|ers)"
    r"|sponsors"
    r"|firms"
    r"|companies"
    r"|investors"
    r"|counterparties"
    r"|offerors"
    r"|suitors"
    r")\b",
    re.IGNORECASE,
)


def has_count_language(text: str) -> bool:
    """Return ``True`` when ``text`` contains both count cues and a participant noun.

    Count obligations are *applicable* only when the surrounding evidence
    actually mentions a count. Stage words like ``first round`` or
    ``best and final`` do not, on their own, justify a count obligation.
    """

    if not text:
        return False
    return bool(
        COUNT_WORD_OR_NUMBER_RE.search(text)
        and PARTICIPATION_NOUN_RE.search(text)
    )


__all__ = [
    "COUNT_WORD_OR_NUMBER_RE",
    "PARTICIPATION_NOUN_RE",
    "has_count_language",
]
