"""FilingPackage builder: the immutable input unit for one deal.

Filing text is truth (design spec §6). The package preserves the raw text
verbatim, exposes a normalized projection for indexing, and binds every
paragraph and exhibit to exact character offsets in the raw text.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Iterable

from ..errors import MissingTenderOfferExhibitError

# Filing types treated as tender offers for substantive-exhibit enforcement.
TENDER_OFFER_FILING_TYPES = frozenset({"SC TO-T", "SC TO-I", "SC 14D9"})

# Paragraph splitter: blank-line-delimited blocks. We compute offsets against
# the raw text directly so paragraphs index back into source coordinates
# without any normalization shift.
_PARAGRAPH_SEP_RE = re.compile(r"\n\s*\n")

# Exhibit marker: a line that begins with "Exhibit " followed by a designation
# like "99.1" or "(a)(1)(A)". The whole line is the marker; the body follows.
_EXHIBIT_MARKER_RE = re.compile(
    r"(?m)^Exhibit\s+(?P<designation>\(?[A-Za-z0-9][A-Za-z0-9.()-]*)\s*$"
)


def _sha256_hex(value: bytes | str) -> str:
    if isinstance(value, str):
        value = value.encode("utf-8")
    return hashlib.sha256(value).hexdigest()


def _normalize_text(raw_text: str) -> str:
    """Return a normalized projection of `raw_text` for retrieval indexing.

    Rules: replace CRLF with LF; collapse runs of three+ blank lines to two;
    strip trailing whitespace per line. Character coordinates from raw_text
    are not preserved across normalization — paragraphs use raw offsets.
    """
    text = raw_text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text


@dataclass(frozen=True, slots=True)
class Paragraph:
    paragraph_id: str
    ordinal: int
    text: str
    char_start: int
    char_end: int


@dataclass(frozen=True, slots=True)
class Exhibit:
    exhibit_id: str
    designation: str
    label: str
    body: str
    char_start: int
    char_end: int
    substantive_offer: bool = False


@dataclass(frozen=True, slots=True)
class FilingPackage:
    filing_id: str
    filing_type: str
    raw_text: str
    raw_sha256: str
    normalized_text: str
    normalized_sha256: str
    paragraphs: tuple[Paragraph, ...]
    exhibits: tuple[Exhibit, ...] = field(default_factory=tuple)

    def paragraph_for_offset(self, char_offset: int) -> Paragraph | None:
        for p in self.paragraphs:
            if p.char_start <= char_offset < p.char_end:
                return p
        return None


def _split_paragraphs(filing_id: str, raw_text: str) -> tuple[Paragraph, ...]:
    paragraphs: list[Paragraph] = []
    cursor = 0
    ordinal = 0
    length = len(raw_text)

    while cursor < length:
        # Skip leading separator whitespace but preserve cursor for offset truth.
        ws = re.match(r"\s+", raw_text[cursor:])
        if ws:
            cursor += ws.end()
            if cursor >= length:
                break

        sep_match = _PARAGRAPH_SEP_RE.search(raw_text, cursor)
        end = sep_match.start() if sep_match else length

        chunk = raw_text[cursor:end]
        chunk_stripped = chunk.rstrip()
        if chunk_stripped:
            char_start = cursor
            char_end = cursor + len(chunk_stripped)
            paragraphs.append(
                Paragraph(
                    paragraph_id=f"{filing_id}:p{ordinal:04d}",
                    ordinal=ordinal,
                    text=raw_text[char_start:char_end],
                    char_start=char_start,
                    char_end=char_end,
                )
            )
            ordinal += 1

        cursor = end
    return tuple(paragraphs)


def _detect_exhibits(raw_text: str) -> list[Exhibit]:
    matches = list(_EXHIBIT_MARKER_RE.finditer(raw_text))
    if not matches:
        return []
    exhibits: list[Exhibit] = []
    for index, match in enumerate(matches):
        body_start = match.end()
        body_end = matches[index + 1].start() if index + 1 < len(matches) else len(raw_text)
        body = raw_text[body_start:body_end].strip("\n")
        designation = match["designation"]
        label_match = re.match(r"\s*(?P<label>[^\n]+)", body)
        label = label_match["label"].strip() if label_match else ""
        substantive_offer = bool(re.search(r"offer\s+to\s+purchase", body, flags=re.IGNORECASE))
        exhibits.append(
            Exhibit(
                exhibit_id=f"exhibit:{designation}",
                designation=designation,
                label=label,
                body=body,
                char_start=match.start(),
                char_end=body_end,
                substantive_offer=substantive_offer,
            )
        )
    return exhibits


def build_filing_package(
    *,
    filing_id: str,
    filing_type: str,
    raw_text: str,
    declared_substantive_exhibits: Iterable[str] | None = None,
) -> FilingPackage:
    """Build a `FilingPackage` from raw filing text.

    `declared_substantive_exhibits` is an optional iterable of exhibit
    designations (e.g. `["(a)(1)(A)"]`) flagged as substantive by the
    upstream caller (e.g. EDGAR exhibit type metadata). When provided, those
    exhibits are marked substantive even if their body lacks the heuristic
    "offer to purchase" phrase.
    """
    if not raw_text:
        raise ValueError("raw_text must be non-empty")

    raw_sha256 = _sha256_hex(raw_text)
    normalized_text = _normalize_text(raw_text)
    normalized_sha256 = _sha256_hex(normalized_text)

    paragraphs = _split_paragraphs(filing_id, raw_text)
    exhibits = _detect_exhibits(raw_text)

    declared = set(declared_substantive_exhibits or ())
    if declared:
        exhibits = [
            Exhibit(
                exhibit_id=ex.exhibit_id,
                designation=ex.designation,
                label=ex.label,
                body=ex.body,
                char_start=ex.char_start,
                char_end=ex.char_end,
                substantive_offer=ex.substantive_offer or ex.designation in declared,
            )
            for ex in exhibits
        ]

    if filing_type in TENDER_OFFER_FILING_TYPES:
        if not any(ex.substantive_offer for ex in exhibits):
            raise MissingTenderOfferExhibitError(
                f"tender-offer filing {filing_id!r} lacks a substantive "
                "Offer to Purchase exhibit; refusing to build package"
            )

    return FilingPackage(
        filing_id=filing_id,
        filing_type=filing_type,
        raw_text=raw_text,
        raw_sha256=raw_sha256,
        normalized_text=normalized_text,
        normalized_sha256=normalized_sha256,
        paragraphs=paragraphs,
        exhibits=tuple(exhibits),
    )
