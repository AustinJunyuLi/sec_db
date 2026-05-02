"""Bidder-cycle row projection.

Projection eligibility (`admitted`) comes ONLY from the latest non-superseded
`projection_eligibility` judgment for the requested projection (default
`bidder_cycle_baseline_v1`). A post-boundary bid is NOT enough to imply
admission. Without a current `included=True` judgment, no row is emitted for
the actor — even if the actor submitted a bid that lands at or after the
cycle boundary.

This is the binding contract from `docs/spec.md` §3.7
"Projection-construction rules" and §18.1 "Treating projection code as
canonical truth".
"""

from __future__ import annotations

import math
from typing import Any

import duckdb


def _latest_projection_judgments(conn: duckdb.DuckDBPyConnection, projection_name: str) -> dict[str, dict[str, Any]]:
    columns = [
        "judgment_id",
        "actor_id",
        "included",
        "rule_id",
        "supersedes_judgment_id",
        "created_at",
    ]
    rows = [
        dict(zip(columns, row, strict=True))
        for row in conn.execute(
            """
            SELECT judgment_id, actor_id, included, rule_id, supersedes_judgment_id, created_at
            FROM judgments
            WHERE judgment_kind = 'projection_eligibility'
              AND projection_name = ?
            ORDER BY created_at, judgment_id
            """,
            [projection_name],
        ).fetchall()
    ]
    superseded = {row["supersedes_judgment_id"] for row in rows if row["supersedes_judgment_id"] is not None}
    return {row["actor_id"]: row for row in rows if row["judgment_id"] not in superseded}


def _w_logwidth(lower: float | None, upper: float | None) -> float | None:
    if lower is None or upper is None or lower <= 0 or upper <= 0:
        return None
    return math.log(upper / lower)


def _boundary_event(conn: duckdb.DuckDBPyConnection, cycle_id: str) -> dict[str, Any] | None:
    columns = ["event_id", "event_date", "event_subtype"]
    row = conn.execute(
        """
        SELECT event_id, event_date, event_subtype
        FROM events
        WHERE cycle_id = ?
          AND event_subtype IN ('advancement_admitted', 'exclusivity_grant')
        ORDER BY event_date NULLS LAST, event_id
        LIMIT 1
        """,
        [cycle_id],
    ).fetchone()
    if row is None:
        return None
    return dict(zip(columns, row, strict=True))


def _bid_events(conn: duckdb.DuckDBPyConnection, actor_id: str, cycle_id: str) -> list[dict[str, Any]]:
    columns = [
        "event_id",
        "event_date",
        "bid_value",
        "bid_value_lower",
        "bid_value_upper",
        "bid_value_unit",
        "consideration_type",
        "event_subtype",
    ]
    rows = conn.execute(
        """
        SELECT events.event_id, events.event_date, events.bid_value, events.bid_value_lower,
               events.bid_value_upper, events.bid_value_unit, events.consideration_type,
               events.event_subtype
        FROM events
        JOIN event_actor_links USING (event_id)
        WHERE event_actor_links.actor_id = ?
          AND events.cycle_id = ?
          AND events.event_type = 'bid'
          AND event_actor_links.role IN ('bid_submitter', 'offeror')
        ORDER BY events.event_date, events.event_id
        """,
        [actor_id, cycle_id],
    ).fetchall()
    return [dict(zip(columns, row, strict=True)) for row in rows]


def _actor_t_value(actor_kind: str, has_strategic_member: bool | None) -> int | None:
    if actor_kind == "group" and has_strategic_member is not None:
        return 1 if has_strategic_member else 0
    return None


def bidder_rows(conn: duckdb.DuckDBPyConnection, *, projection_name: str = "bidder_cycle_baseline_v1") -> list[dict[str, Any]]:
    judgments = _latest_projection_judgments(conn, projection_name)
    rows: list[dict[str, Any]] = []
    cycles = conn.execute(
        """
        SELECT process_cycles.cycle_id, process_cycles.deal_id, deals.deal_slug
        FROM process_cycles
        JOIN deals USING (deal_id)
        ORDER BY process_cycles.cycle_id
        """
    ).fetchall()
    for cycle_id, deal_id, deal_slug in cycles:
        boundary = _boundary_event(conn, cycle_id)
        boundary_date = boundary["event_date"] if boundary is not None else None
        actors = conn.execute(
            """
            SELECT actor_id, actor_label, actor_kind, observability, has_strategic_member
            FROM actors
            WHERE deal_id = ?
            ORDER BY actor_id
            """,
            [deal_id],
        ).fetchall()
        for actor_id, actor_label, actor_kind, observability, has_strategic_member in actors:
            judgment = judgments.get(actor_id)
            if judgment is None or judgment["included"] is not True or observability == "count_only":
                continue
            events = _bid_events(conn, actor_id, cycle_id)
            if not events:
                continue
            pre = [event for event in events if boundary_date is not None and event["event_date"] < boundary_date]
            post = [event for event in events if boundary_date is None or event["event_date"] >= boundary_date]
            b_i_event = pre[-1] if pre else None
            b_f_event = max(post, key=lambda event: event["bid_value"] or float("-inf")) if post else None
            unit_source = b_f_event or b_i_event or {}
            rows.append(
                {
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
                    "admitted": True,
                    "T": _actor_t_value(actor_kind, has_strategic_member),
                    "bid_value_unit": unit_source.get("bid_value_unit"),
                    "consideration_type": unit_source.get("consideration_type"),
                    "boundary_event_id": boundary["event_id"] if boundary is not None else None,
                    "boundary_quality": None,
                    "formal_boundary": boundary["event_subtype"] if boundary is not None else None,
                    "dropout_mechanism": None,
                    "dropout_has_alternative": False,
                    "cycle_visibility": None,
                    "scope_validity": "target_full_proxy",
                    "valuation_comparability": None,
                    "confidence_min": None,
                }
            )
    return rows
