"""Hard-failure and review-item validation.

Validation is split into two lists. ``system_failures`` represents
structural breakage that must mark the run as ``failed_system``.
``review_items`` represents source-backed review burden that does not
block the run from publishing canonical rows.
"""

from __future__ import annotations

import csv
import json
from dataclasses import asdict, dataclass
from enum import StrEnum
from pathlib import Path

import duckdb

from sec_graph.schema import evidence_fingerprint, quote_hash

REPO_ROOT = Path(__file__).resolve().parents[3]


class HardCheck(StrEnum):
    CLAIM_DISPOSITION = "claim_disposition"
    COVERAGE_RESULT = "coverage_result"
    COVERAGE_REVIEW = "coverage_review"
    ROW_EVIDENCE = "row_evidence"
    CLAIM_EVIDENCE = "claim_evidence"
    SOURCE_TRUTH = "source_truth"
    EVIDENCE_FINGERPRINT = "evidence_fingerprint"
    PROJECTION_UNIT = "projection_unit"
    PROJECTION_REVIEW = "projection_review"
    STAGE_ARTIFACT_DIGEST = "stage_artifact_digest"


@dataclass(frozen=True)
class ValidationFinding:
    check: HardCheck
    table_name: str
    row_id: str
    detail: str


@dataclass(frozen=True)
class ValidationResult:
    system_failures: list[ValidationFinding]
    review_items: list[ValidationFinding]

    @property
    def passed(self) -> bool:
        return not self.system_failures

    @property
    def open_review_count(self) -> int:
        return len(self.review_items)


def validate_database(
    conn: duckdb.DuckDBPyConnection,
    *,
    raw_source_root: Path | None = None,
) -> ValidationResult:
    system_failures: list[ValidationFinding] = []
    review_items: list[ValidationFinding] = []

    system_failures.extend(_check_claim_dispositions(conn))
    system, review = _check_coverage_results(conn)
    system_failures.extend(system)
    review_items.extend(review)
    system_failures.extend(_check_claim_evidence(conn))
    system_failures.extend(_check_row_evidence(conn))
    system_failures.extend(_check_source_truth(conn, raw_source_root or REPO_ROOT))
    system, review = _check_projection_units(conn)
    system_failures.extend(system)
    review_items.extend(review)

    return ValidationResult(system_failures=system_failures, review_items=review_items)


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
    report = {
        "passed": result.passed,
        "system_failures": [asdict(item) for item in result.system_failures],
        "review_items": [asdict(item) for item in result.review_items],
    }
    (run_dir / "validation_report.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    with (run_dir / "validation_findings.csv").open(
        "w", newline="", encoding="utf-8"
    ) as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["severity", "check", "table_name", "row_id", "detail"],
        )
        writer.writeheader()
        for finding in result.system_failures:
            writer.writerow(
                {
                    "severity": "system_failure",
                    "check": finding.check,
                    "table_name": finding.table_name,
                    "row_id": finding.row_id,
                    "detail": finding.detail,
                }
            )
        for finding in result.review_items:
            writer.writerow(
                {
                    "severity": "review",
                    "check": finding.check,
                    "table_name": finding.table_name,
                    "row_id": finding.row_id,
                    "detail": finding.detail,
                }
            )
    return report


# --------------------------------------------------------------------------- #
# Claim-level checks                                                          #
# --------------------------------------------------------------------------- #


def _check_claim_dispositions(conn: duckdb.DuckDBPyConnection) -> list[ValidationFinding]:
    rows = conn.execute(
        """
        SELECT claims.claim_id, count(claim_dispositions.disposition_id)
        FROM claims
        LEFT JOIN claim_dispositions
          ON claim_dispositions.claim_id = claims.claim_id
         AND claim_dispositions.current = true
        GROUP BY claims.claim_id
        HAVING count(claim_dispositions.disposition_id) <> 1
        """
    ).fetchall()
    return [
        ValidationFinding(
            HardCheck.CLAIM_DISPOSITION,
            "claims",
            claim_id,
            f"current disposition count is {count}",
        )
        for claim_id, count in rows
    ]


def _check_claim_evidence(conn: duckdb.DuckDBPyConnection) -> list[ValidationFinding]:
    rows = conn.execute(
        """
        SELECT claims.claim_id
        FROM claims
        LEFT JOIN claim_evidence USING (claim_id)
        WHERE claim_evidence.claim_id IS NULL
        ORDER BY claims.claim_id
        """
    ).fetchall()
    return [
        ValidationFinding(
            HardCheck.CLAIM_EVIDENCE,
            "claims",
            row[0],
            "claim has no relational claim_evidence",
        )
        for row in rows
    ]


# --------------------------------------------------------------------------- #
# Coverage checks                                                             #
# --------------------------------------------------------------------------- #


def _check_coverage_results(
    conn: duckdb.DuckDBPyConnection,
) -> tuple[list[ValidationFinding], list[ValidationFinding]]:
    system_failures: list[ValidationFinding] = []
    review_items: list[ValidationFinding] = []

    count_rows = conn.execute(
        """
        SELECT coverage_obligations.obligation_id, count(coverage_results.coverage_result_id)
        FROM coverage_obligations
        LEFT JOIN coverage_results
          ON coverage_results.obligation_id = coverage_obligations.obligation_id
         AND coverage_results.current = true
        WHERE coverage_obligations.current = true
          AND coverage_obligations.applicability = 'applicable'
        GROUP BY coverage_obligations.obligation_id
        HAVING count(coverage_results.coverage_result_id) <> 1
        """
    ).fetchall()
    system_failures.extend(
        ValidationFinding(
            HardCheck.COVERAGE_RESULT,
            "coverage_obligations",
            obligation_id,
            f"current coverage result count is {count}",
        )
        for obligation_id, count in count_rows
    )

    unresolved_rows = conn.execute(
        """
        SELECT coverage_obligations.obligation_id, coverage_obligations.importance,
               coverage_results.result
        FROM coverage_obligations
        JOIN coverage_results
          ON coverage_results.obligation_id = coverage_obligations.obligation_id
         AND coverage_results.current = true
        WHERE coverage_obligations.current = true
          AND coverage_obligations.applicability = 'applicable'
          AND coverage_obligations.importance IN ('required', 'important')
          AND coverage_results.result <> 'claims_emitted'
        ORDER BY coverage_obligations.obligation_id
        """
    ).fetchall()
    review_items.extend(
        ValidationFinding(
            HardCheck.COVERAGE_REVIEW,
            "coverage_obligations",
            obligation_id,
            f"{importance} applicable coverage is unresolved with result {result}",
        )
        for obligation_id, importance, result in unresolved_rows
    )

    bad_not_applicable_rows = conn.execute(
        """
        SELECT coverage_obligations.obligation_id, coverage_results.coverage_result_id
        FROM coverage_obligations
        JOIN coverage_results
          ON coverage_results.obligation_id = coverage_obligations.obligation_id
         AND coverage_results.current = true
        WHERE coverage_obligations.current = true
          AND coverage_obligations.applicability = 'not_applicable'
        ORDER BY coverage_obligations.obligation_id
        """
    ).fetchall()
    system_failures.extend(
        ValidationFinding(
            HardCheck.COVERAGE_RESULT,
            "coverage_obligations",
            obligation_id,
            f"not_applicable obligation has current coverage result {coverage_result_id}",
        )
        for obligation_id, coverage_result_id in bad_not_applicable_rows
    )

    unlinked_claims_emitted = conn.execute(
        """
        SELECT coverage_results.obligation_id
        FROM coverage_results
        LEFT JOIN claim_coverage_links
          ON claim_coverage_links.obligation_id = coverage_results.obligation_id
         AND claim_coverage_links.current = true
        WHERE coverage_results.current = true
          AND coverage_results.result = 'claims_emitted'
        GROUP BY coverage_results.obligation_id, coverage_results.claim_count
        HAVING count(claim_coverage_links.claim_id) = 0
           OR count(claim_coverage_links.claim_id) <> coverage_results.claim_count
        """
    ).fetchall()
    system_failures.extend(
        ValidationFinding(
            HardCheck.COVERAGE_RESULT,
            "coverage_results",
            obligation_id,
            "claims_emitted has no linked claims or claim_count does not match persisted links",
        )
        for (obligation_id,) in unlinked_claims_emitted
    )

    unsupported_claims_emitted = conn.execute(
        """
        SELECT coverage_results.obligation_id, claim_coverage_links.claim_id
        FROM coverage_results
        JOIN claim_coverage_links
          ON claim_coverage_links.obligation_id = coverage_results.obligation_id
         AND claim_coverage_links.current = true
        LEFT JOIN claim_dispositions
          ON claim_dispositions.claim_id = claim_coverage_links.claim_id
         AND claim_dispositions.current = true
        WHERE coverage_results.current = true
          AND coverage_results.result = 'claims_emitted'
          AND (
            claim_dispositions.claim_id IS NULL
            OR claim_dispositions.disposition NOT IN ('supported', 'merged_duplicate')
          )
        ORDER BY coverage_results.obligation_id, claim_coverage_links.claim_id
        """
    ).fetchall()
    system_failures.extend(
        ValidationFinding(
            HardCheck.COVERAGE_RESULT,
            "claim_coverage_links",
            obligation_id,
            f"claims_emitted requires supported linked claims; linked claim {claim_id} is not supported",
        )
        for obligation_id, claim_id in unsupported_claims_emitted
    )

    bad_link_rows = conn.execute(
        """
        SELECT coverage_results.obligation_id, claim_coverage_links.claim_id
        FROM coverage_results
        JOIN coverage_obligations
          ON coverage_obligations.obligation_id = coverage_results.obligation_id
        JOIN claim_coverage_links
          ON claim_coverage_links.obligation_id = coverage_results.obligation_id
         AND claim_coverage_links.current = true
        JOIN claims
          ON claims.claim_id = claim_coverage_links.claim_id
        WHERE coverage_results.current = true
          AND (
            claim_coverage_links.run_id <> coverage_results.run_id
            OR claim_coverage_links.run_id <> claims.run_id
            OR claim_coverage_links.deal_slug <> claims.deal_slug
            OR claim_coverage_links.deal_slug <> coverage_obligations.deal_slug
            OR claim_coverage_links.claim_type <> coverage_obligations.expected_claim_type
            OR claim_coverage_links.claim_type <> claims.claim_type
            OR claims.run_id <> coverage_results.run_id
            OR claims.deal_slug <> coverage_obligations.deal_slug
            OR claims.region_id <> coverage_obligations.region_id
          )
        ORDER BY coverage_results.obligation_id, claim_coverage_links.claim_id
        """
    ).fetchall()
    system_failures.extend(
        ValidationFinding(
            HardCheck.COVERAGE_RESULT,
            "claim_coverage_links",
            obligation_id,
            f"linked claim {claim_id} does not match obligation run, deal, type, or region",
        )
        for obligation_id, claim_id in bad_link_rows
    )

    return system_failures, review_items


# --------------------------------------------------------------------------- #
# Row evidence and source truth                                               #
# --------------------------------------------------------------------------- #


def _check_row_evidence(conn: duckdb.DuckDBPyConnection) -> list[ValidationFinding]:
    failures: list[ValidationFinding] = []
    for table, id_col in (
        ("deals", "deal_id"),
        ("process_cycles", "cycle_id"),
        ("actors", "actor_id"),
        ("actor_relations", "relation_id"),
        ("events", "event_id"),
        ("event_actor_links", "link_id"),
        ("participation_counts", "participation_count_id"),
    ):
        rows = conn.execute(
            f"""
            SELECT {table}.{id_col}
            FROM {table}
            LEFT JOIN row_evidence
              ON row_evidence.row_table = ?
             AND row_evidence.row_id = {table}.{id_col}
            WHERE row_evidence.row_id IS NULL
            ORDER BY {table}.{id_col}
            """,
            [table],
        ).fetchall()
        failures.extend(
            ValidationFinding(
                HardCheck.ROW_EVIDENCE,
                table,
                row[0],
                "canonical row has no relational row_evidence",
            )
            for row in rows
        )
    return failures


def _check_source_truth(
    conn: duckdb.DuckDBPyConnection, raw_source_root: Path
) -> list[ValidationFinding]:
    failures: list[ValidationFinding] = []
    filing_text: dict[str, str] = {}
    for filing_id, source_path, raw_sha256 in conn.execute(
        "SELECT filing_id, source_path, raw_sha256 FROM filings"
    ).fetchall():
        if not source_path:
            failures.append(
                ValidationFinding(
                    HardCheck.SOURCE_TRUTH, "filings", filing_id, "missing source_path"
                )
            )
            continue
        path = _resolve_source_path(raw_source_root, source_path)
        if not path.exists():
            failures.append(
                ValidationFinding(
                    HardCheck.SOURCE_TRUTH,
                    "filings",
                    filing_id,
                    f"source file missing: {path}",
                )
            )
            continue
        text = path.read_text(encoding="utf-8")
        if quote_hash(text) != raw_sha256:
            failures.append(
                ValidationFinding(
                    HardCheck.SOURCE_TRUTH, "filings", filing_id, "raw_sha256 mismatch"
                )
            )
            continue
        filing_text[filing_id] = text

    for evidence_id, filing_id, char_start, char_end, quote_text, quote_text_hash, stored_fingerprint in conn.execute(
        """
        SELECT evidence_id, filing_id, char_start, char_end, quote_text,
               quote_text_hash, evidence_fingerprint
        FROM spans
        """
    ).fetchall():
        text = filing_text.get(filing_id)
        if text is None:
            continue
        if char_start < 0 or char_end < char_start or char_end > len(text):
            failures.append(
                ValidationFinding(
                    HardCheck.SOURCE_TRUTH,
                    "spans",
                    evidence_id,
                    "span coordinates out of bounds",
                )
            )
            continue
        if text[char_start:char_end] != quote_text:
            failures.append(
                ValidationFinding(
                    HardCheck.SOURCE_TRUTH,
                    "spans",
                    evidence_id,
                    "quote_text does not match source coordinates",
                )
            )
        if quote_hash(quote_text) != quote_text_hash:
            failures.append(
                ValidationFinding(
                    HardCheck.EVIDENCE_FINGERPRINT,
                    "spans",
                    evidence_id,
                    "quote_text_hash mismatch",
                )
            )
        expected = evidence_fingerprint(filing_id, char_start, char_end, quote_text_hash)
        if expected != stored_fingerprint:
            failures.append(
                ValidationFinding(
                    HardCheck.EVIDENCE_FINGERPRINT,
                    "spans",
                    evidence_id,
                    "location-aware evidence_fingerprint mismatch",
                )
            )
    return failures


# --------------------------------------------------------------------------- #
# Projection                                                                  #
# --------------------------------------------------------------------------- #


def _check_projection_units(
    conn: duckdb.DuckDBPyConnection,
) -> tuple[list[ValidationFinding], list[ValidationFinding]]:
    rows = conn.execute(
        """
        SELECT bidder_rows.bidder_row_id
        FROM bidder_rows
        LEFT JOIN projection_units USING (projection_unit_id)
        WHERE projection_units.projection_unit_id IS NULL
        """
    ).fetchall()
    system_failures = [
        ValidationFinding(
            HardCheck.PROJECTION_UNIT,
            "bidder_rows",
            row[0],
            "bidder row lacks actor-cycle projection unit",
        )
        for row in rows
    ]
    review_items = [
        ValidationFinding(
            HardCheck.PROJECTION_REVIEW,
            "review_rows",
            review_row_id,
            "projection depends on review-required judgment",
        )
        for (review_row_id,) in conn.execute(
            """
            SELECT review_row_id
            FROM review_rows
            WHERE review_status = 'open'
              AND review_type = 'judgment'
              AND severity IN ('review', 'info')
            ORDER BY review_row_id
            """
        ).fetchall()
    ]
    return system_failures, review_items


def _resolve_source_path(raw_source_root: Path, source_path: str) -> Path:
    candidate = Path(source_path)
    if candidate.is_absolute() and candidate.exists():
        return candidate
    rooted = raw_source_root / source_path
    if rooted.exists():
        return rooted
    return raw_source_root / candidate.name
