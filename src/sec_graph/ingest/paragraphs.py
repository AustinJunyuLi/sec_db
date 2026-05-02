"""Paragraph splitting with raw-coordinate retention."""

from __future__ import annotations

import re
from dataclasses import dataclass

from .cleaning import CleanLine, CleanedMarkdown

PAGE_MARKER_RE = re.compile(r"<!--\s*PAGE\s+(\d+)\s*-->")


@dataclass(frozen=True)
class ParagraphBlock:
    text: str
    char_start: int
    char_end: int
    page_hint: int | None


def split_paragraphs(cleaned: CleanedMarkdown) -> list[ParagraphBlock]:
    blocks: list[ParagraphBlock] = []
    current: list[CleanLine] = []
    current_page: int | None = None

    def flush() -> None:
        nonlocal current
        if not current:
            return
        text = "".join(line.text for line in current)
        if text.strip():
            blocks.append(
                ParagraphBlock(
                    text=text,
                    char_start=current[0].char_start,
                    char_end=current[-1].char_end,
                    page_hint=current_page,
                )
            )
        current = []

    for line in cleaned.lines:
        page_match = PAGE_MARKER_RE.search(line.text)
        if page_match:
            flush()
            current_page = int(page_match.group(1))
            blocks.append(
                ParagraphBlock(
                    text=line.text,
                    char_start=line.char_start,
                    char_end=line.char_end,
                    page_hint=current_page,
                )
            )
            continue
        if not line.text.strip():
            flush()
            continue
        current.append(line)
    flush()
    return blocks
