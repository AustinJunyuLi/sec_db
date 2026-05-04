"""Hard semantic validation checks."""

from __future__ import annotations

import csv
import datetime as dt
import json
import re
from dataclasses import asdict, dataclass
from enum import StrEnum
from pathlib import Path

import duckdb

from sec_graph.schema import evidence_fingerprint, quote_hash

REPO_ROOT = Path(__file__).resolve().parents[3]


class HardCheck(StrEnum):
    CLAIM_DISPOSITION = "claim_disposition"
    COVERAGE_RESULT = "coverage_result"
    ROW_EVIDENCE = "row_evidence"
    CLAIM_EVIDENCE = "claim_evidence"
    SOURCE_TRUTH = "source_truth"
    EVIDENCE_FINGERPRINT = "evidence_fingerprint"
    SEMANTIC_CLAIM_EVIDENCE = "semantic_claim_evidence"
    PROJECTION_UNIT = "projection_unit"
    RULES_ONLY_SOUND = "rules_only_sound"
    STAGE_ARTIFACT_DIGEST = "stage_artifact_digest"


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


def validate_database(conn: duckdb.DuckDBPyConnection, *, raw_source_root: Path | None = None) -> ValidationResult:
    failures: list[ValidationFailure] = []
    failures.extend(_check_claim_dispositions(conn))
    failures.extend(_check_coverage_results(conn))
    failures.extend(_check_claim_evidence(conn))
    failures.extend(_check_semantic_claim_evidence(conn))
    failures.extend(_check_row_evidence(conn))
    failures.extend(_check_source_truth(conn, raw_source_root or REPO_ROOT))
    failures.extend(_check_projection_units(conn))
    return ValidationResult(failures)


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
    report = {"passed": result.passed, "hard_failures": [asdict(item) for item in result.hard_failures]}
    (run_dir / "validation_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    with (run_dir / "ambiguity_queue.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["check", "table_name", "row_id", "detail"])
        writer.writeheader()
        for failure in result.hard_failures:
            writer.writerow(
                {
                    "check": failure.check,
                    "table_name": failure.table_name,
                    "row_id": failure.row_id,
                    "detail": failure.detail,
                }
            )
    return report


def _check_claim_dispositions(conn: duckdb.DuckDBPyConnection) -> list[ValidationFailure]:
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
        ValidationFailure(HardCheck.CLAIM_DISPOSITION, "claims", claim_id, f"current disposition count is {count}")
        for claim_id, count in rows
    ]


def _check_coverage_results(conn: duckdb.DuckDBPyConnection) -> list[ValidationFailure]:
    """Every applicable+current obligation must have exactly one current result.

    Inapplicable obligations are recorded for audit but do not require a
    coverage_result; the LLM never sees them and Python never invents a
    ``missed`` outcome from their absence.
    """
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
    failures = [
        ValidationFailure(HardCheck.COVERAGE_RESULT, "coverage_obligations", obligation_id, f"current coverage result count is {count}")
        for obligation_id, count in count_rows
    ]
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
    failures.extend(
        ValidationFailure(
            HardCheck.COVERAGE_RESULT,
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
    failures.extend(
        ValidationFailure(
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
    failures.extend(
        ValidationFailure(
            HardCheck.COVERAGE_RESULT,
            "coverage_results",
            obligation_id,
            "claims_emitted has no linked claims or claim_count does not match persisted links",
        )
        for (obligation_id,) in unlinked_claims_emitted
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
    failures.extend(
        ValidationFailure(
            HardCheck.COVERAGE_RESULT,
            "claim_coverage_links",
            obligation_id,
            f"linked claim {claim_id} does not match obligation run, deal, type, or region",
        )
        for obligation_id, claim_id in bad_link_rows
    )
    return failures


def _check_claim_evidence(conn: duckdb.DuckDBPyConnection) -> list[ValidationFailure]:
    rows = conn.execute(
        """
        SELECT claims.claim_id
        FROM claims
        LEFT JOIN claim_evidence USING (claim_id)
        WHERE claim_evidence.claim_id IS NULL
        ORDER BY claims.claim_id
        """
    ).fetchall()
    return [ValidationFailure(HardCheck.CLAIM_EVIDENCE, "claims", row[0], "claim has no relational claim_evidence") for row in rows]


def _check_semantic_claim_evidence(conn: duckdb.DuckDBPyConnection) -> list[ValidationFailure]:
    failures: list[ValidationFailure] = []
    failures.extend(_check_bid_claim_semantics(conn))
    failures.extend(_check_actor_relation_claim_semantics(conn))
    return failures


def _check_bid_claim_semantics(conn: duckdb.DuckDBPyConnection) -> list[ValidationFailure]:
    rows = conn.execute(
        """
        SELECT bid_claims.claim_id, bid_claims.bidder_label, bid_claims.bid_date,
               bid_claims.bid_value, bid_claims.bid_value_lower,
               bid_claims.bid_value_upper, bid_claims.bid_stage,
               claims.quote_text, claims.raw_value
        FROM bid_claims
        JOIN claims USING (claim_id)
        ORDER BY bid_claims.claim_id
        """
    ).fetchall()
    failures: list[ValidationFailure] = []
    for claim_id, bidder_label, bid_date, bid_value, bid_value_lower, bid_value_upper, bid_stage, quote_text, raw_value in rows:
        missing: list[str] = []
        if not _contains_phrase(quote_text, bidder_label):
            missing.append("bidder_label")
        if bid_date is None or not _date_supported_by_quote(bid_date, quote_text):
            missing.append("bid_date")
        values = [value for value in (bid_value, bid_value_lower, bid_value_upper) if value is not None]
        if not values or not any(_number_supported_by_quote(float(value), quote_text) for value in values):
            missing.append("bid_value")
        if not _bid_context_supported_by_quote(str(bid_stage), quote_text):
            missing.append("bid_context")
        if missing:
            failures.append(
                ValidationFailure(
                    HardCheck.SEMANTIC_CLAIM_EVIDENCE,
                    "bid_claims",
                    claim_id,
                    (
                        "bid claim quote_text does not support "
                        f"{', '.join(missing)}; raw_value={raw_value!r}"
                    ),
                )
            )
    return failures


def _check_actor_relation_claim_semantics(conn: duckdb.DuckDBPyConnection) -> list[ValidationFailure]:
    rows = conn.execute(
        """
        SELECT actor_relation_claims.claim_id, subject_label, object_label,
               relation_type, role_detail, claims.quote_text, claims.raw_value
        FROM actor_relation_claims
        JOIN claims USING (claim_id)
        ORDER BY actor_relation_claims.claim_id
        """
    ).fetchall()
    failures: list[ValidationFailure] = []
    for claim_id, subject_label, object_label, relation_type, role_detail, quote_text, raw_value in rows:
        missing: list[str] = []
        if not _contains_phrase(quote_text, subject_label):
            missing.append("subject_label")
        if not _contains_phrase(quote_text, object_label):
            missing.append("object_label")
        if not _relation_supported_by_quote(str(relation_type), role_detail, quote_text):
            missing.append("relation_type")
        if missing:
            failures.append(
                ValidationFailure(
                    HardCheck.SEMANTIC_CLAIM_EVIDENCE,
                    "actor_relation_claims",
                    claim_id,
                    (
                        "actor relation quote_text does not support "
                        f"{', '.join(missing)}; raw_value={raw_value!r}"
                    ),
                )
            )
    return failures


def _check_row_evidence(conn: duckdb.DuckDBPyConnection) -> list[ValidationFailure]:
    failures: list[ValidationFailure] = []
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
            ValidationFailure(HardCheck.ROW_EVIDENCE, table, row[0], "canonical row has no relational row_evidence")
            for row in rows
        )
    return failures


def _contains_phrase(text: str | None, phrase: str | None) -> bool:
    if not text or not phrase:
        return False
    return _normalize_text(phrase) in _normalize_text(text)


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value.casefold().replace("-", " ").replace("_", " ")).strip()


def _date_supported_by_quote(value: object, quote_text: str | None) -> bool:
    if not quote_text:
        return False
    parsed = _coerce_date(value)
    if parsed is None:
        return False
    folded = quote_text.casefold()
    if parsed.isoformat() in folded:
        return True
    month_name = parsed.strftime("%B").casefold()
    month_abbr = parsed.strftime("%b").casefold()
    has_month = month_name in folded or month_abbr in folded or str(parsed.month) in _numeric_tokens(folded)
    return str(parsed.year) in folded and has_month and str(parsed.day) in _numeric_tokens(folded)


def _coerce_date(value: object) -> dt.date | None:
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    if isinstance(value, str):
        try:
            return dt.date.fromisoformat(value)
        except ValueError:
            return None
    return None


def _numeric_tokens(value: str) -> set[str]:
    return {token.lstrip("0") or "0" for token in re.findall(r"\d+", value)}


def _number_supported_by_quote(value: float, quote_text: str | None) -> bool:
    if not quote_text:
        return False
    tokens = _numeric_tokens(quote_text)
    candidates = {
        f"{value:g}",
        f"{value:.1f}",
        f"{value:.2f}",
    }
    if value.is_integer():
        candidates.add(str(int(value)))
    normalized_candidates = {candidate.rstrip("0").rstrip(".") for candidate in candidates}
    quote_decimal_values = {match.rstrip("0").rstrip(".") for match in re.findall(r"\d+(?:\.\d+)?", quote_text)}
    return bool(normalized_candidates & quote_decimal_values) or str(int(value)) in tokens


def _bid_context_supported_by_quote(bid_stage: str, quote_text: str | None) -> bool:
    if not quote_text:
        return False
    folded = _normalize_text(quote_text)
    context_terms = {
        "bid",
        "offer",
        "proposal",
        "submitted",
        "proposed",
        "indication of interest",
    }
    if bid_stage and bid_stage != "unspecified":
        context_terms.add(bid_stage.replace("_", " "))
    return any(term in folded for term in context_terms)


def _relation_supported_by_quote(relation_type: str, role_detail: str | None, quote_text: str | None) -> bool:
    if not quote_text:
        return False
    folded = _normalize_text(quote_text)
    terms = {relation_type.replace("_", " ")}
    if role_detail:
        terms.add(role_detail)
    relation_synonyms = {
        "acquisition_vehicle_of": ("acquisition vehicle", "vehicle of"),
        "member_of": ("member of", "part of", "together we refer", "who together", "together as"),
        "affiliate_of": ("affiliate of", "affiliated with"),
        "controls": ("controls", "controlled by", "purchased by", "acquired by", "owned by"),
        "advises": ("advisor", "adviser", "advises"),
        "finances": ("financing", "finances", "provide capital", "capital required", "financing letter"),
        "supports": ("support", "supports", "guarantee", "guarantees"),
        "voting_support_for": ("voting agreement", "support agreement", "vote in favor", "agreed to vote", "voting and support"),
        "rollover_holder_for": ("rollover", "rolled", "contribute", "retain equity", "equity rollover"),
        "committee_member_of": ("committee", "member", "composed of", "appointed", "added"),
        "recused_from": ("recuse", "recused", "exclude", "excluded", "not participate"),
    }
    terms.update(relation_synonyms.get(relation_type, ()))
    return any(_normalize_text(term) in folded for term in terms if term)


def _check_source_truth(conn: duckdb.DuckDBPyConnection, raw_source_root: Path) -> list[ValidationFailure]:
    failures: list[ValidationFailure] = []
    filing_text: dict[str, str] = {}
    for filing_id, source_path, raw_sha256 in conn.execute("SELECT filing_id, source_path, raw_sha256 FROM filings").fetchall():
        if not source_path:
            failures.append(ValidationFailure(HardCheck.SOURCE_TRUTH, "filings", filing_id, "missing source_path"))
            continue
        path = _resolve_source_path(raw_source_root, source_path)
        if not path.exists():
            failures.append(ValidationFailure(HardCheck.SOURCE_TRUTH, "filings", filing_id, f"source file missing: {path}"))
            continue
        text = path.read_text(encoding="utf-8")
        if quote_hash(text) != raw_sha256:
            failures.append(ValidationFailure(HardCheck.SOURCE_TRUTH, "filings", filing_id, "raw_sha256 mismatch"))
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
            failures.append(ValidationFailure(HardCheck.SOURCE_TRUTH, "spans", evidence_id, "span coordinates out of bounds"))
            continue
        if text[char_start:char_end] != quote_text:
            failures.append(ValidationFailure(HardCheck.SOURCE_TRUTH, "spans", evidence_id, "quote_text does not match source coordinates"))
        if quote_hash(quote_text) != quote_text_hash:
            failures.append(ValidationFailure(HardCheck.EVIDENCE_FINGERPRINT, "spans", evidence_id, "quote_text_hash mismatch"))
        expected = evidence_fingerprint(filing_id, char_start, char_end, quote_text_hash)
        if expected != stored_fingerprint:
            failures.append(ValidationFailure(HardCheck.EVIDENCE_FINGERPRINT, "spans", evidence_id, "location-aware evidence_fingerprint mismatch"))
    return failures


def _check_projection_units(conn: duckdb.DuckDBPyConnection) -> list[ValidationFailure]:
    rows = conn.execute(
        """
        SELECT bidder_rows.bidder_row_id
        FROM bidder_rows
        LEFT JOIN projection_units USING (projection_unit_id)
        WHERE projection_units.projection_unit_id IS NULL
        """
    ).fetchall()
    return [
        ValidationFailure(HardCheck.PROJECTION_UNIT, "bidder_rows", row[0], "bidder row lacks actor-cycle projection unit")
        for row in rows
    ]


def _resolve_source_path(raw_source_root: Path, source_path: str) -> Path:
    candidate = Path(source_path)
    if candidate.is_absolute() and candidate.exists():
        return candidate
    rooted = raw_source_root / source_path
    if rooted.exists():
        return rooted
    return raw_source_root / candidate.name
