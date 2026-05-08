"""Filing-local retrieval index and deterministic agent tools.

The retrieval layer supports agents but does not decide truth. Every
returned record carries stable source ids and exact character coordinates
so a verifier can re-inspect the citation. Failures are surfaced, never
silently dropped (design spec §8).
"""

from .index import (
    BM25Hit,
    RegexMatch,
    RetrievalIndex,
    TextPosition,
)
from .tools import (
    ParsedCount,
    ParsedDate,
    ParsedMoney,
    QuoteVerification,
    ActorLabel,
    normalize_actor_label,
    parse_count,
    parse_date,
    parse_money,
    verify_quote,
)

__all__ = [
    "ActorLabel",
    "BM25Hit",
    "ParsedCount",
    "ParsedDate",
    "ParsedMoney",
    "QuoteVerification",
    "RegexMatch",
    "RetrievalIndex",
    "TextPosition",
    "normalize_actor_label",
    "parse_count",
    "parse_date",
    "parse_money",
    "verify_quote",
]
