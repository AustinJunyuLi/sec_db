"""Deterministic ID helpers."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field


def make_id(slug: str, type_: str, sequence: int) -> str:
    if not slug:
        raise ValueError("slug is required")
    if not type_:
        raise ValueError("type_ is required")
    if sequence < 1:
        raise ValueError("sequence must be >= 1")
    return f"{slug}_{type_}_{sequence}"


@dataclass
class SequenceAllocator:
    """Stable per-(slug, type) sequence allocator for deterministic runs."""

    _counters: dict[tuple[str, str], int] = field(default_factory=lambda: defaultdict(int))

    def next(self, slug: str, type_: str) -> str:
        key = (slug, type_)
        self._counters[key] += 1
        return make_id(slug, type_, self._counters[key])
