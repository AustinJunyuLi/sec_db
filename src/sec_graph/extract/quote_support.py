"""Shared quote-support helpers for claim disposition.

Disposition (`extract/disposition.py`) is the single semantic gate. The
helpers here used to live in two places (`validate/integrity.py` and
`extract/disposition.py`); the post-canonical semantic gate has been
deleted, so these helpers live here and are imported once.
"""

from __future__ import annotations

import datetime as dt
import re
from typing import Iterable


def normalize_text(value: str | None) -> str:
    """Casefold and collapse whitespace; strip dashes/underscores."""

    if not value:
        return ""
    folded = value.casefold().replace("-", " ").replace("_", " ")
    return re.sub(r"\s+", " ", folded).strip()


def numeric_tokens(value: str) -> set[str]:
    """Return the set of integer token strings appearing in ``value``.

    Strings are stripped of leading zeros so ``"0007"`` collapses to
    ``"7"``; the empty token is reported as ``"0"`` to keep the set
    well-defined.
    """

    return {token.lstrip("0") or "0" for token in re.findall(r"\d+", value)}


def contains_phrase(text: str | None, phrase: str | None) -> bool:
    if not text or not phrase:
        return False
    return normalize_text(phrase) in normalize_text(text)


def number_supported_by_quote(value: float, quote_text: str | None) -> bool:
    if not quote_text:
        return False
    tokens = numeric_tokens(quote_text)
    candidates = {f"{value:g}", f"{value:.1f}", f"{value:.2f}"}
    if value.is_integer():
        candidates.add(str(int(value)))
    normalized_candidates = {candidate.rstrip("0").rstrip(".") for candidate in candidates}
    quote_decimal_values = {
        match.rstrip("0").rstrip(".") for match in re.findall(r"\d+(?:\.\d+)?", quote_text)
    }
    return bool(normalized_candidates & quote_decimal_values) or str(int(value)) in tokens


def date_supported_by_quote(value: object, quote_text: str | None) -> bool:
    if not quote_text:
        return False
    parsed = _coerce_date(value)
    if parsed is None:
        return False
    folded = quote_text.casefold()
    if parsed.isoformat() in folded:
        return True
    month_name = parsed.strftime("%B").casefold()
    month_abbr = parsed.strftime("%b").casefold()
    has_month = (
        month_name in folded
        or month_abbr in folded
        or str(parsed.month) in numeric_tokens(folded)
    )
    return (
        str(parsed.year) in folded
        and has_month
        and str(parsed.day) in numeric_tokens(folded)
    )


def _coerce_date(value: object) -> dt.date | None:
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    if isinstance(value, str):
        try:
            return dt.date.fromisoformat(value)
        except ValueError:
            return None
    return None


def bid_context_supported_by_quote(bid_stage: str | None, quote_text: str | None) -> bool:
    if not quote_text:
        return False
    folded = normalize_text(quote_text)
    context_terms = {
        "bid",
        "offer",
        "proposal",
        "submitted",
        "proposed",
        "indication of interest",
    }
    if bid_stage and bid_stage != "unspecified":
        context_terms.add(bid_stage.replace("_", " "))
    return any(term in folded for term in context_terms)


def relation_supported_by_quote(
    relation_type: str,
    role_detail: str | None,
    quote_text: str | None,
) -> bool:
    if not quote_text:
        return False
    folded = normalize_text(quote_text)
    terms: set[str] = {relation_type.replace("_", " ")}
    if role_detail:
        terms.add(role_detail)
    relation_synonyms = {
        "acquisition_vehicle_of": ("acquisition vehicle", "vehicle of"),
        "member_of": (
            "member of",
            "part of",
            "together we refer",
            "who together",
            "together as",
        ),
        "affiliate_of": ("affiliate of", "affiliated with"),
        "controls": (
            "controls",
            "controlled by",
            "purchased by",
            "acquired by",
            "owned by",
        ),
        "advises": ("advisor", "adviser", "advises"),
        "finances": (
            "financing",
            "finances",
            "provide capital",
            "capital required",
            "financing letter",
        ),
        "supports": ("support", "supports", "guarantee", "guarantees"),
        "voting_support_for": (
            "voting agreement",
            "support agreement",
            "vote in favor",
            "agreed to vote",
            "voting and support",
        ),
        "rollover_holder_for": (
            "rollover",
            "rolled",
            "contribute",
            "retain equity",
            "equity rollover",
        ),
        "committee_member_of": (
            "committee",
            "member",
            "composed of",
            "appointed",
            "added",
        ),
        "recused_from": (
            "recuse",
            "recused",
            "exclude",
            "excluded",
            "not participate",
        ),
    }
    terms.update(relation_synonyms.get(relation_type, ()))
    return any(normalize_text(term) in folded for term in terms if term)


def any_term_in_text(terms: Iterable[str], quote_text: str | None) -> bool:
    if not quote_text:
        return False
    folded = normalize_text(quote_text)
    return any(normalize_text(term) in folded for term in terms if term)
