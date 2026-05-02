# Stage 1: Schema Scaffolding Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the schema foundation for the sec_graph pipeline — Pydantic models for every canonical type, DuckDB DDL that creates every table, deterministic ID helpers, evidence-binding utilities, run-metadata scaffolding, a synthetic smoke filing fixture, and a hand-authored canonical fixture that exercises every table end-to-end. After Stage 1, three parallel tracks (ingest, schema-validation, extraction) can fan out independently.

**Architecture:** A new `src/sec_graph/schema/` subpackage holds all type definitions and SQL DDL. Pydantic v2 models pair with `CREATE TABLE` strings stored next to them. A small `db.py` provides `connect()`, `apply_ddl()`, `insert_model()`, `fetch_model()` for round-tripping. Lists (e.g., `evidence_ids: list[str]`) map to DuckDB `VARCHAR[]`. The existing `edgar.py` module relocates from `src/sec_graph/` to `src/sec_graph/fetch/` to match the layered architecture. No business logic for ingestion / extraction / reconciliation is implemented in Stage 1; the deliverable is purely the schema contract plus fixtures that prove it works end-to-end.

**Tech Stack:** Python ≥3.11, Pydantic ≥2, DuckDB ≥0.10, pytest ≥8, `sec2md==0.1.22` (already pinned).

---

## Context

**Spec:** [docs/superpowers/specs/2026-05-02-sec-graph-modular-architecture.md](../specs/2026-05-02-sec-graph-modular-architecture.md). Read §3.1, §7, §10, §11, §12 (Stage 1 row), and §13.4 mitigations before starting.

**Current state:**
- `src/sec_graph/edgar.py` — working EDGAR fetcher with 4 passing tests in `tests/test_edgar.py`.
- `src/sec_graph/__init__.py` — version stub only.
- `pyproject.toml` — depends on `sec2md==0.1.22` and `pytest>=8`. No Pydantic, no DuckDB yet.
- 4 example filings under `data/examples/`. ~400 seed URLs in `seeds.csv`.
- No schema, no models, no canonical store yet. Stage 1 builds them.

**Stage 1 done means:**
- Every canonical/auxiliary/runtime table from §3.1 of the spec is creatable via DDL.
- Every Pydantic model round-trips through DuckDB without data loss.
- ID helpers produce stable strings of the form `{slug}_{type}_{sequence}`.
- A synthetic smoke filing exists at `tests/fixtures/smoke_filing.md`.
- A hand-authored canonical record set for the smoke filing exists at `tests/fixtures/smoke_canonical.json` and exercises every table.
- An end-to-end test loads the smoke canonical JSON, validates every record through Pydantic, writes them to a fresh DuckDB, reads them back, and asserts equality.

**Out of scope for Stage 1:** Cleaning policy, paragraph extraction from real markdown, any actual extraction rules, reconciliation logic, validation logic, projection logic. Those belong to later stages.

## File Structure

```
src/sec_graph/
  __init__.py                          # (modify)
  fetch/                               # (NEW)
    __init__.py                        # exports edgar.main
    edgar.py                           # MOVED from src/sec_graph/edgar.py
  schema/                              # (NEW)
    __init__.py                        # re-exports models, helpers, versions
    versions.py                        # stage version constants
    ids.py                             # make_id, parse_id
    evidence.py                        # quote_hash, validate_quote, extract_quote
    db.py                              # connect, apply_ddl, insert_model, fetch_model
    schema_init.py                     # init_schema(conn) applies every module's DDL
    models/                            # (NEW)
      __init__.py                      # re-exports all model classes
      filings.py                       # CleanFiling, Section, Paragraph, SourceSpan + DDL
      extraction.py                    # ExtractionCandidate + DDL
      canonical.py                     # Deal, ProcessCycle, Actor, Event, EventActorLink + DDL
      judgments.py                     # Judgment + DDL (with supersedes_judgment_id)
      auxiliary.py                     # 9 auxiliary models + DDL
      runtime.py                       # RunMetadata + DDL

scripts/
  fetch_filings.py                     # (modify) update import path

tests/
  test_edgar.py                        # (modify) update import path
  test_schema_versions.py              # (NEW)
  test_schema_ids.py                   # (NEW)
  test_schema_evidence.py              # (NEW)
  test_schema_db.py                    # (NEW)
  test_schema_filings.py               # (NEW)
  test_schema_extraction.py            # (NEW)
  test_schema_canonical.py             # (NEW)
  test_schema_judgments.py             # (NEW)
  test_schema_auxiliary.py             # (NEW)
  test_schema_runtime.py               # (NEW)
  test_schema_init.py                  # (NEW) end-to-end create-all-tables
  test_smoke_canonical.py              # (NEW) end-to-end Stage 1 acceptance
  fixtures/                            # (NEW)
    smoke_filing.md                    # synthetic ~50-line filing
    smoke_canonical.json               # hand-authored canonical record set

pyproject.toml                         # (modify) add pydantic + duckdb
```

---

## Task 0: Establish a baseline commit on `main`

The repository has untracked files but no commits yet. Every subsequent task assumes a baseline commit exists. This task creates one.

**Files:** all currently-untracked project files (`AGENTS.md`, `README.md`, `pyproject.toml`, `seeds.csv`, `.gitignore`, `data/`, `docs/`, `scripts/`, `src/`, `tests/`).

- [ ] **Step 1: Verify there are no commits yet**

Run: `git log --oneline 2>&1 | head -5`

Expected: `fatal: your current branch 'main' does not have any commits yet`. If commits already exist, **skip Task 0** and start at Task 1.

- [ ] **Step 2: Stage all project files**

Run: `git add AGENTS.md README.md pyproject.toml seeds.csv .gitignore data/ docs/ scripts/ src/ tests/`

Expected: no errors.

- [ ] **Step 3: Verify staging**

Run: `git status --short`

Expected: every project file appears with `A` (added) prefix; nothing remains as `??`.

- [ ] **Step 4: Create the baseline commit**

```bash
git commit -m "chore: initial commit of sec_graph project baseline

Adds README, AGENTS.md, design.md, GPT-Pro reference plan, EDGAR fetcher
and tests, seeds.csv, four example filings. This is the starting point;
subsequent commits implement Stage 1 (schema scaffolding) per the
modular architecture spec at docs/superpowers/specs/2026-05-02-sec-graph-modular-architecture.md.
"
```

- [ ] **Step 5: Verify the commit landed**

Run: `git log --oneline`

Expected: one commit on `main`.

---

## Task 1: Migrate `edgar.py` into `fetch/` subpackage

**Files:**
- Create: `src/sec_graph/fetch/__init__.py`
- Move: `src/sec_graph/edgar.py` → `src/sec_graph/fetch/edgar.py`
- Modify: `tests/test_edgar.py:7` (import line)
- Modify: `scripts/fetch_filings.py:7` (import line)

- [ ] **Step 1: Create the `fetch/` package directory and `__init__.py`**

Create `src/sec_graph/fetch/__init__.py`:

```python
"""EDGAR fetch module.

Downloads SEC filings, resolves the substantive document, and converts to
sec2md markdown. The single entry point is ``main`` (CLI) or ``process_deal``.
"""

from sec_graph.fetch.edgar import (
    ExcludedFormTypeError,
    FilingDocument,
    Seed,
    main,
    process_deal,
    resolve_substantive_document,
    parse_accession,
)

__all__ = [
    "ExcludedFormTypeError",
    "FilingDocument",
    "Seed",
    "main",
    "process_deal",
    "resolve_substantive_document",
    "parse_accession",
]
```

- [ ] **Step 2: Move `edgar.py` into `fetch/`**

```bash
git mv src/sec_graph/edgar.py src/sec_graph/fetch/edgar.py
```

(After Task 0's baseline commit `edgar.py` is tracked, so `git mv` works. If for any reason it does not, fall back to `mv src/sec_graph/edgar.py src/sec_graph/fetch/edgar.py` and let `git add -A` in Step 6 capture both the deletion and the new path.)

- [ ] **Step 3: Update test import**

In `tests/test_edgar.py`, line 7, change `from sec_graph import edgar` to `from sec_graph.fetch import edgar`.

```python
from sec_graph.fetch import edgar
```

- [ ] **Step 4: Update script import**

In `scripts/fetch_filings.py`, line 7, change `from sec_graph.edgar import main` to `from sec_graph.fetch.edgar import main`.

```python
from sec_graph.fetch.edgar import main
```

- [ ] **Step 5: Run all existing tests to verify no regression**

Run: `pytest tests/ -v`

Expected: 5 tests pass (4 in `test_edgar.py`, 1 in `test_package.py`). Output should include `5 passed`.

- [ ] **Step 6: Commit**

```bash
git add -A src/sec_graph/ tests/test_edgar.py scripts/fetch_filings.py
git commit -m "refactor(fetch): move edgar.py into fetch/ subpackage

Per the modular architecture spec (§3.2), fetch is its own subpackage with
a typed input/output contract. Existing tests and scripts continue to work
via updated import paths.
"
```

---

## Task 2: Add Pydantic + DuckDB dependencies and create the `schema/` skeleton

**Files:**
- Modify: `pyproject.toml`
- Create: `src/sec_graph/schema/__init__.py`
- Create: `src/sec_graph/schema/models/__init__.py`

- [ ] **Step 1: Add dependencies to `pyproject.toml`**

Modify the `[project]` block in `pyproject.toml` to read:

```toml
[project]
name = "sec-graph"
version = "0.1.0"
description = "Canonical graph extraction experiments for SEC merger filings"
requires-python = ">=3.11"
dependencies = [
  "sec2md==0.1.22",
  "pydantic>=2.5",
  "duckdb>=0.10",
]

[project.optional-dependencies]
dev = [
  "pytest>=8",
]

[tool.pytest.ini_options]
pythonpath = ["src"]
testpaths = ["tests"]
```

- [ ] **Step 2: Install the new dependencies**

Run: `python -m pip install -e ".[dev]"`

Expected: pip output ends with `Successfully installed ...pydantic-2... duckdb-...`. No errors.

- [ ] **Step 3: Verify Python can import them**

Run: `python -c "import pydantic; import duckdb; print(pydantic.VERSION, duckdb.__version__)"`

Expected: a Pydantic 2.x version and a DuckDB ≥0.10 version printed.

- [ ] **Step 4: Create `schema/__init__.py` skeleton**

Create `src/sec_graph/schema/__init__.py`:

```python
"""Schema subpackage.

Contains canonical type definitions (Pydantic models), DuckDB DDL, deterministic
ID helpers, evidence-binding utilities, and run-metadata scaffolding. Every
other sec_graph module imports from here. See
docs/superpowers/specs/2026-05-02-sec-graph-modular-architecture.md §3.1.
"""
```

- [ ] **Step 5: Create `schema/models/__init__.py` skeleton**

Create `src/sec_graph/schema/models/__init__.py`:

```python
"""Pydantic model definitions for every canonical and auxiliary table."""
```

- [ ] **Step 6: Verify imports still work**

Run: `pytest tests/ -v`

Expected: 5 tests still pass.

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml src/sec_graph/schema/__init__.py src/sec_graph/schema/models/__init__.py
git commit -m "build(schema): add pydantic and duckdb deps; create schema package skeleton

Foundation for Stage 1 schema scaffolding per the modular architecture spec.
"
```

---

## Task 3: Stage version constants

**Files:**
- Create: `src/sec_graph/schema/versions.py`
- Create: `tests/test_schema_versions.py`

The pipeline records a per-stage version on every run. Per spec §7, when stage rules change, the constant bumps and prior runs are preserved in their snapshots.

- [ ] **Step 1: Write the failing test**

Create `tests/test_schema_versions.py`:

```python
"""Tests for stage version constants."""

import re

from sec_graph.schema import versions


def test_all_stage_versions_exist() -> None:
    expected = {
        "PARSER_VERSION",
        "INGEST_VERSION",
        "EXTRACT_VERSION",
        "RECONCILE_VERSION",
        "VALIDATE_VERSION",
        "PROJECT_VERSION",
    }
    actual = {name for name in dir(versions) if not name.startswith("_")}
    missing = expected - actual
    assert not missing, f"missing version constants: {missing}"


def test_versions_are_semver_strings() -> None:
    for name in (
        "PARSER_VERSION",
        "INGEST_VERSION",
        "EXTRACT_VERSION",
        "RECONCILE_VERSION",
        "VALIDATE_VERSION",
        "PROJECT_VERSION",
    ):
        value = getattr(versions, name)
        assert isinstance(value, str)
        assert re.fullmatch(r"\d+\.\d+\.\d+", value), f"{name}={value!r} not semver"
```

- [ ] **Step 2: Run, expect failure**

Run: `pytest tests/test_schema_versions.py -v`

Expected: `ImportError` or `ModuleNotFoundError` for `sec_graph.schema.versions`.

- [ ] **Step 3: Implement `versions.py`**

Create `src/sec_graph/schema/versions.py`:

```python
"""Per-stage version constants.

When a stage's rules or output format changes meaningfully, bump the relevant
constant. Prior runs remain available in ``runs/{run_id}/`` snapshots. See spec
§7 (Determinism Contract) and §9 (Schema Evolution Policy).
"""

PARSER_VERSION = "0.1.0"
INGEST_VERSION = "0.1.0"
EXTRACT_VERSION = "0.1.0"
RECONCILE_VERSION = "0.1.0"
VALIDATE_VERSION = "0.1.0"
PROJECT_VERSION = "0.1.0"
```

- [ ] **Step 4: Run, expect pass**

Run: `pytest tests/test_schema_versions.py -v`

Expected: 2 tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/sec_graph/schema/versions.py tests/test_schema_versions.py
git commit -m "feat(schema): add per-stage version constants

Constants bump when stage rules change. Prior runs preserved in snapshots
per spec §7 + §9.
"
```

---

## Task 4: Deterministic ID helpers

**Files:**
- Create: `src/sec_graph/schema/ids.py`
- Create: `tests/test_schema_ids.py`

Per spec §7: every record gets a deterministic ID of form `{slug}_{type}_{sequence}` (e.g., `petsmart_actor_3`). Slugs are lowercase letters/digits/hyphens; type tokens are short lowercase identifiers; sequence is a positive integer.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_schema_ids.py`:

```python
"""Tests for deterministic ID helpers."""

import pytest

from sec_graph.schema.ids import make_id, parse_id


def test_make_id_canonical_form() -> None:
    assert make_id("petsmart", "actor", 3) == "petsmart_actor_3"
    assert make_id("zep", "evt", 17) == "zep_evt_17"
    assert make_id("providence-worcester", "judgment", 5) == (
        "providence-worcester_judgment_5"
    )


def test_make_id_sequence_must_be_positive() -> None:
    with pytest.raises(ValueError):
        make_id("petsmart", "actor", 0)
    with pytest.raises(ValueError):
        make_id("petsmart", "actor", -1)


def test_make_id_slug_must_be_lowercase_alnum_hyphen() -> None:
    with pytest.raises(ValueError):
        make_id("PetSmart", "actor", 1)
    with pytest.raises(ValueError):
        make_id("pets_mart", "actor", 1)  # underscore disallowed
    with pytest.raises(ValueError):
        make_id("", "actor", 1)


def test_make_id_type_must_be_lowercase_alpha() -> None:
    with pytest.raises(ValueError):
        make_id("petsmart", "Actor", 1)
    with pytest.raises(ValueError):
        make_id("petsmart", "act-or", 1)
    with pytest.raises(ValueError):
        make_id("petsmart", "", 1)


def test_parse_id_round_trips() -> None:
    assert parse_id("petsmart_actor_3") == ("petsmart", "actor", 3)
    assert parse_id("providence-worcester_judgment_5") == (
        "providence-worcester",
        "judgment",
        5,
    )
    assert parse_id("zep_evt_17") == ("zep", "evt", 17)


def test_parse_id_rejects_malformed() -> None:
    with pytest.raises(ValueError):
        parse_id("petsmart_actor")
    with pytest.raises(ValueError):
        parse_id("petsmart_actor_abc")
    with pytest.raises(ValueError):
        parse_id("petsmart_actor_-1")


def test_make_id_is_deterministic() -> None:
    """Same inputs MUST yield the same ID across calls."""
    a = make_id("petsmart", "actor", 3)
    b = make_id("petsmart", "actor", 3)
    assert a == b
```

- [ ] **Step 2: Run, expect failure**

Run: `pytest tests/test_schema_ids.py -v`

Expected: `ImportError` for `sec_graph.schema.ids`.

- [ ] **Step 3: Implement `ids.py`**

Create `src/sec_graph/schema/ids.py`:

```python
"""Deterministic ID construction.

Every canonical record's primary key has the form ``{slug}_{type}_{sequence}``.
Reruns over identical inputs produce identical IDs. See spec §7.
"""

from __future__ import annotations

import re

_SLUG_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]*$")
_TYPE_PATTERN = re.compile(r"^[a-z]+$")


def make_id(slug: str, type_: str, sequence: int) -> str:
    """Construct a deterministic record ID.

    >>> make_id("petsmart", "actor", 3)
    'petsmart_actor_3'
    """
    if not _SLUG_PATTERN.fullmatch(slug):
        raise ValueError(
            f"slug {slug!r} must be lowercase alphanumeric with hyphens, "
            "non-empty, and not start with a hyphen"
        )
    if not _TYPE_PATTERN.fullmatch(type_):
        raise ValueError(f"type {type_!r} must be a non-empty lowercase alpha string")
    if sequence <= 0:
        raise ValueError(f"sequence must be a positive int, got {sequence}")
    return f"{slug}_{type_}_{sequence}"


def parse_id(record_id: str) -> tuple[str, str, int]:
    """Decompose an ID into ``(slug, type, sequence)``.

    >>> parse_id("petsmart_actor_3")
    ('petsmart', 'actor', 3)
    """
    parts = record_id.rsplit("_", 2)
    if len(parts) != 3:
        raise ValueError(f"ID {record_id!r} does not match {{slug}}_{{type}}_{{seq}}")
    slug, type_, seq_text = parts
    if not _SLUG_PATTERN.fullmatch(slug):
        raise ValueError(f"slug part {slug!r} of ID {record_id!r} is invalid")
    if not _TYPE_PATTERN.fullmatch(type_):
        raise ValueError(f"type part {type_!r} of ID {record_id!r} is invalid")
    try:
        sequence = int(seq_text)
    except ValueError as exc:
        raise ValueError(
            f"sequence part {seq_text!r} of ID {record_id!r} is not an int"
        ) from exc
    if sequence <= 0:
        raise ValueError(f"sequence must be positive in ID {record_id!r}")
    return slug, type_, sequence
```

- [ ] **Step 4: Run, expect pass**

Run: `pytest tests/test_schema_ids.py -v`

Expected: 7 tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/sec_graph/schema/ids.py tests/test_schema_ids.py
git commit -m "feat(schema): add deterministic ID helpers (make_id, parse_id)

IDs follow {slug}_{type}_{sequence} per spec §7. Reruns over identical
inputs yield identical IDs.
"
```

---

## Task 5: Evidence-binding utilities

**Files:**
- Create: `src/sec_graph/schema/evidence.py`
- Create: `tests/test_schema_evidence.py`

Per spec §10.1: every canonical row references at least one `evidence_id` resolving to a span whose `quote_hash` matches the bytes at `(filing_id, char_start, char_end)`. The schema module owns the helpers for span construction and quote-hash verification.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_schema_evidence.py`:

```python
"""Tests for evidence-binding utilities."""

import pytest

from sec_graph.schema.evidence import (
    extract_quote,
    quote_hash,
    validate_quote,
)


def test_quote_hash_is_sha256_hex() -> None:
    h = quote_hash("hello world")
    assert isinstance(h, str)
    assert len(h) == 64
    assert all(c in "0123456789abcdef" for c in h)


def test_quote_hash_deterministic() -> None:
    assert quote_hash("hello") == quote_hash("hello")
    assert quote_hash("hello") != quote_hash("world")


def test_extract_quote_slices_text() -> None:
    text = "abcdefghij"
    assert extract_quote(text, 2, 5) == "cde"
    assert extract_quote(text, 0, len(text)) == text


def test_extract_quote_rejects_invalid_offsets() -> None:
    text = "abcdef"
    with pytest.raises(ValueError):
        extract_quote(text, -1, 3)
    with pytest.raises(ValueError):
        extract_quote(text, 4, 2)  # end before start
    with pytest.raises(ValueError):
        extract_quote(text, 0, 100)  # past end


def test_validate_quote_round_trip() -> None:
    text = "Background of the Merger"
    quoted = "Background"
    h = quote_hash(quoted)
    assert validate_quote(text, 0, len(quoted), h) is True


def test_validate_quote_rejects_mismatch() -> None:
    text = "Background of the Merger"
    h = quote_hash("Reasons")
    assert validate_quote(text, 0, 10, h) is False
```

- [ ] **Step 2: Run, expect failure**

Run: `pytest tests/test_schema_evidence.py -v`

Expected: `ImportError` for `sec_graph.schema.evidence`.

- [ ] **Step 3: Implement `evidence.py`**

Create `src/sec_graph/schema/evidence.py`:

```python
"""Evidence-binding utilities.

Every canonical row references at least one ``SourceSpan`` (via ``evidence_ids``)
whose ``quote_hash`` matches the bytes at ``(filing_id, char_start, char_end)``.
This module provides the primitive helpers for building and validating those
bindings. See spec §10.1.
"""

from __future__ import annotations

import hashlib


def quote_hash(quote_text: str) -> str:
    """SHA-256 hex digest of a quote string (UTF-8 encoded)."""
    return hashlib.sha256(quote_text.encode("utf-8")).hexdigest()


def extract_quote(filing_text: str, char_start: int, char_end: int) -> str:
    """Slice ``filing_text[char_start:char_end]`` with bounds checking."""
    if char_start < 0:
        raise ValueError(f"char_start must be >= 0, got {char_start}")
    if char_end < char_start:
        raise ValueError(
            f"char_end ({char_end}) must be >= char_start ({char_start})"
        )
    if char_end > len(filing_text):
        raise ValueError(
            f"char_end ({char_end}) exceeds filing_text length ({len(filing_text)})"
        )
    return filing_text[char_start:char_end]


def validate_quote(
    filing_text: str, char_start: int, char_end: int, expected_hash: str
) -> bool:
    """Return True iff the slice at ``(char_start, char_end)`` hashes to expected."""
    actual = quote_hash(extract_quote(filing_text, char_start, char_end))
    return actual == expected_hash
```

- [ ] **Step 4: Run, expect pass**

Run: `pytest tests/test_schema_evidence.py -v`

Expected: 6 tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/sec_graph/schema/evidence.py tests/test_schema_evidence.py
git commit -m "feat(schema): add evidence-binding utilities (quote_hash, validate_quote)

Implements the §10.1 contract that every canonical row's evidence chain
resolves to verifiable text spans.
"
```

---

## Task 6: DB connection + DDL helpers (minimal)

**Files:**
- Create: `src/sec_graph/schema/db.py`
- Create: `tests/test_schema_db.py`

This task adds the connection primitive plus a `apply_ddl(conn, sql)` helper. Model-aware helpers (`insert_model`, `fetch_model`) come in Task 13 once all models exist. Each model task (7-12) tests its own DDL using `apply_ddl` and a parameterized insert.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_schema_db.py`:

```python
"""Tests for the schema DB primitive helpers."""

import duckdb

from sec_graph.schema.db import apply_ddl, connect


def test_connect_returns_duckdb_connection() -> None:
    conn = connect(":memory:")
    try:
        assert isinstance(conn, duckdb.DuckDBPyConnection)
        assert conn.execute("SELECT 1").fetchone() == (1,)
    finally:
        conn.close()


def test_apply_ddl_creates_table(tmp_path) -> None:
    db_path = tmp_path / "test.duckdb"
    conn = connect(str(db_path))
    try:
        apply_ddl(
            conn,
            """
            CREATE TABLE foo (
                id VARCHAR PRIMARY KEY,
                value INTEGER
            );
            """,
        )
        conn.execute("INSERT INTO foo VALUES (?, ?)", ["a", 1])
        row = conn.execute("SELECT id, value FROM foo").fetchone()
        assert row == ("a", 1)
    finally:
        conn.close()


def test_apply_ddl_handles_multiple_statements() -> None:
    conn = connect(":memory:")
    try:
        apply_ddl(
            conn,
            """
            CREATE TABLE a (x INTEGER);
            CREATE TABLE b (y INTEGER);
            """,
        )
        tables = {
            row[0]
            for row in conn.execute("SHOW TABLES").fetchall()
        }
        assert {"a", "b"}.issubset(tables)
    finally:
        conn.close()
```

- [ ] **Step 2: Run, expect failure**

Run: `pytest tests/test_schema_db.py -v`

Expected: `ImportError` for `sec_graph.schema.db`.

- [ ] **Step 3: Implement `db.py`**

Create `src/sec_graph/schema/db.py`:

```python
"""DuckDB connection and DDL primitives.

Model-aware insert/fetch helpers are defined in :mod:`sec_graph.schema.schema_init`
once every module's DDL has been registered.
"""

from __future__ import annotations

from pathlib import Path

import duckdb


def connect(path: str | Path) -> duckdb.DuckDBPyConnection:
    """Open a DuckDB connection. ``path`` may be ``":memory:"`` for ephemeral use."""
    return duckdb.connect(str(path))


def apply_ddl(conn: duckdb.DuckDBPyConnection, ddl: str) -> None:
    """Execute one or more semicolon-separated DDL statements."""
    conn.execute(ddl)
```

- [ ] **Step 4: Run, expect pass**

Run: `pytest tests/test_schema_db.py -v`

Expected: 3 tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/sec_graph/schema/db.py tests/test_schema_db.py
git commit -m "feat(schema): add DuckDB connect + apply_ddl helpers

Primitives that downstream model modules use to register their DDL. Model-
aware insert/fetch helpers come in a later task once all models exist.
"
```

---

## Task 7: Filings models + DDL (CleanFiling, Section, Paragraph, SourceSpan)

**Files:**
- Create: `src/sec_graph/schema/models/filings.py`
- Create: `tests/test_schema_filings.py`

These are the artifacts produced by `ingest` per spec §3.3. `Section` is a separate table (one row per section span within a filing) rather than a JSON column on `filings`, for query-cleanliness.

- [ ] **Step 1: Write the failing test**

Create `tests/test_schema_filings.py`:

```python
"""Tests for filings/sections/paragraphs/spans models + DDL."""

from datetime import datetime, timezone

from sec_graph.schema.db import apply_ddl, connect
from sec_graph.schema.models.filings import (
    CleanFiling,
    DDL as FILINGS_DDL,
    Paragraph,
    Section,
    SourceSpan,
)


def _round_trip(model_class, table, model, conn, pk_col):
    data = model.model_dump()
    columns = ", ".join(data.keys())
    placeholders = ", ".join(["?"] * len(data))
    conn.execute(
        f"INSERT INTO {table} ({columns}) VALUES ({placeholders})",
        list(data.values()),
    )
    row = conn.execute(
        f"SELECT * FROM {table} WHERE {pk_col} = ?",
        [data[pk_col]],
    ).fetchone()
    cols = [d[0] for d in conn.description]
    fetched = model_class.model_validate(dict(zip(cols, row)))
    return fetched


def test_filings_ddl_creates_all_four_tables() -> None:
    conn = connect(":memory:")
    apply_ddl(conn, FILINGS_DDL)
    tables = {row[0] for row in conn.execute("SHOW TABLES").fetchall()}
    assert {"filings", "sections", "paragraphs", "spans"}.issubset(tables)
    conn.close()


def test_clean_filing_round_trip() -> None:
    conn = connect(":memory:")
    apply_ddl(conn, FILINGS_DDL)
    f = CleanFiling(
        filing_id="petsmart_filing_1",
        deal_slug="petsmart",
        source_filename="raw.md",
        raw_md_path="data/filings/petsmart/raw.md",
        raw_md_hash="a" * 64,
        clean_md_hash="b" * 64,
        page_count=42,
        parser_version="0.1.0",
        ingested_at=datetime(2026, 5, 2, 12, 0, tzinfo=timezone.utc),
        run_id="2026-05-02_smoke",
    )
    fetched = _round_trip(CleanFiling, "filings", f, conn, "filing_id")
    assert fetched == f
    conn.close()


def test_section_round_trip() -> None:
    conn = connect(":memory:")
    apply_ddl(conn, FILINGS_DDL)
    s = Section(
        section_id="petsmart_section_1",
        filing_id="petsmart_filing_1",
        section_name="Background of the Merger",
        char_start=10000,
        char_end=20000,
        run_id="2026-05-02_smoke",
    )
    fetched = _round_trip(Section, "sections", s, conn, "section_id")
    assert fetched == s
    conn.close()


def test_paragraph_round_trip() -> None:
    conn = connect(":memory:")
    apply_ddl(conn, FILINGS_DDL)
    p = Paragraph(
        paragraph_id="petsmart_paragraph_1",
        filing_id="petsmart_filing_1",
        section="Background of the Merger",
        page_hint=29,
        char_start=10000,
        char_end=10500,
        paragraph_text="The board met to discuss strategic alternatives.",
        paragraph_hash="c" * 64,
        run_id="2026-05-02_smoke",
    )
    fetched = _round_trip(Paragraph, "paragraphs", p, conn, "paragraph_id")
    assert fetched == p
    conn.close()


def test_paragraph_page_hint_nullable() -> None:
    conn = connect(":memory:")
    apply_ddl(conn, FILINGS_DDL)
    p = Paragraph(
        paragraph_id="petsmart_paragraph_2",
        filing_id="petsmart_filing_1",
        section="unknown_section",
        page_hint=None,
        char_start=20000,
        char_end=20100,
        paragraph_text="Some text without a page marker.",
        paragraph_hash="d" * 64,
        run_id="2026-05-02_smoke",
    )
    fetched = _round_trip(Paragraph, "paragraphs", p, conn, "paragraph_id")
    assert fetched.page_hint is None
    conn.close()


def test_source_span_round_trip() -> None:
    conn = connect(":memory:")
    apply_ddl(conn, FILINGS_DDL)
    span = SourceSpan(
        evidence_id="petsmart_span_1",
        filing_id="petsmart_filing_1",
        paragraph_id="petsmart_paragraph_1",
        char_start=10000,
        char_end=10050,
        quote_text="The board met to discuss strategic alternatives.",
        quote_hash="e" * 64,
        normalization_note=None,
        run_id="2026-05-02_smoke",
    )
    fetched = _round_trip(SourceSpan, "spans", span, conn, "evidence_id")
    assert fetched == span
    conn.close()
```

- [ ] **Step 2: Run, expect failure**

Run: `pytest tests/test_schema_filings.py -v`

Expected: `ImportError` for `sec_graph.schema.models.filings`.

- [ ] **Step 3: Implement `filings.py`**

Create `src/sec_graph/schema/models/filings.py`:

```python
"""Pydantic models + DDL for ingestion-stage tables.

- ``CleanFiling`` (one row per filing)
- ``Section`` (one row per section span)
- ``Paragraph`` (one row per paragraph)
- ``SourceSpan`` (one row per evidence span; paragraph seeds + extraction-narrower)

See spec §3.3.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class CleanFiling(BaseModel):
    filing_id: str
    deal_slug: str
    source_filename: str
    raw_md_path: str
    raw_md_hash: str
    clean_md_hash: str
    page_count: int
    parser_version: str
    ingested_at: datetime
    run_id: str


class Section(BaseModel):
    section_id: str
    filing_id: str
    section_name: str
    char_start: int
    char_end: int
    run_id: str


class Paragraph(BaseModel):
    paragraph_id: str
    filing_id: str
    section: str
    page_hint: int | None
    char_start: int
    char_end: int
    paragraph_text: str
    paragraph_hash: str
    run_id: str


class SourceSpan(BaseModel):
    evidence_id: str
    filing_id: str
    paragraph_id: str
    char_start: int
    char_end: int
    quote_text: str
    quote_hash: str
    normalization_note: str | None
    run_id: str


DDL = """
CREATE TABLE IF NOT EXISTS filings (
    filing_id        VARCHAR PRIMARY KEY,
    deal_slug        VARCHAR NOT NULL,
    source_filename  VARCHAR NOT NULL,
    raw_md_path      VARCHAR NOT NULL,
    raw_md_hash      VARCHAR NOT NULL,
    clean_md_hash    VARCHAR NOT NULL,
    page_count       INTEGER NOT NULL,
    parser_version   VARCHAR NOT NULL,
    ingested_at      TIMESTAMPTZ NOT NULL,
    run_id           VARCHAR NOT NULL
);

CREATE TABLE IF NOT EXISTS sections (
    section_id    VARCHAR PRIMARY KEY,
    filing_id     VARCHAR NOT NULL,
    section_name  VARCHAR NOT NULL,
    char_start    INTEGER NOT NULL,
    char_end      INTEGER NOT NULL,
    run_id        VARCHAR NOT NULL
);

CREATE TABLE IF NOT EXISTS paragraphs (
    paragraph_id    VARCHAR PRIMARY KEY,
    filing_id       VARCHAR NOT NULL,
    section         VARCHAR NOT NULL,
    page_hint       INTEGER,
    char_start      INTEGER NOT NULL,
    char_end        INTEGER NOT NULL,
    paragraph_text  VARCHAR NOT NULL,
    paragraph_hash  VARCHAR NOT NULL,
    run_id          VARCHAR NOT NULL
);

CREATE TABLE IF NOT EXISTS spans (
    evidence_id         VARCHAR PRIMARY KEY,
    filing_id           VARCHAR NOT NULL,
    paragraph_id        VARCHAR NOT NULL,
    char_start          INTEGER NOT NULL,
    char_end            INTEGER NOT NULL,
    quote_text          VARCHAR NOT NULL,
    quote_hash          VARCHAR NOT NULL,
    normalization_note  VARCHAR,
    run_id              VARCHAR NOT NULL
);
"""
```

- [ ] **Step 4: Run, expect pass**

Run: `pytest tests/test_schema_filings.py -v`

Expected: 6 tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/sec_graph/schema/models/filings.py tests/test_schema_filings.py
git commit -m "feat(schema): add ingestion-stage models + DDL (filings/sections/paragraphs/spans)

Models pair with DDL string (CREATE TABLE IF NOT EXISTS) so later tasks can
register every module's DDL via a single init. Round-trip tests cover all
four tables.
"
```

---

## Task 8: Extraction model + DDL (`ExtractionCandidate`)

**Files:**
- Create: `src/sec_graph/schema/models/extraction.py`
- Create: `tests/test_schema_extraction.py`

Per spec §3.4: `ExtractionCandidate` is the intermediate row produced by the extract layer. Lists (`evidence_ids`, `dependencies`) map to DuckDB `VARCHAR[]`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_schema_extraction.py`:

```python
"""Tests for ExtractionCandidate model + DDL."""

from sec_graph.schema.db import apply_ddl, connect
from sec_graph.schema.models.extraction import (
    DDL as EXTRACTION_DDL,
    ExtractionCandidate,
)


def test_extraction_ddl_creates_candidates_table() -> None:
    conn = connect(":memory:")
    apply_ddl(conn, EXTRACTION_DDL)
    tables = {row[0] for row in conn.execute("SHOW TABLES").fetchall()}
    assert "candidates" in tables
    conn.close()


def test_extraction_candidate_round_trip_with_lists() -> None:
    conn = connect(":memory:")
    apply_ddl(conn, EXTRACTION_DDL)
    c = ExtractionCandidate(
        candidate_id="petsmart_candidate_1",
        candidate_type="actor_mention",
        raw_value="Buyer Group",
        normalized_value="Buyer Group",
        confidence="high",
        evidence_ids=["petsmart_span_1", "petsmart_span_2"],
        dependencies=[],
        status="proposed",
        run_id="2026-05-02_smoke",
    )
    data = c.model_dump()
    columns = ", ".join(data.keys())
    placeholders = ", ".join(["?"] * len(data))
    conn.execute(
        f"INSERT INTO candidates ({columns}) VALUES ({placeholders})",
        list(data.values()),
    )
    row = conn.execute(
        "SELECT * FROM candidates WHERE candidate_id = ?",
        ["petsmart_candidate_1"],
    ).fetchone()
    cols = [d[0] for d in conn.description]
    fetched = ExtractionCandidate.model_validate(dict(zip(cols, row)))
    assert fetched == c
    assert fetched.evidence_ids == ["petsmart_span_1", "petsmart_span_2"]
    assert fetched.dependencies == []
    conn.close()


def test_extraction_candidate_optional_normalized_value() -> None:
    c = ExtractionCandidate(
        candidate_id="petsmart_candidate_2",
        candidate_type="bid",
        raw_value="around twenty dollars per share",
        normalized_value=None,
        confidence="low",
        evidence_ids=["petsmart_span_3"],
        dependencies=[],
        status="proposed",
        run_id="2026-05-02_smoke",
    )
    assert c.normalized_value is None
```

- [ ] **Step 2: Run, expect failure**

Run: `pytest tests/test_schema_extraction.py -v`

Expected: `ImportError` for `sec_graph.schema.models.extraction`.

- [ ] **Step 3: Implement `extraction.py`**

Create `src/sec_graph/schema/models/extraction.py`:

```python
"""Pydantic model + DDL for the extract stage.

``ExtractionCandidate`` is the intermediate row produced by every extraction
pass. Candidates may overlap or conflict; reconciliation resolves them. See
spec §3.4.
"""

from __future__ import annotations

from pydantic import BaseModel


class ExtractionCandidate(BaseModel):
    candidate_id: str
    candidate_type: str
    raw_value: str
    normalized_value: str | None
    confidence: str  # 'low' | 'medium' | 'high'
    evidence_ids: list[str]
    dependencies: list[str]
    status: str  # 'proposed' | 'rejected' | 'reconciled'
    run_id: str


DDL = """
CREATE TABLE IF NOT EXISTS candidates (
    candidate_id      VARCHAR PRIMARY KEY,
    candidate_type    VARCHAR NOT NULL,
    raw_value         VARCHAR NOT NULL,
    normalized_value  VARCHAR,
    confidence        VARCHAR NOT NULL,
    evidence_ids      VARCHAR[] NOT NULL,
    dependencies      VARCHAR[] NOT NULL,
    status            VARCHAR NOT NULL,
    run_id            VARCHAR NOT NULL
);
"""
```

- [ ] **Step 4: Run, expect pass**

Run: `pytest tests/test_schema_extraction.py -v`

Expected: 3 tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/sec_graph/schema/models/extraction.py tests/test_schema_extraction.py
git commit -m "feat(schema): add ExtractionCandidate model + DDL

Lists (evidence_ids, dependencies) map to DuckDB VARCHAR[]. Round-trip
verified.
"
```

---

## Task 9: Canonical core models + DDL (Deal, ProcessCycle, Actor, Event, EventActorLink)

**Files:**
- Create: `src/sec_graph/schema/models/canonical.py`
- Create: `tests/test_schema_canonical.py`

These are the heart of the canonical store. Per spec §3.5. Each row carries `evidence_ids: list[str]` and `run_id`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_schema_canonical.py`:

```python
"""Tests for canonical core models + DDL."""

from datetime import date

from sec_graph.schema.db import apply_ddl, connect
from sec_graph.schema.models.canonical import (
    Actor,
    DDL as CANONICAL_DDL,
    Deal,
    Event,
    EventActorLink,
    ProcessCycle,
)


def _round_trip(model_class, table, model, conn, pk_col):
    data = model.model_dump()
    columns = ", ".join(data.keys())
    placeholders = ", ".join(["?"] * len(data))
    conn.execute(
        f"INSERT INTO {table} ({columns}) VALUES ({placeholders})",
        list(data.values()),
    )
    row = conn.execute(
        f"SELECT * FROM {table} WHERE {pk_col} = ?",
        [data[pk_col]],
    ).fetchone()
    cols = [d[0] for d in conn.description]
    return model_class.model_validate(dict(zip(cols, row)))


def test_canonical_ddl_creates_all_five_tables() -> None:
    conn = connect(":memory:")
    apply_ddl(conn, CANONICAL_DDL)
    tables = {row[0] for row in conn.execute("SHOW TABLES").fetchall()}
    assert {"deals", "process_cycles", "actors", "events", "event_actor_links"}.issubset(tables)
    conn.close()


def test_deal_round_trip() -> None:
    conn = connect(":memory:")
    apply_ddl(conn, CANONICAL_DDL)
    d = Deal(
        deal_slug="petsmart",
        target_name="PetSmart Inc.",
        filing_url="https://www.sec.gov/...",
        filing_type="DEFM14A",
        filing_date=date(2014, 12, 31),
        deal_outcome="completed",
        winning_acquirer="Buyer Group",
        date_announced=date(2014, 12, 14),
        date_signed=date(2014, 12, 14),
        date_effective=date(2015, 3, 11),
        consideration_type="cash",
        consideration_value=83.00,
        currency="USD",
        evidence_ids=["petsmart_span_1"],
        run_id="2026-05-02_smoke",
    )
    fetched = _round_trip(Deal, "deals", d, conn, "deal_slug")
    assert fetched == d
    conn.close()


def test_process_cycle_round_trip() -> None:
    conn = connect(":memory:")
    apply_ddl(conn, CANONICAL_DDL)
    pc = ProcessCycle(
        cycle_id="petsmart_cycle_1",
        deal_slug="petsmart",
        cycle_sequence=1,
        cycle_start_date=date(2014, 4, 1),
        cycle_end_date=date(2014, 12, 14),
        date_precision_start="month",
        date_precision_end="exact",
        segmentation_basis="full_process",
        cycle_label="primary",
        evidence_ids=["petsmart_span_1"],
        run_id="2026-05-02_smoke",
    )
    fetched = _round_trip(ProcessCycle, "process_cycles", pc, conn, "cycle_id")
    assert fetched == pc
    conn.close()


def test_actor_round_trip() -> None:
    conn = connect(":memory:")
    apply_ddl(conn, CANONICAL_DDL)
    a = Actor(
        actor_id="petsmart_actor_1",
        deal_slug="petsmart",
        actor_label="Buyer Group",
        actor_type="bidder",
        bidder_subtype="financial",
        is_grouped=True,
        group_size_if_known=3,
        public_private_status=None,
        country=None,
        industry=None,
        alias_status="resolved",
        evidence_ids=["petsmart_span_1"],
        run_id="2026-05-02_smoke",
    )
    fetched = _round_trip(Actor, "actors", a, conn, "actor_id")
    assert fetched == a
    conn.close()


def test_event_round_trip_with_optional_bid_value() -> None:
    conn = connect(":memory:")
    apply_ddl(conn, CANONICAL_DDL)
    e = Event(
        event_id="petsmart_evt_1",
        deal_slug="petsmart",
        cycle_id="petsmart_cycle_1",
        event_date_start=date(2014, 12, 12),
        event_date_end=date(2014, 12, 12),
        date_precision="exact",
        event_type="proposal_submitted",
        event_subtype="final_bid",
        bid_value=83.00,
        bid_value_lower=83.00,
        bid_value_upper=83.00,
        bid_value_unit="per_share",
        consideration_type="cash",
        source_text="$83.00 per share",
        source_page_hint=42,
        raw_note=None,
        evidence_ids=["petsmart_span_1"],
        run_id="2026-05-02_smoke",
    )
    fetched = _round_trip(Event, "events", e, conn, "event_id")
    assert fetched == e
    conn.close()


def test_event_actor_link_round_trip() -> None:
    conn = connect(":memory:")
    apply_ddl(conn, CANONICAL_DDL)
    link = EventActorLink(
        link_id="petsmart_link_1",
        event_id="petsmart_evt_1",
        actor_id="petsmart_actor_1",
        role="submitter",
        link_confidence="high",
        evidence_ids=["petsmart_span_1"],
        run_id="2026-05-02_smoke",
    )
    fetched = _round_trip(EventActorLink, "event_actor_links", link, conn, "link_id")
    assert fetched == link
    conn.close()
```

- [ ] **Step 2: Run, expect failure**

Run: `pytest tests/test_schema_canonical.py -v`

Expected: `ImportError` for `sec_graph.schema.models.canonical`.

- [ ] **Step 3: Implement `canonical.py`**

Create `src/sec_graph/schema/models/canonical.py`:

```python
"""Canonical core models + DDL.

Tables: deals, process_cycles, actors, events, event_actor_links. See spec §3.5.
"""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel


class Deal(BaseModel):
    deal_slug: str
    target_name: str | None
    filing_url: str | None
    filing_type: str | None
    filing_date: date | None
    deal_outcome: str | None
    winning_acquirer: str | None
    date_announced: date | None
    date_signed: date | None
    date_effective: date | None
    consideration_type: str | None
    consideration_value: float | None
    currency: str | None
    evidence_ids: list[str]
    run_id: str


class ProcessCycle(BaseModel):
    cycle_id: str
    deal_slug: str
    cycle_sequence: int
    cycle_start_date: date | None
    cycle_end_date: date | None
    date_precision_start: str
    date_precision_end: str
    segmentation_basis: str
    cycle_label: str
    evidence_ids: list[str]
    run_id: str


class Actor(BaseModel):
    actor_id: str
    deal_slug: str
    actor_label: str
    actor_type: str  # 'target'|'bidder'|'acquirer'|'advisor'|'legal_counsel'|'shareholder'|'board_committee'|'regulator'|'other'
    bidder_subtype: str | None  # 'strategic'|'financial'|'mixed_group'|'unknown'
    is_grouped: bool
    group_size_if_known: int | None
    public_private_status: str | None
    country: str | None
    industry: str | None
    alias_status: str | None
    evidence_ids: list[str]
    run_id: str


class Event(BaseModel):
    event_id: str
    deal_slug: str
    cycle_id: str | None
    event_date_start: date | None
    event_date_end: date | None
    date_precision: str
    event_type: str
    event_subtype: str | None
    bid_value: float | None
    bid_value_lower: float | None
    bid_value_upper: float | None
    bid_value_unit: str | None
    consideration_type: str | None
    source_text: str | None
    source_page_hint: int | None
    raw_note: str | None
    evidence_ids: list[str]
    run_id: str


class EventActorLink(BaseModel):
    link_id: str
    event_id: str
    actor_id: str
    role: str
    link_confidence: str
    evidence_ids: list[str]
    run_id: str


DDL = """
CREATE TABLE IF NOT EXISTS deals (
    deal_slug           VARCHAR PRIMARY KEY,
    target_name         VARCHAR,
    filing_url          VARCHAR,
    filing_type         VARCHAR,
    filing_date         DATE,
    deal_outcome        VARCHAR,
    winning_acquirer    VARCHAR,
    date_announced      DATE,
    date_signed         DATE,
    date_effective      DATE,
    consideration_type  VARCHAR,
    consideration_value DOUBLE,
    currency            VARCHAR,
    evidence_ids        VARCHAR[] NOT NULL,
    run_id              VARCHAR NOT NULL
);

CREATE TABLE IF NOT EXISTS process_cycles (
    cycle_id              VARCHAR PRIMARY KEY,
    deal_slug             VARCHAR NOT NULL,
    cycle_sequence        INTEGER NOT NULL,
    cycle_start_date      DATE,
    cycle_end_date        DATE,
    date_precision_start  VARCHAR NOT NULL,
    date_precision_end    VARCHAR NOT NULL,
    segmentation_basis    VARCHAR NOT NULL,
    cycle_label           VARCHAR NOT NULL,
    evidence_ids          VARCHAR[] NOT NULL,
    run_id                VARCHAR NOT NULL
);

CREATE TABLE IF NOT EXISTS actors (
    actor_id              VARCHAR PRIMARY KEY,
    deal_slug             VARCHAR NOT NULL,
    actor_label           VARCHAR NOT NULL,
    actor_type            VARCHAR NOT NULL,
    bidder_subtype        VARCHAR,
    is_grouped            BOOLEAN NOT NULL,
    group_size_if_known   INTEGER,
    public_private_status VARCHAR,
    country               VARCHAR,
    industry              VARCHAR,
    alias_status          VARCHAR,
    evidence_ids          VARCHAR[] NOT NULL,
    run_id                VARCHAR NOT NULL
);

CREATE TABLE IF NOT EXISTS events (
    event_id            VARCHAR PRIMARY KEY,
    deal_slug           VARCHAR NOT NULL,
    cycle_id            VARCHAR,
    event_date_start    DATE,
    event_date_end      DATE,
    date_precision      VARCHAR NOT NULL,
    event_type          VARCHAR NOT NULL,
    event_subtype       VARCHAR,
    bid_value           DOUBLE,
    bid_value_lower     DOUBLE,
    bid_value_upper     DOUBLE,
    bid_value_unit      VARCHAR,
    consideration_type  VARCHAR,
    source_text         VARCHAR,
    source_page_hint    INTEGER,
    raw_note            VARCHAR,
    evidence_ids        VARCHAR[] NOT NULL,
    run_id              VARCHAR NOT NULL
);

CREATE TABLE IF NOT EXISTS event_actor_links (
    link_id          VARCHAR PRIMARY KEY,
    event_id         VARCHAR NOT NULL,
    actor_id         VARCHAR NOT NULL,
    role             VARCHAR NOT NULL,
    link_confidence  VARCHAR NOT NULL,
    evidence_ids     VARCHAR[] NOT NULL,
    run_id           VARCHAR NOT NULL
);
"""
```

- [ ] **Step 4: Run, expect pass**

Run: `pytest tests/test_schema_canonical.py -v`

Expected: 6 tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/sec_graph/schema/models/canonical.py tests/test_schema_canonical.py
git commit -m "feat(schema): add canonical core models + DDL

Tables: deals, process_cycles, actors, events, event_actor_links. Each row
carries evidence_ids and run_id per spec §10.1 + §10.3.
"
```

---

## Task 10: Judgment model + DDL (with `supersedes_judgment_id` for reviewer chain)

**Files:**
- Create: `src/sec_graph/schema/models/judgments.py`
- Create: `tests/test_schema_judgments.py`

Per spec §10.2: judgments are append-only. A reviewer override is a *new* row whose `supersedes_judgment_id` points to the prior judgment. Stage 1 bakes in the column even though Stage 9 is out-of-roadmap.

- [ ] **Step 1: Write the failing test**

Create `tests/test_schema_judgments.py`:

```python
"""Tests for the Judgment model + DDL."""

from sec_graph.schema.db import apply_ddl, connect
from sec_graph.schema.models.judgments import (
    DDL as JUDGMENTS_DDL,
    Judgment,
)


def _round_trip(model, conn):
    data = model.model_dump()
    columns = ", ".join(data.keys())
    placeholders = ", ".join(["?"] * len(data))
    conn.execute(
        f"INSERT INTO judgments ({columns}) VALUES ({placeholders})",
        list(data.values()),
    )
    row = conn.execute(
        "SELECT * FROM judgments WHERE judgment_id = ?",
        [data["judgment_id"]],
    ).fetchone()
    cols = [d[0] for d in conn.description]
    return Judgment.model_validate(dict(zip(cols, row)))


def test_judgments_ddl_creates_table() -> None:
    conn = connect(":memory:")
    apply_ddl(conn, JUDGMENTS_DDL)
    tables = {row[0] for row in conn.execute("SHOW TABLES").fetchall()}
    assert "judgments" in tables
    conn.close()


def test_judgment_round_trip_pipeline_origin() -> None:
    conn = connect(":memory:")
    apply_ddl(conn, JUDGMENTS_DDL)
    j = Judgment(
        judgment_id="petsmart_judgment_1",
        deal_slug="petsmart",
        judgment_type="formal_boundary",
        scope="cycle",
        cycle_id="petsmart_cycle_1",
        actor_id=None,
        event_id="petsmart_evt_5",
        value="2014-11-03",
        confidence="high",
        basis="explicit final-round process letter",
        source_snippet="On November 3, 2014, ...",
        alternative_value=None,
        alternative_basis=None,
        supersedes_judgment_id=None,
        evidence_ids=["petsmart_span_42"],
        run_id="2026-05-02_smoke",
    )
    fetched = _round_trip(j, conn)
    assert fetched == j
    assert fetched.supersedes_judgment_id is None
    conn.close()


def test_judgment_round_trip_reviewer_override_chain() -> None:
    """A reviewer override is a new row pointing to the prior judgment."""
    conn = connect(":memory:")
    apply_ddl(conn, JUDGMENTS_DDL)

    # Original (pipeline) judgment.
    original = Judgment(
        judgment_id="petsmart_judgment_1",
        deal_slug="petsmart",
        judgment_type="dropout_mechanism",
        scope="actor_cycle",
        cycle_id="petsmart_cycle_1",
        actor_id="petsmart_actor_3",
        event_id=None,
        value="ambiguous",
        confidence="low",
        basis="rules-based default",
        source_snippet=None,
        alternative_value="target-rejected",
        alternative_basis="reviewer to confirm",
        supersedes_judgment_id=None,
        evidence_ids=["petsmart_span_60"],
        run_id="2026-05-02_pipeline",
    )
    _round_trip(original, conn)

    # Reviewer override.
    override = Judgment(
        judgment_id="petsmart_judgment_2",
        deal_slug="petsmart",
        judgment_type="dropout_mechanism",
        scope="actor_cycle",
        cycle_id="petsmart_cycle_1",
        actor_id="petsmart_actor_3",
        event_id=None,
        value="target-rejected",
        confidence="high",
        basis="reviewer reading of paragraph 60: target informed bidder it was no longer in process",
        source_snippet="we informed the bidder it was no longer in the process",
        alternative_value=None,
        alternative_basis=None,
        supersedes_judgment_id="petsmart_judgment_1",
        evidence_ids=["petsmart_span_60"],
        run_id="2026-05-02_reviewer",
    )
    fetched = _round_trip(override, conn)
    assert fetched.supersedes_judgment_id == "petsmart_judgment_1"
    assert fetched.run_id == "2026-05-02_reviewer"

    # Both rows coexist.
    count = conn.execute("SELECT COUNT(*) FROM judgments").fetchone()[0]
    assert count == 2
    conn.close()
```

- [ ] **Step 2: Run, expect failure**

Run: `pytest tests/test_schema_judgments.py -v`

Expected: `ImportError` for `sec_graph.schema.models.judgments`.

- [ ] **Step 3: Implement `judgments.py`**

Create `src/sec_graph/schema/models/judgments.py`:

```python
"""Judgment model + DDL.

Judgments are append-only. A reviewer override is a *new* row whose
``supersedes_judgment_id`` points to the prior judgment. Projections select
the latest non-superseded row in the chain. See spec §10.2.
"""

from __future__ import annotations

from pydantic import BaseModel


class Judgment(BaseModel):
    judgment_id: str
    deal_slug: str
    judgment_type: str  # 'formal_boundary' | 'cycle_regime' | 'cycle_visibility' | 'cycle_relation' | 'scope_validity' | 'valuation_comparability' | 'dropout_mechanism' | ...
    scope: str          # 'cycle' | 'actor_cycle' | 'event' | 'deal' | ...
    cycle_id: str | None
    actor_id: str | None
    event_id: str | None
    value: str | None
    confidence: str  # 'low' | 'medium' | 'high'
    basis: str
    source_snippet: str | None
    alternative_value: str | None
    alternative_basis: str | None
    supersedes_judgment_id: str | None
    evidence_ids: list[str]
    run_id: str


DDL = """
CREATE TABLE IF NOT EXISTS judgments (
    judgment_id              VARCHAR PRIMARY KEY,
    deal_slug                VARCHAR NOT NULL,
    judgment_type            VARCHAR NOT NULL,
    scope                    VARCHAR NOT NULL,
    cycle_id                 VARCHAR,
    actor_id                 VARCHAR,
    event_id                 VARCHAR,
    value                    VARCHAR,
    confidence               VARCHAR NOT NULL,
    basis                    VARCHAR NOT NULL,
    source_snippet           VARCHAR,
    alternative_value        VARCHAR,
    alternative_basis        VARCHAR,
    supersedes_judgment_id   VARCHAR,
    evidence_ids             VARCHAR[] NOT NULL,
    run_id                   VARCHAR NOT NULL
);
"""
```

- [ ] **Step 4: Run, expect pass**

Run: `pytest tests/test_schema_judgments.py -v`

Expected: 3 tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/sec_graph/schema/models/judgments.py tests/test_schema_judgments.py
git commit -m "feat(schema): add Judgment model + DDL with supersedes_judgment_id

Per spec §10.2, judgments are append-only and reviewer overrides chain via
supersedes_judgment_id. Stage 1 bakes the column in even though Stage 9 is
out-of-roadmap, to avoid retrofit cost.
"
```

---

## Task 11: Auxiliary models + DDL (9 tables)

**Files:**
- Create: `src/sec_graph/schema/models/auxiliary.py`
- Create: `tests/test_schema_auxiliary.py`

The 9 auxiliary tables per spec §3.5: `advisor_engagements`, `legal_counsel_engagements`, `board_committees`, `deal_terms`, `group_memberships`, `prior_relationships`, `participation_counts`, `bid_normalizations`, `cycle_phase_assignments`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_schema_auxiliary.py`:

```python
"""Tests for the 9 auxiliary models + DDL."""

from datetime import date

from sec_graph.schema.db import apply_ddl, connect
from sec_graph.schema.models.auxiliary import (
    AdvisorEngagement,
    BidNormalization,
    BoardCommittee,
    CyclePhaseAssignment,
    DDL as AUXILIARY_DDL,
    DealTerm,
    GroupMembership,
    LegalCounselEngagement,
    ParticipationCount,
    PriorRelationship,
)


def _round_trip(model_class, table, model, conn, pk_col):
    data = model.model_dump()
    columns = ", ".join(data.keys())
    placeholders = ", ".join(["?"] * len(data))
    conn.execute(
        f"INSERT INTO {table} ({columns}) VALUES ({placeholders})",
        list(data.values()),
    )
    row = conn.execute(
        f"SELECT * FROM {table} WHERE {pk_col} = ?",
        [data[pk_col]],
    ).fetchone()
    cols = [d[0] for d in conn.description]
    return model_class.model_validate(dict(zip(cols, row)))


def test_auxiliary_ddl_creates_all_nine_tables() -> None:
    conn = connect(":memory:")
    apply_ddl(conn, AUXILIARY_DDL)
    tables = {row[0] for row in conn.execute("SHOW TABLES").fetchall()}
    expected = {
        "advisor_engagements",
        "legal_counsel_engagements",
        "board_committees",
        "deal_terms",
        "group_memberships",
        "prior_relationships",
        "participation_counts",
        "bid_normalizations",
        "cycle_phase_assignments",
    }
    assert expected.issubset(tables)
    conn.close()


def test_advisor_engagement_round_trip() -> None:
    conn = connect(":memory:")
    apply_ddl(conn, AUXILIARY_DDL)
    e = AdvisorEngagement(
        engagement_id="petsmart_engagement_1",
        deal_slug="petsmart",
        advisor_actor_id="petsmart_actor_2",
        client_actor_id="petsmart_actor_1",
        role="financial_advisor",
        start_date=date(2014, 4, 1),
        end_date=date(2014, 12, 14),
        evidence_ids=["petsmart_span_5"],
        run_id="2026-05-02_smoke",
    )
    fetched = _round_trip(AdvisorEngagement, "advisor_engagements", e, conn, "engagement_id")
    assert fetched == e
    conn.close()


def test_legal_counsel_engagement_round_trip() -> None:
    conn = connect(":memory:")
    apply_ddl(conn, AUXILIARY_DDL)
    e = LegalCounselEngagement(
        engagement_id="petsmart_legal_1",
        deal_slug="petsmart",
        counsel_actor_id="petsmart_actor_3",
        client_actor_id="petsmart_actor_1",
        role="lead_counsel",
        start_date=date(2014, 4, 1),
        end_date=None,
        evidence_ids=["petsmart_span_6"],
        run_id="2026-05-02_smoke",
    )
    fetched = _round_trip(
        LegalCounselEngagement, "legal_counsel_engagements", e, conn, "engagement_id"
    )
    assert fetched == e
    conn.close()


def test_board_committee_round_trip() -> None:
    conn = connect(":memory:")
    apply_ddl(conn, AUXILIARY_DDL)
    bc = BoardCommittee(
        committee_id="petsmart_committee_1",
        deal_slug="petsmart",
        committee_name="Special Committee",
        authority="evaluate strategic alternatives",
        member_actor_ids=["petsmart_actor_4", "petsmart_actor_5"],
        independence_status="independent",
        start_date=date(2014, 5, 1),
        end_date=date(2014, 12, 14),
        evidence_ids=["petsmart_span_7"],
        run_id="2026-05-02_smoke",
    )
    fetched = _round_trip(BoardCommittee, "board_committees", bc, conn, "committee_id")
    assert fetched == bc
    conn.close()


def test_deal_term_round_trip() -> None:
    conn = connect(":memory:")
    apply_ddl(conn, AUXILIARY_DDL)
    dt = DealTerm(
        term_id="petsmart_term_1",
        deal_slug="petsmart",
        term_type="termination_fee",
        value=325000000.0,
        unit="usd",
        effective_date=date(2014, 12, 14),
        evidence_ids=["petsmart_span_8"],
        run_id="2026-05-02_smoke",
    )
    fetched = _round_trip(DealTerm, "deal_terms", dt, conn, "term_id")
    assert fetched == dt
    conn.close()


def test_group_membership_round_trip() -> None:
    conn = connect(":memory:")
    apply_ddl(conn, AUXILIARY_DDL)
    gm = GroupMembership(
        membership_id="petsmart_membership_1",
        group_actor_id="petsmart_actor_1",
        member_actor_id="petsmart_actor_6",
        start_date=date(2014, 11, 1),
        end_date=None,
        evidence_ids=["petsmart_span_9"],
        run_id="2026-05-02_smoke",
    )
    fetched = _round_trip(GroupMembership, "group_memberships", gm, conn, "membership_id")
    assert fetched == gm
    conn.close()


def test_prior_relationship_round_trip() -> None:
    conn = connect(":memory:")
    apply_ddl(conn, AUXILIARY_DDL)
    pr = PriorRelationship(
        relationship_id="petsmart_relationship_1",
        bidder_actor_id="petsmart_actor_1",
        target_actor_id="petsmart_actor_7",
        relationship_type="prior_offer",
        description="prior unsolicited offer in 2012",
        date_start=date(2012, 6, 1),
        date_end=date(2012, 9, 30),
        evidence_ids=["petsmart_span_10"],
        run_id="2026-05-02_smoke",
    )
    fetched = _round_trip(PriorRelationship, "prior_relationships", pr, conn, "relationship_id")
    assert fetched == pr
    conn.close()


def test_participation_count_round_trip() -> None:
    conn = connect(":memory:")
    apply_ddl(conn, AUXILIARY_DDL)
    pc = ParticipationCount(
        count_id="petsmart_count_1",
        deal_slug="petsmart",
        cycle_id="petsmart_cycle_1",
        count_type="ioi_submitted",
        count_value=5,
        strategic_count=2,
        financial_count=3,
        unknown_count=0,
        process_stage="initial",
        date_start=date(2014, 5, 1),
        date_end=date(2014, 5, 31),
        evidence_ids=["petsmart_span_11"],
        run_id="2026-05-02_smoke",
    )
    fetched = _round_trip(ParticipationCount, "participation_counts", pc, conn, "count_id")
    assert fetched == pc
    conn.close()


def test_bid_normalization_round_trip() -> None:
    conn = connect(":memory:")
    apply_ddl(conn, AUXILIARY_DDL)
    bn = BidNormalization(
        normalization_id="petsmart_normalization_1",
        event_id="petsmart_evt_1",
        raw_amount_text="$83.00 per share",
        currency="USD",
        operator="exact",
        center_rule="exact_value",
        unit_rule="per_share",
        lower_source="exact_value",
        upper_source="exact_value",
        conversion_applied=False,
        conversion_basis=None,
        confidence="high",
        evidence_ids=["petsmart_span_1"],
        run_id="2026-05-02_smoke",
    )
    fetched = _round_trip(BidNormalization, "bid_normalizations", bn, conn, "normalization_id")
    assert fetched == bn
    conn.close()


def test_cycle_phase_assignment_round_trip() -> None:
    conn = connect(":memory:")
    apply_ddl(conn, AUXILIARY_DDL)
    cpa = CyclePhaseAssignment(
        assignment_id="petsmart_assignment_1",
        event_id="petsmart_evt_1",
        cycle_id="petsmart_cycle_1",
        phase="formal",
        phase_basis="post_boundary_proposal",
        eligible_for_estimation_view=True,
        evidence_ids=["petsmart_span_1"],
        run_id="2026-05-02_smoke",
    )
    fetched = _round_trip(
        CyclePhaseAssignment, "cycle_phase_assignments", cpa, conn, "assignment_id"
    )
    assert fetched == cpa
    conn.close()
```

- [ ] **Step 2: Run, expect failure**

Run: `pytest tests/test_schema_auxiliary.py -v`

Expected: `ImportError` for `sec_graph.schema.models.auxiliary`.

- [ ] **Step 3: Implement `auxiliary.py`**

Create `src/sec_graph/schema/models/auxiliary.py`:

```python
"""Auxiliary canonical models + DDL.

Tables: advisor_engagements, legal_counsel_engagements, board_committees,
deal_terms, group_memberships, prior_relationships, participation_counts,
bid_normalizations, cycle_phase_assignments. See spec §3.5.
"""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel


class AdvisorEngagement(BaseModel):
    engagement_id: str
    deal_slug: str
    advisor_actor_id: str
    client_actor_id: str
    role: str
    start_date: date | None
    end_date: date | None
    evidence_ids: list[str]
    run_id: str


class LegalCounselEngagement(BaseModel):
    engagement_id: str
    deal_slug: str
    counsel_actor_id: str
    client_actor_id: str
    role: str
    start_date: date | None
    end_date: date | None
    evidence_ids: list[str]
    run_id: str


class BoardCommittee(BaseModel):
    committee_id: str
    deal_slug: str
    committee_name: str
    authority: str | None
    member_actor_ids: list[str]
    independence_status: str | None
    start_date: date | None
    end_date: date | None
    evidence_ids: list[str]
    run_id: str


class DealTerm(BaseModel):
    term_id: str
    deal_slug: str
    term_type: str
    value: float | None
    unit: str | None
    effective_date: date | None
    evidence_ids: list[str]
    run_id: str


class GroupMembership(BaseModel):
    membership_id: str
    group_actor_id: str
    member_actor_id: str
    start_date: date | None
    end_date: date | None
    evidence_ids: list[str]
    run_id: str


class PriorRelationship(BaseModel):
    relationship_id: str
    bidder_actor_id: str
    target_actor_id: str
    relationship_type: str
    description: str | None
    date_start: date | None
    date_end: date | None
    evidence_ids: list[str]
    run_id: str


class ParticipationCount(BaseModel):
    count_id: str
    deal_slug: str
    cycle_id: str | None
    count_type: str
    count_value: int
    strategic_count: int | None
    financial_count: int | None
    unknown_count: int | None
    process_stage: str | None
    date_start: date | None
    date_end: date | None
    evidence_ids: list[str]
    run_id: str


class BidNormalization(BaseModel):
    normalization_id: str
    event_id: str
    raw_amount_text: str
    currency: str | None
    operator: str | None
    center_rule: str | None
    unit_rule: str | None
    lower_source: str | None
    upper_source: str | None
    conversion_applied: bool
    conversion_basis: str | None
    confidence: str
    evidence_ids: list[str]
    run_id: str


class CyclePhaseAssignment(BaseModel):
    assignment_id: str
    event_id: str
    cycle_id: str
    phase: str  # 'pre_boundary' | 'formal' | 'post_signing_go_shop' | 'outside_process' | 'unknown'
    phase_basis: str
    eligible_for_estimation_view: bool
    evidence_ids: list[str]
    run_id: str


DDL = """
CREATE TABLE IF NOT EXISTS advisor_engagements (
    engagement_id     VARCHAR PRIMARY KEY,
    deal_slug         VARCHAR NOT NULL,
    advisor_actor_id  VARCHAR NOT NULL,
    client_actor_id   VARCHAR NOT NULL,
    role              VARCHAR NOT NULL,
    start_date        DATE,
    end_date          DATE,
    evidence_ids      VARCHAR[] NOT NULL,
    run_id            VARCHAR NOT NULL
);

CREATE TABLE IF NOT EXISTS legal_counsel_engagements (
    engagement_id     VARCHAR PRIMARY KEY,
    deal_slug         VARCHAR NOT NULL,
    counsel_actor_id  VARCHAR NOT NULL,
    client_actor_id   VARCHAR NOT NULL,
    role              VARCHAR NOT NULL,
    start_date        DATE,
    end_date          DATE,
    evidence_ids      VARCHAR[] NOT NULL,
    run_id            VARCHAR NOT NULL
);

CREATE TABLE IF NOT EXISTS board_committees (
    committee_id          VARCHAR PRIMARY KEY,
    deal_slug             VARCHAR NOT NULL,
    committee_name        VARCHAR NOT NULL,
    authority             VARCHAR,
    member_actor_ids      VARCHAR[] NOT NULL,
    independence_status   VARCHAR,
    start_date            DATE,
    end_date              DATE,
    evidence_ids          VARCHAR[] NOT NULL,
    run_id                VARCHAR NOT NULL
);

CREATE TABLE IF NOT EXISTS deal_terms (
    term_id         VARCHAR PRIMARY KEY,
    deal_slug       VARCHAR NOT NULL,
    term_type       VARCHAR NOT NULL,
    value           DOUBLE,
    unit            VARCHAR,
    effective_date  DATE,
    evidence_ids    VARCHAR[] NOT NULL,
    run_id          VARCHAR NOT NULL
);

CREATE TABLE IF NOT EXISTS group_memberships (
    membership_id     VARCHAR PRIMARY KEY,
    group_actor_id    VARCHAR NOT NULL,
    member_actor_id   VARCHAR NOT NULL,
    start_date        DATE,
    end_date          DATE,
    evidence_ids      VARCHAR[] NOT NULL,
    run_id            VARCHAR NOT NULL
);

CREATE TABLE IF NOT EXISTS prior_relationships (
    relationship_id    VARCHAR PRIMARY KEY,
    bidder_actor_id    VARCHAR NOT NULL,
    target_actor_id    VARCHAR NOT NULL,
    relationship_type  VARCHAR NOT NULL,
    description        VARCHAR,
    date_start         DATE,
    date_end           DATE,
    evidence_ids       VARCHAR[] NOT NULL,
    run_id             VARCHAR NOT NULL
);

CREATE TABLE IF NOT EXISTS participation_counts (
    count_id         VARCHAR PRIMARY KEY,
    deal_slug        VARCHAR NOT NULL,
    cycle_id         VARCHAR,
    count_type       VARCHAR NOT NULL,
    count_value      INTEGER NOT NULL,
    strategic_count  INTEGER,
    financial_count  INTEGER,
    unknown_count    INTEGER,
    process_stage    VARCHAR,
    date_start       DATE,
    date_end         DATE,
    evidence_ids     VARCHAR[] NOT NULL,
    run_id           VARCHAR NOT NULL
);

CREATE TABLE IF NOT EXISTS bid_normalizations (
    normalization_id    VARCHAR PRIMARY KEY,
    event_id            VARCHAR NOT NULL,
    raw_amount_text     VARCHAR NOT NULL,
    currency            VARCHAR,
    operator            VARCHAR,
    center_rule         VARCHAR,
    unit_rule           VARCHAR,
    lower_source        VARCHAR,
    upper_source        VARCHAR,
    conversion_applied  BOOLEAN NOT NULL,
    conversion_basis    VARCHAR,
    confidence          VARCHAR NOT NULL,
    evidence_ids        VARCHAR[] NOT NULL,
    run_id              VARCHAR NOT NULL
);

CREATE TABLE IF NOT EXISTS cycle_phase_assignments (
    assignment_id                  VARCHAR PRIMARY KEY,
    event_id                       VARCHAR NOT NULL,
    cycle_id                       VARCHAR NOT NULL,
    phase                          VARCHAR NOT NULL,
    phase_basis                    VARCHAR NOT NULL,
    eligible_for_estimation_view   BOOLEAN NOT NULL,
    evidence_ids                   VARCHAR[] NOT NULL,
    run_id                         VARCHAR NOT NULL
);
"""
```

- [ ] **Step 4: Run, expect pass**

Run: `pytest tests/test_schema_auxiliary.py -v`

Expected: 10 tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/sec_graph/schema/models/auxiliary.py tests/test_schema_auxiliary.py
git commit -m "feat(schema): add 9 auxiliary models + DDL

Tables: advisor_engagements, legal_counsel_engagements, board_committees,
deal_terms, group_memberships, prior_relationships, participation_counts,
bid_normalizations, cycle_phase_assignments. Per spec §3.5.
"
```

---

## Task 12: Runtime model + DDL (`RunMetadata`)

**Files:**
- Create: `src/sec_graph/schema/models/runtime.py`
- Create: `tests/test_schema_runtime.py`

Per spec §7: `run_metadata` records each pipeline run's identity and stage versions.

- [ ] **Step 1: Write the failing test**

Create `tests/test_schema_runtime.py`:

```python
"""Tests for the RunMetadata model + DDL."""

from datetime import datetime, timezone

from sec_graph.schema.db import apply_ddl, connect
from sec_graph.schema.models.runtime import (
    DDL as RUNTIME_DDL,
    RunMetadata,
)


def test_runtime_ddl_creates_table() -> None:
    conn = connect(":memory:")
    apply_ddl(conn, RUNTIME_DDL)
    tables = {row[0] for row in conn.execute("SHOW TABLES").fetchall()}
    assert "run_metadata" in tables
    conn.close()


def test_run_metadata_round_trip() -> None:
    conn = connect(":memory:")
    apply_ddl(conn, RUNTIME_DDL)
    rm = RunMetadata(
        run_id="2026-05-02_a3f9c1",
        input_archive_hash="f" * 64,
        filing_ids=["petsmart_filing_1", "saks_filing_1"],
        ingest_version="0.1.0",
        extract_config_version="0.1.0",
        reconcile_version="0.1.0",
        validate_version="0.1.0",
        project_version="0.1.0",
        started_at=datetime(2026, 5, 2, 12, 0, tzinfo=timezone.utc),
        completed_at=datetime(2026, 5, 2, 12, 5, tzinfo=timezone.utc),
    )
    data = rm.model_dump()
    columns = ", ".join(data.keys())
    placeholders = ", ".join(["?"] * len(data))
    conn.execute(
        f"INSERT INTO run_metadata ({columns}) VALUES ({placeholders})",
        list(data.values()),
    )
    row = conn.execute(
        "SELECT * FROM run_metadata WHERE run_id = ?",
        [rm.run_id],
    ).fetchone()
    cols = [d[0] for d in conn.description]
    fetched = RunMetadata.model_validate(dict(zip(cols, row)))
    assert fetched == rm
    conn.close()


def test_run_metadata_completed_at_optional() -> None:
    """A run that has started but not completed has completed_at=None."""
    rm = RunMetadata(
        run_id="2026-05-02_in_progress",
        input_archive_hash=None,
        filing_ids=[],
        ingest_version="0.1.0",
        extract_config_version=None,
        reconcile_version=None,
        validate_version=None,
        project_version=None,
        started_at=datetime(2026, 5, 2, 12, 0, tzinfo=timezone.utc),
        completed_at=None,
    )
    assert rm.completed_at is None
```

- [ ] **Step 2: Run, expect failure**

Run: `pytest tests/test_schema_runtime.py -v`

Expected: `ImportError` for `sec_graph.schema.models.runtime`.

- [ ] **Step 3: Implement `runtime.py`**

Create `src/sec_graph/schema/models/runtime.py`:

```python
"""RunMetadata model + DDL.

One row per pipeline run. Records run identity, input hash, per-stage
versions, and timestamps. See spec §7 (Determinism Contract).
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class RunMetadata(BaseModel):
    run_id: str
    input_archive_hash: str | None
    filing_ids: list[str]
    ingest_version: str
    extract_config_version: str | None
    reconcile_version: str | None
    validate_version: str | None
    project_version: str | None
    started_at: datetime
    completed_at: datetime | None


DDL = """
CREATE TABLE IF NOT EXISTS run_metadata (
    run_id                  VARCHAR PRIMARY KEY,
    input_archive_hash      VARCHAR,
    filing_ids              VARCHAR[] NOT NULL,
    ingest_version          VARCHAR NOT NULL,
    extract_config_version  VARCHAR,
    reconcile_version       VARCHAR,
    validate_version        VARCHAR,
    project_version         VARCHAR,
    started_at              TIMESTAMPTZ NOT NULL,
    completed_at            TIMESTAMPTZ
);
"""
```

- [ ] **Step 4: Run, expect pass**

Run: `pytest tests/test_schema_runtime.py -v`

Expected: 3 tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/sec_graph/schema/models/runtime.py tests/test_schema_runtime.py
git commit -m "feat(schema): add RunMetadata model + DDL

Records pipeline-run identity, input hashes, stage versions, and timestamps
per spec §7.
"
```

---

## Task 13: Schema orchestration — `init_schema` + model-aware insert/fetch helpers + `__init__.py` exports

**Files:**
- Create: `src/sec_graph/schema/schema_init.py`
- Create: `tests/test_schema_init.py`
- Modify: `src/sec_graph/schema/__init__.py`
- Modify: `src/sec_graph/schema/models/__init__.py`
- Modify: `src/sec_graph/schema/db.py`

This task ties together all module DDLs and provides reusable `insert_model` / `fetch_model` helpers so per-model tests stop duplicating boilerplate. Also makes `from sec_graph.schema import ...` import every model.

- [ ] **Step 1: Write the failing test**

Create `tests/test_schema_init.py`:

```python
"""End-to-end test: init_schema creates every table from every module."""

from sec_graph.schema.db import connect
from sec_graph.schema.schema_init import init_schema


EXPECTED_TABLES = {
    # filings module
    "filings",
    "sections",
    "paragraphs",
    "spans",
    # extraction module
    "candidates",
    # canonical module
    "deals",
    "process_cycles",
    "actors",
    "events",
    "event_actor_links",
    # judgments module
    "judgments",
    # auxiliary module
    "advisor_engagements",
    "legal_counsel_engagements",
    "board_committees",
    "deal_terms",
    "group_memberships",
    "prior_relationships",
    "participation_counts",
    "bid_normalizations",
    "cycle_phase_assignments",
    # runtime module
    "run_metadata",
}


def test_init_schema_creates_every_table() -> None:
    conn = connect(":memory:")
    try:
        init_schema(conn)
        tables = {row[0] for row in conn.execute("SHOW TABLES").fetchall()}
        missing = EXPECTED_TABLES - tables
        assert not missing, f"missing tables: {missing}"
    finally:
        conn.close()


def test_init_schema_idempotent() -> None:
    """Running init_schema twice should not fail."""
    conn = connect(":memory:")
    try:
        init_schema(conn)
        init_schema(conn)  # should not raise
        tables = {row[0] for row in conn.execute("SHOW TABLES").fetchall()}
        assert EXPECTED_TABLES.issubset(tables)
    finally:
        conn.close()


def test_insert_and_fetch_model() -> None:
    """db.insert_model + db.fetch_model round-trip a Pydantic model."""
    from datetime import datetime, timezone

    from sec_graph.schema.db import fetch_model, insert_model
    from sec_graph.schema.models.filings import CleanFiling

    conn = connect(":memory:")
    try:
        init_schema(conn)
        f = CleanFiling(
            filing_id="petsmart_filing_1",
            deal_slug="petsmart",
            source_filename="raw.md",
            raw_md_path="data/filings/petsmart/raw.md",
            raw_md_hash="a" * 64,
            clean_md_hash="b" * 64,
            page_count=42,
            parser_version="0.1.0",
            ingested_at=datetime(2026, 5, 2, 12, 0, tzinfo=timezone.utc),
            run_id="2026-05-02_smoke",
        )
        insert_model(conn, "filings", f)
        fetched = fetch_model(conn, "filings", CleanFiling, "filing_id", "petsmart_filing_1")
        assert fetched == f
    finally:
        conn.close()


def test_top_level_imports_resolve() -> None:
    """Verify `from sec_graph.schema import <Model>` works for each model."""
    from sec_graph.schema import (
        Actor,
        AdvisorEngagement,
        BidNormalization,
        BoardCommittee,
        CleanFiling,
        CyclePhaseAssignment,
        Deal,
        DealTerm,
        Event,
        EventActorLink,
        ExtractionCandidate,
        GroupMembership,
        Judgment,
        LegalCounselEngagement,
        Paragraph,
        ParticipationCount,
        PriorRelationship,
        ProcessCycle,
        RunMetadata,
        Section,
        SourceSpan,
    )

    # Smoke-check: just verify each is a Pydantic model class.
    from pydantic import BaseModel

    for cls in (
        Actor,
        AdvisorEngagement,
        BidNormalization,
        BoardCommittee,
        CleanFiling,
        CyclePhaseAssignment,
        Deal,
        DealTerm,
        Event,
        EventActorLink,
        ExtractionCandidate,
        GroupMembership,
        Judgment,
        LegalCounselEngagement,
        Paragraph,
        ParticipationCount,
        PriorRelationship,
        ProcessCycle,
        RunMetadata,
        Section,
        SourceSpan,
    ):
        assert issubclass(cls, BaseModel), f"{cls.__name__} is not a BaseModel"
```

- [ ] **Step 2: Run, expect failure**

Run: `pytest tests/test_schema_init.py -v`

Expected: `ImportError` for `sec_graph.schema.schema_init` (and missing top-level imports).

- [ ] **Step 3: Implement `schema_init.py`**

Create `src/sec_graph/schema/schema_init.py`:

```python
"""Compose every module's DDL into one ``init_schema`` call.

Runs the ``CREATE TABLE IF NOT EXISTS`` statements from every model module in
dependency-safe order. Idempotent. See spec §3.1.
"""

from __future__ import annotations

import duckdb

from sec_graph.schema.db import apply_ddl
from sec_graph.schema.models.auxiliary import DDL as AUXILIARY_DDL
from sec_graph.schema.models.canonical import DDL as CANONICAL_DDL
from sec_graph.schema.models.extraction import DDL as EXTRACTION_DDL
from sec_graph.schema.models.filings import DDL as FILINGS_DDL
from sec_graph.schema.models.judgments import DDL as JUDGMENTS_DDL
from sec_graph.schema.models.runtime import DDL as RUNTIME_DDL


def init_schema(conn: duckdb.DuckDBPyConnection) -> None:
    """Create every canonical/auxiliary/runtime table on the connection."""
    apply_ddl(conn, RUNTIME_DDL)
    apply_ddl(conn, FILINGS_DDL)
    apply_ddl(conn, EXTRACTION_DDL)
    apply_ddl(conn, CANONICAL_DDL)
    apply_ddl(conn, JUDGMENTS_DDL)
    apply_ddl(conn, AUXILIARY_DDL)
```

- [ ] **Step 4: Add `insert_model` and `fetch_model` to `db.py`**

Modify `src/sec_graph/schema/db.py` to add these helpers at the end of the file:

```python
"""DuckDB connection and DDL primitives.

Model-aware insert/fetch helpers are defined in :mod:`sec_graph.schema.schema_init`
once every module's DDL has been registered.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import duckdb
from pydantic import BaseModel


def connect(path: str | Path) -> duckdb.DuckDBPyConnection:
    """Open a DuckDB connection. ``path`` may be ``":memory:"`` for ephemeral use."""
    return duckdb.connect(str(path))


def apply_ddl(conn: duckdb.DuckDBPyConnection, ddl: str) -> None:
    """Execute one or more semicolon-separated DDL statements."""
    conn.execute(ddl)


def insert_model(
    conn: duckdb.DuckDBPyConnection, table: str, model: BaseModel
) -> None:
    """Insert a Pydantic model instance into ``table`` using its column names."""
    data = model.model_dump()
    columns = ", ".join(data.keys())
    placeholders = ", ".join(["?"] * len(data))
    conn.execute(
        f"INSERT INTO {table} ({columns}) VALUES ({placeholders})",
        list(data.values()),
    )


def fetch_model(
    conn: duckdb.DuckDBPyConnection,
    table: str,
    model_class: type[BaseModel],
    pk_col: str,
    pk_val: Any,
) -> BaseModel:
    """Fetch one row keyed by ``pk_col = pk_val`` and validate into ``model_class``."""
    row = conn.execute(
        f"SELECT * FROM {table} WHERE {pk_col} = ?", [pk_val]
    ).fetchone()
    if row is None:
        raise ValueError(
            f"no row found in {table} with {pk_col} = {pk_val!r}"
        )
    cols = [d[0] for d in conn.description]
    return model_class.model_validate(dict(zip(cols, row)))
```

- [ ] **Step 5: Wire up `schema/models/__init__.py` re-exports**

Modify `src/sec_graph/schema/models/__init__.py`:

```python
"""Pydantic model definitions for every canonical and auxiliary table."""

from sec_graph.schema.models.auxiliary import (
    AdvisorEngagement,
    BidNormalization,
    BoardCommittee,
    CyclePhaseAssignment,
    DealTerm,
    GroupMembership,
    LegalCounselEngagement,
    ParticipationCount,
    PriorRelationship,
)
from sec_graph.schema.models.canonical import (
    Actor,
    Deal,
    Event,
    EventActorLink,
    ProcessCycle,
)
from sec_graph.schema.models.extraction import ExtractionCandidate
from sec_graph.schema.models.filings import (
    CleanFiling,
    Paragraph,
    Section,
    SourceSpan,
)
from sec_graph.schema.models.judgments import Judgment
from sec_graph.schema.models.runtime import RunMetadata

__all__ = [
    "Actor",
    "AdvisorEngagement",
    "BidNormalization",
    "BoardCommittee",
    "CleanFiling",
    "CyclePhaseAssignment",
    "Deal",
    "DealTerm",
    "Event",
    "EventActorLink",
    "ExtractionCandidate",
    "GroupMembership",
    "Judgment",
    "LegalCounselEngagement",
    "Paragraph",
    "ParticipationCount",
    "PriorRelationship",
    "ProcessCycle",
    "RunMetadata",
    "Section",
    "SourceSpan",
]
```

- [ ] **Step 6: Wire up `schema/__init__.py` re-exports**

Modify `src/sec_graph/schema/__init__.py`:

```python
"""Schema subpackage.

Contains canonical type definitions (Pydantic models), DuckDB DDL, deterministic
ID helpers, evidence-binding utilities, and run-metadata scaffolding. Every
other sec_graph module imports from here. See
docs/superpowers/specs/2026-05-02-sec-graph-modular-architecture.md §3.1.
"""

from sec_graph.schema.db import apply_ddl, connect, fetch_model, insert_model
from sec_graph.schema.evidence import extract_quote, quote_hash, validate_quote
from sec_graph.schema.ids import make_id, parse_id
from sec_graph.schema.models import (
    Actor,
    AdvisorEngagement,
    BidNormalization,
    BoardCommittee,
    CleanFiling,
    CyclePhaseAssignment,
    Deal,
    DealTerm,
    Event,
    EventActorLink,
    ExtractionCandidate,
    GroupMembership,
    Judgment,
    LegalCounselEngagement,
    Paragraph,
    ParticipationCount,
    PriorRelationship,
    ProcessCycle,
    RunMetadata,
    Section,
    SourceSpan,
)
from sec_graph.schema.schema_init import init_schema
from sec_graph.schema.versions import (
    EXTRACT_VERSION,
    INGEST_VERSION,
    PARSER_VERSION,
    PROJECT_VERSION,
    RECONCILE_VERSION,
    VALIDATE_VERSION,
)

__all__ = [
    # models
    "Actor",
    "AdvisorEngagement",
    "BidNormalization",
    "BoardCommittee",
    "CleanFiling",
    "CyclePhaseAssignment",
    "Deal",
    "DealTerm",
    "Event",
    "EventActorLink",
    "ExtractionCandidate",
    "GroupMembership",
    "Judgment",
    "LegalCounselEngagement",
    "Paragraph",
    "ParticipationCount",
    "PriorRelationship",
    "ProcessCycle",
    "RunMetadata",
    "Section",
    "SourceSpan",
    # db helpers
    "apply_ddl",
    "connect",
    "fetch_model",
    "init_schema",
    "insert_model",
    # evidence helpers
    "extract_quote",
    "quote_hash",
    "validate_quote",
    # id helpers
    "make_id",
    "parse_id",
    # versions
    "EXTRACT_VERSION",
    "INGEST_VERSION",
    "PARSER_VERSION",
    "PROJECT_VERSION",
    "RECONCILE_VERSION",
    "VALIDATE_VERSION",
]
```

- [ ] **Step 7: Run, expect pass**

Run: `pytest tests/test_schema_init.py -v`

Expected: 4 tests pass.

- [ ] **Step 8: Run the full test suite to verify nothing regressed**

Run: `pytest tests/ -v`

Expected: all prior tests still pass plus the 4 new ones in `test_schema_init.py`. Approximate count: 5 (existing edgar+package) + 2 (versions) + 7 (ids) + 6 (evidence) + 3 (db) + 6 (filings) + 3 (extraction) + 6 (canonical) + 3 (judgments) + 10 (auxiliary) + 3 (runtime) + 4 (init) = ~58 tests passing.

- [ ] **Step 9: Commit**

```bash
git add src/sec_graph/schema/schema_init.py src/sec_graph/schema/db.py src/sec_graph/schema/__init__.py src/sec_graph/schema/models/__init__.py tests/test_schema_init.py
git commit -m "feat(schema): orchestrate init_schema + insert/fetch helpers + top-level exports

init_schema(conn) creates every table from every module in one call.
insert_model / fetch_model in db.py replace per-test boilerplate.
Top-level sec_graph.schema namespace exposes all models, helpers, versions.
"
```

---

## Task 14: Smoke filing fixture (synthetic markdown)

**Files:**
- Create: `tests/fixtures/smoke_filing.md`

A ~50-line synthetic filing exercising every code path the downstream pipeline will need. This is the workhorse fixture for fast CI tests in Stages 2-7.

- [ ] **Step 1: Create the smoke filing**

Create `tests/fixtures/smoke_filing.md`:

```markdown
<!-- PAGE 1 -->
# SMOKE FILING — TEST FIXTURE

This is a synthetic SEC merger proxy fixture for sec_graph testing. It is
not a real SEC filing. It is hand-authored to exercise every code path in
the ingestion, extraction, reconciliation, validation, and projection stages.

## Background of the Merger

On January 5, 2025, the board of directors of Smoke Co. authorized
management to explore strategic alternatives, including a potential sale of
the Company.

On February 10, 2025, the Company engaged Test Advisor LLC as its financial
advisor and Test Counsel LLP as its legal counsel.

During February and March 2025, Test Advisor LLC contacted twelve potential
buyers, comprising five strategic buyers and seven financial buyers. Eight
of those parties executed confidentiality agreements with the Company.

On April 1, 2025, the Company received four preliminary indications of
interest. The bids ranged from $18.00 per share to $24.00 per share. The
parties were Bidder Alpha (strategic, $24.00 per share), Bidder Beta
(financial, $22.00 per share), Bidder Gamma (financial, $20.00 per share),
and Party D (an unsolicited unnamed party, range $18.00-$19.00 per share).

<!-- PAGE 2 -->

On May 15, 2025, after management presentations and due diligence, Bidder
Gamma withdrew, citing financing difficulties. On May 20, 2025, the
Company informed Party D that it was no longer being considered.

## Reasons for the Merger

On June 1, 2025, the board determined to proceed to a final round with
Bidder Alpha and Bidder Beta. Final bids were due June 30, 2025.

On June 30, 2025, Bidder Alpha submitted a final bid of $25.00 per share
in cash. Bidder Beta submitted a final bid of $23.50 per share in cash.

## Opinion of the Financial Advisor

On July 1, 2025, the board accepted Bidder Alpha's final bid. The merger
agreement was signed July 2, 2025, with a $50 million termination fee and
a 30-day go-shop window.

## Financing

Bidder Alpha's offer is fully financed by committed equity and debt.

## Interests of Directors and Executive Officers

No material conflicts of interest were identified.
```

- [ ] **Step 2: Verify the file exists and contains expected content**

Run: `wc -l tests/fixtures/smoke_filing.md && grep -c "<!-- PAGE" tests/fixtures/smoke_filing.md`

Expected: Around 50 lines and 2 page markers.

- [ ] **Step 3: Commit**

```bash
git add tests/fixtures/smoke_filing.md
git commit -m "test(fixtures): add smoke_filing.md synthetic fixture

Hand-authored ~50-line synthetic merger proxy that exercises every code
path: page markers, all expected sections, multiple bidders (named +
unnamed), aggregate counts, range bids, withdrawal, target rejection,
final-round formal proposals, signing, go-shop, termination fee.
Used as the fast CI fixture in Stages 2-7.
"
```

---

## Task 15: Hand-authored canonical fixture for the smoke filing

**Files:**
- Create: `tests/fixtures/smoke_canonical.json`

A JSON document with one section per table. Every row's `evidence_ids` references a span that exists in the same fixture. Together, the fixture exercises every table defined in Stage 1.

- [ ] **Step 1: Create the canonical fixture**

Create `tests/fixtures/smoke_canonical.json`:

```json
{
  "run_metadata": [
    {
      "run_id": "smoke_run_001",
      "input_archive_hash": "0000000000000000000000000000000000000000000000000000000000000000",
      "filing_ids": ["smoke_filing_1"],
      "ingest_version": "0.1.0",
      "extract_config_version": "0.1.0",
      "reconcile_version": "0.1.0",
      "validate_version": "0.1.0",
      "project_version": "0.1.0",
      "started_at": "2026-05-02T12:00:00+00:00",
      "completed_at": "2026-05-02T12:05:00+00:00"
    }
  ],
  "filings": [
    {
      "filing_id": "smoke_filing_1",
      "deal_slug": "smoke",
      "source_filename": "smoke_filing.md",
      "raw_md_path": "tests/fixtures/smoke_filing.md",
      "raw_md_hash": "1111111111111111111111111111111111111111111111111111111111111111",
      "clean_md_hash": "2222222222222222222222222222222222222222222222222222222222222222",
      "page_count": 2,
      "parser_version": "0.1.0",
      "ingested_at": "2026-05-02T12:00:00+00:00",
      "run_id": "smoke_run_001"
    }
  ],
  "sections": [
    {
      "section_id": "smoke_section_1",
      "filing_id": "smoke_filing_1",
      "section_name": "Background of the Merger",
      "char_start": 0,
      "char_end": 2000,
      "run_id": "smoke_run_001"
    },
    {
      "section_id": "smoke_section_2",
      "filing_id": "smoke_filing_1",
      "section_name": "Reasons for the Merger",
      "char_start": 2000,
      "char_end": 2500,
      "run_id": "smoke_run_001"
    }
  ],
  "paragraphs": [
    {
      "paragraph_id": "smoke_paragraph_1",
      "filing_id": "smoke_filing_1",
      "section": "Background of the Merger",
      "page_hint": 1,
      "char_start": 100,
      "char_end": 280,
      "paragraph_text": "On January 5, 2025, the board of directors of Smoke Co. authorized management to explore strategic alternatives, including a potential sale of the Company.",
      "paragraph_hash": "3333333333333333333333333333333333333333333333333333333333333333",
      "run_id": "smoke_run_001"
    },
    {
      "paragraph_id": "smoke_paragraph_2",
      "filing_id": "smoke_filing_1",
      "section": "Reasons for the Merger",
      "page_hint": 2,
      "char_start": 2000,
      "char_end": 2200,
      "paragraph_text": "On June 30, 2025, Bidder Alpha submitted a final bid of $25.00 per share in cash.",
      "paragraph_hash": "4444444444444444444444444444444444444444444444444444444444444444",
      "run_id": "smoke_run_001"
    }
  ],
  "spans": [
    {
      "evidence_id": "smoke_span_1",
      "filing_id": "smoke_filing_1",
      "paragraph_id": "smoke_paragraph_1",
      "char_start": 100,
      "char_end": 280,
      "quote_text": "On January 5, 2025, the board of directors of Smoke Co. authorized management to explore strategic alternatives, including a potential sale of the Company.",
      "quote_hash": "5555555555555555555555555555555555555555555555555555555555555555",
      "normalization_note": null,
      "run_id": "smoke_run_001"
    },
    {
      "evidence_id": "smoke_span_2",
      "filing_id": "smoke_filing_1",
      "paragraph_id": "smoke_paragraph_2",
      "char_start": 2000,
      "char_end": 2080,
      "quote_text": "On June 30, 2025, Bidder Alpha submitted a final bid of $25.00 per share in cash.",
      "quote_hash": "6666666666666666666666666666666666666666666666666666666666666666",
      "normalization_note": null,
      "run_id": "smoke_run_001"
    }
  ],
  "candidates": [
    {
      "candidate_id": "smoke_candidate_1",
      "candidate_type": "actor_mention",
      "raw_value": "Bidder Alpha",
      "normalized_value": "Bidder Alpha",
      "confidence": "high",
      "evidence_ids": ["smoke_span_2"],
      "dependencies": [],
      "status": "reconciled",
      "run_id": "smoke_run_001"
    }
  ],
  "deals": [
    {
      "deal_slug": "smoke",
      "target_name": "Smoke Co.",
      "filing_url": null,
      "filing_type": "DEFM14A",
      "filing_date": "2025-08-01",
      "deal_outcome": "completed",
      "winning_acquirer": "Bidder Alpha",
      "date_announced": "2025-07-02",
      "date_signed": "2025-07-02",
      "date_effective": null,
      "consideration_type": "cash",
      "consideration_value": 25.00,
      "currency": "USD",
      "evidence_ids": ["smoke_span_2"],
      "run_id": "smoke_run_001"
    }
  ],
  "process_cycles": [
    {
      "cycle_id": "smoke_cycle_1",
      "deal_slug": "smoke",
      "cycle_sequence": 1,
      "cycle_start_date": "2025-01-05",
      "cycle_end_date": "2025-07-02",
      "date_precision_start": "exact",
      "date_precision_end": "exact",
      "segmentation_basis": "full_process",
      "cycle_label": "primary",
      "evidence_ids": ["smoke_span_1"],
      "run_id": "smoke_run_001"
    }
  ],
  "actors": [
    {
      "actor_id": "smoke_actor_1",
      "deal_slug": "smoke",
      "actor_label": "Smoke Co.",
      "actor_type": "target",
      "bidder_subtype": null,
      "is_grouped": false,
      "group_size_if_known": null,
      "public_private_status": "public",
      "country": "US",
      "industry": "test",
      "alias_status": "resolved",
      "evidence_ids": ["smoke_span_1"],
      "run_id": "smoke_run_001"
    },
    {
      "actor_id": "smoke_actor_2",
      "deal_slug": "smoke",
      "actor_label": "Bidder Alpha",
      "actor_type": "bidder",
      "bidder_subtype": "strategic",
      "is_grouped": false,
      "group_size_if_known": null,
      "public_private_status": null,
      "country": null,
      "industry": null,
      "alias_status": "resolved",
      "evidence_ids": ["smoke_span_2"],
      "run_id": "smoke_run_001"
    },
    {
      "actor_id": "smoke_actor_3",
      "deal_slug": "smoke",
      "actor_label": "Test Advisor LLC",
      "actor_type": "advisor",
      "bidder_subtype": null,
      "is_grouped": false,
      "group_size_if_known": null,
      "public_private_status": null,
      "country": null,
      "industry": null,
      "alias_status": "resolved",
      "evidence_ids": ["smoke_span_1"],
      "run_id": "smoke_run_001"
    },
    {
      "actor_id": "smoke_actor_4",
      "deal_slug": "smoke",
      "actor_label": "Test Counsel LLP",
      "actor_type": "legal_counsel",
      "bidder_subtype": null,
      "is_grouped": false,
      "group_size_if_known": null,
      "public_private_status": null,
      "country": null,
      "industry": null,
      "alias_status": "resolved",
      "evidence_ids": ["smoke_span_1"],
      "run_id": "smoke_run_001"
    },
    {
      "actor_id": "smoke_actor_5",
      "deal_slug": "smoke",
      "actor_label": "Special Committee",
      "actor_type": "board_committee",
      "bidder_subtype": null,
      "is_grouped": true,
      "group_size_if_known": 2,
      "public_private_status": null,
      "country": null,
      "industry": null,
      "alias_status": "resolved",
      "evidence_ids": ["smoke_span_1"],
      "run_id": "smoke_run_001"
    }
  ],
  "events": [
    {
      "event_id": "smoke_evt_1",
      "deal_slug": "smoke",
      "cycle_id": "smoke_cycle_1",
      "event_date_start": "2025-06-30",
      "event_date_end": "2025-06-30",
      "date_precision": "exact",
      "event_type": "proposal_submitted",
      "event_subtype": "final_bid",
      "bid_value": 25.00,
      "bid_value_lower": 25.00,
      "bid_value_upper": 25.00,
      "bid_value_unit": "per_share",
      "consideration_type": "cash",
      "source_text": "$25.00 per share in cash",
      "source_page_hint": 2,
      "raw_note": null,
      "evidence_ids": ["smoke_span_2"],
      "run_id": "smoke_run_001"
    }
  ],
  "event_actor_links": [
    {
      "link_id": "smoke_link_1",
      "event_id": "smoke_evt_1",
      "actor_id": "smoke_actor_2",
      "role": "submitter",
      "link_confidence": "high",
      "evidence_ids": ["smoke_span_2"],
      "run_id": "smoke_run_001"
    }
  ],
  "judgments": [
    {
      "judgment_id": "smoke_judgment_1",
      "deal_slug": "smoke",
      "judgment_type": "formal_boundary",
      "scope": "cycle",
      "cycle_id": "smoke_cycle_1",
      "actor_id": null,
      "event_id": "smoke_evt_1",
      "value": "2025-06-01",
      "confidence": "high",
      "basis": "explicit final-round invitation on June 1, 2025",
      "source_snippet": "the board determined to proceed to a final round with Bidder Alpha and Bidder Beta",
      "alternative_value": null,
      "alternative_basis": null,
      "supersedes_judgment_id": null,
      "evidence_ids": ["smoke_span_1"],
      "run_id": "smoke_run_001"
    }
  ],
  "advisor_engagements": [
    {
      "engagement_id": "smoke_engagement_1",
      "deal_slug": "smoke",
      "advisor_actor_id": "smoke_actor_3",
      "client_actor_id": "smoke_actor_1",
      "role": "financial_advisor",
      "start_date": "2025-02-10",
      "end_date": "2025-07-02",
      "evidence_ids": ["smoke_span_1"],
      "run_id": "smoke_run_001"
    }
  ],
  "legal_counsel_engagements": [
    {
      "engagement_id": "smoke_legal_1",
      "deal_slug": "smoke",
      "counsel_actor_id": "smoke_actor_4",
      "client_actor_id": "smoke_actor_1",
      "role": "lead_counsel",
      "start_date": "2025-02-10",
      "end_date": null,
      "evidence_ids": ["smoke_span_1"],
      "run_id": "smoke_run_001"
    }
  ],
  "board_committees": [
    {
      "committee_id": "smoke_committee_1",
      "deal_slug": "smoke",
      "committee_name": "Special Committee",
      "authority": "evaluate strategic alternatives",
      "member_actor_ids": ["smoke_actor_5"],
      "independence_status": "independent",
      "start_date": "2025-01-05",
      "end_date": "2025-07-02",
      "evidence_ids": ["smoke_span_1"],
      "run_id": "smoke_run_001"
    }
  ],
  "deal_terms": [
    {
      "term_id": "smoke_term_1",
      "deal_slug": "smoke",
      "term_type": "termination_fee",
      "value": 50000000.0,
      "unit": "usd",
      "effective_date": "2025-07-02",
      "evidence_ids": ["smoke_span_2"],
      "run_id": "smoke_run_001"
    },
    {
      "term_id": "smoke_term_2",
      "deal_slug": "smoke",
      "term_type": "go_shop_length",
      "value": 30.0,
      "unit": "days",
      "effective_date": "2025-07-02",
      "evidence_ids": ["smoke_span_2"],
      "run_id": "smoke_run_001"
    }
  ],
  "group_memberships": [
    {
      "membership_id": "smoke_membership_1",
      "group_actor_id": "smoke_actor_5",
      "member_actor_id": "smoke_actor_2",
      "start_date": "2025-01-05",
      "end_date": null,
      "evidence_ids": ["smoke_span_1"],
      "run_id": "smoke_run_001"
    }
  ],
  "prior_relationships": [
    {
      "relationship_id": "smoke_relationship_1",
      "bidder_actor_id": "smoke_actor_2",
      "target_actor_id": "smoke_actor_1",
      "relationship_type": "none",
      "description": "no prior relationship disclosed",
      "date_start": null,
      "date_end": null,
      "evidence_ids": ["smoke_span_1"],
      "run_id": "smoke_run_001"
    }
  ],
  "participation_counts": [
    {
      "count_id": "smoke_count_1",
      "deal_slug": "smoke",
      "cycle_id": "smoke_cycle_1",
      "count_type": "contacted",
      "count_value": 12,
      "strategic_count": 5,
      "financial_count": 7,
      "unknown_count": 0,
      "process_stage": "outreach",
      "date_start": "2025-02-01",
      "date_end": "2025-03-31",
      "evidence_ids": ["smoke_span_1"],
      "run_id": "smoke_run_001"
    }
  ],
  "bid_normalizations": [
    {
      "normalization_id": "smoke_normalization_1",
      "event_id": "smoke_evt_1",
      "raw_amount_text": "$25.00 per share in cash",
      "currency": "USD",
      "operator": "exact",
      "center_rule": "exact_value",
      "unit_rule": "per_share",
      "lower_source": "exact_value",
      "upper_source": "exact_value",
      "conversion_applied": false,
      "conversion_basis": null,
      "confidence": "high",
      "evidence_ids": ["smoke_span_2"],
      "run_id": "smoke_run_001"
    }
  ],
  "cycle_phase_assignments": [
    {
      "assignment_id": "smoke_assignment_1",
      "event_id": "smoke_evt_1",
      "cycle_id": "smoke_cycle_1",
      "phase": "formal",
      "phase_basis": "post_boundary_proposal",
      "eligible_for_estimation_view": true,
      "evidence_ids": ["smoke_span_2"],
      "run_id": "smoke_run_001"
    }
  ]
}
```

- [ ] **Step 2: Verify the JSON is well-formed**

Run: `python -c "import json; json.load(open('tests/fixtures/smoke_canonical.json'))"`

Expected: no output (success). If JSON is malformed, this raises a `json.JSONDecodeError`.

- [ ] **Step 3: Verify every table has at least one row**

Run:
```bash
python -c "
import json
data = json.load(open('tests/fixtures/smoke_canonical.json'))
expected = {
    'run_metadata', 'filings', 'sections', 'paragraphs', 'spans', 'candidates',
    'deals', 'process_cycles', 'actors', 'events', 'event_actor_links',
    'judgments', 'advisor_engagements', 'legal_counsel_engagements',
    'board_committees', 'deal_terms', 'group_memberships', 'prior_relationships',
    'participation_counts', 'bid_normalizations', 'cycle_phase_assignments'
}
missing = expected - set(data.keys())
empty = {t for t in data if not data[t]}
print(f'tables: {len(data)}, missing: {missing}, empty: {empty}')
assert not missing and not empty, 'fixture is incomplete'
print('OK')
"
```

Expected: `tables: 21, missing: set(), empty: set()` then `OK`.

- [ ] **Step 4: Commit**

```bash
git add tests/fixtures/smoke_canonical.json
git commit -m "test(fixtures): add smoke_canonical.json hand-authored canonical fixture

One section per table. Every evidence_id references a span defined in the
same fixture. Exercises all 21 tables defined in Stage 1.
"
```

---

## Task 16: End-to-end Stage 1 acceptance test

**Files:**
- Create: `tests/test_smoke_canonical.py`

The Stage 1 acceptance gate: load `smoke_canonical.json`, validate every record through Pydantic, write them to a fresh DuckDB, read them back, assert equality. This is the single test that proves Stage 1 is done.

- [ ] **Step 1: Write the failing test**

Create `tests/test_smoke_canonical.py`:

```python
"""Stage 1 acceptance: smoke_canonical.json round-trips through Pydantic + DuckDB.

This is the gate test for Stage 1. If it passes, the schema scaffolding is
complete and the project can fan out into Tracks A/B/C.
"""

import json
from pathlib import Path

import pytest

from sec_graph.schema import (
    Actor,
    AdvisorEngagement,
    BidNormalization,
    BoardCommittee,
    CleanFiling,
    CyclePhaseAssignment,
    Deal,
    DealTerm,
    Event,
    EventActorLink,
    ExtractionCandidate,
    GroupMembership,
    Judgment,
    LegalCounselEngagement,
    Paragraph,
    ParticipationCount,
    PriorRelationship,
    ProcessCycle,
    RunMetadata,
    Section,
    SourceSpan,
    connect,
    fetch_model,
    init_schema,
    insert_model,
)


_FIXTURE = Path(__file__).parent / "fixtures" / "smoke_canonical.json"

# (table_name, model_class, primary_key_column)
_TABLE_SPEC: list[tuple[str, type, str]] = [
    # run_metadata first to satisfy any future FK to run_id
    ("run_metadata", RunMetadata, "run_id"),
    ("filings", CleanFiling, "filing_id"),
    ("sections", Section, "section_id"),
    ("paragraphs", Paragraph, "paragraph_id"),
    ("spans", SourceSpan, "evidence_id"),
    ("candidates", ExtractionCandidate, "candidate_id"),
    ("deals", Deal, "deal_slug"),
    ("process_cycles", ProcessCycle, "cycle_id"),
    ("actors", Actor, "actor_id"),
    ("events", Event, "event_id"),
    ("event_actor_links", EventActorLink, "link_id"),
    ("judgments", Judgment, "judgment_id"),
    ("advisor_engagements", AdvisorEngagement, "engagement_id"),
    ("legal_counsel_engagements", LegalCounselEngagement, "engagement_id"),
    ("board_committees", BoardCommittee, "committee_id"),
    ("deal_terms", DealTerm, "term_id"),
    ("group_memberships", GroupMembership, "membership_id"),
    ("prior_relationships", PriorRelationship, "relationship_id"),
    ("participation_counts", ParticipationCount, "count_id"),
    ("bid_normalizations", BidNormalization, "normalization_id"),
    ("cycle_phase_assignments", CyclePhaseAssignment, "assignment_id"),
]


@pytest.fixture
def fixture_data() -> dict:
    return json.loads(_FIXTURE.read_text(encoding="utf-8"))


def test_fixture_validates_against_every_model(fixture_data: dict) -> None:
    """Every record in every table validates as its corresponding Pydantic model."""
    for table, model_class, _pk in _TABLE_SPEC:
        rows = fixture_data[table]
        assert rows, f"fixture table {table} is empty"
        for raw in rows:
            instance = model_class.model_validate(raw)
            assert instance is not None


def test_fixture_round_trips_through_duckdb(fixture_data: dict) -> None:
    """Insert every record, fetch by PK, assert equality."""
    conn = connect(":memory:")
    try:
        init_schema(conn)
        for table, model_class, pk in _TABLE_SPEC:
            for raw in fixture_data[table]:
                model = model_class.model_validate(raw)
                insert_model(conn, table, model)
                fetched = fetch_model(conn, table, model_class, pk, raw[pk])
                assert fetched == model, (
                    f"round-trip mismatch in {table} for {pk}={raw[pk]!r}"
                )
    finally:
        conn.close()


def test_fixture_evidence_ids_resolve(fixture_data: dict) -> None:
    """Every evidence_id referenced by any row points to an actual span."""
    span_ids = {s["evidence_id"] for s in fixture_data["spans"]}
    for table, _model_class, _pk in _TABLE_SPEC:
        for raw in fixture_data[table]:
            for ev_id in raw.get("evidence_ids", []) or []:
                assert ev_id in span_ids, (
                    f"row in {table} references evidence_id {ev_id!r} "
                    "but that span is not defined in the fixture"
                )


def test_fixture_run_ids_resolve(fixture_data: dict) -> None:
    """Every row's run_id appears in run_metadata."""
    run_ids = {r["run_id"] for r in fixture_data["run_metadata"]}
    for table, _model_class, _pk in _TABLE_SPEC:
        if table == "run_metadata":
            continue
        for raw in fixture_data[table]:
            run_id = raw.get("run_id")
            if run_id is None:
                continue
            assert run_id in run_ids, (
                f"row in {table} has run_id {run_id!r} "
                "but that run is not defined in run_metadata"
            )


def test_fixture_paragraph_ids_resolve(fixture_data: dict) -> None:
    """Every span's paragraph_id resolves to an actual paragraph."""
    paragraph_ids = {p["paragraph_id"] for p in fixture_data["paragraphs"]}
    for span in fixture_data["spans"]:
        assert span["paragraph_id"] in paragraph_ids


def test_fixture_filing_ids_resolve(fixture_data: dict) -> None:
    """Every paragraph/span/section's filing_id resolves to an actual filing."""
    filing_ids = {f["filing_id"] for f in fixture_data["filings"]}
    for table_name in ("paragraphs", "spans", "sections"):
        for row in fixture_data[table_name]:
            assert row["filing_id"] in filing_ids


def test_supersedes_judgment_id_resolves_when_present(fixture_data: dict) -> None:
    """Where a judgment has supersedes_judgment_id, the prior judgment exists."""
    judgment_ids = {j["judgment_id"] for j in fixture_data["judgments"]}
    for j in fixture_data["judgments"]:
        if j["supersedes_judgment_id"] is not None:
            assert j["supersedes_judgment_id"] in judgment_ids
```

- [ ] **Step 2: Run, expect failure**

Run: `pytest tests/test_smoke_canonical.py -v`

Expected: import errors are gone now (Task 13 wired exports), but the round-trip test should run. If `smoke_canonical.json` has any mismatched fields or missing references, the test fails with a clear message.

If everything is correct, all 7 tests should pass. If they don't, the failure message points at the broken row — fix the JSON fixture inline (no schema changes needed).

- [ ] **Step 3: Verify it now passes**

Run: `pytest tests/test_smoke_canonical.py -v`

Expected: 7 tests pass.

- [ ] **Step 4: Run the full Stage 1 acceptance suite**

Run: `pytest tests/ -v`

Expected: every test passes. Approximate count: ~65 tests.

- [ ] **Step 5: Commit**

```bash
git add tests/test_smoke_canonical.py
git commit -m "test(stage-1): add Stage 1 acceptance test for smoke_canonical fixture

Loads smoke_canonical.json, validates every record through Pydantic, writes
to fresh DuckDB, fetches back, asserts equality. Plus referential-integrity
checks (evidence_ids, run_id, paragraph_id, filing_id, supersedes chain).

If this passes, Stage 1 is done and Tracks A/B/C can fan out.
"
```

---

## Stage 1 Done When

All of the following are true after Task 16:

1. `pytest tests/ -v` reports all tests passing.
2. `python -c "from sec_graph.schema import init_schema, connect; c = connect(':memory:'); init_schema(c); print(len(c.execute('SHOW TABLES').fetchall()))"` prints `21`.
3. `python -c "from sec_graph.fetch import edgar; print(edgar.USER_AGENT)"` works (post-relocation).
4. `python -c "from sec_graph.schema import make_id; print(make_id('petsmart', 'actor', 3))"` prints `petsmart_actor_3`.
5. `tests/fixtures/smoke_filing.md` exists and contains 2 page markers.
6. `tests/fixtures/smoke_canonical.json` exists and parses; every table has ≥1 row.

After Stage 1 lands, three parallel tracks can begin (per spec §13.5):
- **Track A:** Stage 2 (`ingest`)
- **Track B:** Stages 3 → 4 → 5 (reconcile-skeleton → validate → project)
- **Track C:** Stage 6 (`extract/rules`)
