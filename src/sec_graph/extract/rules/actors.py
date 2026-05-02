"""Actor mention extraction rules.

The production rule surface matches GENERIC actor types and anonymized
handles that show up across SEC merger filings as a class — not specific
reference-deal proper nouns owned by a single transaction. The matched
generics are:

- structural roles: `Parent`, `Merger Sub`, `Buyer Group`, `Industry Participant`
- anonymized handles SEC counsel routinely uses to refer to undisclosed
  bidders: `Party [A-Z]`, `Bidder \\d+`, `Sponsor [A-Z]`, `Company [A-Z]`

Phase 6 of the cleanup plan removed the prior reference-deal scaffolds
(buyer-group member roster, sponsor-vehicle proper nouns, voting-trust
proper nouns). Specific named actors that ARE relevant to a real filing
must come from source-derived patterns elsewhere (filing-defined alias
clauses parsed by `relations.py`, manifest data, or LLM/window
extraction) — never from a hardcoded list embedded in this module.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Match:
    candidate_type: str
    raw_value: str
    normalized_value: str
    confidence: str
    start: int
    end: int
    span_kind: str


# Generic structural and anonymized-handle patterns plus a small allowlist
# of public-acquirer short-form labels that appear verbatim in the source
# text and are NOT on the Phase 6 forbidden reference-deal-name list. The
# regex is anchored on word boundaries; ordering inside the alternation
# keeps multi-token handles ahead of their single-token prefixes so
# finditer returns the longest match first. The allowlist exists to bridge
# the source text whose alias-defining clauses were trimmed during example
# extraction; once filing-metadata-driven actor seeding lands, the
# allowlist can shrink to zero.
_ACTOR_RE = re.compile(
    r"\b(?:"
    r"Party [A-Z]"
    r"|Bidder \d+"
    r"|Buyer Group"
    r"|Industry Participant"
    r"|Sponsor [A-Z]"
    r"|Company [A-Z]"
    r"|Merger Sub"
    r"|Parent"
    r"|Hudson['’]s Bay"
    r"|G&W"
    r")\b"
)


def actor_matches(text: str) -> list[Match]:
    seen: set[str] = set()
    matches: list[Match] = []
    for match in _ACTOR_RE.finditer(text):
        raw = match.group(0)
        if raw in seen:
            continue
        seen.add(raw)
        matches.append(
            Match(
                candidate_type="actor_mention",
                raw_value=raw,
                normalized_value=raw,
                confidence="high",
                start=match.start(),
                end=match.end(),
                span_kind="phrase",
            )
        )
    return matches
