"""Process-cycle assignment from dated candidates."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass


@dataclass(frozen=True)
class CycleWindow:
    sequence: int
    start_date: dt.date
    end_date: dt.date
    first_char: int
    last_char: int
    evidence_ids: list[str]


def build_cycle_windows(dated_rows: list[object], max_gap_days: int = 120) -> list[CycleWindow]:
    if not dated_rows:
        return []
    sorted_rows = sorted(dated_rows, key=lambda row: (row.event_date, row.char_start, row.candidate_id))
    groups: list[list[object]] = []
    current: list[object] = []
    previous_date: dt.date | None = None
    for row in sorted_rows:
        if previous_date is not None and (row.event_date - previous_date).days > max_gap_days:
            groups.append(current)
            current = []
        current.append(row)
        previous_date = row.event_date
    if current:
        groups.append(current)
    return [
        CycleWindow(
            sequence=index,
            start_date=group[0].event_date,
            end_date=group[-1].event_date,
            first_char=min(row.char_start for row in group),
            last_char=max(row.char_end for row in group),
            evidence_ids=[group[0].evidence_id, group[-1].evidence_id],
        )
        for index, group in enumerate(groups, start=1)
    ]


def cycle_for(date_value: dt.date | None, char_start: int, cycles: list[CycleWindow]) -> CycleWindow:
    if not cycles:
        raise ValueError("cannot assign candidate without at least one cycle")
    if date_value is not None:
        for cycle in cycles:
            if cycle.start_date <= date_value <= cycle.end_date:
                return cycle
        return min(cycles, key=lambda cycle: abs((cycle.start_date - date_value).days))
    for cycle in cycles:
        if cycle.first_char <= char_start <= cycle.last_char:
            return cycle
    return min(cycles, key=lambda cycle: abs(cycle.first_char - char_start))
