"""Actor-cycle scoped bidder projection."""

from __future__ import annotations

import datetime as dt
import json
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
    conn.execute(
        "DELETE FROM review_rows WHERE run_id = ? AND review_type = 'projection'",
        [run_id],
    )
    rows: list[dict[str, Any]] = []
    units = _projection_candidates(conn, run_id=run_id)
    accepted_judgments = _accepted_judgments_by_target(conn, run_id=run_id)
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
        unit_judgments = _judgments_for_unit(accepted_judgments, unit["event_ids"])
        fate_values = {
            value
            for values in unit_judgments.values()
            for key, value in values
            if key == "projected_fate"
        }
        included = bool(unit["has_bid"]) and "observed_drop" not in fate_values
        conn.execute(
            "INSERT INTO projection_judgments VALUES (?, ?, ?, ?, ?, ?)",
            [
                projection_judgment_id,
                run_id,
                projection_unit_id,
                "actor_cycle_accepted_judgments",
                included,
                "Projection unit is actor-cycle scoped and uses accepted Python judgments for projection-affecting fate.",
            ],
        )
        if not included:
            continue

        events_missing_formality = _events_missing_formality(
            conn, run_id=run_id, event_ids=unit["event_ids"]
        )
        if events_missing_formality:
            for event_id in events_missing_formality:
                _insert_review_row(
                    conn,
                    run_id=run_id,
                    deal_slug=unit["deal_slug"],
                    review_type="projection",
                    severity="review",
                    reason_code="missing_formality_judgment",
                    message=(
                        f"Bidder projection cannot include actor {unit['actor_id']!r} "
                        f"because event {event_id!r} lacks an accepted bid_formality "
                        "judgment."
                    ),
                    review_question=(
                        "Does the source support this event's formality classification "
                        "before the bidder row can be projected?"
                    ),
                    source_table="projection_units",
                    source_id=projection_unit_id,
                    canonical_table="events",
                    canonical_id=event_id,
                )
            continue

        admitted = _admitted_from_judgments(unit_judgments)
        if not admitted:
            _insert_review_row(
                conn,
                run_id=run_id,
                deal_slug=unit["deal_slug"],
                review_type="projection",
                severity="review",
                reason_code="admitted_substrate_missing",
                message=(
                    f"Bidder projection cannot mark actor {unit['actor_id']!r} as "
                    "admitted because no accepted bid_formality judgment supports it."
                ),
                review_question=(
                    "Should this bidder be marked admitted given the available "
                    "judgment substrate?"
                ),
                source_table="projection_units",
                source_id=projection_unit_id,
            )
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
            "admitted": admitted,
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


def _projection_candidates(conn: duckdb.DuckDBPyConnection, *, run_id: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT deals.deal_slug, deals.deal_id, events.cycle_id, actors.actor_id,
               actors.actor_label,
               min(events.bid_value) AS b_i,
               min(events.bid_value_lower) AS b_i_lower,
               max(events.bid_value_upper) AS b_i_upper,
               max(events.bid_value) AS b_f,
               count(*) > 0 AS has_bid,
               to_json(list(events.event_id ORDER BY events.event_id)) AS event_ids_json
        FROM events
        JOIN event_actor_links USING (event_id)
        JOIN actors USING (actor_id)
        JOIN deals ON deals.deal_id = events.deal_id
        WHERE events.run_id = ?
          AND events.event_type = 'bid'
          AND event_actor_links.role IN ('bid_submitter', 'offeror')
          AND actors.observability IN ('named', 'anonymous_handle')
          AND actors.actor_kind IN ('organization', 'person', 'group', 'vehicle')
        GROUP BY deals.deal_slug, deals.deal_id, events.cycle_id, actors.actor_id, actors.actor_label
        ORDER BY deals.deal_slug, events.cycle_id, actors.actor_id
        """,
        [run_id],
    ).fetchall()
    columns = ["deal_slug", "deal_id", "cycle_id", "actor_id", "actor_label", "b_i", "b_i_lower", "b_i_upper", "b_f", "has_bid", "event_ids_json"]
    candidates = [dict(zip(columns, row, strict=True)) for row in rows]
    for row in candidates:
        row["event_ids"] = json.loads(row.pop("event_ids_json"))
    return [row for row in candidates if not is_generic_bidder_label(str(row["actor_label"]))]


def _accepted_judgments_by_target(
    conn: duckdb.DuckDBPyConnection,
    *,
    run_id: str,
) -> dict[str, list[tuple[str, str | None]]]:
    rows = conn.execute(
        """
        SELECT target_id, judgment_key, judgment_value
        FROM judgments
        WHERE run_id = ?
          AND current = true
          AND judgment_status = 'accepted'
        ORDER BY target_id, judgment_key, judgment_value
        """,
        [run_id],
    ).fetchall()
    out: dict[str, list[tuple[str, str | None]]] = {}
    for target_id, judgment_key, judgment_value in rows:
        out.setdefault(target_id, []).append((judgment_key, judgment_value))
    return out


def _judgments_for_unit(
    accepted_judgments: dict[str, list[tuple[str, str | None]]],
    event_ids: list[str],
) -> dict[str, list[tuple[str, str | None]]]:
    return {
        event_id: accepted_judgments[event_id]
        for event_id in event_ids
        if event_id in accepted_judgments
    }


def _events_missing_formality(
    conn: duckdb.DuckDBPyConnection,
    *,
    run_id: str,
    event_ids: list[str],
) -> list[str]:
    """Return event_ids in ``event_ids`` that do not have an accepted
    bid_formality judgment but DO have an open formality review row.
    """
    if not event_ids:
        return []
    review_rows = conn.execute(
        """
        SELECT source_id
        FROM review_rows
        WHERE run_id = ?
          AND review_type = 'judgment'
          AND reason_code = 'formality_substrate_missing'
          AND review_status = 'open'
          AND source_table = 'events'
        """,
        [run_id],
    ).fetchall()
    flagged = {row[0] for row in review_rows}
    return [event_id for event_id in event_ids if event_id in flagged]


def _admitted_from_judgments(
    unit_judgments: dict[str, list[tuple[str, str | None]]],
) -> bool:
    """Return True iff the unit has at least one accepted bid_formality
    judgment among its events.
    """
    for values in unit_judgments.values():
        for key, _value in values:
            if key == "bid_formality":
                return True
    return False


def _insert_review_row(
    conn: duckdb.DuckDBPyConnection,
    *,
    run_id: str,
    deal_slug: str,
    review_type: str,
    severity: str,
    reason_code: str,
    message: str,
    review_question: str,
    source_table: str,
    source_id: str,
    canonical_table: str | None = None,
    canonical_id: str | None = None,
) -> None:
    sequence = _next_review_row_sequence(conn, deal_slug)
    conn.execute(
        "INSERT INTO review_rows VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            make_id(deal_slug, "reviewrow", sequence),
            run_id,
            deal_slug,
            "open",
            review_type,
            source_table,
            source_id,
            severity,
            reason_code,
            message,
            review_question,
            None,
            None,
            None,
            canonical_table,
            canonical_id,
            None,
            None,
            None,
            None,
            _now_iso(),
        ],
    )


def _next_review_row_sequence(conn: duckdb.DuckDBPyConnection, deal_slug: str) -> int:
    prefix = f"{deal_slug}_reviewrow_"
    rows = conn.execute(
        "SELECT review_row_id FROM review_rows WHERE review_row_id LIKE ?",
        [f"{prefix}%"],
    ).fetchall()
    if not rows:
        return 1
    return max(int(row[0].rsplit("_", maxsplit=1)[1]) for row in rows) + 1


def _now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


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
