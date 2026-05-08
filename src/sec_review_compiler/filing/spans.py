"""SourceSpan: an exact byte-coordinate citation into filing text.

Identity is computed from `filing_id || char_start || char_end ||
quote_text_hash`. Two spans citing the same quoted text at different
coordinates therefore receive distinct evidence ids — text-only quote
hashes are not evidence identity (design spec §7).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field


def _sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class SourceSpan:
    filing_id: str
    char_start: int
    char_end: int
    quote_text: str
    quote_text_hash: str = field(default="", repr=False)
    paragraph_id: str | None = None

    def __post_init__(self) -> None:
        if self.char_end < self.char_start:
            raise ValueError(
                f"char_end ({self.char_end}) precedes char_start ({self.char_start})"
            )
        if not self.quote_text_hash:
            object.__setattr__(self, "quote_text_hash", _sha256_hex(self.quote_text))

    def identity(self) -> str:
        """Return the deterministic evidence id for this span."""
        payload = f"{self.filing_id}{self.char_start}{self.char_end}{self.quote_text_hash}"
        return _sha256_hex(payload)

    @property
    def evidence_id(self) -> str:
        return self.identity()
