import json
import argparse
from datetime import datetime, timezone
from pathlib import Path

import pytest

from sec_graph.cli import _argv_from_namespace
from sec_graph.run import (
    ResumeRefused,
    RunKernel,
    RunLock,
    RunLockError,
    RunSecretError,
    RunClock,
    append_jsonl_atomic,
    atomic_write_json,
    atomic_write_text,
    check_resume_config,
    make_run_id,
    sha256_file,
    stable_config_hash,
    validate_run_id,
)


def test_run_id_factory_and_clock_are_deterministic_from_run_id_and_config_hash() -> None:
    config_hash = stable_config_hash(
        {"model": "gpt-5.5", "provider": "linkflow", "request_modes": ["claims", "coverage"]}
    )
    assert config_hash == stable_config_hash(
        {"request_modes": ["claims", "coverage"], "provider": "linkflow", "model": "gpt-5.5"}
    )

    run_id = make_run_id(
        scope="petsmart-inc",
        started_at=datetime(2026, 5, 3, 1, 2, 3, tzinfo=timezone.utc),
        config_hash=config_hash,
    )

    assert run_id == f"2026-05-03T010203Z_petsmart-inc_{config_hash[:8]}"
    assert validate_run_id(run_id).scope == "petsmart-inc"
    assert validate_run_id(run_id).short_hash == config_hash[:8]

    clock = RunClock.from_run_id(run_id, config_hash=config_hash)
    same_clock = RunClock.from_run_id(run_id, config_hash=config_hash)
    different_clock = RunClock.from_run_id(run_id, config_hash="f" * 64)

    assert clock.started_at_iso == "2026-05-03T01:02:03Z"
    assert clock.timestamp("extract", sequence=3) == same_clock.timestamp("extract", sequence=3)
    assert clock.timestamp("extract", sequence=3) != different_clock.timestamp("extract", sequence=3)

    with pytest.raises(ValueError):
        validate_run_id("2026-05-03T010203Z_bad_scope_deadbeef")

    with pytest.raises(ValueError):
        make_run_id(
            scope="Bad Scope",
            started_at=datetime(2026, 5, 3, 1, 2, 3, tzinfo=timezone.utc),
            config_hash=config_hash,
        )


def test_atomic_writers_are_canonical_durable_and_reject_secret_keys(tmp_path: Path) -> None:
    json_path = tmp_path / "manifest.json"
    text_path = tmp_path / "memo.txt"
    jsonl_path = tmp_path / "progress.jsonl"

    json_digest = atomic_write_json(json_path, {"b": 2, "a": 1})
    text_digest = atomic_write_text(text_path, "proof memo\n")
    append_jsonl_atomic(jsonl_path, {"state": "queued", "stage": "ingest"})
    append_jsonl_atomic(jsonl_path, {"state": "ingested", "stage": "ingest"})

    assert json_path.read_text(encoding="utf-8") == '{\n  "a": 1,\n  "b": 2\n}\n'
    assert json_digest == sha256_file(json_path)
    assert text_digest == sha256_file(text_path)
    assert [json.loads(line) for line in jsonl_path.read_text(encoding="utf-8").splitlines()] == [
        {"stage": "ingest", "state": "queued"},
        {"stage": "ingest", "state": "ingested"},
    ]
    assert not list(tmp_path.glob("*.tmp"))

    with pytest.raises(RunSecretError):
        atomic_write_json(tmp_path / "bad.json", {"api_key": "do-not-write"})

    with pytest.raises(RunSecretError):
        append_jsonl_atomic(jsonl_path, {"authorization": "Bearer do-not-write"})


def test_run_lock_fails_loudly_for_second_writer(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    run_id = "2026-05-03T010203Z_petsmart-inc_deadbeef"

    with RunLock.acquire(run_dir, run_id=run_id, config_hash="a" * 64):
        lock_payload = json.loads((run_dir / "run.lock").read_text(encoding="utf-8"))
        assert lock_payload["run_id"] == run_id

        with pytest.raises(RunLockError):
            RunLock.acquire(run_dir, run_id=run_id, config_hash="a" * 64)

    assert not (run_dir / "run.lock").exists()


def test_kernel_ledgers_record_progress_and_stage_artifact_digests(tmp_path: Path) -> None:
    config = {"provider": "linkflow", "model": "gpt-5.5", "reasoning_effort": "high"}
    config_hash = stable_config_hash(config)
    run_id = make_run_id(
        scope="petsmart-inc",
        started_at=datetime(2026, 5, 3, 1, 2, 3, tzinfo=timezone.utc),
        config_hash=config_hash,
    )
    kernel = RunKernel.create(tmp_path / run_id, run_id=run_id, config_hash=config_hash, run_config=config)

    artifact_path = kernel.run_dir / "extract" / "claims.json"
    artifact_digest = atomic_write_json(artifact_path, {"claims": []})
    progress_entry = kernel.append_progress(
        deal_slug="petsmart-inc",
        stage="extract",
        state="llm_artifacts_written",
        attempt=1,
        artifact_digests={"claims": artifact_digest},
    )
    stage_entry = kernel.record_stage_artifact(
        artifact_path,
        artifact_kind="llm_claims",
        owning_stage="extract",
        deal_slug="petsmart-inc",
    )

    assert progress_entry["run_id"] == run_id
    assert progress_entry["created_at"] == kernel.clock.timestamp("progress:extract:petsmart-inc", sequence=1)
    assert stage_entry["sha256"] == artifact_digest
    assert stage_entry["artifact_path"] == "extract/claims.json"

    progress_rows = [
        json.loads(line) for line in (kernel.run_dir / "progress_ledger.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    artifact_rows = [
        json.loads(line) for line in (kernel.run_dir / "stage_artifacts.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert progress_rows == [progress_entry]
    assert artifact_rows == [stage_entry]


def test_resume_check_refuses_changed_config_and_tampered_artifacts(tmp_path: Path) -> None:
    config_hash = stable_config_hash({"provider": "linkflow", "model": "gpt-5.5"})
    run_id = make_run_id(
        scope="petsmart-inc",
        started_at=datetime(2026, 5, 3, 1, 2, 3, tzinfo=timezone.utc),
        config_hash=config_hash,
    )
    kernel = RunKernel.create(tmp_path / run_id, run_id=run_id, config_hash=config_hash)
    artifact_path = kernel.run_dir / "ingest" / "paragraphs.json"
    atomic_write_json(artifact_path, {"paragraphs": []})
    kernel.record_stage_artifact(artifact_path, artifact_kind="paragraphs", owning_stage="ingest")

    decision = check_resume_config(kernel.run_dir, run_id=run_id, config_hash=config_hash)

    assert decision.can_resume is True
    assert decision.reused_artifacts == ["ingest/paragraphs.json"]

    with pytest.raises(ResumeRefused):
        check_resume_config(kernel.run_dir, run_id=run_id, config_hash="f" * 64)

    artifact_path.write_text("tampered\n", encoding="utf-8")
    with pytest.raises(ResumeRefused):
        check_resume_config(kernel.run_dir, run_id=run_id, config_hash=config_hash)


def test_top_level_cli_forwards_explicit_resume() -> None:
    args = argparse.Namespace(
        slug=None,
        all=False,
        slugs=["petsmart-inc"],
        source="filings",
        filing_id=None,
        db=None,
        examples_dir=None,
        input=None,
        run_dir=Path("runs/demo"),
        snapshot_dir=None,
        run_id="2026-05-03T010203Z_petsmart-inc_deadbeef",
        projection="bidder_cycle_baseline_v1",
        llm_provider="linkflow",
        llm_model="gpt-5.5",
        llm_reasoning_effort="high",
        request_mode="semantic_claims_v1",
        resume=True,
        fresh=False,
    )

    rebuilt = _argv_from_namespace(args, [])

    assert "--resume" in rebuilt
