"""Failed-validation proof writer integration test.

Validates that ``run_pipeline`` writes the ``failed_validation_proof.json``
artifact when validation reports any ``system_failure``. The fixture
forces a structural fault by monkeypatching ``validate_database`` to
return a fixed ``ValidationResult`` with one system failure, so the test
exercises the proof writer independently of taxonomy/extraction
behaviour (which is owned by other tasks).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from sec_graph.cli.run_cmd import run_pipeline
from sec_graph.extract.llm.models import DEFAULT_REQUEST_MODE
from sec_graph.validate.integrity import (
    HardCheck,
    ValidationFinding,
    ValidationResult,
)


def _stub_validation_with_one_failure(*_args, **_kwargs) -> ValidationResult:
    return ValidationResult(
        system_failures=[
            ValidationFinding(
                check=HardCheck.SOURCE_TRUTH,
                table_name="filings",
                row_id="forced-failure",
                detail="forced for failed_validation_proof integration test",
            )
        ],
        review_items=[],
    )


def test_failed_validation_run_writes_failed_validation_proof(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run_id = "2026-05-04T120000Z_failed-validation_deadbeef"
    run_dir = tmp_path / run_id
    monkeypatch.setattr("sec_graph.cli.run_cmd.reconcile_all", lambda conn, run_id: None)
    monkeypatch.setattr(
        "sec_graph.validate.integrity.validate_database",
        _stub_validation_with_one_failure,
    )

    with pytest.raises(RuntimeError) as excinfo:
        run_pipeline(
            run_id=run_id,
            run_dir=run_dir,
            source="examples",
            slugs=["petsmart-inc"],
            projection_name="bidder_cycle_baseline_v1",
            request_mode=DEFAULT_REQUEST_MODE,
            llm_config=None,
        )

    assert "run failed validation" in str(excinfo.value)
    proof_path = run_dir / "failed_validation_proof.json"
    assert proof_path.exists()
    proof = json.loads(proof_path.read_text(encoding="utf-8"))
    assert proof["run_id"] == run_id
    assert proof["validation_passed"] is False
    assert proof["validation_failure_count"] >= 1
    assert proof["provider"] is None
    assert proof["model"] is None
    assert proof["reasoning_effort"] is None
    assert proof["request_mode"] == DEFAULT_REQUEST_MODE
    assert proof["artifact_counts"] == {
        "linkflow_success": 0,
        "linkflow_failure": 0,
    }
    assert isinstance(proof["resolved_commit"], str)
    assert len(proof["resolved_commit"]) == 40
