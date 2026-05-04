"""Section heading vocabulary for conservative ingest assignment."""

from __future__ import annotations

# Sale-process section headings. Order longest-first so prefix variants like
# "Background of the Offer and Merger" are tested before "Background of the
# Offer". Matching against these names uses exact equality after stripping
# inline markup, leading section numbers, and trailing punctuation; we do not
# fall back to prefix matching because body sentences can begin with the same
# words and would otherwise be promoted to headings.
SALE_PROCESS_HEADINGS: tuple[str, ...] = (
    "Background of the Offer and Merger",
    "Background of the Solicitation",
    "Background of the Offer",
    "Background of the Merger",
    "Past Contacts, Transactions, Negotiations and Agreements",
    "Past Contacts and Negotiations",
    "Background and Reasons for the Recommendation",
)

# Non-sale-process headings retained for state tracking. Prefix matching is
# allowed here because legacy headings like "Opinion of <advisor>" carry
# advisor-specific suffixes.
OTHER_HEADINGS: tuple[str, ...] = (
    "Reasons for the Merger",
    "Opinion of",
    "Financing",
    "Interests of Directors and Executive Officers",
    "No-Boundary Cycle Marker",
)

SECTION_HEADINGS: tuple[str, ...] = SALE_PROCESS_HEADINGS + OTHER_HEADINGS

# Sentinel returned when a paragraph looks like a heading line but does not
# match any vocabulary entry. The section assigner treats it as a section
# terminator so sticky sale-process labels stop spreading.
NON_CANONICAL_HEADING = "__other_heading__"

SALE_PROCESS_SECTIONS = frozenset(SALE_PROCESS_HEADINGS)
