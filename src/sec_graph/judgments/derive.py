"""Derive research judgments from supported canonical facts."""

from __future__ import annotations

import datetime as dt
import json
import re

import duckdb

from sec_graph.schema import make_id


_BEST_AND_FINAL_CUE_RE = re.compile(
    r"\bbest\s+and\s+final\b|\bfinal\s+(?:bid|offer|proposal)\b",
    re.IGNORECASE,
)


def derive_judgments(conn: duckdb.DuckDBPyConnection, *, run_id: str) -> None:
    _clear_current(conn, run_id)
    _derive_bid_formality(conn, run_id)
    _derive_actor_relation_roles(conn, run_id)
    _derive_projected_fate(conn, run_id)


def _clear_current(conn: duckdb.DuckDBPyConnection, run_id: str) -> None:
    conn.execute("DELETE FROM judgments WHERE run_id = ?", [run_id])
    conn.execute(
        "DELETE FROM review_rows WHERE run_id = ? AND review_type = 'judgment'",
        [run_id],
    )


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
    for row in rows:
        (
            event_id,
            deal_id,
            cycle_id,
            event_subtype,
            event_date,
            bid_value,
            bid_value_lower,
            bid_value_upper,
        ) = row
        has_value = any(
            value is not None for value in (bid_value, bid_value_lower, bid_value_upper)
        )
        final_round_boundary = (
            cycle_id
            if cycle_id is not None
            and _final_round_boundary_for_cycle(conn, cycle_id, run_id)
            else None
        )
        best_and_final_cue = _event_has_best_and_final_cue(conn, event_id)
        source_cues: list[str] = []

        formality: str | None = None
        rule_id = "bid_formality_v1"
        reason_code = ""

        if event_subtype == "final_round_bid":
            formality = "formal"
            rule_id = "bid_formality_final_round_subtype_v1"
            reason_code = "final_round_bid_subtype"
            source_cues.append("final_round_bid_subtype")
        elif final_round_boundary is not None and has_value:
            formality = "formal"
            rule_id = "bid_formality_final_round_with_value_v1"
            reason_code = "final_round_boundary_with_value"
            source_cues.append("final_round_boundary_with_value")
        elif best_and_final_cue:
            formality = "formal"
            rule_id = "bid_formality_best_and_final_quote_v1"
            reason_code = "best_and_final_quote_cue"
            source_cues.append("best_and_final_quote_cue")
        elif event_subtype in {"ioi_submitted", "first_round_bid"} and final_round_boundary is None:
            formality = "informal"
            rule_id = "bid_formality_v1"
            reason_code = f"{event_subtype}_is_informal"
            source_cues.append(f"{event_subtype}_subtype")

        if formality is not None:
            basis: dict[str, object] = {
                "bid_id": event_id,
                "event_subtype": event_subtype,
                "has_value": has_value,
                "final_round_boundary": final_round_boundary,
                "source_cues": source_cues,
            }
            if event_date is not None:
                basis["event_date"] = str(event_date)
            _insert_judgment(
                conn,
                run_id=run_id,
                deal_id=deal_id,
                cycle_id=cycle_id,
                target_table="events",
                target_id=event_id,
                judgment_key="bid_formality",
                judgment_value=formality,
                judgment_status="accepted",
                rule_id=rule_id,
                reason_code=reason_code,
                basis=basis,
            )
        else:
            _insert_review_row(
                conn,
                run_id=run_id,
                deal_slug=_deal_slug(conn, deal_id),
                review_type="judgment",
                severity="review",
                reason_code="formality_substrate_missing",
                message=(
                    f"Cannot derive bid formality for event {event_id!r} "
                    f"(event_subtype={event_subtype!r})."
                ),
                review_question=(
                    "Does the source support informal or formal bid treatment for this event?"
                ),
                source_table="events",
                source_id=event_id,
                canonical_table="events",
                canonical_id=event_id,
            )


def _final_round_boundary_for_cycle(
    conn: duckdb.DuckDBPyConnection,
    cycle_id: str,
    run_id: str,
) -> bool:
    """Return True iff ``cycle_id`` is the final-round boundary cycle.

    The boundary is defined as a cycle whose canonical events include any
    event with ``event_subtype='final_round_bid'`` OR whose
    ``participation_counts`` rows include ``process_stage='final_round'``.
    """
    has_final_event = conn.execute(
        """
        SELECT count(*)
        FROM events
        WHERE run_id = ?
          AND cycle_id = ?
          AND event_subtype = 'final_round_bid'
        """,
        [run_id, cycle_id],
    ).fetchone()[0]
    if int(has_final_event) > 0:
        return True
    has_final_participation = conn.execute(
        """
        SELECT count(*)
        FROM participation_counts
        WHERE run_id = ?
          AND cycle_id = ?
          AND process_stage = 'final_round'
        """,
        [run_id, cycle_id],
    ).fetchone()[0]
    return int(has_final_participation) > 0


def _event_has_best_and_final_cue(
    conn: duckdb.DuckDBPyConnection,
    event_id: str,
) -> bool:
    """Return True iff any supported bid claim canonicalized to ``event_id``
    contains a "best and final" / "final bid|offer|proposal" cue in its quote.
    """
    rows = conn.execute(
        """
        SELECT claims.quote_text
        FROM claims
        JOIN claim_dispositions
          ON claim_dispositions.claim_id = claims.claim_id
         AND claim_dispositions.current = true
        WHERE claim_dispositions.canonical_table = 'events'
          AND claim_dispositions.canonical_id = ?
          AND claim_dispositions.disposition IN ('supported', 'merged_duplicate')
        """,
        [event_id],
    ).fetchall()
    for (quote_text,) in rows:
        if quote_text and _BEST_AND_FINAL_CUE_RE.search(str(quote_text)):
            return True
    return False


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
    for event_id, deal_id, cycle_id, event_subtype in rows:
        value = "signed_transaction" if event_subtype == "merger_agreement_executed" else "observed_drop"
        _insert_judgment(
            conn,
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


def _derive_actor_relation_roles(conn: duckdb.DuckDBPyConnection, run_id: str) -> None:
    rows = conn.execute(
        """
        SELECT actor_relations.relation_id, actor_relations.deal_id,
               actor_relations.cycle_id_first_observed, actor_relations.relation_type,
               actors.actor_label
        FROM actor_relations
        JOIN actors ON actors.actor_id = actor_relations.subject_actor_id
        WHERE actor_relations.run_id = ?
          AND actor_relations.relation_type = 'advises'
        ORDER BY actor_relations.relation_id
        """,
        [run_id],
    ).fetchall()
    for relation_id, deal_id, cycle_id, relation_type, subject_label in rows:
        lowered = str(subject_label).casefold()
        value = "legal_advisor" if any(term in lowered for term in ("llp", "law", "legal", "counsel")) else "financial_advisor"
        _insert_judgment(
            conn,
            run_id=run_id,
            deal_id=deal_id,
            cycle_id=cycle_id,
            target_table="actor_relations",
            target_id=relation_id,
            judgment_key="process_role",
            judgment_value=value,
            judgment_status="accepted",
            rule_id="advisor_role_v1",
            reason_code=f"{value}_from_advises_relation",
            basis={"relation_type": relation_type, "subject_label": subject_label},
        )


def _insert_judgment(
    conn: duckdb.DuckDBPyConnection,
    *,
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
    sequence = _next_sequence(conn, "judgments", "judgment_id", deal_slug, "judgment")
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
    judgment_id: str | None = None,
) -> None:
    sequence = _next_sequence(conn, "review_rows", "review_row_id", deal_slug, "reviewrow")
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
            judgment_id,
            canonical_table,
            canonical_id,
            None,
            None,
            None,
            None,
            _now_iso(),
        ],
    )


def _deal_slug(conn: duckdb.DuckDBPyConnection, deal_id: str) -> str:
    row = conn.execute("SELECT deal_slug FROM deals WHERE deal_id = ?", [deal_id]).fetchone()
    if row is None:
        return deal_id.split("_", maxsplit=1)[0]
    return row[0]


def _next_sequence(
    conn: duckdb.DuckDBPyConnection,
    table_name: str,
    id_col: str,
    slug: str,
    type_name: str,
) -> int:
    prefix = f"{slug}_{type_name}_"
    rows = conn.execute(
        f"SELECT {id_col} FROM {table_name} WHERE {id_col} LIKE ?",
        [f"{prefix}%"],
    ).fetchall()
    if not rows:
        return 1
    return max(int(row[0].rsplit("_", maxsplit=1)[1]) for row in rows) + 1


def _now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
