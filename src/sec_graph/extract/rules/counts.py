"""Participation-count extraction rules."""

from __future__ import annotations

import re

from .actors import Match

_COUNT_RE = re.compile(r"\b(\d+) financial buyers\b")


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
    return matches
