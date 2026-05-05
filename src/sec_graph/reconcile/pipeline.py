"""Canonicalize typed claims into the generic graph."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

import duckdb

from sec_graph.reconcile.aliases import canonical_label
from sec_graph.schema import make_id

_COUNT_TERMS = {
    "one",
    "two",
    "three",
    "four",
    "five",
    "six",
    "seven",
    "eight",
    "nine",
    "ten",
    "eleven",
    "twelve",
    "thirteen",
    "fourteen",
    "fifteen",
    "sixteen",
    "seventeen",
    "eighteen",
    "nineteen",
    "twenty",
    "couple",
    "several",
    "multiple",
    "various",
    "numerous",
    "many",
    "some",
    "certain",
}
_GENERIC_BIDDER_NOUNS = {
    "party",
    "parties",
    "bidder",
    "bidders",
    "buyer",
    "buyers",
    "entity",
    "entities",
    "firm",
    "firms",
    "purchaser",
    "purchasers",
    "sponsor",
    "sponsors",
    "participant",
    "participants",
}
_GENERIC_BIDDER_LABELS = {
    "potential bidder",
    "potential bidders",
    "potential buyer",
    "potential buyers",
    "prospective bidder",
    "prospective bidders",
    "prospective buyer",
    "prospective buyers",
    "interested party",
    "interested parties",
    "potentially interested party",
    "potentially interested parties",
    "financial buyer",
    "financial buyers",
    "strategic buyer",
    "strategic buyers",
    "financial sponsor",
    "financial sponsors",
    "private equity firm",
    "private equity firms",
    "other party",
    "other parties",
    "other bidder",
    "other bidders",
    "other buyer",
    "other buyers",
}
_GENERIC_BIDDER_MODIFIERS = {
    "potential",
    "potentially",
    "interested",
    "prospective",
    "financial",
    "private",
    "equity",
    "strategic",
    "other",
    "remaining",
    "additional",
    "qualified",
    "initial",
}


@dataclass
class ReconcileState:
    conn: duckdb.DuckDBPyConnection
    slug: str
    filing_id: str
    run_id: str
    deal_id: str
    cycle_id: str
    actor_ids: dict[str, str]
    actor_sequence: int = 1
    relation_sequence: int = 1
    event_sequence: int = 1
    link_sequence: int = 1
    count_sequence: int = 1
    disposition_sequence: int = 1


def reconcile_filing(conn: duckdb.DuckDBPyConnection, *, filing_id: str, run_id: str) -> None:
    slug = _slug(conn, filing_id)
    undisposed = conn.execute(
        """
        SELECT count(*)
        FROM claims
        LEFT JOIN claim_dispositions
          ON claim_dispositions.claim_id = claims.claim_id
         AND claim_dispositions.current = true
        WHERE claims.filing_id = ?
          AND claims.status = 'validated'
          AND claim_dispositions.claim_id IS NULL
        """,
        [filing_id],
    ).fetchone()[0]
    if undisposed:
        raise ValueError(f"filing {filing_id} has undisposed supported claims")
    claims = _claim_rows(conn, filing_id)
    if not claims:
        if _already_reconciled(conn, filing_id, slug):
            return
        raise ValueError(f"filing {filing_id} has no validated claims")
    _clear_outputs(conn, filing_id, slug)
    first_evidence = _claim_evidence(conn, claims[0]["claim_id"])[0]
    deal_id = make_id(slug, "deal", 1)
    cycle_id = make_id(slug, "cycle", 1)
    state = ReconcileState(
        conn,
        slug,
        filing_id,
        run_id,
        deal_id,
        cycle_id,
        {},
        disposition_sequence=_next_disposition_sequence(conn, slug),
    )
    target_actor_id = make_id(slug, "actor", 1)
    conn.execute("INSERT INTO deals VALUES (?, ?, ?, ?, ?)", [deal_id, run_id, slug, target_actor_id, _announcement_date(conn, filing_id)])
    _link_row_evidence(conn, "deals", deal_id, first_evidence)
    created_target_actor_id = _ensure_actor(
        state,
        label=_target_label(slug, claims),
        actor_kind="organization",
        observability="named",
        evidence_id=first_evidence,
    )
    if created_target_actor_id != target_actor_id:
        raise AssertionError("target actor id allocation drifted")
    conn.execute(
        "INSERT INTO process_cycles VALUES (?, ?, ?, ?, ?, ?, ?)",
        [cycle_id, run_id, deal_id, 1, "primary sale process", _min_date(conn, filing_id), _max_date(conn, filing_id)],
    )
    _link_row_evidence(conn, "process_cycles", cycle_id, first_evidence)

    for claim in claims:
        claim_type = claim["claim_type"]
        if claim_type == "actor":
            _canonicalize_actor(state, claim)
        elif claim_type == "event":
            _canonicalize_event(state, claim)
        elif claim_type == "bid":
            _canonicalize_bid(state, claim)
        elif claim_type == "participation_count":
            _canonicalize_count(state, claim)
        elif claim_type == "actor_relation":
            _canonicalize_relation(state, claim)
        else:
            _dispose(state, claim["claim_id"], "out_of_scope", "unsupported_claim_type", f"unsupported claim_type={claim_type}", None, None)


def reconcile_all(conn: duckdb.DuckDBPyConnection, *, run_id: str) -> None:
    filing_rows = conn.execute("SELECT filing_id FROM filings ORDER BY deal_slug").fetchall()
    for (filing_id,) in filing_rows:
        reconcile_filing(conn, filing_id=filing_id, run_id=run_id)


def _slug(conn: duckdb.DuckDBPyConnection, filing_id: str) -> str:
    row = conn.execute("SELECT deal_slug FROM filings WHERE filing_id = ?", [filing_id]).fetchone()
    if row is None:
        raise ValueError(f"unknown filing_id={filing_id}")
    return row[0]


def _claim_rows(conn: duckdb.DuckDBPyConnection, filing_id: str) -> list[dict[str, object]]:
    columns = [
        "claim_id",
        "claim_type",
        "confidence",
        "raw_value",
        "normalized_value",
        "quote_text",
        "claim_sequence",
    ]
    rows = conn.execute(
        """
        SELECT claims.claim_id, claims.claim_type, claims.confidence,
               claims.raw_value, claims.normalized_value,
               claims.quote_text, claims.claim_sequence
        FROM claims
        JOIN claim_dispositions
          ON claim_dispositions.claim_id = claims.claim_id
         AND claim_dispositions.current = true
        WHERE claims.filing_id = ?
          AND claims.status = 'validated'
          AND claim_dispositions.disposition IN ('supported', 'merged_duplicate')
        ORDER BY claims.claim_sequence, claims.claim_id
        """,
        [filing_id],
    ).fetchall()
    return [dict(zip(columns, row, strict=True)) for row in rows]


def _already_reconciled(
    conn: duckdb.DuckDBPyConnection, filing_id: str, slug: str
) -> bool:
    disposed_supported = conn.execute(
        """
        SELECT count(*)
        FROM claims
        JOIN claim_dispositions
          ON claim_dispositions.claim_id = claims.claim_id
         AND claim_dispositions.current = true
        WHERE claims.filing_id = ?
          AND claims.status = 'disposed'
          AND claim_dispositions.disposition IN ('supported', 'merged_duplicate')
        """,
        [filing_id],
    ).fetchone()[0]
    if not disposed_supported:
        return False
    canonical_rows = conn.execute(
        "SELECT count(*) FROM deals WHERE deal_slug = ?",
        [slug],
    ).fetchone()[0]
    return bool(canonical_rows)


def _clear_outputs(conn: duckdb.DuckDBPyConnection, filing_id: str, slug: str) -> None:
    del filing_id
    conn.execute("DELETE FROM bidder_rows WHERE deal_slug = ?", [slug])
    conn.execute("DELETE FROM projection_judgments WHERE projection_unit_id LIKE ?", [f"{slug}_%"])
    conn.execute("DELETE FROM projection_units WHERE deal_id LIKE ?", [f"{slug}_%"])
    for table in ("participation_counts", "event_actor_links", "events", "actor_relations", "process_cycles", "actors", "deals"):
        id_col = {
            "participation_counts": "participation_count_id",
            "event_actor_links": "link_id",
            "events": "event_id",
            "actor_relations": "relation_id",
            "process_cycles": "cycle_id",
            "actors": "actor_id",
            "deals": "deal_id",
        }[table]
        conn.execute(f"DELETE FROM row_evidence WHERE row_table = ? AND row_id LIKE ?", [table, f"{slug}_%"])
        conn.execute(f"DELETE FROM {table} WHERE {id_col} LIKE ?", [f"{slug}_%"])
    conn.execute(
        """
        DELETE FROM claim_dispositions
        WHERE created_stage = 'reconcile'
          AND claim_id IN (SELECT claim_id FROM claims WHERE deal_slug = ?)
        """,
        [slug],
    )


def _target_label(slug: str, claims: list[dict[str, object]]) -> str:
    for claim in claims:
        if claim["claim_type"] == "actor":
            raw = str(claim["raw_value"])
            if slug.split("-", maxsplit=1)[0].casefold() in raw.casefold():
                return canonical_label(raw)
    return " ".join(part.capitalize() for part in slug.split("-"))


def _claim_evidence(conn: duckdb.DuckDBPyConnection, claim_id: str) -> list[str]:
    rows = conn.execute(
        "SELECT evidence_id FROM claim_evidence WHERE claim_id = ? ORDER BY ordinal",
        [claim_id],
    ).fetchall()
    if not rows:
        raise ValueError(f"claim {claim_id} has no claim_evidence")
    return [row[0] for row in rows]


def _next_disposition_sequence(conn: duckdb.DuckDBPyConnection, slug: str) -> int:
    row = conn.execute(
        """
        SELECT count(*)
        FROM claim_dispositions
        JOIN claims USING (claim_id)
        WHERE claims.deal_slug = ?
        """,
        [slug],
    ).fetchone()
    return int(row[0]) + 1


def _link_row_evidence(conn: duckdb.DuckDBPyConnection, table: str, row_id: str, evidence_id: str, ordinal: int = 1) -> None:
    conn.execute("INSERT INTO row_evidence VALUES (?, ?, ?, ?)", [table, row_id, evidence_id, ordinal])


def _ensure_actor(
    state: ReconcileState,
    *,
    label: str,
    actor_kind: str,
    observability: str,
    evidence_id: str,
) -> str:
    normalized = canonical_label(label)
    existing = state.actor_ids.get(normalized)
    if existing is not None:
        return existing
    actor_id = make_id(state.slug, "actor", state.actor_sequence)
    state.actor_sequence += 1
    state.actor_ids[normalized] = actor_id
    state.conn.execute(
        "INSERT INTO actors VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [actor_id, state.run_id, state.deal_id, normalized, actor_kind, observability, None, None, None, None],
    )
    _link_row_evidence(state.conn, "actors", actor_id, evidence_id)
    return actor_id


def _dispose(
    state: ReconcileState,
    claim_id: str,
    disposition: str,
    reason_code: str,
    reason: str,
    canonical_table: str | None,
    canonical_id: str | None,
    surviving_claim_id: str | None = None,
) -> None:
    disposition_id = make_id(state.slug, "disposition", state.disposition_sequence)
    state.disposition_sequence += 1
    state.conn.execute(
        "DELETE FROM claim_dispositions WHERE claim_id = ? AND current = true",
        [claim_id],
    )
    state.conn.execute(
        "INSERT INTO claim_dispositions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            disposition_id,
            claim_id,
            state.run_id,
            disposition,
            reason_code,
            reason,
            canonical_table,
            canonical_id,
            surviving_claim_id,
            "reconcile",
            True,
        ],
    )
    state.conn.execute("UPDATE claims SET status = 'disposed' WHERE claim_id = ?", [claim_id])


def _canonicalize_actor(state: ReconcileState, claim: dict[str, object]) -> None:
    row = state.conn.execute(
        "SELECT actor_label, actor_kind, observability FROM actor_claims WHERE claim_id = ?",
        [claim["claim_id"]],
    ).fetchone()
    if row is None:
        _dispose(state, str(claim["claim_id"]), "rejected_unsupported", "missing_actor_claim", "actor claim missing typed row", None, None)
        return
    evidence_id = _claim_evidence(state.conn, str(claim["claim_id"]))[0]
    label, actor_kind, observability = row
    before = dict(state.actor_ids)
    actor_id = _ensure_actor(state, label=label, actor_kind=actor_kind, observability=observability, evidence_id=evidence_id)
    disposition = "supported" if before != state.actor_ids else "merged_duplicate"
    _dispose(state, str(claim["claim_id"]), disposition, "actor_label_canonicalized", "actor claim mapped by canonical label", "actors", actor_id)


def _canonicalize_event(state: ReconcileState, claim: dict[str, object]) -> None:
    row = state.conn.execute(
        """
        SELECT event_type, event_subtype, event_date, description, actor_label, actor_role
        FROM event_claims
        WHERE claim_id = ?
        """,
        [claim["claim_id"]],
    ).fetchone()
    if row is None:
        _dispose(state, str(claim["claim_id"]), "rejected_unsupported", "missing_event_claim", "event claim missing typed row", None, None)
        return
    evidence_id = _claim_evidence(state.conn, str(claim["claim_id"]))[0]
    event_type, event_subtype, event_date, description, actor_label, actor_role = row
    event_id = make_id(state.slug, "event", state.event_sequence)
    state.event_sequence += 1
    state.conn.execute(
        "INSERT INTO events VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [event_id, state.run_id, state.deal_id, state.cycle_id, event_type, event_subtype, event_date, description, None, None, None, None, None],
    )
    _link_row_evidence(state.conn, "events", event_id, evidence_id)
    if actor_label and actor_role:
        actor_id = _ensure_actor(state, label=actor_label, actor_kind="organization", observability="named", evidence_id=evidence_id)
        _insert_event_link(state, event_id, actor_id, actor_role, None, evidence_id)
    _dispose(state, str(claim["claim_id"]), "supported", "event_claim_canonicalized", "event claim mapped to canonical event", "events", event_id)


def _canonicalize_bid(state: ReconcileState, claim: dict[str, object]) -> None:
    row = state.conn.execute(
        """
        SELECT bidder_label, bid_date, bid_value, bid_value_lower, bid_value_upper,
               bid_value_unit, consideration_type, bid_stage
        FROM bid_claims
        WHERE claim_id = ?
        """,
        [claim["claim_id"]],
    ).fetchone()
    if row is None:
        _dispose(state, str(claim["claim_id"]), "rejected_unsupported", "missing_bid_claim", "bid claim missing typed row", None, None)
        return
    evidence_id = _claim_evidence(state.conn, str(claim["claim_id"]))[0]
    bidder_label, bid_date, bid_value, bid_value_lower, bid_value_upper, bid_value_unit, consideration_type, bid_stage = row
    if is_generic_bidder_label(bidder_label):
        _dispose(
            state,
            str(claim["claim_id"]),
            "rejected_unsupported",
            "generic_bidder_label_not_projectable",
            "bid claim label is a count/cohort phrase, not a source-backed bidder identity fit for projection",
            None,
            None,
        )
        return
    actor_id = _ensure_actor(state, label=bidder_label, actor_kind="organization", observability="named", evidence_id=evidence_id)
    event_id = make_id(state.slug, "event", state.event_sequence)
    state.event_sequence += 1
    event_subtype = "final_round_bid" if bid_stage == "final" else "first_round_bid"
    state.conn.execute(
        "INSERT INTO events VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            event_id,
            state.run_id,
            state.deal_id,
            state.cycle_id,
            "bid",
            event_subtype,
            bid_date,
            f"{bidder_label} bid",
            bid_value,
            bid_value_lower,
            bid_value_upper,
            bid_value_unit,
            consideration_type,
        ],
    )
    _link_row_evidence(state.conn, "events", event_id, evidence_id)
    _insert_event_link(state, event_id, actor_id, "bid_submitter", None, evidence_id)
    _dispose(state, str(claim["claim_id"]), "supported", "bid_claim_canonicalized", "bid claim mapped to canonical bid event", "events", event_id)


def is_generic_bidder_label(label: str) -> bool:
    normalized = _normalized_label_tokens(label)
    if not normalized:
        return True
    if normalized in _GENERIC_BIDDER_LABELS:
        return True

    tokens = normalized.split()
    if len(tokens) == 1 and tokens[0] in _GENERIC_BIDDER_NOUNS:
        return True
    if _has_count_or_quantifier(tokens) and tokens[-1] in _GENERIC_BIDDER_NOUNS:
        return True
    return all(token in _GENERIC_BIDDER_MODIFIERS | _GENERIC_BIDDER_NOUNS for token in tokens) and any(
        token in _GENERIC_BIDDER_NOUNS for token in tokens
    )


def _normalized_label_tokens(label: str) -> str:
    normalized = canonical_label(label).casefold()
    normalized = re.sub(r"[^a-z0-9]+", " ", normalized)
    return " ".join(normalized.split())


def _has_count_or_quantifier(tokens: list[str]) -> bool:
    return any(token.isdigit() or token in _COUNT_TERMS for token in tokens)


def _canonicalize_count(state: ReconcileState, claim: dict[str, object]) -> None:
    row = state.conn.execute(
        """
        SELECT process_stage, actor_class, count_min, count_max, count_qualifier
        FROM participation_count_claims
        WHERE claim_id = ?
        """,
        [claim["claim_id"]],
    ).fetchone()
    if row is None:
        _dispose(state, str(claim["claim_id"]), "rejected_unsupported", "missing_participation_count_claim", "count claim missing typed row", None, None)
        return
    evidence_id = _claim_evidence(state.conn, str(claim["claim_id"]))[0]
    count_id = make_id(state.slug, "count", state.count_sequence)
    state.count_sequence += 1
    state.conn.execute(
        "INSERT INTO participation_counts VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [count_id, state.run_id, state.deal_id, state.cycle_id, None, *row, json.dumps([]), 0],
    )
    _link_row_evidence(state.conn, "participation_counts", count_id, evidence_id)
    _dispose(state, str(claim["claim_id"]), "supported", "participation_count_canonicalized", "count claim mapped to canonical participation count", "participation_counts", count_id)


def _canonicalize_relation(state: ReconcileState, claim: dict[str, object]) -> None:
    row = state.conn.execute(
        """
        SELECT subject_label, object_label, relation_type, role_detail, effective_date_first
        FROM actor_relation_claims
        WHERE claim_id = ?
        """,
        [claim["claim_id"]],
    ).fetchone()
    if row is None:
        _dispose(state, str(claim["claim_id"]), "rejected_unsupported", "missing_actor_relation_claim", "relation claim missing typed row", None, None)
        return
    evidence_id = _claim_evidence(state.conn, str(claim["claim_id"]))[0]
    subject_label, object_label, relation_type, role_detail, effective_date_first = row
    subject_id = _ensure_actor(state, label=subject_label, actor_kind="organization", observability="named", evidence_id=evidence_id)
    object_id = _ensure_actor(state, label=object_label, actor_kind="organization", observability="named", evidence_id=evidence_id)
    relation_id = make_id(state.slug, "relation", state.relation_sequence)
    state.relation_sequence += 1
    state.conn.execute(
        "INSERT INTO actor_relations VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            relation_id,
            state.run_id,
            state.deal_id,
            subject_id,
            object_id,
            relation_type,
            role_detail,
            state.cycle_id,
            None,
            effective_date_first,
            None,
            claim["confidence"],
        ],
    )
    _link_row_evidence(state.conn, "actor_relations", relation_id, evidence_id)
    _dispose(state, str(claim["claim_id"]), "supported", "actor_relation_canonicalized", "relation claim mapped to canonical relation", "actor_relations", relation_id)


def _insert_event_link(
    state: ReconcileState,
    event_id: str,
    actor_id: str,
    role: str,
    role_detail: str | None,
    evidence_id: str,
) -> None:
    link_id = make_id(state.slug, "link", state.link_sequence)
    state.link_sequence += 1
    state.conn.execute(
        "INSERT INTO event_actor_links VALUES (?, ?, ?, ?, ?, ?)",
        [link_id, state.run_id, event_id, actor_id, role, role_detail],
    )
    _link_row_evidence(state.conn, "event_actor_links", link_id, evidence_id)


def _announcement_date(conn: duckdb.DuckDBPyConnection, filing_id: str):
    return _max_date(conn, filing_id)


def _min_date(conn: duckdb.DuckDBPyConnection, filing_id: str):
    rows = conn.execute(
        """
        SELECT event_date FROM event_claims JOIN claims USING (claim_id)
        WHERE filing_id = ? AND event_date IS NOT NULL
        UNION ALL
        SELECT bid_date FROM bid_claims JOIN claims USING (claim_id)
        WHERE filing_id = ? AND bid_date IS NOT NULL
        """,
        [filing_id, filing_id],
    ).fetchall()
    return min((row[0] for row in rows), default=None)


def _max_date(conn: duckdb.DuckDBPyConnection, filing_id: str):
    rows = conn.execute(
        """
        SELECT event_date FROM event_claims JOIN claims USING (claim_id)
        WHERE filing_id = ? AND event_date IS NOT NULL
        UNION ALL
        SELECT bid_date FROM bid_claims JOIN claims USING (claim_id)
        WHERE filing_id = ? AND bid_date IS NOT NULL
        """,
        [filing_id, filing_id],
    ).fetchall()
    return max((row[0] for row in rows), default=None)
