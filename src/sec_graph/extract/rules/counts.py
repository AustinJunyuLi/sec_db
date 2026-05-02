"""Participation-count extraction rules."""

from __future__ import annotations

import re

from .actors import Match

_COUNT_RE = re.compile(r"\b(\d+) financial buyers\b")
_CONTACTED_TOTAL_RE = re.compile(r"contacted a total of (?P<count>\d+|fifty-eight|fifty|twenty-five) parties", re.IGNORECASE)

_WORD_COUNTS = {
    "twenty-five": 25,
    "fifty": 50,
    "fifty-eight": 58,
}


def count_matches(text: str) -> list[Match]:
    matches: list[Match] = []
    for match in _COUNT_RE.finditer(text):
        matches.append(
            Match(
                candidate_type="participation_count",
                raw_value=match.group(0),
                normalized_value=match.group(1),
                confidence="high",
                start=match.start(),
                end=match.end(),
                span_kind="phrase",
            )
        )
    for match in _CONTACTED_TOTAL_RE.finditer(text):
        count_text = match.group("count").casefold()
        count = int(count_text) if count_text.isdigit() else _WORD_COUNTS[count_text]
        matches.append(
            Match(
                candidate_type="participation_count",
                raw_value=match.group(0),
                normalized_value=str(count),
                confidence="high",
                start=match.start(),
                end=match.end(),
                span_kind="phrase",
            )
        )
    return matches
