"""Bidder-cycle row projection."""

from __future__ import annotations

import math
from typing import Any

import duckdb

_CONF_RANK = {"low": 0, "medium": 1, "high": 2}
_CONF_BY_RANK = {value: key for key, value in _CONF_RANK.items()}


def _judgments(conn: duckdb.DuckDBPyConnection) -> list[dict[str, Any]]:
    columns = [
        "judgment_id",
        "run_id",
        "deal_id",
        "cycle_id",
        "actor_id",
        "event_id",
        "judgment_type",
        "judgment_value",
        "confidence",
        "alternative_value",
        "supersedes_judgment_id",
        "evidence_ids",
    ]
    return [
        dict(zip(columns, row, strict=True))
        for row in conn.execute("SELECT * FROM judgments ORDER BY judgment_id").fetchall()
    ]


def _first_judgment(judgments: list[dict[str, Any]], judgment_type: str, cycle_id: str, actor_id: str | None = None) -> dict[str, Any] | None:
    for judgment in judgments:
        if judgment["judgment_type"] != judgment_type or judgment["cycle_id"] != cycle_id:
            continue
        if actor_id is not None and judgment["actor_id"] != actor_id:
            continue
        if actor_id is None and judgment["actor_id"] is not None:
            continue
        return judgment
    return None


def _confidence_min(values: list[str | None]) -> str | None:
    present = [value for value in values if value is not None]
    if not present:
        return None
    return _CONF_BY_RANK[min(_CONF_RANK[value] for value in present)]


def _w_logwidth(lower: float | None, upper: float | None) -> float | None:
    if lower is None or upper is None or lower <= 0 or upper <= 0:
        return None
    return math.log(upper / lower)


def _bid_events(conn: duckdb.DuckDBPyConnection, actor_id: str, cycle_id: str) -> list[dict[str, Any]]:
    columns = [
        "event_id",
        "event_date",
        "bid_value",
        "bid_value_lower",
        "bid_value_upper",
        "bid_value_unit",
        "consideration_type",
    ]
    rows = conn.execute(
        """
        SELECT events.event_id, events.event_date, events.bid_value, events.bid_value_lower,
               events.bid_value_upper, events.bid_value_unit, events.consideration_type
        FROM events
        JOIN event_actor_links USING (event_id)
        WHERE event_actor_links.actor_id = ?
          AND events.cycle_id = ?
          AND events.event_type = 'bid'
        ORDER BY events.event_date, events.event_id
        """,
        [actor_id, cycle_id],
    ).fetchall()
    return [dict(zip(columns, row, strict=True)) for row in rows]


def bidder_rows(conn: duckdb.DuckDBPyConnection) -> list[dict[str, Any]]:
    judgments = _judgments(conn)
    rows: list[dict[str, Any]] = []
    cycles = conn.execute(
        """
        SELECT process_cycles.cycle_id, process_cycles.deal_id, filings.deal_slug
        FROM process_cycles
        JOIN deals USING (deal_id)
        JOIN filings ON filings.deal_slug = deals.deal_slug
        ORDER BY process_cycles.cycle_id
        """
    ).fetchall()
    for cycle_id, deal_id, deal_slug in cycles:
        boundary = _first_judgment(judgments, "formal_boundary", cycle_id)
        boundary_event_id = boundary["judgment_value"] if boundary is not None else None
        boundary_date = None
        if boundary_event_id is not None:
            result = conn.execute("SELECT event_date FROM events WHERE event_id = ?", [boundary_event_id]).fetchone()
            boundary_date = result[0] if result is not None else None
        visibility = _first_judgment(judgments, "cycle_visibility", cycle_id)
        actors = conn.execute(
            """
            SELECT DISTINCT actors.actor_id, actors.actor_label, actors.bidder_subtype
            FROM actors
            LEFT JOIN event_actor_links
              ON event_actor_links.actor_id = actors.actor_id
            LEFT JOIN events
              ON events.event_id = event_actor_links.event_id
             AND events.cycle_id = ?
            LEFT JOIN judgments
              ON judgments.actor_id = actors.actor_id
             AND judgments.cycle_id = ?
            WHERE actors.deal_id = ?
              AND actors.actor_type = 'bidder'
              AND (events.event_id IS NOT NULL OR judgments.judgment_id IS NOT NULL)
            ORDER BY actors.actor_id
            """,
            [cycle_id, cycle_id, deal_id],
        ).fetchall()
        for actor_id, actor_label, bidder_subtype in actors:
            events = _bid_events(conn, actor_id, cycle_id)
            pre = [event for event in events if boundary_date is not None and event["event_date"] < boundary_date]
            post = [event for event in events if boundary_date is None or event["event_date"] >= boundary_date]
            b_i_event = pre[-1] if pre else None
            b_f_event = max(post, key=lambda event: event["bid_value"] or float("-inf")) if post else None
            admission = _first_judgment(judgments, "admission", cycle_id, actor_id)
            dropout = _first_judgment(judgments, "dropout_mechanism", cycle_id, actor_id)
            admitted = (admission["judgment_value"] == "true") if admission is not None else b_f_event is not None
            unit_source = b_f_event or b_i_event or {}
            row = {
                "deal_slug": deal_slug,
                "cycle_id": cycle_id,
                "actor_id": actor_id,
                "actor_label": actor_label,
                "bI": b_i_event["bid_value"] if b_i_event else None,
                "bI_lo": b_i_event["bid_value_lower"] if b_i_event else None,
                "bI_hi": b_i_event["bid_value_upper"] if b_i_event else None,
                "w_logwidth": _w_logwidth(
                    b_i_event["bid_value_lower"] if b_i_event else None,
                    b_i_event["bid_value_upper"] if b_i_event else None,
                ),
                "bF": b_f_event["bid_value"] if b_f_event else None,
                "admitted": admitted,
                "T": 0 if bidder_subtype == "financial" else 1 if bidder_subtype == "strategic" else None,
                "bid_value_unit": unit_source.get("bid_value_unit"),
                "consideration_type": unit_source.get("consideration_type"),
                "boundary_event_id": boundary_event_id,
                "boundary_quality": boundary["confidence"] if boundary is not None else None,
                "formal_boundary": boundary["judgment_value"] if boundary is not None else None,
                "dropout_mechanism": dropout["judgment_value"] if dropout is not None else None,
                "dropout_has_alternative": bool(dropout and dropout["alternative_value"]),
                "cycle_visibility": visibility["judgment_value"] if visibility is not None else None,
                "scope_validity": None,
                "valuation_comparability": None,
                "confidence_min": _confidence_min(
                    [
                        boundary["confidence"] if boundary is not None else None,
                        visibility["confidence"] if visibility is not None else None,
                        dropout["confidence"] if dropout is not None else None,
                    ]
                ),
            }
            rows.append(row)
    return rows
