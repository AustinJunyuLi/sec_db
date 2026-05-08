"""Deterministic agent-facing tools.

These helpers are deliberately conservative: when the source text is
genuinely ambiguous (e.g. "early March 2026"), the tool returns an
ambiguous structured value rather than guessing an exact answer.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover — avoid circular import at runtime
    from .index import RetrievalIndex


# ====================================================== verify_quote

@dataclass(frozen=True, slots=True)
class QuoteVerification:
    quote_text: str
    verbatim_present: bool
    positions: tuple[tuple[int, int], ...]
    paragraph_ids: tuple[str, ...]
    ambiguity: str  # "absent" | "unique" | "ambiguous_multiple"


def verify_quote(index: "RetrievalIndex", quote_text: str) -> QuoteVerification:
    """Check that `quote_text` is verbatim in the filing.

    Returns the deterministic positions and the paragraph ids hosting the
    matches. When the quote occurs more than once, ambiguity is set to
    `ambiguous_multiple` so the caller can ask for disambiguating
    coordinates rather than picking arbitrarily.
    """
    matches = index.literal(quote_text)
    if not matches:
        return QuoteVerification(
            quote_text=quote_text,
            verbatim_present=False,
            positions=(),
            paragraph_ids=(),
            ambiguity="absent",
        )
    positions = tuple((m.char_start, m.char_end) for m in matches)
    paragraph_ids = tuple(m.paragraph_id for m in matches if m.paragraph_id is not None)
    ambiguity = "unique" if len(matches) == 1 else "ambiguous_multiple"
    return QuoteVerification(
        quote_text=quote_text,
        verbatim_present=True,
        positions=positions,
        paragraph_ids=paragraph_ids,
        ambiguity=ambiguity,
    )


# ====================================================== parse_date

_MONTHS: dict[str, int] = {
    "january": 1, "february": 2, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
}
_VAGUE_PREFIXES = {"early", "earlier", "mid", "mid-", "middle", "late", "later", "end", "beginning"}
_QUARTER_RE = re.compile(
    r"^\s*(?:Q(?P<qn>[1-4])|(?P<words>first|second|third|fourth)\s+quarter)\s+(?:of\s+)?(?P<year>\d{4})\s*$",
    re.IGNORECASE,
)
_EXACT_DATE_RE = re.compile(
    r"^\s*(?P<month>january|february|march|april|may|june|july|august|september|october|november|december)"
    r"\s+(?P<day>\d{1,2})\s*,\s*(?P<year>\d{4})\s*$",
    re.IGNORECASE,
)
_MONTH_YEAR_RE = re.compile(
    r"^\s*(?P<month>january|february|march|april|may|june|july|august|september|october|november|december)"
    r"\s+(?P<year>\d{4})\s*$",
    re.IGNORECASE,
)
_VAGUE_INTRA_MONTH_RE = re.compile(
    r"^\s*(?P<adverb>early|earlier|mid-?|middle|late|later|end\s+of|beginning\s+of)\s+"
    r"(?P<month>january|february|march|april|may|june|july|august|september|october|november|december)"
    r"\s+(?P<year>\d{4})\s*$",
    re.IGNORECASE,
)
_YEAR_ONLY_RE = re.compile(r"^\s*(?:in\s+|during\s+|the\s+year\s+)?(?P<year>\d{4})\s*$", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class ParsedDate:
    text: str
    iso_date: str | None  # Set only when granularity == "day"
    year: int | None
    month: int | None
    day: int | None
    granularity: str  # "day" | "month" | "quarter" | "year" | "ambiguous"
    quarter: int | None
    ambiguous: bool
    ambiguity_reason: str | None


def parse_date(text: str) -> ParsedDate:
    if not text or not text.strip():
        return ParsedDate(
            text=text, iso_date=None, year=None, month=None, day=None,
            granularity="ambiguous", quarter=None, ambiguous=True,
            ambiguity_reason="empty_input",
        )

    m = _EXACT_DATE_RE.match(text)
    if m:
        month = _MONTHS[m["month"].lower()]
        day = int(m["day"])
        year = int(m["year"])
        if 1 <= day <= 31:
            return ParsedDate(
                text=text,
                iso_date=f"{year:04d}-{month:02d}-{day:02d}",
                year=year, month=month, day=day,
                granularity="day", quarter=None,
                ambiguous=False, ambiguity_reason=None,
            )

    m = _VAGUE_INTRA_MONTH_RE.match(text)
    if m:
        month = _MONTHS[m["month"].lower()]
        year = int(m["year"])
        adverb = re.sub(r"\s+", "_", m["adverb"].strip().rstrip("-").lower())
        return ParsedDate(
            text=text, iso_date=None, year=year, month=month, day=None,
            granularity="month", quarter=None,
            ambiguous=True,
            ambiguity_reason=f"vague_intra_month:{adverb}",
        )

    m = _MONTH_YEAR_RE.match(text)
    if m:
        return ParsedDate(
            text=text, iso_date=None,
            year=int(m["year"]), month=_MONTHS[m["month"].lower()], day=None,
            granularity="month", quarter=None,
            ambiguous=True, ambiguity_reason="month_only",
        )

    m = _QUARTER_RE.match(text)
    if m:
        quarter = (
            int(m["qn"])
            if m["qn"]
            else {"first": 1, "second": 2, "third": 3, "fourth": 4}[m["words"].lower()]
        )
        return ParsedDate(
            text=text, iso_date=None,
            year=int(m["year"]), month=None, day=None,
            granularity="quarter", quarter=quarter,
            ambiguous=True, ambiguity_reason="quarter_only",
        )

    m = _YEAR_ONLY_RE.match(text)
    if m:
        return ParsedDate(
            text=text, iso_date=None,
            year=int(m["year"]), month=None, day=None,
            granularity="year", quarter=None,
            ambiguous=True, ambiguity_reason="year_only",
        )

    return ParsedDate(
        text=text, iso_date=None, year=None, month=None, day=None,
        granularity="ambiguous", quarter=None,
        ambiguous=True, ambiguity_reason="unrecognized_shape",
    )


# ====================================================== parse_money

_CURRENCY_SYMBOLS: dict[str, str] = {"$": "USD", "€": "EUR", "£": "GBP", "¥": "JPY"}
_SCALE_WORDS: dict[str, Decimal] = {
    "thousand": Decimal("1000"),
    "million": Decimal("1000000"),
    "billion": Decimal("1000000000"),
    "trillion": Decimal("1000000000000"),
}
_PER_SHARE_RE = re.compile(r"\bper\s+share\b", re.IGNORECASE)
_APPROX_RE = re.compile(r"\b(approximately|approx\.?|about|around|roughly)\b", re.IGNORECASE)
_MONEY_RE = re.compile(
    r"(?P<symbol>[$€£¥])\s*(?P<num>\d{1,3}(?:,\d{3})*(?:\.\d+)?|\d+(?:\.\d+)?)\s*"
    r"(?P<scale>thousand|million|billion|trillion)?",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class ParsedMoney:
    text: str
    amount_decimal: Decimal | None
    currency: str | None
    unit: str  # "per_share" | "absolute" | "unknown"
    ambiguous: bool
    ambiguity_reason: str | None


def parse_money(text: str) -> ParsedMoney:
    if not text or not text.strip():
        return ParsedMoney(
            text=text, amount_decimal=None, currency=None,
            unit="unknown", ambiguous=True, ambiguity_reason="empty_input",
        )
    m = _MONEY_RE.search(text)
    if not m:
        return ParsedMoney(
            text=text, amount_decimal=None, currency=None,
            unit="unknown", ambiguous=True, ambiguity_reason="no_currency_amount_found",
        )
    currency = _CURRENCY_SYMBOLS[m["symbol"]]
    raw_num = m["num"].replace(",", "")
    try:
        amount = Decimal(raw_num)
    except InvalidOperation:
        return ParsedMoney(
            text=text, amount_decimal=None, currency=currency,
            unit="unknown", ambiguous=True, ambiguity_reason="non_decimal_amount",
        )
    if m["scale"]:
        amount = amount * _SCALE_WORDS[m["scale"].lower()]
    unit = "per_share" if _PER_SHARE_RE.search(text) else "absolute"
    approximate = bool(_APPROX_RE.search(text))
    return ParsedMoney(
        text=text,
        amount_decimal=amount,
        currency=currency,
        unit=unit,
        ambiguous=approximate,
        ambiguity_reason="approximate" if approximate else None,
    )


# ====================================================== parse_count

_BETWEEN_RE = re.compile(
    r"\bbetween\s+(?P<lo>\d{1,3}(?:,\d{3})*)\s+and\s+(?P<hi>\d{1,3}(?:,\d{3})*)\b",
    re.IGNORECASE,
)
_RANGE_DASH_RE = re.compile(
    r"\b(?P<lo>\d{1,3}(?:,\d{3})*)\s*[-–—]\s*(?P<hi>\d{1,3}(?:,\d{3})*)\b"
)
_MORE_THAN_RE = re.compile(
    r"\b(?:more\s+than|over|at\s+least)\s+(?P<n>\d{1,3}(?:,\d{3})*)\b",
    re.IGNORECASE,
)
_FEWER_THAN_RE = re.compile(
    r"\b(?:fewer\s+than|less\s+than|under|at\s+most|no\s+more\s+than)\s+(?P<n>\d{1,3}(?:,\d{3})*)\b",
    re.IGNORECASE,
)
_APPROX_COUNT_RE = re.compile(
    r"\b(?:approximately|approx\.?|about|around|roughly|some)\s+(?P<n>\d{1,3}(?:,\d{3})*)\b",
    re.IGNORECASE,
)
_EXACT_COUNT_RE = re.compile(r"\b(?P<n>\d{1,3}(?:,\d{3})*)\b")


@dataclass(frozen=True, slots=True)
class ParsedCount:
    text: str
    min_count: int | None
    max_count: int | None
    exact: bool
    ambiguous: bool
    ambiguity_reason: str | None


def _to_int(s: str) -> int:
    return int(s.replace(",", ""))


def parse_count(text: str) -> ParsedCount:
    if not text or not text.strip():
        return ParsedCount(text=text, min_count=None, max_count=None,
                           exact=False, ambiguous=True, ambiguity_reason="empty_input")

    m = _BETWEEN_RE.search(text) or _RANGE_DASH_RE.search(text)
    if m:
        lo, hi = _to_int(m["lo"]), _to_int(m["hi"])
        if hi < lo:
            lo, hi = hi, lo
        return ParsedCount(
            text=text, min_count=lo, max_count=hi,
            exact=False, ambiguous=False,
            ambiguity_reason="range" if lo != hi else None,
        )

    m = _MORE_THAN_RE.search(text)
    if m:
        return ParsedCount(
            text=text, min_count=_to_int(m["n"]) + 1, max_count=None,
            exact=False, ambiguous=True, ambiguity_reason="open_upper_bound",
        )

    m = _FEWER_THAN_RE.search(text)
    if m:
        return ParsedCount(
            text=text, min_count=None, max_count=_to_int(m["n"]) - 1,
            exact=False, ambiguous=True, ambiguity_reason="open_lower_bound",
        )

    m = _APPROX_COUNT_RE.search(text)
    if m:
        n = _to_int(m["n"])
        return ParsedCount(
            text=text, min_count=n, max_count=n,
            exact=False, ambiguous=True, ambiguity_reason="approximate",
        )

    m = _EXACT_COUNT_RE.search(text)
    if m:
        n = _to_int(m["n"])
        return ParsedCount(
            text=text, min_count=n, max_count=n,
            exact=True, ambiguous=False, ambiguity_reason=None,
        )

    return ParsedCount(
        text=text, min_count=None, max_count=None,
        exact=False, ambiguous=True, ambiguity_reason="no_count_found",
    )


# ====================================================== normalize_actor_label

_LEGAL_SUFFIX_MAP: dict[str, str] = {
    "corporation": "Corp",
    "corp.": "Corp",
    "corp": "Corp",
    "incorporated": "Inc",
    "inc.": "Inc",
    "inc": "Inc",
    "limited liability company": "LLC",
    "l.l.c.": "LLC",
    "l.l.c": "LLC",
    "llc": "LLC",
    "limited": "Ltd",
    "ltd.": "Ltd",
    "ltd": "Ltd",
    "company": "Co",
    "co.": "Co",
    "co": "Co",
    "n.a.": "N.A.",
    "n.a": "N.A.",
}
_SUFFIX_PATTERN = re.compile(
    r"\s*(?:" + "|".join(re.escape(k) for k in sorted(_LEGAL_SUFFIX_MAP, key=len, reverse=True)) + r")\s*$",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class ActorLabel:
    raw: str
    canonical_local: str
    aliases: tuple[str, ...]
    filing_id: str
    locality: str = field(default="filing")


def normalize_actor_label(*, label: str, filing_id: str) -> ActorLabel:
    """Filing-local actor canonicalization.

    Strips whitespace, normalises a fixed set of legal suffixes, and
    preserves the original raw form as an alias. There is *no* cross-deal
    actor pooling — `locality="filing"` is the contract.
    """
    raw = label
    cleaned = re.sub(r"\s+", " ", raw).strip().rstrip(",;:")
    normalized_suffix: str | None = None
    suffix_match = _SUFFIX_PATTERN.search(cleaned)
    if suffix_match:
        suffix_text = suffix_match.group(0).strip()
        normalized_suffix = _LEGAL_SUFFIX_MAP[suffix_text.lower()]
        body = cleaned[: suffix_match.start()].rstrip(", ")
    else:
        body = cleaned

    canonical = body if normalized_suffix is None else f"{body} {normalized_suffix}"
    aliases = (raw,) if raw != canonical else ()
    return ActorLabel(
        raw=raw,
        canonical_local=canonical,
        aliases=aliases,
        filing_id=filing_id,
        locality="filing",
    )
