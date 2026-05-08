"""RetrievalIndex: filing-local search built from a `FilingPackage`+`Atlas`.

Read-only. Holds paragraphs, sections, tables, and pre-computed token
statistics. The original raw filing text is exposed but never mutated; all
methods return positions/snapshots and never grant write access.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass
from typing import Sequence

from ..filing.atlas import (
    Atlas,
    SectionRecord,
    TableRecord,
)
from ..filing.package import Paragraph

_TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9'-]*")
BM25_K1 = 1.5
BM25_B = 0.75


def _tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


@dataclass(frozen=True, slots=True)
class TextPosition:
    char_start: int
    char_end: int
    quote_text: str
    paragraph_id: str | None


@dataclass(frozen=True, slots=True)
class RegexMatch:
    char_start: int
    char_end: int
    matched_text: str
    paragraph_id: str | None
    groups: tuple[str | None, ...]


@dataclass(frozen=True, slots=True)
class BM25Hit:
    paragraph_id: str
    score: float
    paragraph: Paragraph


class RetrievalIndex:
    """Per-filing retrieval index. Read-only by construction."""

    def __init__(
        self,
        *,
        filing_id: str,
        raw_text: str,
        paragraphs: Sequence[Paragraph],
        sections: Sequence[SectionRecord],
        tables: Sequence[TableRecord],
    ) -> None:
        self._filing_id = filing_id
        self._raw_text = raw_text
        self._paragraphs: tuple[Paragraph, ...] = tuple(paragraphs)
        self._sections: tuple[SectionRecord, ...] = tuple(sections)
        self._tables: tuple[TableRecord, ...] = tuple(tables)

        self._paragraph_by_id: dict[str, Paragraph] = {
            p.paragraph_id: p for p in self._paragraphs
        }
        self._section_by_id: dict[str, SectionRecord] = {
            s.section_id: s for s in self._sections
        }
        self._table_by_id: dict[str, TableRecord] = {
            t.table_id: t for t in self._tables
        }

        # BM25 stats over paragraphs.
        self._paragraph_tokens: dict[str, list[str]] = {
            p.paragraph_id: _tokenize(p.text) for p in self._paragraphs
        }
        self._paragraph_lengths: dict[str, int] = {
            pid: len(toks) for pid, toks in self._paragraph_tokens.items()
        }
        self._avg_dl: float = (
            sum(self._paragraph_lengths.values()) / len(self._paragraph_lengths)
            if self._paragraph_lengths
            else 0.0
        )
        df: Counter[str] = Counter()
        for tokens in self._paragraph_tokens.values():
            df.update(set(tokens))
        self._df: dict[str, int] = dict(df)
        self._n: int = len(self._paragraphs)

    # ------------------------------------------------------ factories

    @classmethod
    def from_atlas(
        cls,
        atlas: Atlas,
        *,
        raw_text: str,
        filing_id: str | None = None,
    ) -> "RetrievalIndex":
        if filing_id is None:
            if not atlas.filings:
                raise ValueError("atlas must contain at least one filing")
            filing_id = atlas.filings[0].filing_id
        return cls(
            filing_id=filing_id,
            raw_text=raw_text,
            paragraphs=atlas.paragraphs,
            sections=atlas.sections,
            tables=atlas.tables,
        )

    # ------------------------------------------------------ properties

    @property
    def filing_id(self) -> str:
        return self._filing_id

    @property
    def raw_text(self) -> str:
        return self._raw_text

    @property
    def paragraphs(self) -> tuple[Paragraph, ...]:
        return self._paragraphs

    # ------------------------------------------------------ literal

    def literal(self, quote: str) -> list[TextPosition]:
        """All exact occurrences of `quote` in the raw text."""
        if not quote:
            return []
        positions: list[TextPosition] = []
        cursor = 0
        while True:
            idx = self._raw_text.find(quote, cursor)
            if idx == -1:
                break
            end = idx + len(quote)
            positions.append(
                TextPosition(
                    char_start=idx,
                    char_end=end,
                    quote_text=self._raw_text[idx:end],
                    paragraph_id=self._paragraph_for_offset(idx),
                )
            )
            cursor = end
        return positions

    # ------------------------------------------------------ regex

    def regex(self, pattern: str, *, flags: int = 0) -> list[RegexMatch]:
        """Regex search. The raw text is never mutated by this call."""
        compiled = re.compile(pattern, flags)
        results: list[RegexMatch] = []
        for match in compiled.finditer(self._raw_text):
            results.append(
                RegexMatch(
                    char_start=match.start(),
                    char_end=match.end(),
                    matched_text=match.group(0),
                    paragraph_id=self._paragraph_for_offset(match.start()),
                    groups=tuple(match.groups()),
                )
            )
        return results

    # ------------------------------------------------------ BM25

    def bm25(self, query: str, *, k: int = 5) -> list[BM25Hit]:
        query_tokens = _tokenize(query)
        if not query_tokens or self._n == 0:
            return []
        unique_query = set(query_tokens)
        hits: list[tuple[Paragraph, float]] = []
        for paragraph in self._paragraphs:
            doc_tokens = self._paragraph_tokens[paragraph.paragraph_id]
            if not doc_tokens:
                continue
            tf_counter = Counter(doc_tokens)
            score = 0.0
            dl = self._paragraph_lengths[paragraph.paragraph_id]
            for token in unique_query:
                tf = tf_counter[token]
                if tf == 0:
                    continue
                df = self._df.get(token, 0)
                if df == 0:
                    continue
                idf = math.log((self._n - df + 0.5) / (df + 0.5) + 1.0)
                denom = tf + BM25_K1 * (1.0 - BM25_B + BM25_B * dl / max(self._avg_dl, 1.0))
                score += idf * (tf * (BM25_K1 + 1.0)) / denom
            if score > 0:
                hits.append((paragraph, score))
        hits.sort(key=lambda item: (-item[1], item[0].ordinal))
        return [
            BM25Hit(paragraph_id=p.paragraph_id, score=score, paragraph=p)
            for p, score in hits[:k]
        ]

    # ------------------------------------------------------ fetches

    def get_paragraph(self, paragraph_id: str) -> Paragraph:
        try:
            return self._paragraph_by_id[paragraph_id]
        except KeyError as exc:
            raise KeyError(f"unknown paragraph_id: {paragraph_id!r}") from exc

    def get_section(self, section_id: str) -> SectionRecord:
        try:
            return self._section_by_id[section_id]
        except KeyError as exc:
            raise KeyError(f"unknown section_id: {section_id!r}") from exc

    def get_table(self, table_id: str) -> TableRecord:
        try:
            return self._table_by_id[table_id]
        except KeyError as exc:
            raise KeyError(f"unknown table_id: {table_id!r}") from exc

    def neighborhood(
        self,
        paragraph_id: str,
        *,
        before: int = 1,
        after: int = 1,
    ) -> list[Paragraph]:
        if before < 0 or after < 0:
            raise ValueError("before/after must be non-negative")
        anchor = self.get_paragraph(paragraph_id)
        anchor_index = anchor.ordinal
        start = max(0, anchor_index - before)
        end = min(len(self._paragraphs), anchor_index + after + 1)
        return [
            self._paragraphs[i]
            for i in range(start, end)
        ]

    # ------------------------------------------------------ helpers

    def _paragraph_for_offset(self, char_offset: int) -> str | None:
        for p in self._paragraphs:
            if p.char_start <= char_offset < p.char_end:
                return p.paragraph_id
        return None
