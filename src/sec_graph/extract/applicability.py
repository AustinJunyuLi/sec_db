"""Python-owned applicability engine for sale-process coverage obligations.

Phase 2 replaces the static ten-obligation bundle with a per-region decision:
universal obligations are always applicable, conditional obligations are
applicable only when the region text emits a documented trigger phrase, and
scope-driven obligations apply only to filings of the named process scope.

Linkflow never sees inapplicable obligations and never emits absence
judgments. Python owns the entire applicability surface so the audit trail is
deterministic and inspectable in DuckDB.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal

from sec_graph.extract.source_support import SupportState, classify_obligation_support
from sec_graph.schema.models.extraction import ClaimType

Importance = Literal["required", "important", "optional"]
Applicability = Literal["applicable", "not_applicable"]


@dataclass(frozen=True)
class ObligationKind:
    """Static metadata for a candidate coverage obligation.

    ``kind`` is the stable identifier used in the audit ledger. ``label`` is
    the human-readable label sent to Linkflow. ``triggers`` is retained as
    documented lexical metadata for conditional kinds; positive support is
    classified by ``source_support.py`` rather than by broad trigger presence.
    """

    kind: str
    claim_type: ClaimType
    label: str
    importance: Importance
    family: Literal["universal", "conditional", "scope"]
    triggers: tuple[re.Pattern[str], ...] = field(default_factory=tuple)
    scopes: tuple[str, ...] = field(default_factory=tuple)


def _ci(*patterns: str) -> tuple[re.Pattern[str], ...]:
    return tuple(re.compile(pattern, re.IGNORECASE) for pattern in patterns)


# Universal obligations are always applicable in any sale-process region.
# These cover the minimum facts a trusted extraction must establish.
UNIVERSAL_OBLIGATIONS: tuple[ObligationKind, ...] = (
    ObligationKind(
        kind="process_initiation",
        claim_type="event",
        label="Sales process initiation",
        importance="required",
        family="universal",
    ),
    ObligationKind(
        kind="target_board",
        claim_type="actor",
        label="Target board",
        importance="required",
        family="universal",
    ),
    ObligationKind(
        kind="target_financial_advisor",
        claim_type="actor_relation",
        label="Financial advisor for target",
        importance="required",
        family="universal",
    ),
    ObligationKind(
        kind="target_legal_advisor",
        claim_type="actor_relation",
        label="Legal advisor for target",
        importance="required",
        family="universal",
    ),
    ObligationKind(
        kind="final_consideration",
        claim_type="bid",
        label="Final transaction price",
        importance="required",
        family="universal",
    ),
    ObligationKind(
        kind="final_approval_event",
        claim_type="event",
        label="Final approval or signing event",
        importance="required",
        family="universal",
    ),
)


# Conditional obligations are applicable when the region text emits at least
# one of the listed trigger patterns.
CONDITIONAL_OBLIGATIONS: tuple[ObligationKind, ...] = (
    ObligationKind(
        kind="contacted_count",
        claim_type="participation_count",
        label="Bidder count at contact stage",
        importance="important",
        family="conditional",
        triggers=_ci(
            r"contacted\s+(?:approximately\s+|by\s+)?\d+",
            r"\d+\s+potential\s+(?:buyers|bidders|parties|acquirers)",
            r"\d+\s+(?:financial|strategic)\s+(?:buyers|parties)",
        ),
    ),
    ObligationKind(
        kind="ioi_count",
        claim_type="participation_count",
        label="Bidder count at IOI stage",
        importance="important",
        family="conditional",
        triggers=_ci(
            r"indications?\s+of\s+interest",
            r"preliminary\s+(?:non-?binding\s+)?(?:proposals?|indications?)",
            r"\bIOIs?\b",
        ),
    ),
    ObligationKind(
        kind="first_round_count",
        claim_type="participation_count",
        label="Bidder count at first round",
        importance="important",
        family="conditional",
        triggers=_ci(
            r"first[\s-]round",
            r"first\s+phase",
        ),
    ),
    ObligationKind(
        kind="final_round_count",
        claim_type="participation_count",
        label="Bidder count at final round",
        importance="important",
        family="conditional",
        triggers=_ci(
            r"final[\s-]round",
            r"final\s+(?:phase|bids?)",
            r"best\s+and\s+final",
        ),
    ),
    ObligationKind(
        kind="final_round_bid_event",
        claim_type="event",
        label="Final round bid receipt",
        importance="important",
        family="conditional",
        triggers=_ci(
            r"final[\s-]round\s+bid",
            r"final\s+(?:bid|proposal)\s+(?:was\s+)?(?:submitted|received)",
            r"best\s+and\s+final\s+(?:offer|proposal|bid)",
        ),
    ),
    ObligationKind(
        kind="exclusivity_grant",
        claim_type="event",
        label="Exclusivity grant",
        importance="important",
        family="conditional",
        triggers=_ci(
            r"\bexclusivity\b",
            r"exclusive\s+negotiations?",
            r"granted\s+exclusivity",
        ),
    ),
    ObligationKind(
        kind="go_shop_period",
        claim_type="event",
        label="Go-shop period",
        importance="optional",
        family="conditional",
        triggers=_ci(
            r"go-?shop\s+(?:period|process)?",
            r"go-?shop\b",
        ),
    ),
    ObligationKind(
        kind="buyer_group_composition",
        claim_type="actor_relation",
        label="Buyer group composition",
        importance="important",
        family="conditional",
        triggers=_ci(
            r"buyer\s+group",
            r"\bconsortium\b",
            r"acquisition\s+vehicle",
            r"merger\s+sub(?:sidiary)?\b",
            r"investment\s+vehicle",
        ),
    ),
    ObligationKind(
        kind="rollover_holder",
        claim_type="actor_relation",
        label="Rollover holder",
        importance="important",
        family="conditional",
        triggers=_ci(
            r"\brollover\b",
            r"\broll-?over\b",
            r"\brolled?\s+(?:over|equity|shares)",
            r"retain\s+(?:equity|a\s+stake)",
            r"contribute\s+shares",
        ),
    ),
    ObligationKind(
        kind="voting_support",
        claim_type="actor_relation",
        label="Voting support agreement",
        importance="important",
        family="conditional",
        triggers=_ci(
            r"voting\s+(?:and\s+support\s+)?agreement",
            r"support\s+agreement",
            r"agreed\s+to\s+vote",
            r"vote\s+in\s+favor",
        ),
    ),
    ObligationKind(
        kind="special_committee",
        claim_type="actor_relation",
        label="Special committee membership",
        importance="optional",
        family="conditional",
        triggers=_ci(
            r"special\s+committee",
            r"transaction\s+committee",
        ),
    ),
    ObligationKind(
        kind="recusal",
        claim_type="actor_relation",
        label="Recusal from sale process",
        importance="optional",
        family="conditional",
        triggers=_ci(
            r"\brecused?\b",
            r"did\s+not\s+participate",
            r"abstained\s+from",
        ),
    ),
    ObligationKind(
        kind="financing_committed",
        claim_type="event",
        label="Financing commitment",
        importance="important",
        family="conditional",
        triggers=_ci(
            r"debt\s+commitment",
            r"equity\s+commitment",
            r"financing\s+(?:letter|commitment)",
            r"committed\s+financing",
        ),
    ),
    ObligationKind(
        kind="amendment",
        claim_type="event",
        label="Merger agreement amendment",
        importance="optional",
        family="conditional",
        triggers=_ci(
            r"amendment\s+(?:to\s+)?the\s+merger\s+agreement",
            r"amended\s+(?:and\s+restated\s+)?merger\s+agreement",
        ),
    ),
)


# Scope-driven obligations apply when the filing's process_scope is one of the
# listed scopes (e.g., tender-offer-specific obligations only fire on Schedule
# TO-T-derived filings).
SCOPE_OBLIGATIONS: tuple[ObligationKind, ...] = (
    ObligationKind(
        kind="tender_offer_prior_contacts",
        claim_type="event",
        label="Tender-offer prior contacts",
        importance="important",
        family="scope",
        scopes=("bidder_partial_schedule_to",),
    ),
)


ALL_OBLIGATION_KINDS: tuple[ObligationKind, ...] = (
    UNIVERSAL_OBLIGATIONS + CONDITIONAL_OBLIGATIONS + SCOPE_OBLIGATIONS
)


@dataclass(frozen=True)
class ApplicabilityDecision:
    """Per-region applicability outcome for a single obligation kind."""

    obligation_kind: ObligationKind
    applicability: Applicability
    reason_code: str
    basis: tuple[str, ...]


def _trigger_hits(text: str, triggers: tuple[re.Pattern[str], ...]) -> tuple[str, ...]:
    hits: list[str] = []
    for pattern in triggers:
        match = pattern.search(text)
        if match is not None:
            hits.append(match.group(0))
    return tuple(hits)


def decide_applicability(
    *,
    region_text: str,
    process_scope: str,
) -> list[ApplicabilityDecision]:
    """Return a deterministic applicability decision for every obligation kind.

    The returned list preserves the canonical order of ``ALL_OBLIGATION_KINDS``
    so identical inputs produce identical evidence-map rows.
    """

    decisions: list[ApplicabilityDecision] = []
    for kind in ALL_OBLIGATION_KINDS:
        if kind.family == "universal":
            decisions.append(
                ApplicabilityDecision(
                    obligation_kind=kind,
                    applicability="applicable",
                    reason_code="universal_sale_process",
                    basis=(),
                )
            )
        elif kind.family == "scope":
            if process_scope in kind.scopes:
                decisions.append(
                    ApplicabilityDecision(
                        obligation_kind=kind,
                        applicability="applicable",
                        reason_code=f"process_scope:{process_scope}",
                        basis=(process_scope,),
                    )
                )
            else:
                decisions.append(
                    ApplicabilityDecision(
                        obligation_kind=kind,
                        applicability="not_applicable",
                        reason_code="process_scope_mismatch",
                        basis=(process_scope,),
                    )
                )
        elif kind.family == "conditional":
            support = classify_obligation_support(kind.kind, region_text)
            if support.state == SupportState.POSITIVE:
                decisions.append(
                    ApplicabilityDecision(
                        obligation_kind=kind,
                        applicability="applicable",
                        reason_code="positive_source_support",
                        basis=support.basis,
                    )
                )
            elif support.state in {SupportState.NEGATIVE, SupportState.AMBIGUOUS}:
                decisions.append(
                    ApplicabilityDecision(
                        obligation_kind=kind,
                        applicability="not_applicable",
                        reason_code=support.reason_code,
                        basis=support.basis,
                    )
                )
            else:
                decisions.append(
                    ApplicabilityDecision(
                        obligation_kind=kind,
                        applicability="not_applicable",
                        reason_code="source_support_absent",
                        basis=(),
                    )
                )
        else:  # pragma: no cover - exhausted by Literal
            raise ValueError(f"unknown obligation family {kind.family!r}")
    return decisions


# --------------------------------------------------------------------------- #
# Count-language gate (Task 5)                                                 #
# --------------------------------------------------------------------------- #
#
# Count obligations are *applicable* only when the surrounding evidence
# actually mentions a count. Stage words like ``first round`` or
# ``best and final`` do not, on their own, justify a count obligation.
#
# This module is the single home for the gate. Other modules import from
# here rather than reimplementing the regular expressions.

_COUNT_WORDS: tuple[str, ...] = (
    "one", "two", "three", "four", "five", "six", "seven", "eight", "nine",
    "ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen",
    "seventeen", "eighteen", "nineteen", "twenty",
    "twenty-one", "twenty-two", "twenty-three", "twenty-four", "twenty-five",
    "twenty-six", "twenty-seven", "twenty-eight", "twenty-nine",
    "thirty", "thirty-five", "forty", "fifty", "sixty", "seventy",
    "eighty", "ninety", "hundred",
)

_count_word_pattern = "|".join(
    sorted((re.escape(word) for word in _COUNT_WORDS), key=len, reverse=True)
)
COUNT_WORD_OR_NUMBER_RE = re.compile(
    rf"(?:\b\d+\b|\b(?:{_count_word_pattern})\b)",
    re.IGNORECASE,
)

# Participation nouns. Restricted to *people-or-firm* nouns the filing uses to
# describe sale-process participants. Stage nouns ("round", "proposal",
# "process") are excluded so ``preliminary proposal`` does not, on its own,
# trigger a count obligation.
PARTICIPATION_NOUN_RE = re.compile(
    r"\b(?:"
    r"buyers"
    r"|bidders"
    r"|parties"
    r"|participants"
    r"|acquir(?:ors|ers)"
    r"|sponsors"
    r"|firms"
    r"|companies"
    r"|investors"
    r"|counterparties"
    r"|offerors"
    r"|suitors"
    r")\b",
    re.IGNORECASE,
)


def has_count_language(text: str) -> bool:
    """Return ``True`` when ``text`` contains both count cues and a participation noun.

    Count obligations are applicable only when the surrounding evidence
    mentions a count. Stage words like ``first round`` or ``best and final``
    do not, on their own, justify a count obligation.
    """

    if not text:
        return False
    return bool(
        COUNT_WORD_OR_NUMBER_RE.search(text)
        and PARTICIPATION_NOUN_RE.search(text)
    )
