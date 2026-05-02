"""CLI dispatcher contract tests.

These tests cover the dispatch contract documented in ``docs/spec.md``:

- ``python -m sec_graph`` is the single top-level entry point and the ``ingest``
  subcommand MUST receive ``--fresh`` when invoked through top-level dispatch.
- ``scripts/fetch_filings.py`` is a deliberate root convenience command, NOT a
  backward-compatibility shim, and its module docstring must say so.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from sec_graph.cli import __init__ as cli_pkg  # noqa: F401  (ensure package importable)
from sec_graph.cli import ingest_cmd
from sec_graph.cli import main as dispatcher_main


REPO_ROOT = Path(__file__).resolve().parents[1]
FETCH_SCRIPT = REPO_ROOT / "scripts" / "fetch_filings.py"


def test_top_level_ingest_forwards_fresh(monkeypatch, tmp_path) -> None:
    """`python -m sec_graph ingest ... --fresh` MUST forward fresh=True."""

    captured: dict[str, object] = {}

    def fake_ingest_examples_to_db(db_path, examples_dir, fresh):
        captured["db"] = Path(db_path)
        captured["examples_dir"] = Path(examples_dir)
        captured["fresh"] = fresh
        return []

    # Stub the ingest function so we never touch DuckDB.
    monkeypatch.setattr(
        ingest_cmd,
        "ingest_examples_to_db",
        fake_ingest_examples_to_db,
    )

    db_path = tmp_path / "x.duckdb"
    examples_dir = tmp_path / "examples"
    examples_dir.mkdir()

    rc = dispatcher_main(
        [
            "ingest",
            "--all",
            "--examples-dir",
            str(examples_dir),
            "--db",
            str(db_path),
            "--fresh",
        ]
    )

    assert rc == 0
    assert captured.get("fresh") is True, (
        "Top-level dispatcher dropped --fresh; ingest received "
        f"fresh={captured.get('fresh')!r}"
    )
    assert captured.get("db") == db_path
    assert captured.get("examples_dir") == examples_dir


def test_fetch_script_is_not_documented_as_backward_compatibility() -> None:
    """`scripts/fetch_filings.py` must be framed as deliberate, not legacy."""

    text = FETCH_SCRIPT.read_text(encoding="utf-8")

    # Extract the module docstring (the first triple-quoted block).
    import ast

    module = ast.parse(text)
    docstring = ast.get_docstring(module)
    assert docstring is not None, (
        "scripts/fetch_filings.py must have a module docstring stating its role"
    )

    lowered = docstring.lower()

    forbidden = [
        "backward-compatibility",
        "backward compatibility",
        "compat shim",
        "compatibility shim",
        "legacy",
    ]
    for needle in forbidden:
        assert needle not in lowered, (
            f"scripts/fetch_filings.py docstring must NOT frame itself as "
            f"{needle!r}; spec calls it a deliberate root convenience command."
        )

    assert "deliberate root convenience" in lowered, (
        "scripts/fetch_filings.py docstring must positively frame itself as a "
        "'deliberate root convenience' command per docs/spec.md."
    )
