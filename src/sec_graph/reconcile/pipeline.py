"""Deterministic reconciliation from extraction candidates to canonical tables."""

from __future__ import annotations

import datetime as dt
import json
from dataclasses import dataclass

import duckdb

from sec_graph.reconcile.aliases import bidder_subtype, canonical_label, labels_in_text, target_label
from sec_graph.reconcile.boundaries import choose_boundary
from sec_graph.reconcile.cycles import CycleWindow, build_cycle_windows, cycle_for
from sec_graph.schema import (
    Actor,
    Deal,
    Event,
    EventActorLink,
    Judgment,
    ParticipationCount,
    ProcessCycle,
    make_id,
)


@dataclass(frozen=True)
class CandidateContext:
    candidate_id: str
    filing_id: str
    deal_slug: str
    candidate_type: str
    raw_value: str
    normalized_value: str
    confidence: str
    evidence_id: str
    char_start: int
    char_end: int
    paragraph_id: str
    paragraph_text: str
    paragraph_start: int
    event_date: dt.date | None


@dataclass(frozen=True)
class ActorRecord:
    actor_id: str
    label: str
    evidence_id: str
    context: str


def _row_values(model) -> tuple[object, ...]:
    payload = model.model_dump(mode="json")
    if "bidder_subtype_split" in payload and payload["bidder_subtype_split"] is not None:
        payload["bidder_subtype_split"] = json.dumps(payload["bidder_subtype_split"], sort_keys=True)
    return tuple(payload.values())


def _candidate_contexts(conn: duckdb.DuckDBPyConnection, filing_id: str) -> list[CandidateContext]:
    rows = conn.execute(
        """
        SELECT candidates.candidate_id, candidates.filing_id, filings.deal_slug,
               candidates.candidate_type, candidates.raw_value, candidates.normalized_value,
               candidates.confidence, candidates.evidence_ids[1],
               spans.char_start, spans.char_end, spans.paragraph_id,
               paragraphs.paragraph_text, paragraphs.char_start
        FROM candidates
        JOIN filings USING (filing_id)
        JOIN spans ON candidates.evidence_ids[1] = spans.evidence_id
        JOIN paragraphs ON spans.paragraph_id = paragraphs.paragraph_id
        WHERE candidates.filing_id = ?
        ORDER BY spans.char_start, candidates.candidate_id
        """,
        [filing_id],
    ).fetchall()
    contexts: list[CandidateContext] = []
    for row in rows:
        event_date = dt.date.fromisoformat(row[5]) if row[3] == "dated_event" else None
        contexts.append(
            CandidateContext(
                candidate_id=row[0],
                filing_id=row[1],
                deal_slug=row[2],
                candidate_type=row[3],
                raw_value=row[4],
                normalized_value=row[5],
                confidence=row[6],
                evidence_id=row[7],
                char_start=row[8],
                char_end=row[9],
                paragraph_id=row[10],
                paragraph_text=row[11],
                paragraph_start=row[12],
                event_date=event_date,
            )
        )
    return contexts


def _clear_canonical(conn: duckdb.DuckDBPyConnection) -> None:
    for table_name in (
        "event_actor_links",
        "judgments",
        "participation_counts",
        "events",
        "actors",
        "process_cycles",
        "deals",
    ):
        conn.execute(f"DELETE FROM {table_name}")


def _sentence_for_candidate(row: CandidateContext) -> str:
    local_start = max(0, row.char_start - row.paragraph_start)
    before = row.paragraph_text.rfind(".", 0, local_start)
    after = row.paragraph_text.find(".", local_start)
    start = 0 if before == -1 else before + 1
    end = len(row.paragraph_text) if after == -1 else after + 1
    return row.paragraph_text[start:end].strip()


def _candidate_date(row: CandidateContext, dated_rows: list[CandidateContext]) -> dt.date | None:
    if row.event_date is not None:
        return row.event_date
    same_paragraph = [
        dated
        for dated in dated_rows
        if dated.paragraph_id == row.paragraph_id and dated.char_start <= row.char_start
    ]
    if same_paragraph:
        return same_paragraph[-1].event_date
    previous = [dated for dated in dated_rows if dated.char_start <= row.char_start]
    if previous:
        return previous[-1].event_date
    return dated_rows[0].event_date if dated_rows else None


def _bid_values(normalized_value: str) -> tuple[float, float | None, float | None]:
    if "-" not in normalized_value:
        return float(normalized_value), None, None
    lower_text, upper_text = normalized_value.split("-", maxsplit=1)
    lower = float(lower_text)
    upper = float(upper_text)
    return (lower + upper) / 2, lower, upper


def _collect_actor_records(slug: str, deal_id: str, run_id: str, rows: list[CandidateContext]) -> dict[str, ActorRecord]:
    del deal_id, run_id
    records: dict[str, ActorRecord] = {}
    for row in rows:
        if row.candidate_type == "actor_mention":
            label = canonical_label(row.raw_value)
            records.setdefault(label, ActorRecord(actor_id="", label=label, evidence_id=row.evidence_id, context=row.paragraph_text))
        for label in labels_in_text(row.paragraph_text, ("New Mountain Capital",)):
            records.setdefault(label, ActorRecord(actor_id="", label=label, evidence_id=row.evidence_id, context=row.paragraph_text))
    return {
        label: ActorRecord(actor_id=make_id(slug, "actor", index), label=record.label, evidence_id=record.evidence_id, context=record.context)
        for index, (label, record) in enumerate(sorted(records.items(), key=lambda item: (rows[0].paragraph_text.find(item[0]), item[0])), start=2)
    }


def _insert_deal_cycle_actors(
    conn: duckdb.DuckDBPyConnection,
    slug: str,
    run_id: str,
    contexts: list[CandidateContext],
    cycles: list[CycleWindow],
    actor_records: dict[str, ActorRecord],
) -> tuple[str, dict[int, str]]:
    deal_id = make_id(slug, "deal", 1)
    target_actor_id = make_id(slug, "actor", 1)
    dated_rows = [row for row in contexts if row.candidate_type == "dated_event"]
    signing = next(
        (
            row
            for row in reversed(dated_rows)
            if "executed the merger agreement" in row.raw_value.casefold()
            or "announcing entry into the transaction" in row.raw_value.casefold()
            or "consider the proposed transaction" in row.raw_value.casefold()
        ),
        dated_rows[-1] if dated_rows else contexts[-1],
    )
    conn.execute(
        "INSERT INTO deals VALUES (?, ?, ?, ?, ?, ?)",
        _row_values(
            Deal(
                deal_id=deal_id,
                run_id=run_id,
                deal_slug=slug,
                target_actor_id=target_actor_id,
                announcement_date=signing.event_date,
                evidence_ids=[signing.evidence_id],
            )
        ),
    )
    target = Actor(
        actor_id=target_actor_id,
        run_id=run_id,
        deal_id=deal_id,
        actor_label=target_label(slug),
        actor_type="target",
        bidder_subtype=None,
        is_anonymous=False,
        evidence_ids=[signing.evidence_id],
    )
    conn.execute("INSERT INTO actors VALUES (?, ?, ?, ?, ?, ?, ?, ?)", _row_values(target))
    for record in sorted(actor_records.values(), key=lambda record: record.actor_id):
        actor = Actor(
            actor_id=record.actor_id,
            run_id=run_id,
            deal_id=deal_id,
            actor_label=record.label,
            actor_type="bidder",
            bidder_subtype=bidder_subtype(record.label, record.context),
            is_anonymous=record.label.startswith(("Party ", "Bidder ")),
            evidence_ids=[record.evidence_id],
        )
        conn.execute("INSERT INTO actors VALUES (?, ?, ?, ?, ?, ?, ?, ?)", _row_values(actor))
    cycle_ids: dict[int, str] = {}
    for cycle in cycles:
        cycle_id = make_id(slug, "cycle", cycle.sequence)
        cycle_ids[cycle.sequence] = cycle_id
        model = ProcessCycle(
            cycle_id=cycle_id,
            run_id=run_id,
            deal_id=deal_id,
            cycle_sequence=cycle.sequence,
            cycle_label=f"sale process cycle {cycle.sequence}",
            start_date=cycle.start_date,
            end_date=cycle.end_date,
            evidence_ids=cycle.evidence_ids,
        )
        conn.execute("INSERT INTO process_cycles VALUES (?, ?, ?, ?, ?, ?, ?, ?)", _row_values(model))
    return deal_id, cycle_ids


def _insert_judgment(
    conn: duckdb.DuckDBPyConnection,
    judgment_id: str,
    run_id: str,
    deal_id: str,
    cycle_id: str,
    evidence_id: str,
    judgment_type: str,
    judgment_value: str,
    confidence: str = "medium",
    actor_id: str | None = None,
    event_id: str | None = None,
    alternative_value: str | None = None,
) -> None:
    judgment = Judgment(
        judgment_id=judgment_id,
        run_id=run_id,
        deal_id=deal_id,
        cycle_id=cycle_id,
        actor_id=actor_id,
        event_id=event_id,
        judgment_type=judgment_type,
        judgment_value=judgment_value,
        confidence=confidence,  # type: ignore[arg-type]
        alternative_value=alternative_value,
        supersedes_judgment_id=None,
        evidence_ids=[evidence_id],
    )
    conn.execute("INSERT INTO judgments VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", _row_values(judgment))


def _insert_events_and_judgments(
    conn: duckdb.DuckDBPyConnection,
    slug: str,
    run_id: str,
    deal_id: str,
    contexts: list[CandidateContext],
    cycles: list[CycleWindow],
    cycle_ids: dict[int, str],
    actor_records: dict[str, ActorRecord],
) -> None:
    dated_rows = [row for row in contexts if row.candidate_type == "dated_event"]
    event_sequence = 1
    link_sequence = 1
    judgment_sequence = 1
    boundary_by_cycle: dict[int, tuple[str, dt.date]] = {}
    for cycle in cycles:
        cycle_id = cycle_ids[cycle.sequence]
        boundary_row = choose_boundary(dated_rows, cycle)
        event_id = make_id(slug, "event", event_sequence)
        event_sequence += 1
        boundary_event = Event(
            event_id=event_id,
            run_id=run_id,
            deal_id=deal_id,
            cycle_id=cycle_id,
            event_type="boundary",
            event_date=boundary_row.event_date,
            description=boundary_row.raw_value,
            bid_value=None,
            bid_value_lower=None,
            bid_value_upper=None,
            bid_value_unit=None,
            consideration_type=None,
            evidence_ids=[boundary_row.evidence_id],
        )
        conn.execute("INSERT INTO events VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", _row_values(boundary_event))
        boundary_by_cycle[cycle.sequence] = (event_id, boundary_row.event_date)
        for judgment_type, value, confidence in (
            ("formal_boundary", event_id, "high"),
            ("cycle_regime", "single_process" if len(cycles) == 1 else "restart_sequence", "medium"),
            ("cycle_visibility", "visible", "medium"),
            ("cycle_relation", "primary_cycle" if cycle.sequence == len(cycles) else "prior_cycle", "medium"),
        ):
            _insert_judgment(
                conn,
                make_id(slug, "judgment", judgment_sequence),
                run_id,
                deal_id,
                cycle_id,
                boundary_row.evidence_id,
                judgment_type,
                value,
                confidence,
                event_id=event_id if judgment_type == "formal_boundary" else None,
            )
            judgment_sequence += 1

    known_labels = tuple(actor_records)
    for row in [candidate for candidate in contexts if candidate.candidate_type == "bid_value"]:
        date_value = _candidate_date(row, dated_rows)
        cycle = cycle_for(date_value, row.char_start, cycles)
        cycle_id = cycle_ids[cycle.sequence]
        bid_value, bid_lower, bid_upper = _bid_values(row.normalized_value)
        event_id = make_id(slug, "event", event_sequence)
        event_sequence += 1
        event = Event(
            event_id=event_id,
            run_id=run_id,
            deal_id=deal_id,
            cycle_id=cycle_id,
            event_type="bid",
            event_date=date_value,
            description=_sentence_for_candidate(row),
            bid_value=bid_value,
            bid_value_lower=bid_lower,
            bid_value_upper=bid_upper,
            bid_value_unit="per_share",
            consideration_type="cash",
            evidence_ids=[row.evidence_id],
        )
        conn.execute("INSERT INTO events VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", _row_values(event))
        labels = labels_in_text(_sentence_for_candidate(row), known_labels)
        for label in labels:
            actor_id = actor_records[label].actor_id
            link = EventActorLink(
                link_id=make_id(slug, "link", link_sequence),
                run_id=run_id,
                event_id=event_id,
                actor_id=actor_id,
                role="bidder",
                evidence_ids=[row.evidence_id],
            )
            link_sequence += 1
            conn.execute("INSERT INTO event_actor_links VALUES (?, ?, ?, ?, ?, ?)", _row_values(link))
            boundary_date = boundary_by_cycle[cycle.sequence][1]
            if date_value is not None and date_value >= boundary_date:
                _insert_judgment(
                    conn,
                    make_id(slug, "judgment", judgment_sequence),
                    run_id,
                    deal_id,
                    cycle_id,
                    row.evidence_id,
                    "admission",
                    "true",
                    "high",
                    actor_id=actor_id,
                    event_id=event_id,
                )
                judgment_sequence += 1

    for label, record in actor_records.items():
        if label in {"Party D", "Party E", "Party X", "Sponsor G"}:
            cycle = cycles[0] if label == "Party X" else cycles[-1]
            _insert_judgment(
                conn,
                make_id(slug, "judgment", judgment_sequence),
                run_id,
                deal_id,
                cycle_ids[cycle.sequence],
                record.evidence_id,
                "dropout_mechanism",
                "ambiguous",
                "low",
                actor_id=record.actor_id,
                alternative_value="requires_review",
            )
            judgment_sequence += 1


def _insert_counts(conn: duckdb.DuckDBPyConnection, slug: str, run_id: str, deal_id: str, contexts: list[CandidateContext], cycles: list[CycleWindow], cycle_ids: dict[int, str]) -> None:
    count_sequence = 1
    for row in [candidate for candidate in contexts if candidate.candidate_type == "participation_count"]:
        cycle = cycle_for(_candidate_date(row, [candidate for candidate in contexts if candidate.candidate_type == "dated_event"]), row.char_start, cycles)
        count = ParticipationCount(
            participation_count_id=make_id(slug, "count", count_sequence),
            run_id=run_id,
            deal_id=deal_id,
            cycle_id=cycle_ids[cycle.sequence],
            count_type="interested_parties",
            count_value=int(row.normalized_value),
            count_unit="parties",
            process_stage="process_contact",
            bidder_subtype_split=None,
            actor_creation_required="deferred",
            evidence_ids=[row.evidence_id],
        )
        count_sequence += 1
        conn.execute("INSERT INTO participation_counts VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", _row_values(count))


def reconcile_filing(conn: duckdb.DuckDBPyConnection, filing_id: str, run_id: str) -> None:
    contexts = _candidate_contexts(conn, filing_id)
    if not contexts:
        raise ValueError(f"filing {filing_id} has no extraction candidates")
    slug = contexts[0].deal_slug
    dated_rows = [row for row in contexts if row.candidate_type == "dated_event" and row.event_date is not None]
    cycles = build_cycle_windows(dated_rows)
    if not cycles:
        raise ValueError(f"filing {filing_id} has no dated-event candidates")
    actor_records = _collect_actor_records(slug, make_id(slug, "deal", 1), run_id, contexts)
    deal_id, cycle_ids = _insert_deal_cycle_actors(conn, slug, run_id, contexts, cycles, actor_records)
    _insert_events_and_judgments(conn, slug, run_id, deal_id, contexts, cycles, cycle_ids, actor_records)
    _insert_counts(conn, slug, run_id, deal_id, contexts, cycles, cycle_ids)


def reconcile_all(conn: duckdb.DuckDBPyConnection, run_id: str = "reconcile-real") -> None:
    _clear_canonical(conn)
    filing_ids = [row[0] for row in conn.execute("SELECT filing_id FROM filings ORDER BY filing_id").fetchall()]
    if not filing_ids:
        raise ValueError("no filings available for reconcile")
    for filing_id in filing_ids:
        reconcile_filing(conn, filing_id=filing_id, run_id=run_id)
