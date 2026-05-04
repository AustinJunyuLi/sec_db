"""Section assignment for ingested paragraphs."""

from __future__ import annotations

import re

from .section_vocabulary import (
    NON_CANONICAL_HEADING,
    OTHER_HEADINGS,
    SALE_PROCESS_HEADINGS,
)

_COMMAND_STYLED_RE = re.compile(r"COMMAND=STYLE_ADDED,\"[^\"]*\"\s*")
_COMMAND_OTHER_RE = re.compile(r"COMMAND=[^\s*]+")
_INLINE_MARKUP_RE = re.compile(r"[*_`#]")
_LEADING_SECTION_NUMBER_RE = re.compile(r"^\d+\.\s+")
_HEADING_WRAPPER_RE = re.compile(r"^(\*{2,3}|__)(?P<inner>.+?)\1\s*$")
_NUMBERED_HEADING_RE = re.compile(r"^\d+\.\s+[A-Z]")
_TRAILING_HEADING_PUNCT = ".:"


def _strip_markup(text: str) -> str:
    text = _COMMAND_STYLED_RE.sub(" ", text)
    text = _COMMAND_OTHER_RE.sub(" ", text)
    text = _INLINE_MARKUP_RE.sub(" ", text)
    return re.sub(r"\s+", " ", text).strip()


def _normalize_heading(line: str) -> str:
    body = _strip_markup(line)
    body = body.rstrip(_TRAILING_HEADING_PUNCT)
    return body.casefold()


def _looks_like_heading(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return False
    if stripped.startswith("|"):
        return False
    has_emphasis = bool(_HEADING_WRAPPER_RE.match(stripped) or stripped.startswith("#"))
    has_number = bool(_NUMBERED_HEADING_RE.match(stripped))
    if not (has_emphasis or has_number):
        return False
    body = _strip_markup(stripped).rstrip(_TRAILING_HEADING_PUNCT)
    body = _LEADING_SECTION_NUMBER_RE.sub("", body)
    if not body:
        return False
    if len(body) > 120:
        return False
    if len(body.split()) > 15:
        return False
    return True


def detect_section(paragraph_text: str) -> str | None:
    first_line = next((line for line in paragraph_text.splitlines() if line.strip()), "")
    if not first_line:
        return None
    if first_line.lstrip().startswith("|"):
        # Markdown table-of-contents row, never a heading.
        return None

    normalized = _normalize_heading(first_line)
    stripped_number = _LEADING_SECTION_NUMBER_RE.sub("", normalized)

    for heading in SALE_PROCESS_HEADINGS:
        target = heading.casefold()
        if normalized == target or stripped_number == target:
            return heading

    for heading in OTHER_HEADINGS:
        target = heading.casefold()
        if normalized == target or normalized.startswith(target + " "):
            return heading

    if _looks_like_heading(first_line):
        return NON_CANONICAL_HEADING

    return None


def assign_sections(paragraph_texts: list[str]) -> list[str]:
    current = "unknown_section"
    sections: list[str] = []
    for text in paragraph_texts:
        detected = detect_section(text)
        if detected == NON_CANONICAL_HEADING:
            current = "unknown_section"
        elif detected is not None:
            current = detected
        sections.append(current)
    return sections
