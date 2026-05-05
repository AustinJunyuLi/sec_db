"""Derive research judgments from supported canonical facts."""

from __future__ import annotations

import json

import duckdb

from sec_graph.schema import make_id


def derive_judgments(conn: duckdb.DuckDBPyConnection, *, run_id: str) -> None:
    _clear_current(conn, run_id)
    _derive_bid_formality(conn, run_id)
    _derive_projected_fate(conn, run_id)


def _clear_current(conn: duckdb.DuckDBPyConnection, run_id: str) -> None:
    conn.execute("DELETE FROM judgments WHERE run_id = ?", [run_id])
    conn.execute("DELETE FROM review_flags WHERE run_id = ? AND flag_type LIKE 'judgment_%'", [run_id])


def _derive_bid_formality(conn: duckdb.DuckDBPyConnection, run_id: str) -> None:
    rows = conn.execute(
        """
        SELECT events.event_id, events.deal_id, events.cycle_id,
               events.event_subtype, events.event_date,
               events.bid_value, events.bid_value_lower, events.bid_value_upper
        FROM events
        WHERE events.run_id = ?
          AND events.event_type = 'bid'
        ORDER BY events.event_date NULLS LAST, events.event_id
        """,
        [run_id],
    ).fetchall()
    for sequence, row in enumerate(rows, start=1):
        event_id, deal_id, cycle_id, event_subtype, event_date, bid_value, bid_value_lower, bid_value_upper = row
        if event_subtype in {"ioi_submitted", "first_round_bid"}:
            _insert_judgment(
                conn,
                sequence=sequence,
                run_id=run_id,
                deal_id=deal_id,
                cycle_id=cycle_id,
                target_table="events",
                target_id=event_id,
                judgment_key="bid_formality",
                judgment_value="informal",
                judgment_status="accepted",
                rule_id="bid_formality_v1",
                reason_code=f"{event_subtype}_is_informal",
                basis={"event_subtype": event_subtype},
            )
        elif event_subtype == "final_round_bid" and any(
            value is not None for value in (bid_value, bid_value_lower, bid_value_upper)
        ):
            _insert_judgment(
                conn,
                sequence=sequence,
                run_id=run_id,
                deal_id=deal_id,
                cycle_id=cycle_id,
                target_table="events",
                target_id=event_id,
                judgment_key="bid_formality",
                judgment_value="formal",
                judgment_status="accepted",
                rule_id="bid_formality_v1",
                reason_code="final_round_bid_is_formal",
                basis={"event_subtype": event_subtype, "event_date": str(event_date)},
            )
        else:
            _insert_review_flag(
                conn,
                sequence=sequence,
                run_id=run_id,
                deal_slug=_deal_slug(conn, deal_id),
                flag_type="judgment_substrate_missing",
                severity="review",
                reason_code="formality_substrate_missing",
                reason=f"Cannot derive bid formality for event_subtype={event_subtype!r}.",
                canonical_table="events",
                canonical_id=event_id,
                recommended_review_question="Does the source support informal or formal bid treatment for this event?",
            )


def _derive_projected_fate(conn: duckdb.DuckDBPyConnection, run_id: str) -> None:
    rows = conn.execute(
        """
        SELECT events.event_id, events.deal_id, events.cycle_id,
               events.event_subtype
        FROM events
        WHERE events.run_id = ?
          AND events.event_subtype IN ('withdrawn_by_bidder', 'excluded_by_target', 'non_responsive', 'merger_agreement_executed')
        ORDER BY events.event_id
        """,
        [run_id],
    ).fetchall()
    start = _next_judgment_sequence(conn)
    for offset, (event_id, deal_id, cycle_id, event_subtype) in enumerate(rows, start=0):
        value = "signed_transaction" if event_subtype == "merger_agreement_executed" else "observed_drop"
        _insert_judgment(
            conn,
            sequence=start + offset,
            run_id=run_id,
            deal_id=deal_id,
            cycle_id=cycle_id,
            target_table="events",
            target_id=event_id,
            judgment_key="projected_fate",
            judgment_value=value,
            judgment_status="accepted",
            rule_id="projected_fate_v1",
            reason_code=f"{event_subtype}_fate",
            basis={"event_subtype": event_subtype},
        )


def _insert_judgment(
    conn: duckdb.DuckDBPyConnection,
    *,
    sequence: int,
    run_id: str,
    deal_id: str,
    cycle_id: str | None,
    target_table: str,
    target_id: str,
    judgment_key: str,
    judgment_value: str | None,
    judgment_status: str,
    rule_id: str,
    reason_code: str,
    basis: dict[str, object],
) -> None:
    deal_slug = _deal_slug(conn, deal_id)
    conn.execute(
        "INSERT INTO judgments VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            make_id(deal_slug, "judgment", sequence),
            run_id,
            deal_id,
            cycle_id,
            target_table,
            target_id,
            judgment_key,
            judgment_value,
            judgment_status,
            rule_id,
            reason_code,
            reason_code.replace("_", " "),
            json.dumps(basis, sort_keys=True),
            True,
            None,
        ],
    )


def _insert_review_flag(
    conn: duckdb.DuckDBPyConnection,
    *,
    sequence: int,
    run_id: str,
    deal_slug: str,
    flag_type: str,
    severity: str,
    reason_code: str,
    reason: str,
    canonical_table: str,
    canonical_id: str,
    recommended_review_question: str,
) -> None:
    conn.execute(
        "INSERT INTO review_flags VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            make_id(deal_slug, "reviewflag", sequence),
            run_id,
            deal_slug,
            None,
            None,
            None,
            None,
            None,
            canonical_table,
            canonical_id,
            flag_type,
            severity,
            reason_code,
            reason,
            None,
            None,
            None,
            recommended_review_question,
            True,
        ],
    )


def _deal_slug(conn: duckdb.DuckDBPyConnection, deal_id: str) -> str:
    row = conn.execute("SELECT deal_slug FROM deals WHERE deal_id = ?", [deal_id]).fetchone()
    if row is None:
        return deal_id.split("_", maxsplit=1)[0]
    return row[0]


def _next_judgment_sequence(conn: duckdb.DuckDBPyConnection) -> int:
    row = conn.execute("SELECT count(*) FROM judgments").fetchone()
    return int(row[0]) + 1
