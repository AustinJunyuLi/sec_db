"""Actor mention extraction rules."""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Match:
    candidate_type: str
    raw_value: str
    normalized_value: str
    confidence: str
    start: int
    end: int
    span_kind: str


_ACTOR_RE = re.compile(
    r"\b(?:"
    r"Party [A-Z]"
    r"|Bidder \d+"
    r"|Buyer Group"
    r"|Industry Participant"
    r"|Sponsor [A-Z]"
    r"|Company [A-Z]"
    "|Hudson['\u2019]s Bay"
    r"|G&W"
    r")\b"
)


def actor_matches(text: str) -> list[Match]:
    seen: set[str] = set()
    matches: list[Match] = []
    for match in _ACTOR_RE.finditer(text):
        raw = match.group(0)
        if raw in seen:
            continue
        seen.add(raw)
        matches.append(
            Match(
                candidate_type="actor_mention",
                raw_value=raw,
                normalized_value=raw,
                confidence="high",
                start=match.start(),
                end=match.end(),
                span_kind="phrase",
            )
        )
    return matches
