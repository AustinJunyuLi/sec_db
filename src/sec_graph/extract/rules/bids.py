"""Bid-value extraction rules."""

from __future__ import annotations

import re

from .actors import Match

_BID_RE = re.compile(r"\$(\d+(?:\.\d+)?) per share")


def bid_matches(text: str) -> list[Match]:
    matches: list[Match] = []
    for match in _BID_RE.finditer(text):
        normalized = str(float(match.group(1)))
        matches.append(
            Match(
                candidate_type="bid_value",
                raw_value=match.group(0),
                normalized_value=normalized,
                confidence="high",
                start=match.start(),
                end=match.end(),
                span_kind="phrase",
            )
        )
    return matches
