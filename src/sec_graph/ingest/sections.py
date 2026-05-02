"""Section assignment for ingested paragraphs."""

from __future__ import annotations

import re

from .section_vocabulary import SECTION_HEADINGS


def _normalize(text: str) -> str:
    text = re.sub(r"[*_`#]", " ", text)
    text = re.sub(r"COMMAND=[^ ]+", " ", text)
    return re.sub(r"\s+", " ", text).strip().casefold()


def detect_section(paragraph_text: str) -> str | None:
    normalized = _normalize(paragraph_text)
    for heading in SECTION_HEADINGS:
        if heading.casefold() in normalized:
            return heading
    return None


def assign_sections(paragraph_texts: list[str]) -> list[str]:
    current = "unknown_section"
    sections: list[str] = []
    for text in paragraph_texts:
        detected = detect_section(text)
        if detected is not None:
            current = detected
        sections.append(current)
    return sections
