"""Phase 10 (US-011) — CLI run-synthetic + summarize-run."""

from __future__ import annotations

import io
import json
import os
import sys
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path

import pytest

from sec_review_compiler.cli import main, summarize_run
from sec_review_compiler.filing.examples import SYNTHETIC_FILING_PATH


# ---------------------------------------------------------------- offline run

class TestRunSyntheticOffline:
    def test_run_synthetic_offline_produces_artifacts(self, tmp_path: Path, capsys) -> None:
        run_root = tmp_path / "runs"
        rc = main([
            "run-synthetic",
            "--run-root", str(run_root),
            "--deal-slug", "synthetic-demo",
            "--mode", "offline",
            "--filing-path", str(SYNTHETIC_FILING_PATH),
        ])
        out = capsys.readouterr().out
        assert rc == 0
        payload = json.loads(out)
        assert payload["accepted"] >= 1
        deal_dir = Path(payload["deal_dir"])
        assert (deal_dir / "deal_room.duckdb").exists()
        assert (deal_dir / "exports" / "claim_cards.csv").exists()
        assert (deal_dir / "exports" / "review_queue.csv").exists()
        assert (deal_dir / "exports" / "human_decisions_template.csv").exists()
        assert (deal_dir / "provider_calls.jsonl").exists()
        assert (deal_dir / "tool_calls.jsonl").exists()

    def test_summarize_run_prints_counts(self, tmp_path: Path, capsys) -> None:
        # First run synthetic-offline to populate a deal-room.
        run_root = tmp_path / "runs"
        rc = main([
            "run-synthetic",
            "--run-root", str(run_root),
            "--deal-slug", "synthetic-demo",
            "--mode", "offline",
        ])
        assert rc == 0
        run_payload = json.loads(capsys.readouterr().out)
        deal_dir = Path(run_payload["deal_dir"])

        rc = main(["summarize-run", str(deal_dir)])
        out = capsys.readouterr().out
        assert rc == 0
        summary = json.loads(out)
        assert summary["deal_dir"] == str(deal_dir)
        assert summary["attempts_by_status"]["accepted"] >= 1
        assert summary["review_queue_size"] == 0
        assert summary["provider_call_count"] == 0
        assert summary["tool_call_count"] == 0


# ---------------------------------------------------------------- live without creds

class TestLiveWithoutCredentials:
    def test_live_mode_without_key_fails_before_network(
        self, tmp_path: Path, capsys, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Strip every Linkflow env var so live mode must refuse.
        monkeypatch.delenv("LINKFLOW_API_KEY", raising=False)
        monkeypatch.delenv("LINKFLOW_BASE_URL", raising=False)
        monkeypatch.delenv("LINKFLOW_MODEL", raising=False)
        monkeypatch.delenv("LINKFLOW_REASONING_EFFORT", raising=False)
        monkeypatch.delenv("LINKFLOW_DEFAULT_REASONING", raising=False)
        monkeypatch.delenv("LINKFLOW_MAX_CONCURRENCY", raising=False)

        rc = main([
            "run-synthetic",
            "--run-root", str(tmp_path / "runs"),
            "--deal-slug", "synthetic-demo",
            "--mode", "live",
        ])
        captured = capsys.readouterr()
        assert rc == 2
        # The error message comes from MissingLinkflowCredentialsError.
        assert "LINKFLOW_API_KEY" in captured.err
        # No network artifact should exist (the run dir is created for the
        # manifest, but no deal_room.duckdb because we exited before then).
        for path in (tmp_path / "runs").rglob("deal_room.duckdb"):
            raise AssertionError(f"unexpected deal-room created: {path}")
