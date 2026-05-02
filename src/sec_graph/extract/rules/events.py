"""Dated event extraction rules."""

from __future__ import annotations

import datetime as dt
import re

from .actors import Match

_DATED_SENTENCE_RE = re.compile(r"\bOn ([A-Z][a-z]+ \d{1,2}, \d{4}), .+\.")


def dated_event_matches(text: str) -> list[Match]:
    matches: list[Match] = []
    for match in _DATED_SENTENCE_RE.finditer(text):
        date_value = dt.datetime.strptime(match.group(1), "%B %d, %Y").date().isoformat()
        matches.append(
            Match(
                candidate_type="dated_event",
                raw_value=match.group(0),
                normalized_value=date_value,
                confidence="medium",
                start=match.start(),
                end=match.end(),
                span_kind="sentence",
            )
        )
    return matches
