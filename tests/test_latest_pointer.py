"""Tests for ``runs/latest/{slug}.json`` pointer-status semantics."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from sec_graph.run.latest import (
    POINTER_SCHEMA_VERSION,
    read_latest_pointer,
    update_latest_pointer,
)


def _make_run(runs_root: Path, run_id: str) -> Path:
    run_dir = runs_root / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    # ``stage_artifacts.jsonl`` is the integrity proxy used by the pointer.
    (run_dir / "stage_artifacts.jsonl").write_text("[]\n", encoding="utf-8")
    return run_dir


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.mark.parametrize("status", ["passed_clean", "needs_review", "high_burden"])
def test_trusted_status_mirrors_attempt_and_sets_latest_trusted(
    tmp_path: Path, status: str
) -> None:
    runs_root = tmp_path / "runs"
    run_dir = _make_run(runs_root, "run-1")

    pointer_path = update_latest_pointer(
        run_dir,
        {"run_id": "run-1", "deal_slug": "demo", "status": status},
        runs_root=runs_root,
    )

    payload = _read_json(pointer_path)
    assert payload["schema_version"] == POINTER_SCHEMA_VERSION
    assert payload["pointer_status"] == status
    assert payload["latest_attempt"]["run_id"] == "run-1"
    assert payload["latest_attempt"]["status"] == status
    assert payload["latest_trusted"]["run_id"] == "run-1"
    assert payload["latest_trusted"]["status"] == status


def test_failed_system_first_attempt_sets_failed_system_pointer(
    tmp_path: Path,
) -> None:
    runs_root = tmp_path / "runs"
    run_dir = _make_run(runs_root, "run-1")

    update_latest_pointer(
        run_dir,
        {"run_id": "run-1", "deal_slug": "demo", "status": "failed_system"},
        runs_root=runs_root,
    )

    payload = read_latest_pointer("demo", runs_root=runs_root)
    assert payload is not None
    assert payload["pointer_status"] == "failed_system"
    assert payload["latest_attempt"]["status"] == "failed_system"
    assert payload["latest_trusted"] is None


def test_failed_system_after_prior_trusted_yields_stale_after_failure(
    tmp_path: Path,
) -> None:
    runs_root = tmp_path / "runs"
    trusted_dir = _make_run(runs_root, "run-1-trusted")
    update_latest_pointer(
        trusted_dir,
        {
            "run_id": "run-1-trusted",
            "deal_slug": "demo",
            "status": "needs_review",
        },
        runs_root=runs_root,
    )

    failed_dir = _make_run(runs_root, "run-2-failed")
    update_latest_pointer(
        failed_dir,
        {
            "run_id": "run-2-failed",
            "deal_slug": "demo",
            "status": "failed_system",
        },
        runs_root=runs_root,
    )

    payload = read_latest_pointer("demo", runs_root=runs_root)
    assert payload is not None
    assert payload["pointer_status"] == "stale_after_failure"
    assert payload["latest_attempt"]["run_id"] == "run-2-failed"
    assert payload["latest_attempt"]["status"] == "failed_system"
    assert payload["latest_trusted"]["run_id"] == "run-1-trusted"
    assert payload["latest_trusted"]["status"] == "needs_review"
    # latest_trusted's run_dir is preserved unchanged.
    assert payload["latest_trusted"]["run_dir"] == trusted_dir.as_posix()


def test_trusted_after_stale_advances_both_pointers(tmp_path: Path) -> None:
    runs_root = tmp_path / "runs"

    trusted_dir = _make_run(runs_root, "run-1-trusted")
    update_latest_pointer(
        trusted_dir,
        {"run_id": "run-1-trusted", "deal_slug": "demo", "status": "needs_review"},
        runs_root=runs_root,
    )

    failed_dir = _make_run(runs_root, "run-2-failed")
    update_latest_pointer(
        failed_dir,
        {"run_id": "run-2-failed", "deal_slug": "demo", "status": "failed_system"},
        runs_root=runs_root,
    )

    new_trusted_dir = _make_run(runs_root, "run-3-trusted")
    update_latest_pointer(
        new_trusted_dir,
        {"run_id": "run-3-trusted", "deal_slug": "demo", "status": "passed_clean"},
        runs_root=runs_root,
    )

    payload = read_latest_pointer("demo", runs_root=runs_root)
    assert payload is not None
    assert payload["pointer_status"] == "passed_clean"
    assert payload["latest_attempt"]["run_id"] == "run-3-trusted"
    assert payload["latest_trusted"]["run_id"] == "run-3-trusted"


def test_pointer_file_is_atomically_replaced(tmp_path: Path) -> None:
    runs_root = tmp_path / "runs"
    run_dir = _make_run(runs_root, "run-1")
    update_latest_pointer(
        run_dir,
        {"run_id": "run-1", "deal_slug": "demo", "status": "passed_clean"},
        runs_root=runs_root,
    )
    update_latest_pointer(
        run_dir,
        {"run_id": "run-1", "deal_slug": "demo", "status": "needs_review"},
        runs_root=runs_root,
    )
    latest_dir = runs_root / "latest"
    leftovers = [path for path in latest_dir.iterdir() if path.name.endswith(".tmp")]
    assert leftovers == []


def test_schema_version_constant_exact(tmp_path: Path) -> None:
    runs_root = tmp_path / "runs"
    run_dir = _make_run(runs_root, "run-1")
    update_latest_pointer(
        run_dir,
        {"run_id": "run-1", "deal_slug": "demo", "status": "passed_clean"},
        runs_root=runs_root,
    )
    payload = read_latest_pointer("demo", runs_root=runs_root)
    assert payload is not None
    assert payload["schema_version"] == "sec_graph_latest_pointer_v1"


def test_prior_trusted_with_missing_stage_artifacts_treated_as_absent(
    tmp_path: Path,
) -> None:
    runs_root = tmp_path / "runs"

    trusted_dir = _make_run(runs_root, "run-1-trusted")
    update_latest_pointer(
        trusted_dir,
        {"run_id": "run-1-trusted", "deal_slug": "demo", "status": "needs_review"},
        runs_root=runs_root,
    )

    # Corrupt the prior trusted run's integrity proxy.
    (trusted_dir / "stage_artifacts.jsonl").unlink()

    failed_dir = _make_run(runs_root, "run-2-failed")
    update_latest_pointer(
        failed_dir,
        {"run_id": "run-2-failed", "deal_slug": "demo", "status": "failed_system"},
        runs_root=runs_root,
    )

    payload = read_latest_pointer("demo", runs_root=runs_root)
    assert payload is not None
    assert payload["pointer_status"] == "failed_system"
    assert payload["latest_trusted"] is None


def test_read_latest_pointer_returns_none_when_missing(tmp_path: Path) -> None:
    runs_root = tmp_path / "runs"
    runs_root.mkdir()
    assert read_latest_pointer("demo", runs_root=runs_root) is None
