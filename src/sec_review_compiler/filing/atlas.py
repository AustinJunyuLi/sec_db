"""Filing atlas: a deterministic map of filing source material.

Per design spec §7, the atlas is *not* truth about deal facts — it is an
indexable record of what source material exists, where it lives by
character offsets, and where the heading structure is uncertain. Ambiguity
is recorded explicitly via `atlas_warnings`; ambiguous sections are *not*
silently skipped.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Sequence

from .package import Exhibit, FilingPackage, Paragraph
from .spans import SourceSpan


# A heading is a short paragraph (single non-empty line) that does not end
# with sentence punctuation and has at most twelve words. Headings are
# *candidates* — confirmation of section identity is not the atlas's job.
_HEADING_TERMINAL_PUNCT = ".!?:;"


@dataclass(frozen=True, slots=True)
class FilingRecord:
    filing_id: str
    filing_type: str
    raw_sha256: str
    normalized_sha256: str
    paragraph_count: int


@dataclass(frozen=True, slots=True)
class ExhibitRecord:
    exhibit_id: str
    designation: str
    label: str
    char_start: int
    char_end: int
    substantive_offer: bool


@dataclass(frozen=True, slots=True)
class SectionCandidate:
    candidate_id: str
    label: str
    label_normalised: str
    char_start: int
    char_end: int
    paragraph_id: str
    confidence: str  # "confident" | "ambiguous"


@dataclass(frozen=True, slots=True)
class SectionRecord:
    section_id: str
    label: str
    label_normalised: str
    char_start: int
    char_end: int
    heading_paragraph_id: str
    body_paragraph_ids: tuple[str, ...]
    is_ambiguous_label: bool


@dataclass(frozen=True, slots=True)
class TableRecord:
    table_id: str
    paragraph_id: str
    char_start: int
    char_end: int
    column_count: int
    row_count: int


@dataclass(frozen=True, slots=True)
class AtlasWarning:
    code: str
    message: str
    payload: tuple[tuple[str, str], ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class Atlas:
    filings: tuple[FilingRecord, ...]
    exhibits: tuple[ExhibitRecord, ...]
    sections: tuple[SectionRecord, ...]
    paragraphs: tuple[Paragraph, ...]
    tables: tuple[TableRecord, ...]
    source_spans: tuple[SourceSpan, ...]
    section_candidates: tuple[SectionCandidate, ...]
    atlas_warnings: tuple[AtlasWarning, ...]


# ---------------------------------------------------------------- helpers

def _normalise_label(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip()).lower()


def _looks_like_heading(text: str) -> bool:
    if "\n" in text.strip():
        return False
    cleaned = text.strip()
    if not cleaned or cleaned[-1] in _HEADING_TERMINAL_PUNCT:
        return False
    if len(cleaned.split()) > 12:
        return False
    return True


def _looks_like_table_block(text: str) -> bool:
    """A table block is 2+ consecutive lines each carrying 2+ column gaps."""
    lines = text.splitlines()
    if len(lines) < 2:
        return False
    aligned_lines = 0
    for line in lines:
        if not line.strip():
            continue
        # Count runs of two-or-more spaces — each run separates two columns.
        gaps = re.findall(r"  +", line)
        if len(gaps) >= 2:
            aligned_lines += 1
    return aligned_lines >= 2


def _detect_table(paragraph: Paragraph) -> TableRecord | None:
    if not _looks_like_table_block(paragraph.text):
        return None
    lines = [ln for ln in paragraph.text.splitlines() if ln.strip()]
    column_counts = []
    for line in lines:
        columns = re.split(r"  +", line.strip())
        column_counts.append(len(columns))
    column_count = max(column_counts) if column_counts else 0
    return TableRecord(
        table_id=f"table:{paragraph.paragraph_id}",
        paragraph_id=paragraph.paragraph_id,
        char_start=paragraph.char_start,
        char_end=paragraph.char_end,
        column_count=column_count,
        row_count=len(lines),
    )


def _build_section_candidates(
    paragraphs: Sequence[Paragraph],
) -> list[SectionCandidate]:
    candidates: list[SectionCandidate] = []
    for paragraph in paragraphs:
        if not _looks_like_heading(paragraph.text):
            continue
        candidates.append(
            SectionCandidate(
                candidate_id=f"section_candidate:{paragraph.paragraph_id}",
                label=paragraph.text.strip(),
                label_normalised=_normalise_label(paragraph.text),
                char_start=paragraph.char_start,
                char_end=paragraph.char_end,
                paragraph_id=paragraph.paragraph_id,
                confidence="confident",  # promoted to "ambiguous" below if duplicated
            )
        )
    return candidates


def _resolve_section_candidates(
    candidates: list[SectionCandidate],
) -> tuple[list[SectionCandidate], set[str]]:
    label_counts = Counter(c.label_normalised for c in candidates)
    ambiguous_labels = {label for label, count in label_counts.items() if count > 1}
    resolved = [
        SectionCandidate(
            candidate_id=c.candidate_id,
            label=c.label,
            label_normalised=c.label_normalised,
            char_start=c.char_start,
            char_end=c.char_end,
            paragraph_id=c.paragraph_id,
            confidence="ambiguous" if c.label_normalised in ambiguous_labels else "confident",
        )
        for c in candidates
    ]
    return resolved, ambiguous_labels


def _build_sections(
    candidates: list[SectionCandidate],
    paragraphs: Sequence[Paragraph],
    ambiguous_labels: set[str],
    raw_text_length: int,
) -> list[SectionRecord]:
    """Emit one SectionRecord per heading candidate; never silently skip."""
    if not candidates:
        return []

    sections: list[SectionRecord] = []
    for index, heading in enumerate(candidates):
        next_start = (
            candidates[index + 1].char_start
            if index + 1 < len(candidates)
            else raw_text_length
        )
        body_paragraph_ids = tuple(
            p.paragraph_id
            for p in paragraphs
            if p.char_start >= heading.char_end
            and p.char_end <= next_start
            and p.paragraph_id != heading.paragraph_id
        )
        sections.append(
            SectionRecord(
                section_id=f"section:{heading.paragraph_id}",
                label=heading.label,
                label_normalised=heading.label_normalised,
                char_start=heading.char_start,
                char_end=next_start,
                heading_paragraph_id=heading.paragraph_id,
                body_paragraph_ids=body_paragraph_ids,
                is_ambiguous_label=heading.label_normalised in ambiguous_labels,
            )
        )
    return sections


def _exhibit_records(exhibits: Sequence[Exhibit]) -> list[ExhibitRecord]:
    return [
        ExhibitRecord(
            exhibit_id=ex.exhibit_id,
            designation=ex.designation,
            label=ex.label,
            char_start=ex.char_start,
            char_end=ex.char_end,
            substantive_offer=ex.substantive_offer,
        )
        for ex in exhibits
    ]


def _paragraph_spans(filing_id: str, paragraphs: Sequence[Paragraph]) -> list[SourceSpan]:
    return [
        SourceSpan(
            filing_id=filing_id,
            char_start=p.char_start,
            char_end=p.char_end,
            quote_text=p.text,
            paragraph_id=p.paragraph_id,
        )
        for p in paragraphs
    ]


# ---------------------------------------------------------------- public

def build_atlas(package: FilingPackage) -> Atlas:
    paragraphs = list(package.paragraphs)
    raw_candidates = _build_section_candidates(paragraphs)
    resolved_candidates, ambiguous_labels = _resolve_section_candidates(raw_candidates)
    sections = _build_sections(
        resolved_candidates,
        paragraphs,
        ambiguous_labels,
        raw_text_length=len(package.raw_text),
    )

    tables: list[TableRecord] = []
    for paragraph in paragraphs:
        record = _detect_table(paragraph)
        if record is not None:
            tables.append(record)

    source_spans = _paragraph_spans(package.filing_id, paragraphs)

    warnings: list[AtlasWarning] = []
    for label in sorted(ambiguous_labels):
        occurrences = [c.label for c in resolved_candidates if c.label_normalised == label]
        warnings.append(
            AtlasWarning(
                code="ambiguous_section_label",
                message=(
                    f"section label {label!r} occurs {len(occurrences)} times; "
                    "all occurrences are recorded as separate sections"
                ),
                payload=(("label", label), ("occurrences", str(len(occurrences)))),
            )
        )

    filing_record = FilingRecord(
        filing_id=package.filing_id,
        filing_type=package.filing_type,
        raw_sha256=package.raw_sha256,
        normalized_sha256=package.normalized_sha256,
        paragraph_count=len(paragraphs),
    )

    return Atlas(
        filings=(filing_record,),
        exhibits=tuple(_exhibit_records(package.exhibits)),
        sections=tuple(sections),
        paragraphs=tuple(paragraphs),
        tables=tuple(tables),
        source_spans=tuple(source_spans),
        section_candidates=tuple(resolved_candidates),
        atlas_warnings=tuple(warnings),
    )
