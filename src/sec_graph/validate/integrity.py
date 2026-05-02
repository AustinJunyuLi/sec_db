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


class HardCheck(StrEnum):
    REFERENTIAL_INTEGRITY = "referential_integrity"
    EVIDENCE_HASH = "evidence_hash"
    DATE_SANITY = "date_sanity"
    BID_BOUNDS = "bid_bounds"
    REQUIRED_JUDGMENTS = "required_judgments"
    ID_FORMAT = "id_format"


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
    ("events", "event_id"),
    ("event_actor_links", "link_id"),
    ("judgments", "judgment_id"),
    ("participation_counts", "participation_count_id"),
)
_REQUIRED_JUDGMENTS = {"formal_boundary", "cycle_regime", "cycle_visibility", "cycle_relation"}


def _fail(check: HardCheck, table_name: str, row_id: str, detail: str) -> ValidationFailure:
    return ValidationFailure(check=check, table_name=table_name, row_id=row_id, detail=detail)


def _check_fk(conn: duckdb.DuckDBPyConnection) -> list[ValidationFailure]:
    failures: list[ValidationFailure] = []
    queries = [
        ("deals", "deal_id", "target_actor_id", "actors", "actor_id"),
        ("actors", "actor_id", "deal_id", "deals", "deal_id"),
        ("process_cycles", "cycle_id", "deal_id", "deals", "deal_id"),
        ("events", "event_id", "deal_id", "deals", "deal_id"),
        ("events", "event_id", "cycle_id", "process_cycles", "cycle_id"),
        ("event_actor_links", "link_id", "event_id", "events", "event_id"),
        ("event_actor_links", "link_id", "actor_id", "actors", "actor_id"),
        ("judgments", "judgment_id", "deal_id", "deals", "deal_id"),
        ("participation_counts", "participation_count_id", "cycle_id", "process_cycles", "cycle_id"),
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


def _check_required_judgments(conn: duckdb.DuckDBPyConnection) -> list[ValidationFailure]:
    failures: list[ValidationFailure] = []
    for (cycle_id,) in conn.execute("SELECT cycle_id FROM process_cycles ORDER BY cycle_id").fetchall():
        types = {
            row[0]
            for row in conn.execute(
                "SELECT judgment_type FROM judgments WHERE cycle_id = ?",
                [cycle_id],
            ).fetchall()
        }
        missing = sorted(_REQUIRED_JUDGMENTS - types)
        if missing:
            failures.append(_fail(HardCheck.REQUIRED_JUDGMENTS, "process_cycles", cycle_id, f"missing {missing}"))
    return failures


def _check_id_format(conn: duckdb.DuckDBPyConnection) -> list[ValidationFailure]:
    failures: list[ValidationFailure] = []
    for table, id_col in _CANONICAL_EVIDENCE_TABLES + (("filings", "filing_id"), ("paragraphs", "paragraph_id"), ("spans", "evidence_id")):
        for (row_id,) in conn.execute(f"SELECT {id_col} FROM {table}").fetchall():
            if not _ID_RE.match(row_id):
                failures.append(_fail(HardCheck.ID_FORMAT, table, row_id, "ID does not match {slug}_{type}_{sequence}"))
    return failures


def validate_database(conn: duckdb.DuckDBPyConnection) -> ValidationResult:
    failures: list[ValidationFailure] = []
    failures.extend(_check_fk(conn))
    failures.extend(_check_evidence(conn))
    failures.extend(_check_dates(conn))
    failures.extend(_check_bid_bounds(conn))
    failures.extend(_check_required_judgments(conn))
    failures.extend(_check_id_format(conn))
    return ValidationResult(hard_failures=failures)


def write_validation_outputs(conn: duckdb.DuckDBPyConnection, run_dir: Path) -> dict[str, object]:
    run_dir.mkdir(parents=True, exist_ok=True)
    result = validate_database(conn)
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
