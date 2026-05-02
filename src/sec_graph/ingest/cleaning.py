"""Conservative filing-text cleaning with removal provenance."""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Removal:
    rule_id: str
    char_start: int
    char_end: int
    text: str


@dataclass(frozen=True)
class CleanLine:
    text: str
    char_start: int
    char_end: int


@dataclass(frozen=True)
class CleanedMarkdown:
    text: str
    lines: list[CleanLine]
    removals: list[Removal]


_ZEP_BANNER = re.compile(r"^ZEQ\.=")
_ISOLATED_FOLIO = re.compile(r"^\d{1,4}$")


def _removal_rule(stripped: str) -> str | None:
    if not stripped:
        return None
    if _ZEP_BANNER.match(stripped):
        return "zeq_banner"
    if stripped == "Table of Contents":
        return "table_of_contents"
    if stripped == "TOC_END":
        return "toc_end"
    if _ISOLATED_FOLIO.fullmatch(stripped):
        return "isolated_folio"
    if stripped.startswith("COMMAND=") and " Background of " not in stripped:
        return "printer_command"
    return None


def clean_markdown(raw_text: str) -> CleanedMarkdown:
    lines: list[CleanLine] = []
    removals: list[Removal] = []
    offset = 0
    for line in raw_text.splitlines(keepends=True):
        stripped = line.strip()
        rule_id = _removal_rule(stripped)
        end = offset + len(line)
        if rule_id is None:
            lines.append(CleanLine(text=line, char_start=offset, char_end=end))
        else:
            removals.append(Removal(rule_id=rule_id, char_start=offset, char_end=end, text=line))
        offset = end
    return CleanedMarkdown(text="".join(line.text for line in lines), lines=lines, removals=removals)
