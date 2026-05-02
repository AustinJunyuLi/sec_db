from pathlib import Path

import pytest

from sec_graph.cli.run_cmd import run_pipeline
from sec_graph.ingest.pipeline import ingest_examples_to_db


def test_ingest_refuses_to_delete_existing_db_without_fresh_flag(tmp_path: Path) -> None:
    db_path = tmp_path / "pipeline.duckdb"
    db_path.write_bytes(b"existing")

    with pytest.raises(FileExistsError):
        ingest_examples_to_db(db_path, fresh=False)


def test_ingest_can_create_fresh_db_explicitly(tmp_path: Path) -> None:
    db_path = tmp_path / "pipeline.duckdb"
    db_path.write_bytes(b"existing")
    examples_dir = tmp_path / "examples"
    examples_dir.mkdir()

    with pytest.raises(FileNotFoundError):
        ingest_examples_to_db(db_path, examples_dir=examples_dir, fresh=True)

    assert db_path.exists() is False


def test_run_pipeline_writes_immutable_snapshot(tmp_path: Path) -> None:
    run_id = "2026-05-02T120000Z_petsmart_test"
    run_dir = tmp_path / run_id

    run_pipeline(
        run_id=run_id,
        run_dir=run_dir,
        source="examples",
        slugs=["petsmart-inc"],
        projection_name="bidder_cycle_baseline_v1",
    )

    assert (run_dir / "canonical.duckdb").exists()
    assert (run_dir / "run_manifest.json").exists()
    assert (run_dir / "validation_report.json").exists()


def test_run_pipeline_refuses_existing_run_dir(tmp_path: Path) -> None:
    run_id = "2026-05-02T120000Z_petsmart_test"
    run_dir = tmp_path / run_id
    run_dir.mkdir()

    with pytest.raises(FileExistsError):
        run_pipeline(
            run_id=run_id,
            run_dir=run_dir,
            source="examples",
            slugs=["petsmart-inc"],
            projection_name="bidder_cycle_baseline_v1",
        )

