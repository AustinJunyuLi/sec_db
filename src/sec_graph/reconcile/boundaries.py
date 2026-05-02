"""Formal-boundary selection."""

from __future__ import annotations

from sec_graph.reconcile.cycles import CycleWindow

_KEYWORDS = (
    "proceed to the final round",
    "request for submission of offers",
    "submitted proposals expressing their continued interest",
    "draft of the merger agreement was distributed",
    "intended to enter into a merger agreement",
    "exclusivity",
    "best and final",
)


def choose_boundary(dated_rows: list[object], cycle: CycleWindow) -> object:
    cycle_rows = [
        row
        for row in dated_rows
        if cycle.start_date <= row.event_date <= cycle.end_date
    ]
    for keyword in _KEYWORDS:
        for row in cycle_rows:
            context = f"{row.raw_value}\n{row.paragraph_text}".casefold()
            if keyword in context:
                return row
    return cycle_rows[-1] if cycle_rows else dated_rows[-1]
