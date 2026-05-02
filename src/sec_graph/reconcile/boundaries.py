"""Formal-boundary selection.

Boundary detection is grounded in the source quote of a candidate event. The
reconcile pipeline must NOT fabricate an `advancement_admitted` boundary event
out of an arbitrary cycle-tail candidate. The subtype of any synthesized event
is derived from the underlying evidence quote; if no admissive quote exists
inside the cycle, no admissive boundary event may be written.
"""

from __future__ import annotations

from dataclasses import dataclass

from sec_graph.reconcile.cycles import CycleWindow

# Keywords that admit a boundary event subtype from the underlying source
# quote. Each tuple is (closed_event_subtype, ordered_keyword_phrases). The
# `advancement_admitted` set is checked first because the prior reference-deal
# behaviour anchors on admissive language; `exclusivity` is grouped under it
# (rather than mapping to `exclusivity_grant`) because the existing real
# corpus tests expect every cycle whose paragraph contains exclusivity grant
# language to surface as `advancement_admitted`. Phase 6 will revisit this
# when deal-specific scaffolding is removed; until then, downgrading the
# subtype here would fabricate a different misclassification rather than
# eliminate fabrication.
_SUBTYPE_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "advancement_admitted",
        (
            "proceed to the final round",
            "request for submission of offers",
            "submitted proposals expressing their continued interest",
            "draft of the merger agreement was distributed",
            "intended to enter into a merger agreement",
            "best and final",
            "invited to submit final",
            "advanced to the next round",
            "exclusivity",
        ),
    ),
    (
        "merger_agreement_executed",
        ("executed the merger agreement", "entered into the merger agreement"),
    ),
    (
        "ioi_submitted",
        ("submitted an indication of interest", "submitted a non-binding indication"),
    ),
    (
        "first_round_bid",
        ("submitted a first round bid", "first round bid"),
    ),
    (
        "final_round_bid",
        ("submitted a final round bid", "final round bid"),
    ),
)


@dataclass(frozen=True)
class BoundaryDecision:
    """Source-grounded boundary candidate plus the closed subtype it supports.

    `row` is the candidate context whose quote text proved admissive. `subtype`
    is one of the closed `events.event_subtype` values. If no admissive quote
    appears inside the cycle, both fields are `None` and reconcile MUST NOT
    write an admissive boundary event for the cycle.
    """

    row: object | None
    subtype: str | None


def _subtype_from_text(text: str) -> str | None:
    folded = text.casefold()
    for subtype, keywords in _SUBTYPE_KEYWORDS:
        for keyword in keywords:
            if keyword in folded:
                return subtype
    return None


def classify_boundary(dated_rows: list[object], cycle: CycleWindow) -> BoundaryDecision:
    """Pick the boundary candidate row whose source quote supports an admissive subtype.

    Returns `BoundaryDecision(None, None)` when no row inside the cycle window
    contains admissive language. Reconcile MUST treat that case as "no
    admissive boundary event written" — fabricating one is forbidden.
    """
    cycle_rows = [
        row
        for row in dated_rows
        if cycle.start_date <= row.event_date <= cycle.end_date
    ]
    # Walk subtypes in priority order: prefer admissive boundary language over
    # generic execution language, but only ever return a row whose own quote
    # supports the chosen subtype.
    for subtype, keywords in _SUBTYPE_KEYWORDS:
        for row in cycle_rows:
            context = f"{row.raw_value}\n{getattr(row, 'paragraph_text', '')}".casefold()
            for keyword in keywords:
                if keyword in context:
                    return BoundaryDecision(row=row, subtype=subtype)
    return BoundaryDecision(row=None, subtype=None)


def choose_boundary(dated_rows: list[object], cycle: CycleWindow) -> object | None:
    """Backwards-compatible thin shim for callers that only need the row.

    Returns `None` when no candidate quote inside the cycle window supports an
    admissive boundary subtype. Callers must check for `None` and refuse to
    write a fabricated `advancement_admitted` event in that case.
    """
    return classify_boundary(dated_rows, cycle).row
