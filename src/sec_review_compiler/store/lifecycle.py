"""Lifecycle policy: state machine, verdict aggregation, coverage gate.

Two invariants matter most here:

1. **No latest-verdict-wins.** Aggregation reads *all* verdicts on an
   attempt and applies a deterministic policy. The most recent verdict
   never overrides earlier conflicting ones implicitly.
2. **`failed_to_check` blocks publication.** A required coverage check in
   that state means the system did not inspect enough source material to
   judge — no canonical row that depends on the category may be marked
   trusted.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Sequence, TYPE_CHECKING

from .schema import LIFECYCLE_STATES, TRANSITIONS, VERDICT_TYPES

if TYPE_CHECKING:  # pragma: no cover
    from .repository import CoverageCheck, Verdict


AGGREGATION_POLICY_VERSION = "v1"


# ---------------------------------------------------------------- state machine

class IllegalTransitionError(ValueError):
    """Raised when a lifecycle transition is not in the policy."""


def validate_transition(*, from_status: str, to_status: str) -> None:
    if from_status not in LIFECYCLE_STATES:
        raise IllegalTransitionError(f"unknown from_status: {from_status!r}")
    if to_status not in LIFECYCLE_STATES:
        raise IllegalTransitionError(f"unknown to_status: {to_status!r}")
    allowed = TRANSITIONS[from_status]
    if to_status not in allowed:
        raise IllegalTransitionError(
            f"transition {from_status} -> {to_status} not allowed; "
            f"allowed targets are {sorted(allowed)}"
        )


# ---------------------------------------------------------------- aggregation

@dataclass(frozen=True, slots=True)
class AggregatedVerdict:
    outcome: str  # see _AGGREGATE_OUTCOMES
    rationale: str
    input_verdict_ids: tuple[str, ...]
    counts: tuple[tuple[str, int], ...]


_AGGREGATE_OUTCOMES = (
    "no_verdicts",
    "verifier_stage_failed",
    "rejected",
    "escalated",
    "correction_required",
    "confirmed",
)


def aggregate_verdicts(verdicts: "Sequence[Verdict]") -> AggregatedVerdict:
    """Apply the aggregation policy across *all* verdicts on an attempt.

    The function is pure: same input always produces the same outcome,
    irrespective of arrival order. That means a "latest verdict wins"
    rule is structurally impossible — the policy ignores verdict order
    entirely.
    """
    counts_counter: Counter[str] = Counter(v.verdict for v in verdicts)
    counts = tuple(sorted(counts_counter.items()))
    input_ids = tuple(v.verdict_id for v in verdicts)

    if not verdicts:
        return AggregatedVerdict(
            outcome="no_verdicts",
            rationale="attempt has no verifier verdicts",
            input_verdict_ids=input_ids,
            counts=counts,
        )

    confirms = counts_counter.get("confirm", 0)
    rejects = counts_counter.get("reject", 0)
    partials = counts_counter.get("partial", 0)
    ambiguous = counts_counter.get("ambiguous", 0)
    malformed = counts_counter.get("malformed", 0)

    if malformed >= 2:
        return AggregatedVerdict(
            outcome="verifier_stage_failed",
            rationale=f"{malformed} malformed verdicts indicate a verifier stage failure",
            input_verdict_ids=input_ids,
            counts=counts,
        )

    if rejects and confirms:
        return AggregatedVerdict(
            outcome="escalated",
            rationale=(
                f"disagreement: {confirms} confirm vs {rejects} reject — "
                "policy requires independent resolution, not recency"
            ),
            input_verdict_ids=input_ids,
            counts=counts,
        )

    if rejects:
        return AggregatedVerdict(
            outcome="rejected",
            rationale=f"{rejects} reject verdict(s) and no confirming counterparty",
            input_verdict_ids=input_ids,
            counts=counts,
        )

    if partials:
        return AggregatedVerdict(
            outcome="correction_required",
            rationale=f"{partials} partial verdict(s) — emit corrected attempt",
            input_verdict_ids=input_ids,
            counts=counts,
        )

    if confirms and not ambiguous:
        return AggregatedVerdict(
            outcome="confirmed",
            rationale=f"{confirms} confirm verdict(s) and no challenge",
            input_verdict_ids=input_ids,
            counts=counts,
        )

    # confirms with ambiguous, or only ambiguous
    if confirms and ambiguous:
        return AggregatedVerdict(
            outcome="escalated",
            rationale=(
                f"{confirms} confirm but {ambiguous} ambiguous — independent "
                "resolution required"
            ),
            input_verdict_ids=input_ids,
            counts=counts,
        )

    return AggregatedVerdict(
        outcome="escalated",
        rationale="no confirming verdict against ambiguous-only response",
        input_verdict_ids=input_ids,
        counts=counts,
    )


# ---------------------------------------------------------------- coverage gate

@dataclass(frozen=True, slots=True)
class PublicationDecision:
    can_publish_trusted: bool
    blocking_categories: tuple[str, ...]
    rationale: str


def can_publish_trusted(
    coverage_checks: "Sequence[CoverageCheck]",
) -> PublicationDecision:
    """Refuse trusted publication when any required coverage is `failed_to_check`."""
    blocking: list[str] = []
    for check in coverage_checks:
        if not check.required:
            continue
        if check.check_state == "failed_to_check":
            blocking.append(
                check.subcategory
                if check.subcategory
                else check.category
            )
    if blocking:
        return PublicationDecision(
            can_publish_trusted=False,
            blocking_categories=tuple(sorted(set(blocking))),
            rationale=(
                "required coverage in failed_to_check blocks trusted publication: "
                + ", ".join(sorted(set(blocking)))
            ),
        )
    return PublicationDecision(
        can_publish_trusted=True,
        blocking_categories=(),
        rationale="all required coverage checks completed",
    )


# Sanity check: ensure verdict types and lifecycle states stay aligned.
assert set(VERDICT_TYPES) == {"confirm", "partial", "reject", "ambiguous", "malformed"}
assert set(LIFECYCLE_STATES).issuperset(
    {
        "proposed",
        "binding_failed",
        "bound",
        "verified_confirmed",
        "verified_partial",
        "verified_rejected",
        "escalated",
        "consistent",
        "accepted",
        "superseded",
    }
)
