"""Projection and proof artifact writer."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

import duckdb

from sec_graph.costs import (
    CostEnvelopeAssumptions,
    DealCostRuntimeMetrics,
    build_cost_runtime_summary,
    cost_summary_csv_rows,
)
from sec_graph.project.bidder_rows import build_bidder_rows
from sec_graph.validate.integrity import HardCheck, validate_database


def write_projection_outputs(
    conn: duckdb.DuckDBPyConnection,
    run_dir: Path,
    *,
    run_id: str,
    projection_name: str,
    allow_existing: bool = False,
) -> dict[str, Any]:
    if run_dir.exists() and not allow_existing:
        raise FileExistsError(f"{run_dir} already exists")
    run_dir.mkdir(parents=True, exist_ok=allow_existing)
    rows = build_bidder_rows(conn, run_id=run_id, projection_name=projection_name)
    proof = proof_summary(conn, run_id=run_id, projection_name=projection_name, bidder_rows=rows)
    _write_json(run_dir / "proof_summary.json", proof)
    _write_jsonl(run_dir / "bidder_rows.jsonl", rows)
    _write_csv(run_dir / "bidder_summary.csv", rows, ["deal_slug", "cycle_id", "actor_id", "actor_label", "bF", "admitted"])
    _write_csv(
        run_dir / "coverage_results.csv",
        _coverage_rows(conn),
        [
            "deal_slug",
            "obligation_id",
            "obligation_kind",
            "expected_claim_type",
            "importance",
            "applicability",
            "applicability_reason_code",
            "applicability_basis_json",
            "coverage_result_id",
            "result",
            "claim_count",
            "reason_code",
            "coverage_current",
            "obligation_current",
            "linked_claim_ids_json",
        ],
    )
    _write_csv(run_dir / "claim_dispositions.csv", _disposition_rows(conn), ["deal_slug", "claim_id", "claim_type", "disposition", "canonical_table", "canonical_id", "reason_code"])
    _write_csv(
        run_dir / "judgments.csv",
        _judgment_rows(conn),
        [
            "deal_slug",
            "judgment_id",
            "target_table",
            "target_id",
            "judgment_key",
            "judgment_value",
            "judgment_status",
            "rule_id",
            "reason_code",
            "current",
        ],
    )
    _write_csv(
        run_dir / "review_flags.csv",
        _review_flag_rows(conn),
        [
            "deal_slug",
            "flag_type",
            "severity",
            "reason_code",
            "claim_id",
            "judgment_id",
            "canonical_table",
            "canonical_id",
            "recommended_review_question",
        ],
    )
    cost_summary = _cost_summary(conn, run_id)
    _write_json(run_dir / "cost_runtime_summary.json", cost_summary)
    _write_csv_dynamic(run_dir / "cost_runtime_summary.csv", _cost_summary_csv_rows(cost_summary))
    _write_jsonl(run_dir / "provider_usage_ledger.jsonl", _provider_usage_rows(conn, run_id))
    _write_jsonl(run_dir / "latency_ledger.jsonl", _latency_rows(conn, run_id))
    _write_run_memo(run_dir / "run_memo.md", proof)
    return proof


def default_cost_envelope_assumptions() -> CostEnvelopeAssumptions:
    return CostEnvelopeAssumptions(
        input_cost_per_million_tokens=0.0,
        output_cost_per_million_tokens=0.0,
        latency_projection="linear deal-count scaling from observed Linkflow call latencies",
        retry_projection="observed retry rate scales linearly by deal count",
        rejection_projection="observed quote-validation rejection rate scales linearly by claim count",
    )


def proof_summary(
    conn: duckdb.DuckDBPyConnection,
    *,
    run_id: str,
    projection_name: str,
    bidder_rows: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    bidder_rows = bidder_rows if bidder_rows is not None else []
    row_counts = {table: _count(conn, table) for table in (
        "evidence_regions",
        "coverage_obligations",
        "coverage_results",
        "claims",
        "claim_dispositions",
        "deals",
        "actors",
        "actor_relations",
        "events",
        "event_actor_links",
        "participation_counts",
        "projection_units",
        "projection_judgments",
        "bidder_rows",
        "judgments",
        "review_flags",
    )}
    row_counts["applicable_coverage_obligations"] = _count_query(
        conn,
        "SELECT count(*) FROM coverage_obligations WHERE current = true AND applicability = 'applicable'",
    )
    insufficient_required = _count_query(
        conn,
        """
        SELECT count(DISTINCT coverage_obligations.obligation_id)
        FROM coverage_obligations
        LEFT JOIN coverage_results
          ON coverage_results.obligation_id = coverage_obligations.obligation_id
         AND coverage_results.current = true
        WHERE coverage_obligations.importance IN ('required', 'important')
          AND coverage_obligations.current = true
          AND coverage_obligations.applicability = 'applicable'
          AND (coverage_results.result IS NULL OR coverage_results.result <> 'claims_emitted')
        """,
    )
    undisposed_claims = _count_query(
        conn,
        """
        SELECT count(*)
        FROM claims
        LEFT JOIN claim_dispositions
          ON claim_dispositions.claim_id = claims.claim_id
         AND claim_dispositions.current = true
        WHERE claim_dispositions.claim_id IS NULL
        """,
    )
    rows_without_evidence = _rows_without_evidence(conn)
    validation = validate_database(conn)
    validation_failure_count = len(validation.hard_failures)
    semantic_validation_failures = sum(
        1 for failure in validation.hard_failures if failure.check == HardCheck.SEMANTIC_CLAIM_EVIDENCE
    )
    live_claims = _count_query(conn, "SELECT count(*) FROM claims WHERE provider_source_stage = 'linkflow'")
    thin_live = live_claims < max(1, row_counts["applicable_coverage_obligations"] // 3)
    review_flag_count = _count_query(conn, "SELECT count(*) FROM review_flags WHERE current = true AND severity = 'review'")
    blocking_flag_count = _count_query(conn, "SELECT count(*) FROM review_flags WHERE current = true AND severity = 'blocking'")
    verdict = _proof_verdict(conn, validation_passed=validation.passed, thin_live=thin_live)
    return {
        "run_id": run_id,
        "projection_name": projection_name,
        "verdict": verdict,
        "row_counts": row_counts,
        "live_linkflow_claims": live_claims,
        "insufficient_required_or_important_obligations": insufficient_required,
        "undisposed_claims": undisposed_claims,
        "canonical_rows_without_relational_evidence": rows_without_evidence,
        "hard_validation_failures": validation_failure_count,
        "semantic_validation_failures": semantic_validation_failures,
        "thin_live_claim_warning": thin_live,
        "review_flag_count": review_flag_count,
        "blocking_flag_count": blocking_flag_count,
        "judgment_counts": _group_count(conn, "judgments", "judgment_status"),
        "claim_counts_by_type": _group_count(conn, "claims", "claim_type"),
        "claim_dispositions": _group_count(conn, "claim_dispositions", "disposition"),
        "coverage_results": _group_count(conn, "coverage_results", "result"),
        "bidder_rows": bidder_rows,
        "deals": _deal_summaries(conn),
    }


def _proof_verdict(conn: duckdb.DuckDBPyConnection, *, validation_passed: bool, thin_live: bool) -> str:
    blocking_count = _count_query(
        conn,
        "SELECT count(*) FROM review_flags WHERE current = true AND severity = 'blocking'",
    )
    review_count = _count_query(
        conn,
        "SELECT count(*) FROM review_flags WHERE current = true AND severity = 'review'",
    )
    if not validation_passed or blocking_count:
        return "UNSOUND"
    if review_count or thin_live:
        return "REVIEW_REQUIRED"
    return "SOUND"


def _rows_without_evidence(conn: duckdb.DuckDBPyConnection) -> int:
    total = 0
    for table, id_col in (
        ("deals", "deal_id"),
        ("process_cycles", "cycle_id"),
        ("actors", "actor_id"),
        ("actor_relations", "relation_id"),
        ("events", "event_id"),
        ("event_actor_links", "link_id"),
        ("participation_counts", "participation_count_id"),
    ):
        total += _count_query(
            conn,
            f"""
            SELECT count(*)
            FROM {table}
            LEFT JOIN row_evidence
              ON row_evidence.row_table = '{table}'
             AND row_evidence.row_id = {table}.{id_col}
            WHERE row_evidence.row_id IS NULL
            """,
        )
    return total


def _deal_summaries(conn: duckdb.DuckDBPyConnection) -> dict[str, dict[str, int]]:
    rows = conn.execute("SELECT deal_slug, deal_id FROM deals ORDER BY deal_slug").fetchall()
    out: dict[str, dict[str, int]] = {}
    for slug, deal_id in rows:
        out[slug] = {
            "actors": _count_where(conn, "actors", "deal_id", deal_id),
            "actor_relations": _count_where(conn, "actor_relations", "deal_id", deal_id),
            "events": _count_where(conn, "events", "deal_id", deal_id),
            "event_actor_links": _count_query(conn, "SELECT count(*) FROM event_actor_links JOIN events USING (event_id) WHERE events.deal_id = ?", [deal_id]),
            "participation_counts": _count_where(conn, "participation_counts", "deal_id", deal_id),
            "bidder_rows": _count_where(conn, "bidder_rows", "deal_slug", slug),
        "claim_dispositions": _count_query(conn, "SELECT count(*) FROM claim_dispositions JOIN claims USING (claim_id) WHERE claims.deal_slug = ? AND claim_dispositions.current = true", [slug]),
        "coverage_results": _count_query(conn, "SELECT count(*) FROM coverage_results JOIN coverage_obligations USING (obligation_id) WHERE coverage_obligations.deal_slug = ? AND coverage_results.current = true", [slug]),
        }
    return out


def _coverage_rows(conn: duckdb.DuckDBPyConnection) -> list[dict[str, Any]]:
    columns = [
        "deal_slug",
        "obligation_id",
        "obligation_kind",
        "expected_claim_type",
        "importance",
        "applicability",
        "applicability_reason_code",
        "applicability_basis_json",
        "coverage_result_id",
        "result",
        "claim_count",
        "reason_code",
        "coverage_current",
        "obligation_current",
        "linked_claim_ids_json",
    ]
    rows = conn.execute(
        """
        SELECT coverage_obligations.deal_slug, coverage_obligations.obligation_id,
               obligation_kind, expected_claim_type, importance, applicability,
               applicability_reason_code, applicability_basis_json,
               coverage_results.coverage_result_id, result, claim_count, reason_code,
               coverage_results.current AS coverage_current,
               coverage_obligations.current AS obligation_current,
               COALESCE(
                 to_json(list(claim_coverage_links.claim_id ORDER BY claim_coverage_links.claim_id)
                   FILTER (WHERE claim_coverage_links.claim_id IS NOT NULL)),
                 '[]'
               ) AS linked_claim_ids_json
        FROM coverage_obligations
        LEFT JOIN coverage_results
          ON coverage_results.obligation_id = coverage_obligations.obligation_id
         AND coverage_results.current = true
        LEFT JOIN claim_coverage_links
          ON claim_coverage_links.obligation_id = coverage_obligations.obligation_id
         AND claim_coverage_links.current = true
        WHERE coverage_obligations.current = true
        GROUP BY coverage_obligations.deal_slug, coverage_obligations.obligation_id,
                 obligation_kind, expected_claim_type, importance, applicability,
                 applicability_reason_code, applicability_basis_json,
                 coverage_results.coverage_result_id, result, claim_count, reason_code,
                 coverage_results.current, coverage_obligations.current
        ORDER BY coverage_obligations.deal_slug, coverage_obligations.obligation_id
        """
    ).fetchall()
    return [dict(zip(columns, row, strict=True)) for row in rows]


def _disposition_rows(conn: duckdb.DuckDBPyConnection) -> list[dict[str, Any]]:
    columns = ["deal_slug", "claim_id", "claim_type", "disposition", "canonical_table", "canonical_id", "reason_code"]
    rows = conn.execute(
        """
        SELECT claims.deal_slug, claims.claim_id, claims.claim_type,
               claim_dispositions.disposition, claim_dispositions.canonical_table,
               claim_dispositions.canonical_id, claim_dispositions.reason_code
        FROM claims
        LEFT JOIN claim_dispositions
          ON claim_dispositions.claim_id = claims.claim_id
         AND claim_dispositions.current = true
        ORDER BY claims.deal_slug, claims.claim_sequence, claims.claim_id
        """
    ).fetchall()
    return [dict(zip(columns, row, strict=True)) for row in rows]


def _judgment_rows(conn: duckdb.DuckDBPyConnection) -> list[dict[str, Any]]:
    columns = [
        "deal_slug",
        "judgment_id",
        "target_table",
        "target_id",
        "judgment_key",
        "judgment_value",
        "judgment_status",
        "rule_id",
        "reason_code",
        "current",
    ]
    rows = conn.execute(
        """
        SELECT deals.deal_slug, judgments.judgment_id, judgments.target_table,
               judgments.target_id, judgments.judgment_key,
               judgments.judgment_value, judgments.judgment_status,
               judgments.rule_id, judgments.reason_code, judgments.current
        FROM judgments
        LEFT JOIN deals USING (deal_id)
        ORDER BY deals.deal_slug, judgments.judgment_id
        """
    ).fetchall()
    return [dict(zip(columns, row, strict=True)) for row in rows]


def _review_flag_rows(conn: duckdb.DuckDBPyConnection) -> list[dict[str, Any]]:
    columns = [
        "deal_slug",
        "flag_type",
        "severity",
        "reason_code",
        "claim_id",
        "judgment_id",
        "canonical_table",
        "canonical_id",
        "recommended_review_question",
    ]
    rows = conn.execute(
        """
        SELECT deal_slug, flag_type, severity, reason_code, claim_id,
               judgment_id, canonical_table, canonical_id,
               recommended_review_question
        FROM review_flags
        WHERE current = true
        ORDER BY deal_slug, flag_id
        """
    ).fetchall()
    return [dict(zip(columns, row, strict=True)) for row in rows]


def observed_deal_metrics(conn: duckdb.DuckDBPyConnection, run_id: str) -> list[DealCostRuntimeMetrics]:
    slugs = [row[0] for row in conn.execute("SELECT deal_slug FROM deals ORDER BY deal_slug").fetchall()]
    metrics: list[DealCostRuntimeMetrics] = []
    for slug in slugs:
        cost_rows = conn.execute(
            """
            SELECT input_tokens, output_tokens, token_source, latency_ms, retry_count,
                   provider_failure
            FROM cost_runtime_records
            WHERE run_id = ? AND deal_slug = ?
            ORDER BY window_id
            """,
            [run_id, slug],
        ).fetchall()
        token_sources = {row[2] for row in cost_rows if row[2]}
        if token_sources == {"actual"}:
            token_basis = "actual"
        elif token_sources and token_sources != {"estimated"}:
            token_basis = "mixed"
        else:
            token_basis = "estimated"
        disposition_counts = {
            row[0]: int(row[1])
            for row in conn.execute(
                """
                SELECT claim_dispositions.disposition, count(*)
                FROM claim_dispositions
                JOIN claims USING (claim_id)
                WHERE claims.deal_slug = ?
                  AND claim_dispositions.current = true
                GROUP BY claim_dispositions.disposition
                ORDER BY claim_dispositions.disposition
                """,
                [slug],
            ).fetchall()
        }
        quote_rejections = _count_query(
            conn,
            """
            SELECT count(*)
            FROM claim_dispositions
            JOIN claims USING (claim_id)
            WHERE claims.deal_slug = ?
              AND claim_dispositions.disposition = 'rejected_unsupported'
              AND claim_dispositions.reason_code LIKE '%quote%'
              AND claim_dispositions.current = true
            """,
            [slug],
        )
        metrics.append(
            DealCostRuntimeMetrics(
                deal_slug=slug,
                windows=len(cost_rows),
                input_tokens=sum(row[0] or 0 for row in cost_rows),
                output_tokens=sum(row[1] or 0 for row in cost_rows),
                claims=_count_where(conn, "claims", "deal_slug", slug),
                coverage_obligations=_count_where(conn, "coverage_obligations", "deal_slug", slug),
                linkflow_latencies_seconds=tuple((row[3] or 0) / 1000 for row in cost_rows),
                retry_count=sum(row[4] or 0 for row in cost_rows),
                provider_failure_count=sum(1 for row in cost_rows if row[5]),
                quote_validation_rejection_count=quote_rejections,
                disposition_counts=disposition_counts,
                token_usage_basis=token_basis,
            )
        )
    return metrics


def _cost_summary(conn: duckdb.DuckDBPyConnection, run_id: str) -> dict[str, Any]:
    rows = conn.execute(
        """
        SELECT deal_slug, input_tokens, output_tokens, token_source, latency_ms,
               retry_count, provider_failure
        FROM cost_runtime_records
        WHERE run_id = ?
        ORDER BY deal_slug, window_id
        """,
        [run_id],
    ).fetchall()
    token_sources = {row[3] for row in rows}
    metrics = observed_deal_metrics(conn, run_id)
    if len(metrics) == 3:
        return {
            "run_id": run_id,
            "record_count": len(rows),
            "cost_numbers_are": "token_usage_only_no_pricing_config",
            "pricing_config_source": None,
            **build_cost_runtime_summary(metrics, default_cost_envelope_assumptions()),
        }
    return {
        "summary_version": "proof_cost_runtime_summary_v1",
        "run_id": run_id,
        "record_count": len(rows),
        "observed_deal_count": len(metrics),
        "input_tokens": sum(row[1] or 0 for row in rows),
        "output_tokens": sum(row[2] or 0 for row in rows),
        "token_usage_basis": "mixed" if len(token_sources) > 1 else (next(iter(token_sources)) if token_sources else "estimated"),
        "latency_ms_max": max((row[4] or 0 for row in rows), default=0),
        "retry_count": sum(row[5] or 0 for row in rows),
        "provider_failures": sum(1 for row in rows if row[6]),
        "cost_numbers_are": "token_usage_only_no_pricing_config",
        "projections": [],
    }


def _cost_summary_csv_rows(cost_summary: dict[str, Any]) -> list[dict[str, Any]]:
    if cost_summary.get("summary_version") == "corpus_cost_runtime_envelope_v1":
        return cost_summary_csv_rows(cost_summary)
    return [
        {
            "deal_count": cost_summary["observed_deal_count"],
            "cost_basis": cost_summary["token_usage_basis"],
            "projected_windows": cost_summary["record_count"],
            "projected_input_tokens": cost_summary["input_tokens"],
            "projected_output_tokens": cost_summary["output_tokens"],
            "projected_claims": "",
            "projected_coverage_obligations": "",
            "projected_retry_count": cost_summary["retry_count"],
            "projected_provider_failures": cost_summary["provider_failures"],
            "projected_quote_validation_rejections": "",
            "estimated_cost_usd": "",
            "actual_cost_usd": "",
            "assumption_basis": "not_projected_requires_three_observed_deals",
        }
    ]


def _provider_usage_rows(conn: duckdb.DuckDBPyConnection, run_id: str) -> list[dict[str, Any]]:
    columns = [
        "run_id",
        "deal_slug",
        "window_id",
        "provider",
        "model",
        "reasoning_effort",
        "input_tokens",
        "output_tokens",
        "token_source",
    ]
    rows = conn.execute(
        """
        SELECT run_id, deal_slug, window_id, provider, model, reasoning_effort,
               input_tokens, output_tokens, token_source
        FROM cost_runtime_records
        WHERE run_id = ?
        ORDER BY deal_slug, window_id
        """,
        [run_id],
    ).fetchall()
    return [dict(zip(columns, row, strict=True)) for row in rows]


def _latency_rows(conn: duckdb.DuckDBPyConnection, run_id: str) -> list[dict[str, Any]]:
    columns = ["run_id", "deal_slug", "window_id", "latency_ms", "retry_count", "provider_failure"]
    rows = conn.execute(
        """
        SELECT run_id, deal_slug, window_id, latency_ms, retry_count, provider_failure
        FROM cost_runtime_records
        WHERE run_id = ?
        ORDER BY deal_slug, window_id
        """,
        [run_id],
    ).fetchall()
    return [dict(zip(columns, row, strict=True)) for row in rows]


def _write_run_memo(path: Path, proof: dict[str, Any]) -> None:
    lines = [
        "# sec_graph Run Memo",
        "",
        f"- Proof verdict: {proof['verdict']}",
        f"- Claims: {proof['row_counts']['claims']}",
        f"- Claim dispositions: {proof['row_counts']['claim_dispositions']}",
        f"- Coverage results: {proof['row_counts']['coverage_results']}",
        f"- Bidder rows: {proof['row_counts']['bidder_rows']}",
        f"- Rows without relational evidence: {proof['canonical_rows_without_relational_evidence']}",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _count(conn: duckdb.DuckDBPyConnection, table: str) -> int:
    return int(conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0])


def _count_where(conn: duckdb.DuckDBPyConnection, table: str, column: str, value: str) -> int:
    return int(conn.execute(f"SELECT count(*) FROM {table} WHERE {column} = ?", [value]).fetchone()[0])


def _count_query(conn: duckdb.DuckDBPyConnection, query: str, params: list[Any] | None = None) -> int:
    return int(conn.execute(query, params or []).fetchone()[0])


def _group_count(conn: duckdb.DuckDBPyConnection, table: str, column: str) -> dict[str, int]:
    where_current = " WHERE current = true" if _table_has_current(conn, table) else ""
    return {
        row[0]: int(row[1])
        for row in conn.execute(
            f"SELECT {column}, count(*) FROM {table}{where_current} GROUP BY {column} ORDER BY {column}"
        ).fetchall()
    }


def _table_has_current(conn: duckdb.DuckDBPyConnection, table: str) -> bool:
    return any(row[1] == "current" for row in conn.execute(f"PRAGMA table_info({table})").fetchall())


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str), encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text("\n".join(json.dumps(row, sort_keys=True, default=str) for row in rows) + ("\n" if rows else ""), encoding="utf-8")


def _write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field) for field in fieldnames})


def _write_csv_dynamic(path: Path, rows: list[dict[str, Any]]) -> None:
    fieldnames = list(rows[0].keys()) if rows else []
    with path.open("w", newline="", encoding="utf-8") as handle:
        if not fieldnames:
            handle.write("")
            return
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
