"""Actor-cycle scoped bidder projection."""

from __future__ import annotations

from typing import Any

import duckdb

from sec_graph.reconcile.pipeline import is_generic_bidder_label
from sec_graph.schema import make_id


def build_bidder_rows(
    conn: duckdb.DuckDBPyConnection,
    *,
    run_id: str,
    projection_name: str = "bidder_cycle_baseline_v1",
) -> list[dict[str, Any]]:
    conn.execute("DELETE FROM bidder_rows WHERE run_id = ?", [run_id])
    conn.execute(
        "DELETE FROM projection_judgments WHERE projection_unit_id IN (SELECT projection_unit_id FROM projection_units WHERE run_id = ?)",
        [run_id],
    )
    conn.execute("DELETE FROM projection_units WHERE run_id = ?", [run_id])
    rows: list[dict[str, Any]] = []
    units = _projection_candidates(conn)
    for sequence, unit in enumerate(units, start=1):
        projection_unit_id = make_id(unit["deal_slug"], "projectionunit", sequence)
        projection_judgment_id = make_id(unit["deal_slug"], "projectionjudgment", sequence)
        bidder_row_id = make_id(unit["deal_slug"], "bidderrow", sequence)
        conn.execute(
            "INSERT INTO projection_units VALUES (?, ?, ?, ?, ?, ?)",
            [
                projection_unit_id,
                run_id,
                projection_name,
                unit["deal_id"],
                unit["cycle_id"],
                unit["actor_id"],
            ],
        )
        included = bool(unit["has_bid"])
        conn.execute(
            "INSERT INTO projection_judgments VALUES (?, ?, ?, ?, ?, ?)",
            [
                projection_judgment_id,
                run_id,
                projection_unit_id,
                "actor_cycle_has_source_backed_bid",
                included,
                "Projection unit is actor-cycle scoped and included only when source-backed bid evidence exists in that cycle.",
            ],
        )
        if not included:
            continue
        row = {
            "bidder_row_id": bidder_row_id,
            "run_id": run_id,
            "projection_unit_id": projection_unit_id,
            "deal_slug": unit["deal_slug"],
            "cycle_id": unit["cycle_id"],
            "actor_id": unit["actor_id"],
            "actor_label": unit["actor_label"],
            "b_i": unit["b_i"],
            "b_i_lower": unit["b_i_lower"],
            "b_i_upper": unit["b_i_upper"],
            "b_f": unit["b_f"],
            "admitted": True,
        }
        conn.execute(
            "INSERT INTO bidder_rows VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            list(row.values()),
        )
        rows.append(_export_row(row))
    return rows


def bidder_rows(conn: duckdb.DuckDBPyConnection, *, projection_name: str = "bidder_cycle_baseline_v1") -> list[dict[str, Any]]:
    del projection_name
    rows = conn.execute(
        """
        SELECT bidder_row_id, run_id, projection_unit_id, deal_slug, cycle_id,
               actor_id, actor_label, b_i, b_i_lower, b_i_upper, b_f, admitted
        FROM bidder_rows
        ORDER BY deal_slug, cycle_id, actor_id
        """
    ).fetchall()
    columns = ["bidder_row_id", "run_id", "projection_unit_id", "deal_slug", "cycle_id", "actor_id", "actor_label", "b_i", "b_i_lower", "b_i_upper", "b_f", "admitted"]
    return [_export_row(dict(zip(columns, row, strict=True))) for row in rows]


def _projection_candidates(conn: duckdb.DuckDBPyConnection) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT deals.deal_slug, deals.deal_id, events.cycle_id, actors.actor_id,
               actors.actor_label,
               min(events.bid_value) AS b_i,
               min(events.bid_value_lower) AS b_i_lower,
               max(events.bid_value_upper) AS b_i_upper,
               max(events.bid_value) AS b_f,
               count(*) > 0 AS has_bid
        FROM events
        JOIN event_actor_links USING (event_id)
        JOIN actors USING (actor_id)
        JOIN deals ON deals.deal_id = events.deal_id
        WHERE events.event_type = 'bid'
          AND event_actor_links.role IN ('bid_submitter', 'offeror')
          AND actors.observability IN ('named', 'anonymous_handle')
          AND actors.actor_kind IN ('organization', 'person', 'group', 'vehicle')
        GROUP BY deals.deal_slug, deals.deal_id, events.cycle_id, actors.actor_id, actors.actor_label
        ORDER BY deals.deal_slug, events.cycle_id, actors.actor_id
        """
    ).fetchall()
    columns = ["deal_slug", "deal_id", "cycle_id", "actor_id", "actor_label", "b_i", "b_i_lower", "b_i_upper", "b_f", "has_bid"]
    candidates = [dict(zip(columns, row, strict=True)) for row in rows]
    return [row for row in candidates if not is_generic_bidder_label(str(row["actor_label"]))]


def _export_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "bidder_row_id": row["bidder_row_id"],
        "run_id": row["run_id"],
        "projection_unit_id": row["projection_unit_id"],
        "deal_slug": row["deal_slug"],
        "cycle_id": row["cycle_id"],
        "actor_id": row["actor_id"],
        "actor_label": row["actor_label"],
        "bI": row["b_i"],
        "bI_lo": row["b_i_lower"],
        "bI_hi": row["b_i_upper"],
        "bF": row["b_f"],
        "admitted": row["admitted"],
    }
