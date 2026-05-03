"""Evidence hashing and quote validation helpers."""

from __future__ import annotations

import hashlib


def quote_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def evidence_fingerprint(
    filing_id: str,
    char_start: int,
    char_end: int,
    quote_text_hash: str,
) -> str:
    payload = f"{filing_id}\0{char_start}\0{char_end}\0{quote_text_hash}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def validate_quote(
    filing_text: str,
    char_start: int,
    char_end: int,
    expected_hash: str,
) -> bool:
    if char_start < 0 or char_end < char_start or char_end > len(filing_text):
        return False
    return quote_hash(filing_text[char_start:char_end]) == expected_hash
