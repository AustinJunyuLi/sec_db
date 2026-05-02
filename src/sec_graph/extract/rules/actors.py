"""Actor mention extraction rules.

The production rule surface matches generic actor handles and source-situated
proper names. It does not contain one-off public-company or sponsor-name
allowlists; named actors are admitted only when their local sentence context
uses them as sale-process participants.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from sec_graph.schema import RelationCandidate


@dataclass(frozen=True)
class Match:
    candidate_type: str
    raw_value: str
    normalized_value: str
    confidence: str
    start: int
    end: int
    span_kind: str
    relation_payload: RelationCandidate | None = None


_GENERIC_ACTOR_RE = re.compile(
    r"\b(?:"
    r"Party [A-Z]"
    r"|Bidder \d+"
    r"|Buyer Group"
    r"|Industry Participant"
    r"|Sponsor [A-Z]"
    r"|Company [A-Z]"
    r"|Merger Sub"
    r"|Parent"
    r")\b"
)

_NAME_TOKEN = (
    r"(?:"
    r"[A-Z](?:&[A-Z])+"
    r"|(?:Inc|Corp|L\.P|LLC|Ltd)\."
    r"|[A-Z][A-Za-z0-9'’À-ſ-]+"
    r")"
)
_NAMED_ACTOR_RE = re.compile(rf"\b{_NAME_TOKEN}(?:\s+{_NAME_TOKEN}){{0,5}}\b")
_PARTICIPANT_CONTEXT_RE = re.compile(
    r"\b("
    r"submitted|proposal|proposals|offer|offers|loi|bid|bids|bidders|buyer|buyers|"
    r"acquir|remained active|continued interest|merger agreement|"
    r"confidentiality agreement|non-disclosure agreement|exclusivity"
    r")\b",
    re.IGNORECASE,
)
_ORG_SIGNAL_SUFFIXES = frozenset(
    {
        "Bay",
        "Capital",
        "Corp.",
        "Corporation",
        "Group",
        "Holdings",
        "Inc.",
        "Investments",
        "LLC",
        "Limited",
        "LP",
        "L.P.",
        "Ltd.",
        "Management",
        "Partners",
        "Railway",
    }
)
_NON_ACTOR_LABELS = frozenset(
    {
        "Board",
        "Company",
        "Table of Contents",
        "Transaction Committee",
    }
)


def _candidate_span(text: str, start: int, end: int) -> tuple[str, int, int]:
    raw = text[start:end].strip(" ,.;:")
    lead_trim = len(text[start:end]) - len(text[start:end].lstrip(" ,.;:"))
    start += lead_trim
    if raw.startswith("The "):
        start += 4
        raw = raw[4:]
    if raw.endswith(("'s", "’s")):
        end -= 2
        raw = raw[:-2]
    raw = raw.strip(" ,.;:")
    end = start + len(raw)
    return raw, start, end


def _has_actor_name_shape(label: str) -> bool:
    if label in _NON_ACTOR_LABELS:
        return False
    tokens = label.split()
    if not tokens:
        return False
    if "&" in label:
        return True
    if len(tokens) < 2:
        return False
    return tokens[-1] in _ORG_SIGNAL_SUFFIXES


def _has_sale_process_context(text: str, start: int, end: int) -> bool:
    lo = max(0, start - 120)
    hi = min(len(text), end + 120)
    return bool(_PARTICIPANT_CONTEXT_RE.search(text[lo:hi]))


def _candidate_named_actor_matches(text: str) -> list[tuple[str, int, int]]:
    matches: list[tuple[str, int, int]] = []
    for match in _NAMED_ACTOR_RE.finditer(text):
        label, start, end = _candidate_span(text, match.start(), match.end())
        if not _has_actor_name_shape(label):
            continue
        if not _has_sale_process_context(text, match.start(), match.end()):
            continue
        matches.append((label, start, end))
    return matches


def actor_matches(text: str) -> list[Match]:
    seen: set[str] = set()
    matches: list[Match] = []
    generic_matches = [(match.group(0), match.start(), match.end()) for match in _GENERIC_ACTOR_RE.finditer(text)]
    named_matches = _candidate_named_actor_matches(text)
    for raw, start, end in sorted([*generic_matches, *named_matches], key=lambda item: (item[1], item[2])):
        if raw in seen:
            continue
        seen.add(raw)
        matches.append(
            Match(
                candidate_type="actor_mention",
                raw_value=raw,
                normalized_value=raw,
                confidence="high",
                start=start,
                end=end,
                span_kind="phrase",
            )
        )
    return matches
