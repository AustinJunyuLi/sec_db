"""Hard validation checks for canonical tables."""

from __future__ import annotations

import csv
import json
import re
from dataclasses import asdict, dataclass
from enum import StrEnum
from pathlib import Path

import duckdb

from sec_graph.schema import quote_hash
from sec_graph.validate.flags import soft_flags

REPO_ROOT = Path(__file__).resolve().parents[3]

class HardCheck(StrEnum):
    REFERENTIAL_INTEGRITY = "referential_integrity"
    EVIDENCE_HASH = "evidence_hash"
    DATE_SANITY = "date_sanity"
    BID_BOUNDS = "bid_bounds"
    PROJECTION_ELIGIBILITY = "projection_eligibility"
    RELATION_STRUCTURE = "relation_structure"
    SOURCE_SCOPE = "source_scope"
    ID_FORMAT = "id_format"
    SOURCE_TRUTH = "source_truth"
    SPAN_PARENTAGE = "span_parentage"
    EVENT_SUBTYPE_EVIDENCE = "event_subtype_evidence"


# Closed admissive boundary subtype -> phrases that must appear in source text.
# A canonical event with one of these subtypes must reference at least one
# evidence span whose `quote_text` (or the candidate `raw_value` that produced
# it) contains one of the admissive phrases. Otherwise the event is a
# fabrication and validation MUST fail.
_ADMISSIVE_SUBTYPE_PHRASES: dict[str, tuple[str, ...]] = {
    "advancement_admitted": (
        "proceed to the final round",
        "request for submission of offers",
        "submitted proposals expressing their continued interest",
        "draft of the merger agreement was distributed",
        "intended to enter into a merger agreement",
        "best and final",
        "invited to submit final",
        "advanced to the next round",
    ),
    "exclusivity_grant": ("exclusivity",),
}


_NON_PARAGRAPH_SPAN_KINDS: frozenset[str] = frozenset(
    {"sentence", "clause", "phrase", "llm_extract"}
)


@dataclass(frozen=True)
class ValidationFailure:
    check: HardCheck
    table_name: str
    row_id: str
    detail: str


@dataclass(frozen=True)
class ValidationResult:
    hard_failures: list[ValidationFailure]

    @property
    def passed(self) -> bool:
        return not self.hard_failures


_ID_RE = re.compile(r"^[a-z0-9-]+_[a-z]+_\d+$")
_CANONICAL_EVIDENCE_TABLES = (
    ("deals", "deal_id"),
    ("process_cycles", "cycle_id"),
    ("actors", "actor_id"),
    ("actor_relations", "relation_id"),
    ("events", "event_id"),
    ("event_actor_links", "link_id"),
    ("judgments", "judgment_id"),
    ("participation_counts", "participation_count_id"),
)
_PROJECTION_NAME = "bidder_cycle_baseline_v1"


def _fail(check: HardCheck, table_name: str, row_id: str, detail: str) -> ValidationFailure:
    return ValidationFailure(check=check, table_name=table_name, row_id=row_id, detail=detail)


def _check_fk(conn: duckdb.DuckDBPyConnection) -> list[ValidationFailure]:
    failures: list[ValidationFailure] = []
    queries = [
        ("deals", "deal_id", "target_actor_id", "actors", "actor_id"),
        ("actors", "actor_id", "deal_id", "deals", "deal_id"),
        ("process_cycles", "cycle_id", "deal_id", "deals", "deal_id"),
        ("actor_relations", "relation_id", "deal_id", "deals", "deal_id"),
        ("actor_relations", "relation_id", "subject_actor_id", "actors", "actor_id"),
        ("actor_relations", "relation_id", "object_actor_id", "actors", "actor_id"),
        ("actor_relations", "relation_id", "cycle_id_first_observed", "process_cycles", "cycle_id"),
        ("actor_relations", "relation_id", "cycle_id_last_observed", "process_cycles", "cycle_id"),
        ("events", "event_id", "deal_id", "deals", "deal_id"),
        ("events", "event_id", "cycle_id", "process_cycles", "cycle_id"),
        ("event_actor_links", "link_id", "event_id", "events", "event_id"),
        ("event_actor_links", "link_id", "actor_id", "actors", "actor_id"),
        ("judgments", "judgment_id", "actor_id", "actors", "actor_id"),
        ("judgments", "judgment_id", "supersedes_judgment_id", "judgments", "judgment_id"),
        ("participation_counts", "participation_count_id", "deal_id", "deals", "deal_id"),
        ("participation_counts", "participation_count_id", "cycle_id", "process_cycles", "cycle_id"),
        ("participation_counts", "participation_count_id", "event_id", "events", "event_id"),
    ]
    for table, id_col, fk_col, target_table, target_col in queries:
        rows = conn.execute(
            f"""
            SELECT source.{id_col}, source.{fk_col}
            FROM {table} AS source
            LEFT JOIN {target_table} AS target
              ON source.{fk_col} = target.{target_col}
            WHERE source.{fk_col} IS NOT NULL AND target.{target_col} IS NULL
            """
        ).fetchall()
        for row_id, fk_value in rows:
            failures.append(_fail(HardCheck.REFERENTIAL_INTEGRITY, table, row_id, f"{fk_col}={fk_value} does not resolve"))
    return failures


def _check_array_fks(conn: duckdb.DuckDBPyConnection) -> list[ValidationFailure]:
    failures: list[ValidationFailure] = []
    actor_ids = {row[0] for row in conn.execute("SELECT actor_id FROM actors").fetchall()}
    rows = conn.execute("SELECT participation_count_id, named_subset_actor_ids FROM participation_counts").fetchall()
    for count_id, actor_subset in rows:
        for actor_id in actor_subset:
            if actor_id not in actor_ids:
                failures.append(
                    _fail(
                        HardCheck.REFERENTIAL_INTEGRITY,
                        "participation_counts",
                        count_id,
                        f"named_subset_actor_ids contains unresolved actor_id={actor_id}",
                    )
                )
    return failures


def _check_evidence(conn: duckdb.DuckDBPyConnection) -> list[ValidationFailure]:
    failures: list[ValidationFailure] = []
    spans = {
        row[0]: (row[1], row[2])
        for row in conn.execute("SELECT evidence_id, quote_text, quote_hash FROM spans").fetchall()
    }
    for table, id_col in _CANONICAL_EVIDENCE_TABLES:
        for row_id, evidence_ids in conn.execute(f"SELECT {id_col}, evidence_ids FROM {table}").fetchall():
            if not evidence_ids:
                failures.append(_fail(HardCheck.EVIDENCE_HASH, table, row_id, "missing evidence_ids"))
                continue
            for evidence_id in evidence_ids:
                if evidence_id not in spans:
                    failures.append(_fail(HardCheck.EVIDENCE_HASH, table, row_id, f"{evidence_id} does not resolve"))
                    continue
                quote_text, expected_hash = spans[evidence_id]
                if quote_hash(quote_text) != expected_hash:
                    failures.append(_fail(HardCheck.EVIDENCE_HASH, table, row_id, f"{evidence_id} quote_hash mismatch"))
    return failures


def _check_dates(conn: duckdb.DuckDBPyConnection) -> list[ValidationFailure]:
    rows = conn.execute(
        """
        SELECT events.event_id, events.event_date, process_cycles.start_date
        FROM events
        JOIN process_cycles USING (cycle_id)
        WHERE events.event_date IS NOT NULL
          AND process_cycles.start_date IS NOT NULL
          AND events.event_date < process_cycles.start_date
        """
    ).fetchall()
    return [_fail(HardCheck.DATE_SANITY, "events", row[0], f"{row[1]} before cycle start {row[2]}") for row in rows]


def _check_bid_bounds(conn: duckdb.DuckDBPyConnection) -> list[ValidationFailure]:
    rows = conn.execute(
        """
        SELECT event_id, bid_value, bid_value_lower, bid_value_upper
        FROM events
        WHERE bid_value IS NOT NULL
          AND (
            (bid_value_lower IS NOT NULL AND bid_value < bid_value_lower)
            OR (bid_value_upper IS NOT NULL AND bid_value > bid_value_upper)
          )
        """
    ).fetchall()
    return [
        _fail(HardCheck.BID_BOUNDS, "events", row[0], f"bid_value={row[1]} outside [{row[2]}, {row[3]}]")
        for row in rows
    ]


def _latest_projection_actor_ids(conn: duckdb.DuckDBPyConnection) -> dict[str, bool]:
    rows = conn.execute(
        """
        SELECT judgment_id, actor_id, included, supersedes_judgment_id
        FROM judgments
        WHERE judgment_kind = 'projection_eligibility'
          AND projection_name = ?
        ORDER BY created_at, judgment_id
        """,
        [_PROJECTION_NAME],
    ).fetchall()
    superseded = {row[3] for row in rows if row[3] is not None}
    return {actor_id: included for judgment_id, actor_id, included, _ in rows if judgment_id not in superseded}


def _check_projection_eligibility(conn: duckdb.DuckDBPyConnection) -> list[ValidationFailure]:
    failures: list[ValidationFailure] = []
    current = _latest_projection_actor_ids(conn)
    actor_rows = conn.execute(
        """
        SELECT DISTINCT actors.actor_id, actors.actor_kind, actors.observability
        FROM actors
        JOIN event_actor_links USING (actor_id)
        WHERE event_actor_links.role IN ('bid_submitter', 'potential_buyer', 'offeror')
        ORDER BY actors.actor_id
        """
    ).fetchall()
    for actor_id, actor_kind, observability in actor_rows:
        if actor_id not in current:
            failures.append(_fail(HardCheck.PROJECTION_ELIGIBILITY, "actors", actor_id, "missing current projection_eligibility"))
        if actor_kind == "vehicle" and current.get(actor_id) is True:
            failures.append(
                _fail(
                    HardCheck.PROJECTION_ELIGIBILITY,
                    "actors",
                    actor_id,
                    "vehicle actor cannot enter bidder_cycle_baseline_v1",
                )
            )
        if observability == "count_only" and current.get(actor_id) is True:
            failures.append(
                _fail(
                    HardCheck.PROJECTION_ELIGIBILITY,
                    "actors",
                    actor_id,
                    "count-only actor cannot enter bidder_cycle_baseline_v1",
                )
            )
    vehicle_rows = conn.execute(
        """
        SELECT actors.actor_id
        FROM judgments
        JOIN actors ON actors.actor_id = judgments.actor_id
        WHERE judgments.judgment_kind = 'projection_eligibility'
          AND judgments.projection_name = ?
          AND judgments.included = true
          AND actors.actor_kind = 'vehicle'
        ORDER BY actors.actor_id
        """,
        [_PROJECTION_NAME],
    ).fetchall()
    for (actor_id,) in vehicle_rows:
        if not any(failure.table_name == "actors" and failure.row_id == actor_id for failure in failures):
            failures.append(
                _fail(
                    HardCheck.PROJECTION_ELIGIBILITY,
                    "actors",
                    actor_id,
                    "vehicle actor cannot enter bidder_cycle_baseline_v1",
                )
            )
    return failures


def _check_relation_structure(conn: duckdb.DuckDBPyConnection) -> list[ValidationFailure]:
    failures: list[ValidationFailure] = []
    rows = conn.execute(
        """
        SELECT relation_id
        FROM actor_relations
        WHERE cycle_id_first_observed IS NULL
          AND effective_date_first IS NULL
        """
    ).fetchall()
    for (relation_id,) in rows:
        failures.append(
            _fail(
                HardCheck.RELATION_STRUCTURE,
                "actor_relations",
                relation_id,
                "actor relation lacks cycle/date first-observed marker",
            )
        )
    member_rows = conn.execute(
        """
        SELECT link_id, actor_id
        FROM event_actor_links
        WHERE role = 'group_member'
        ORDER BY link_id
        """
    ).fetchall()
    for link_id, actor_id in member_rows:
        relation = conn.execute(
            """
            SELECT relation_id
            FROM actor_relations
            WHERE subject_actor_id = ?
              AND relation_type = 'member_of'
            LIMIT 1
            """,
            [actor_id],
        ).fetchone()
        if relation is None:
            failures.append(_fail(HardCheck.RELATION_STRUCTURE, "event_actor_links", link_id, "group event member lacks active member_of relation"))
    return failures


def _check_source_scope(conn: duckdb.DuckDBPyConnection) -> list[ValidationFailure]:
    failures: list[ValidationFailure] = []
    rows = conn.execute(
        """
        SELECT judgments.judgment_id, actors.actor_id, filings.process_scope
        FROM judgments
        JOIN actors USING (actor_id)
        JOIN deals USING (deal_id)
        JOIN filings USING (deal_slug)
        WHERE judgments.judgment_kind = 'projection_eligibility'
          AND judgments.projection_name = ?
          AND judgments.included = true
          AND filings.process_scope <> 'target_full_proxy'
        ORDER BY judgments.judgment_id
        """,
        [_PROJECTION_NAME],
    ).fetchall()
    for judgment_id, actor_id, process_scope in rows:
        failures.append(
            _fail(
                HardCheck.SOURCE_SCOPE,
                "judgments",
                judgment_id,
                f"process_scope={process_scope} blocks baseline projection for actor_id={actor_id}",
            )
        )
    return failures


def _check_id_format(conn: duckdb.DuckDBPyConnection) -> list[ValidationFailure]:
    failures: list[ValidationFailure] = []
    for table, id_col in _CANONICAL_EVIDENCE_TABLES + (("filings", "filing_id"), ("paragraphs", "paragraph_id"), ("spans", "evidence_id")):
        for (row_id,) in conn.execute(f"SELECT {id_col} FROM {table}").fetchall():
            if not _ID_RE.match(row_id):
                failures.append(_fail(HardCheck.ID_FORMAT, table, row_id, "ID does not match {slug}_{type}_{sequence}"))
    return failures


def _resolve_source_path(raw_source_root: Path, source_path: str) -> Path:
    candidate = Path(source_path)
    if candidate.is_absolute() and candidate.exists():
        return candidate
    rooted = raw_source_root / candidate.name
    if rooted.exists():
        return rooted
    rooted_full = raw_source_root / source_path
    if rooted_full.exists():
        return rooted_full
    return candidate  # Will trigger an unreadable-source failure below.


def _check_span_parentage(conn: duckdb.DuckDBPyConnection) -> list[ValidationFailure]:
    failures: list[ValidationFailure] = []
    rows = conn.execute(
        "SELECT evidence_id, filing_id, span_kind, parent_evidence_id FROM spans"
    ).fetchall()
    seed_ids = {
        row[0]
        for row in conn.execute(
            "SELECT evidence_id FROM spans WHERE span_kind = 'paragraph_seed'"
        ).fetchall()
    }
    for evidence_id, filing_id, span_kind, parent_evidence_id in rows:
        if span_kind == "paragraph_seed":
            continue
        if span_kind not in _NON_PARAGRAPH_SPAN_KINDS:
            continue
        if parent_evidence_id is None:
            failures.append(
                _fail(
                    HardCheck.SPAN_PARENTAGE,
                    "spans",
                    evidence_id,
                    f"filing_id={filing_id} span_kind={span_kind} missing parent_evidence_id",
                )
            )
            continue
        if parent_evidence_id not in seed_ids:
            failures.append(
                _fail(
                    HardCheck.SPAN_PARENTAGE,
                    "spans",
                    evidence_id,
                    (
                        f"filing_id={filing_id} parent_evidence_id={parent_evidence_id} "
                        "does not resolve to a paragraph_seed span"
                    ),
                )
            )
    return failures


def _check_source_truth(
    conn: duckdb.DuckDBPyConnection, raw_source_root: Path
) -> list[ValidationFailure]:
    failures: list[ValidationFailure] = []
    filing_rows = conn.execute(
        "SELECT filing_id, deal_slug, source_path, raw_sha256 FROM filings"
    ).fetchall()
    raw_text_by_filing: dict[str, str] = {}
    for filing_id, deal_slug, source_path, raw_sha256 in filing_rows:
        if not source_path:
            failures.append(
                _fail(
                    HardCheck.SOURCE_TRUTH,
                    "filings",
                    filing_id,
                    "filing has no source_path; cannot verify spans against raw source",
                )
            )
            continue
        resolved = _resolve_source_path(raw_source_root, source_path)
        if not resolved.exists():
            failures.append(
                _fail(
                    HardCheck.SOURCE_TRUTH,
                    "filings",
                    filing_id,
                    (
                        f"raw source not found at {resolved} (deal_slug={deal_slug}); "
                        f"raw_source_root={raw_source_root}"
                    ),
                )
            )
            continue
        raw_text = resolved.read_text(encoding="utf-8")
        actual_sha = quote_hash(raw_text)
        if actual_sha != raw_sha256:
            failures.append(
                _fail(
                    HardCheck.SOURCE_TRUTH,
                    "filings",
                    filing_id,
                    (
                        f"raw source sha256 mismatch at {resolved}: "
                        f"stored={raw_sha256} actual={actual_sha}"
                    ),
                )
            )
            continue
        raw_text_by_filing[filing_id] = raw_text

    span_rows = conn.execute(
        """
        SELECT evidence_id, filing_id, span_basis, span_kind,
               char_start, char_end, quote_text, quote_hash
        FROM spans
        """
    ).fetchall()
    for (
        evidence_id,
        filing_id,
        span_basis,
        span_kind,
        char_start,
        char_end,
        quote_text,
        stored_hash,
    ) in span_rows:
        raw_text = raw_text_by_filing.get(filing_id)
        if raw_text is None:
            continue  # Already reported via filing-level failure.
        if char_start < 0 or char_end < char_start or char_end > len(raw_text):
            failures.append(
                _fail(
                    HardCheck.SOURCE_TRUTH,
                    "spans",
                    evidence_id,
                    (
                        f"filing_id={filing_id} char_start={char_start} char_end={char_end} "
                        f"out of bounds for raw source of length {len(raw_text)}"
                    ),
                )
            )
            continue
        if quote_hash(quote_text) != stored_hash:
            failures.append(
                _fail(
                    HardCheck.SOURCE_TRUTH,
                    "spans",
                    evidence_id,
                    (
                        f"filing_id={filing_id} stored quote_hash does not match "
                        f"sha256(quote_text)"
                    ),
                )
            )
            continue
        if span_basis == "raw_md":
            slice_text = raw_text[char_start:char_end]
            if quote_text != slice_text:
                failures.append(
                    _fail(
                        HardCheck.SOURCE_TRUTH,
                        "spans",
                        evidence_id,
                        (
                            f"filing_id={filing_id} stored quote does not equal "
                            f"source slice at given coordinates "
                            f"[{char_start}:{char_end}] (basis=raw_md)"
                        ),
                    )
                )
    return failures


def _check_event_subtype_evidence(
    conn: duckdb.DuckDBPyConnection,
) -> list[ValidationFailure]:
    """Reject canonical admission events without supporting source-quote evidence.

    Surgical additive check (Phase 5): for every canonical event whose
    `event_subtype` belongs to the admissive set, at least one of the event's
    referenced evidence spans must contain admissive language in either the
    span's `quote_text` or the candidate `raw_value` that produced that span.
    Without this check, reconcile could fabricate `advancement_admitted`
    boundaries from arbitrary cycle-tail rows; the spec forbids that
    (`docs/spec.md` §1A "Events" and §18.1 "Avoid these traps").
    """
    failures: list[ValidationFailure] = []
    rows = conn.execute(
        """
        SELECT event_id, event_subtype, evidence_ids
        FROM events
        WHERE event_subtype IN ('advancement_admitted', 'exclusivity_grant')
        """
    ).fetchall()
    if not rows:
        return failures
    span_quotes = {
        row[0]: row[1]
        for row in conn.execute("SELECT evidence_id, quote_text FROM spans").fetchall()
    }
    candidate_quotes_by_span: dict[str, list[str]] = {}
    for evidence_array, raw_value in conn.execute(
        "SELECT evidence_ids, raw_value FROM candidates"
    ).fetchall():
        for evidence_id in evidence_array or []:
            candidate_quotes_by_span.setdefault(evidence_id, []).append(raw_value)
    for event_id, subtype, evidence_ids in rows:
        phrases = _ADMISSIVE_SUBTYPE_PHRASES.get(subtype, ())
        if not phrases:
            continue
        admissive = False
        for evidence_id in evidence_ids or []:
            haystacks: list[str] = []
            if evidence_id in span_quotes:
                haystacks.append(span_quotes[evidence_id])
            haystacks.extend(candidate_quotes_by_span.get(evidence_id, []))
            for haystack in haystacks:
                folded = haystack.casefold()
                if any(phrase in folded for phrase in phrases):
                    admissive = True
                    break
            if admissive:
                break
        if not admissive:
            failures.append(
                _fail(
                    HardCheck.EVENT_SUBTYPE_EVIDENCE,
                    "events",
                    event_id,
                    (
                        f"event_subtype={subtype} is admissive but no referenced evidence "
                        f"quote contains admissive language; refusing fabrication"
                    ),
                )
            )
    return failures


def validate_database(
    conn: duckdb.DuckDBPyConnection,
    *,
    raw_source_root: Path | None = None,
) -> ValidationResult:
    failures: list[ValidationFailure] = []
    failures.extend(_check_fk(conn))
    failures.extend(_check_array_fks(conn))
    failures.extend(_check_evidence(conn))
    failures.extend(_check_dates(conn))
    failures.extend(_check_bid_bounds(conn))
    failures.extend(_check_projection_eligibility(conn))
    failures.extend(_check_relation_structure(conn))
    failures.extend(_check_source_scope(conn))
    failures.extend(_check_id_format(conn))
    failures.extend(_check_span_parentage(conn))
    failures.extend(_check_event_subtype_evidence(conn))
    failures.extend(_check_source_truth(conn, raw_source_root or REPO_ROOT))
    return ValidationResult(hard_failures=failures)


def write_validation_outputs(
    conn: duckdb.DuckDBPyConnection,
    run_dir: Path,
    *,
    raw_source_root: Path | None = None,
    allow_existing: bool = False,
) -> dict[str, object]:
    if run_dir.exists() and not allow_existing:
        raise FileExistsError(f"{run_dir} already exists")
    run_dir.mkdir(parents=True, exist_ok=allow_existing)
    result = validate_database(conn, raw_source_root=raw_source_root)
    flags = soft_flags(conn)
    report = {
        "passed": result.passed,
        "hard_failures": [asdict(failure) for failure in result.hard_failures],
        "soft_flag_count": len(flags),
    }
    (run_dir / "validation_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    with (run_dir / "ambiguity_queue.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["flag_type", "table_name", "row_id", "detail"])
        writer.writeheader()
        for flag in flags:
            writer.writerow(asdict(flag))
    return report
