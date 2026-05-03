"""Participation-count extraction rules."""

from __future__ import annotations

import re

from .actors import Match

_WORD_COUNTS: dict[str, int] = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
    "thirteen": 13,
    "fourteen": 14,
    "fifteen": 15,
    "sixteen": 16,
    "seventeen": 17,
    "eighteen": 18,
    "nineteen": 19,
    "twenty": 20,
    "twenty-four": 24,
    "twenty-five": 25,
    "twenty-seven": 27,
    "thirty-five": 35,
    "fifty": 50,
    "fifty-eight": 58,
}
_NUMBER = r"\d+|" + "|".join(sorted((re.escape(key) for key in _WORD_COUNTS), key=len, reverse=True))
_COUNT_VALUE_RE = re.compile(rf"^(?:{_NUMBER})$", re.IGNORECASE)
_ATOMIC_COHORT_RE = re.compile(
    rf"\b(?P<count>{_NUMBER})\s+"
    r"(?P<label>"
    r"(?:potentially interested\s+)?"
    r"(?:potential\s+)?"
    r"(?:financial buyers|financial participants|financial bidders|financial sponsors|"
    r"strategic parties|strategic buyers|strategic bidders|strategic acquirers|"
    r"potential participants|potential bidders|parties|bidders)"
    r")\b",
    re.IGNORECASE,
)
_CONTACTED_SIMPLE_RE = re.compile(
    rf"\bcontacted\b[^.]*?\b(?P<count>{_NUMBER})\s+(?P<label>parties|potential participants|potential buyers)\b",
    re.IGNORECASE,
)
_OF_PARTIES_IOI_RE = re.compile(
    rf"\b(?P<count>{_NUMBER})\s+of the\s+(?P<label>potentially interested parties)\s+"
    r"submitted indications of interest\b",
    re.IGNORECASE,
)
_FINAL_ROUND_BIDDERS_RE = re.compile(
    rf"\b(?P<count>{_NUMBER})\s+(?P<label>bidders)\s+that had indicated\b.*?\bfinal round\b",
    re.IGNORECASE,
)
_CONFIDENTIALITY_SUBSET_RE = re.compile(
    rf"\b(?:all\s+)?(?P<count>{_NUMBER})\s+(?:of the\s+)?(?P<label>financial buyers|strategic buyers)\s+"
    r"entered into confidentiality agreements\b",
    re.IGNORECASE,
)
_POTENTIAL_BIDDERS_CONFIDENTIALITY_RE = re.compile(
    rf"\b(?P<count>{_NUMBER})\s+(?P<label>potential bidders)\b[^.]*?\bentered into confidentiality agreements\b",
    re.IGNORECASE,
)
_TOTAL_CONTACTED_RE = re.compile(
    rf"\bcontacted a total of\s+(?P<count>{_NUMBER})\s+(?P<label>parties)\b",
    re.IGNORECASE,
)


def _count_value(text: str) -> int:
    folded = text.casefold()
    if folded.isdigit():
        return int(folded)
    if not _COUNT_VALUE_RE.match(folded):
        raise ValueError(f"unsupported count value {text!r}")
    return _WORD_COUNTS[folded]


def _match_to_count(match: re.Match[str], raw_value: str | None = None) -> Match:
    raw = raw_value if raw_value is not None else match.group(0)
    return Match(
        candidate_type="participation_count",
        raw_value=raw,
        normalized_value=str(_count_value(match.group("count"))),
        confidence="high",
        start=match.start(),
        end=match.start() + len(raw),
        span_kind="phrase",
    )


def count_matches(text: str) -> list[Match]:
    matches: list[Match] = []
    occupied: list[tuple[int, int]] = []
    for pattern in (
        _OF_PARTIES_IOI_RE,
        _FINAL_ROUND_BIDDERS_RE,
        _CONFIDENTIALITY_SUBSET_RE,
        _POTENTIAL_BIDDERS_CONFIDENTIALITY_RE,
        _TOTAL_CONTACTED_RE,
        _CONTACTED_SIMPLE_RE,
        _ATOMIC_COHORT_RE,
    ):
        for match in pattern.finditer(text):
            if any(match.start() < end and start < match.end() for start, end in occupied):
                continue
            matches.append(_match_to_count(match))
            occupied.append((match.start(), match.end()))
    return sorted(matches, key=lambda item: item.start)
