import csv
import json
from pathlib import Path

import pytest

from sec_graph.corpus import create_corpus_skeleton
from sec_graph.costs import CostEnvelopeAssumptions, DealCostRuntimeMetrics


def _observed_metrics() -> list[DealCostRuntimeMetrics]:
    return [
        DealCostRuntimeMetrics(
            deal_slug="petsmart-inc",
            windows=2,
            input_tokens=1000,
            output_tokens=200,
            claims=5,
            coverage_obligations=8,
            linkflow_latencies_seconds=(10.0, 20.0),
            retry_count=1,
            provider_failure_count=0,
            quote_validation_rejection_count=1,
            disposition_counts={"accepted": 4, "rejected": 1},
            cost_usd=0.012,
            token_usage_basis="actual",
        ),
        DealCostRuntimeMetrics(
            deal_slug="mac-gray",
            windows=3,
            input_tokens=1500,
            output_tokens=300,
            claims=6,
            coverage_obligations=9,
            linkflow_latencies_seconds=(30.0, 40.0, 50.0),
            retry_count=0,
            provider_failure_count=1,
            quote_validation_rejection_count=2,
            disposition_counts={"accepted": 5, "ambiguous": 1},
            cost_usd=None,
            token_usage_basis="estimated",
        ),
        DealCostRuntimeMetrics(
            deal_slug="providence-worcester",
            windows=1,
            input_tokens=500,
            output_tokens=100,
            claims=4,
            coverage_obligations=7,
            linkflow_latencies_seconds=(60.0,),
            retry_count=2,
            provider_failure_count=0,
            quote_validation_rejection_count=0,
            disposition_counts={"accepted": 4},
            cost_usd=0.006,
            token_usage_basis="actual",
        ),
    ]


def test_create_corpus_skeleton_writes_required_artifacts_and_cost_projection(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"

    result = create_corpus_skeleton(
        run_dir=run_dir,
        run_id="2026-05-03T120000Z_3-deals_deadbeef",
        deal_slugs=["petsmart-inc", "mac-gray", "providence-worcester", "fourth-deal"],
        observed_metrics=_observed_metrics(),
        assumptions=CostEnvelopeAssumptions(
            input_cost_per_million_tokens=2.00,
            output_cost_per_million_tokens=8.00,
            latency_projection="linear deal-count scaling using observed Linkflow call latencies",
            retry_projection="observed retry rate scales linearly by deal",
            rejection_projection="observed quote-validation rejection rate scales linearly by claim",
        ),
        shard_size=2,
    )

    required = {
        "corpus_manifest.jsonl",
        "shard_plan.jsonl",
        "attempt_ledger.jsonl",
        "failure_ledger.jsonl",
        "progress_ledger.jsonl",
        "stage_artifacts.jsonl",
        "cost_runtime_summary.csv",
        "cost_runtime_summary.json",
        "aggregate_proof_summary.json",
        "resume_report.json",
    }
    assert {path.name for path in result.artifact_paths} == required
    for name in required:
        assert (run_dir / name).exists(), name

    manifest_rows = [
        json.loads(line)
        for line in (run_dir / "corpus_manifest.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert [row["deal_slug"] for row in manifest_rows] == [
        "petsmart-inc",
        "mac-gray",
        "providence-worcester",
        "fourth-deal",
    ]
    assert {row["status"] for row in manifest_rows} == {"queued"}

    shard_rows = [
        json.loads(line)
        for line in (run_dir / "shard_plan.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert shard_rows == [
        {
            "run_id": "2026-05-03T120000Z_3-deals_deadbeef",
            "shard_id": "shard-0001",
            "deal_slugs": ["petsmart-inc", "mac-gray"],
            "parallel_linkflow_artifact_writers": True,
            "duckdb_writer": "single_import_reconcile_validate_project_writer",
        },
        {
            "run_id": "2026-05-03T120000Z_3-deals_deadbeef",
            "shard_id": "shard-0002",
            "deal_slugs": ["providence-worcester", "fourth-deal"],
            "parallel_linkflow_artifact_writers": True,
            "duckdb_writer": "single_import_reconcile_validate_project_writer",
        },
    ]

    summary = json.loads((run_dir / "cost_runtime_summary.json").read_text(encoding="utf-8"))
    assert summary["usage_basis"] == "mixed"
    assert summary["observed"]["deal_count"] == 3
    assert summary["observed"]["windows_per_deal"] == pytest.approx(2.0)
    assert summary["observed"]["latency_seconds"]["p50"] == 35.0
    assert summary["observed"]["latency_seconds"]["p95"] == 60.0
    assert summary["observed"]["quote_validation_rejection_rate"] == pytest.approx(3 / 15)
    assert summary["observed"]["disposition_mix"] == {"accepted": 13, "ambiguous": 1, "rejected": 1}
    assert summary["assumptions"]["input_cost_per_million_tokens"] == 2.0

    projections = {row["deal_count"]: row for row in summary["projections"]}
    assert set(projections) == {3, 9, 30, 400, 800}
    assert projections[9]["projected_windows"] == pytest.approx(18.0)
    assert projections[9]["projected_input_tokens"] == pytest.approx(9000.0)
    assert projections[9]["projected_output_tokens"] == pytest.approx(1800.0)
    assert projections[9]["cost_basis"] == "mixed"

    with (run_dir / "cost_runtime_summary.csv").open(newline="", encoding="utf-8") as handle:
        csv_rows = list(csv.DictReader(handle))
    assert [int(row["deal_count"]) for row in csv_rows] == [3, 9, 30, 400, 800]
    assert csv_rows[1]["cost_basis"] == "mixed"

    artifact_rows = [
        json.loads(line)
        for line in (run_dir / "stage_artifacts.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert {row["artifact_path"] for row in artifact_rows} == required
    stage_self = next(row for row in artifact_rows if row["artifact_path"] == "stage_artifacts.jsonl")
    assert stage_self["digest"] is None
    assert stage_self["digest_status"] == "self_referential_digest_not_recorded"
    for row in artifact_rows:
        assert row["finalized"] is True
        if row["artifact_path"] != "stage_artifacts.jsonl":
            assert len(row["digest"]) == 64


def test_create_corpus_skeleton_requires_three_observed_deals(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="exactly three observed deal metrics"):
        create_corpus_skeleton(
            run_dir=tmp_path / "run",
            run_id="2026-05-03T120000Z_3-deals_deadbeef",
            deal_slugs=["petsmart-inc"],
            observed_metrics=_observed_metrics()[:2],
            assumptions=CostEnvelopeAssumptions(
                input_cost_per_million_tokens=2.00,
                output_cost_per_million_tokens=8.00,
                latency_projection="linear deal-count scaling using observed Linkflow call latencies",
                retry_projection="observed retry rate scales linearly by deal",
                rejection_projection="observed quote-validation rejection rate scales linearly by claim",
            ),
        )


def test_create_corpus_skeleton_refuses_to_overwrite_existing_artifacts(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "resume_report.json").write_text("{}", encoding="utf-8")

    with pytest.raises(FileExistsError, match="resume_report.json"):
        create_corpus_skeleton(
            run_dir=run_dir,
            run_id="2026-05-03T120000Z_3-deals_deadbeef",
            deal_slugs=["petsmart-inc", "mac-gray", "providence-worcester"],
            observed_metrics=_observed_metrics(),
            assumptions=CostEnvelopeAssumptions(
                input_cost_per_million_tokens=2.00,
                output_cost_per_million_tokens=8.00,
                latency_projection="linear deal-count scaling using observed Linkflow call latencies",
                retry_projection="observed retry rate scales linearly by deal",
                rejection_projection="observed quote-validation rejection rate scales linearly by claim",
            ),
        )
