import json
from pathlib import Path

import pytest

from sec_graph.cli.run_cmd import _short_input_hash, run_pipeline
from sec_graph.ingest.pipeline import IngestSource
from sec_graph.ingest.pipeline import ingest_examples_to_db
from sec_graph.schema import versions


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
    source_path = Path("data/examples/petsmart-inc.md")
    run_id = f"2026-05-02T120000Z_petsmart-inc_{_short_input_hash([IngestSource('petsmart-inc', source_path)])}"
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
    manifest = json.loads((run_dir / "run_manifest.json").read_text(encoding="utf-8"))
    assert manifest["schema_version"] == versions.SCHEMA_VERSION
    assert manifest["parser_version"] == versions.PARSER_VERSION
    assert manifest["ingest_version"] == versions.INGEST_VERSION
    assert manifest["extract_version"] == versions.EXTRACT_VERSION
    assert manifest["reconcile_version"] == versions.RECONCILE_VERSION
    assert manifest["validate_version"] == versions.VALIDATE_VERSION
    assert manifest["project_version"] == versions.PROJECT_VERSION


def test_run_pipeline_refuses_existing_run_dir(tmp_path: Path) -> None:
    source_path = Path("data/examples/petsmart-inc.md")
    run_id = f"2026-05-02T120000Z_petsmart-inc_{_short_input_hash([IngestSource('petsmart-inc', source_path)])}"
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


def test_run_pipeline_rejects_bad_run_id(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        run_pipeline(
            run_id="foo",
            run_dir=tmp_path / "foo",
            source="examples",
            slugs=["petsmart-inc"],
            projection_name="bidder_cycle_baseline_v1",
        )
