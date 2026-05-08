"""Phase 1 (US-002) — sec_review_compiler run kernel + CLI."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from sec_review_compiler import __version__
from sec_review_compiler.cli import init_run, main
from sec_review_compiler.config import LINKFLOW_PROBE_RUN_ID, config_hash
from sec_review_compiler.errors import AtomicWriteError, InvalidRunIdError
from sec_review_compiler.run.ids import RunClock, RunId
from sec_review_compiler.run.io import atomic_write_json, atomic_write_text
from sec_review_compiler.run.manifest import MANIFEST_FILENAME, RunManifest


# ---------------------------------------------------------------- RunId

class TestRunId:
    def test_parse_canonical(self) -> None:
        rid = RunId.parse("20260508T131745Z_synthetic-demo_deadbeef")
        assert rid.timestamp == "20260508T131745Z"
        assert rid.slug == "synthetic-demo"
        assert rid.short_hex == "deadbeef"
        assert str(rid) == "20260508T131745Z_synthetic-demo_deadbeef"

    @pytest.mark.parametrize(
        "value",
        [
            "",
            "20260508T131745Z_synthetic-demo",
            "20260508T131745Z_synthetic-demo_DEADBEEF",
            "20260508T131745Z_synthetic-demo_deadbee",
            "20260508T131745Z_synthetic-demo_deadbeef0",
            "20260508T131745_synthetic-demo_deadbeef",
            "20260532T131745Z_synthetic-demo_deadbeef",
            "20260508T131745Z_Synthetic_deadbeef",
            "20260508T131745Z__deadbeef",
            "not-a-run-id",
        ],
    )
    def test_invalid_ids_raise(self, value: str) -> None:
        with pytest.raises(InvalidRunIdError):
            RunId.parse(value)

    def test_new_round_trips_through_parse(self) -> None:
        rid = RunId.new("synthetic-demo")
        assert RunId.parse(str(rid)) == rid

    def test_new_rejects_invalid_slug(self) -> None:
        with pytest.raises(InvalidRunIdError):
            RunId.new("Bad_Slug")

    def test_run_clock_from_id_is_deterministic(self) -> None:
        rid = RunId.parse("20260508T131745Z_synthetic-demo_deadbeef")
        clock = RunClock.from_run_id(rid)
        assert clock.now().isoformat() == "2026-05-08T13:17:45+00:00"
        # Calling again returns the same instant — no drift.
        assert clock.now() == clock.now()


# --------------------------------------------------------------- IO

class TestAtomicIO:
    def test_atomic_write_text_creates_only_final_file(self, tmp_path: Path) -> None:
        target = tmp_path / "nested" / "thing.txt"
        atomic_write_text(target, "hello")
        assert target.read_text() == "hello"
        assert list(target.parent.iterdir()) == [target]

    def test_atomic_write_json_round_trip(self, tmp_path: Path) -> None:
        target = tmp_path / "obj.json"
        atomic_write_json(target, {"a": 1, "b": [2, 3]})
        loaded = json.loads(target.read_text())
        assert loaded == {"a": 1, "b": [2, 3]}
        assert list(target.parent.iterdir()) == [target]

    def test_atomic_write_failure_cleans_temp(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        target = tmp_path / "fail.txt"

        def boom(*args: object, **kwargs: object) -> None:
            raise RuntimeError("disk full")

        monkeypatch.setattr("sec_review_compiler.run.io.os.replace", boom)
        with pytest.raises(AtomicWriteError):
            atomic_write_text(target, "data")
        assert not target.exists()
        # Temp file cleanup leaves the parent dir empty.
        assert list(tmp_path.iterdir()) == []


# --------------------------------------------------------------- Manifest

class TestRunManifest:
    def test_manifest_fields_and_serialisation(self, tmp_path: Path) -> None:
        rid = RunId.parse("20260508T131745Z_synthetic-demo_deadbeef")
        manifest = RunManifest.for_run(rid, config={"k": "v"})

        assert manifest.run_id == str(rid)
        assert manifest.started_at.isoformat() == "2026-05-08T13:17:45+00:00"
        assert manifest.config_hash == config_hash({"k": "v"})
        assert manifest.linkflow_probe_run_id == LINKFLOW_PROBE_RUN_ID
        assert manifest.linkflow_probe_run_id == "20260508T123815Z"
        assert manifest.package_version == __version__

        path = manifest.write(tmp_path)
        assert path == tmp_path / MANIFEST_FILENAME
        loaded = json.loads(path.read_text())
        assert loaded["run_id"] == str(rid)
        assert loaded["linkflow_probe_run_id"] == "20260508T123815Z"
        assert loaded["package_version"] == __version__
        assert sorted(loaded.keys()) == sorted(
            ["run_id", "started_at", "config_hash", "linkflow_probe_run_id", "package_version"]
        )

    def test_extra_fields_rejected(self) -> None:
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            RunManifest(  # type: ignore[call-arg]
                run_id="20260508T131745Z_demo_deadbeef",
                started_at="2026-05-08T13:17:45+00:00",
                config_hash="x" * 64,
                linkflow_probe_run_id=LINKFLOW_PROBE_RUN_ID,
                package_version="0.1.0",
                extra="boom",
            )

    def test_manifest_is_frozen(self) -> None:
        from pydantic import ValidationError

        rid = RunId.parse("20260508T131745Z_synthetic-demo_deadbeef")
        manifest = RunManifest.for_run(rid, config={})
        with pytest.raises(ValidationError):
            manifest.run_id = "other"  # type: ignore[misc]


# --------------------------------------------------------------- CLI

class TestCLI:
    def test_init_run_creates_manifest(self, tmp_path: Path) -> None:
        run_dir = init_run("synthetic-demo", tmp_path)
        manifest_path = run_dir / MANIFEST_FILENAME
        assert manifest_path.exists()
        loaded = json.loads(manifest_path.read_text())
        assert loaded["linkflow_probe_run_id"] == "20260508T123815Z"
        assert "_synthetic-demo_" in loaded["run_id"]
        assert loaded["package_version"] == __version__

    def test_main_invokes_init_run(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        rc = main(["init-run", "--deal-slug", "synthetic-demo", "--run-root", str(tmp_path)])
        assert rc == 0
        printed = Path(capsys.readouterr().out.strip())
        assert printed.is_dir()
        assert (printed / MANIFEST_FILENAME).exists()

    def test_module_entrypoint_via_subprocess(self, tmp_path: Path) -> None:
        repo_root = Path(__file__).resolve().parent.parent
        env = os.environ.copy()
        src_dir = repo_root / "src"
        existing = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = (
            f"{src_dir}{os.pathsep}{existing}" if existing else str(src_dir)
        )
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "sec_review_compiler",
                "init-run",
                "--deal-slug",
                "synthetic-demo",
                "--run-root",
                str(tmp_path),
            ],
            cwd=str(repo_root),
            env=env,
            capture_output=True,
            text=True,
            check=True,
        )
        printed = Path(result.stdout.strip())
        assert printed.is_dir()
        assert (printed / MANIFEST_FILENAME).exists()
