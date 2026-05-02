"""Bid-value extraction rules."""

from __future__ import annotations

import re

from .actors import Match

_AMOUNT = r"\$(\d+(?:\.\d+)?)"
_RANGE_RE = re.compile(f"{_AMOUNT}\\s*(?:per share\\s*)?(?:-|\\u2013|\\u2014|to|and)\\s*{_AMOUNT}\\s*per share")
_BID_RE = re.compile(rf"{_AMOUNT} per share")


def _normalized_amount(value: str) -> str:
    return str(float(value))


def _overlaps(span: tuple[int, int], spans: list[tuple[int, int]]) -> bool:
    return any(span[0] < existing[1] and existing[0] < span[1] for existing in spans)


def bid_matches(text: str) -> list[Match]:
    matches: list[Match] = []
    range_spans: list[tuple[int, int]] = []
    for match in _RANGE_RE.finditer(text):
        range_spans.append((match.start(), match.end()))
        matches.append(
            Match(
                candidate_type="bid_value",
                raw_value=match.group(0),
                normalized_value=f"{_normalized_amount(match.group(1))}-{_normalized_amount(match.group(2))}",
                confidence="high",
                start=match.start(),
                end=match.end(),
                span_kind="phrase",
            )
        )
    for match in _BID_RE.finditer(text):
        if _overlaps((match.start(), match.end()), range_spans):
            continue
        matches.append(
            Match(
                candidate_type="bid_value",
                raw_value=match.group(0),
                normalized_value=_normalized_amount(match.group(1)),
                confidence="high",
                start=match.start(),
                end=match.end(),
                span_kind="phrase",
            )
        )
    return sorted(matches, key=lambda match: match.start)
