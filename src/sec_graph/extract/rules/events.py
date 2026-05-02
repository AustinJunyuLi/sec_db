"""Dated event extraction rules."""

from __future__ import annotations

import datetime as dt
import re

from .actors import Match

_DATED_START_RE = re.compile(r"\bOn ([A-Z][a-z]+ \d{1,2}, \d{4}),")
_ABBREVIATIONS = (
    "J.P.",
    "U.S.",
    "Mr.",
    "Ms.",
    "Dr.",
    "Inc.",
    "Co.",
    "Ltd.",
    "L.P.",
    "L.L.C.",
    "LLC.",
)


def _is_sentence_period(text: str, index: int) -> bool:
    if index > 0 and index + 1 < len(text) and text[index - 1].isdigit() and text[index + 1].isdigit():
        return False
    prefix = text[max(0, index - 12) : index + 1]
    if any(prefix.endswith(abbreviation) for abbreviation in _ABBREVIATIONS):
        return False
    if re.search(r"\b[A-Z]\.$", prefix):
        return False
    return True


def _sentence_end(text: str, start: int) -> int:
    for index in range(start, len(text)):
        if text[index] == "." and _is_sentence_period(text, index):
            return index + 1
    return len(text)


def dated_event_matches(text: str) -> list[Match]:
    matches: list[Match] = []
    starts = list(_DATED_START_RE.finditer(text))
    for index, match in enumerate(starts):
        date_value = dt.datetime.strptime(match.group(1), "%B %d, %Y").date().isoformat()
        end = _sentence_end(text, match.start())
        if index + 1 < len(starts):
            end = min(end, starts[index + 1].start())
        raw_value = text[match.start() : end].strip()
        matches.append(
            Match(
                candidate_type="dated_event",
                raw_value=raw_value,
                normalized_value=date_value,
                confidence="medium",
                start=match.start(),
                end=match.start() + len(raw_value),
                span_kind="sentence",
            )
        )
    return matches
