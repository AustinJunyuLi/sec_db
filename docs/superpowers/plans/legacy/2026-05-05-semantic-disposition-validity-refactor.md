# Semantic Disposition Validity Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor `sec_graph` so unsupported claims cannot enter canonical tables, mature judgments are derived from supported facts, and underextraction becomes compact review flags instead of silent loss.

**Architecture:** Add a pre-reconcile support-disposition gate, then run a post-reconcile derived-judgment layer before validation and projection. Materialize review flags and proof verdicts so `SOUND`, `REVIEW_REQUIRED`, and `UNSOUND` mean different operational states.

**Tech Stack:** Python 3.12, DuckDB, Pydantic, pytest, `uv`, Linkflow GPT-5.5 via the existing P8 claim-only contract.

---

## Required Context

Read these files before editing:

```bash
sed -n '1,260p' AGENTS.md
sed -n '1,260p' docs/spec.md
sed -n '1,260p' docs/llm-interface.md
sed -n '1,260p' docs/superpowers/specs/2026-05-03-pipeline-hard-reset-design.md
sed -n '1,260p' docs/superpowers/specs/2026-05-05-semantic-disposition-validity-design.md
```

Non-negotiables:

- No fallbacks.
- No backward compatibility readers.
- No in-pipeline AI repair.
- No provider-owned source offsets, coverage results, or scalar judgments.
- No Alex or workbook taxonomy as canonical graph shape.
- No hardcoded deal-specific repair rules.
- Do not commit secrets. Use `LINKFLOW_API_KEY` from the environment only.
- Do not delete `data/filings/`.

## File Structure

Create:

- `src/sec_graph/extract/disposition.py`  
  Pre-reconcile support gate. Reads claims, typed claim rows, evidence, coverage links, and source text. Writes claim dispositions and review flags for unsupported or ambiguous claims.

- `src/sec_graph/judgments/__init__.py`  
  Exports the derived-judgment entry point.

- `src/sec_graph/judgments/derive.py`  
  Post-reconcile derived judgments for formal/informal, dropout taxonomy, projected fate, process role, actor class, and agreement kind.

- `tests/test_claim_disposition_gate.py`  
  Red-first tests for pre-reconcile support disposition and reconcile exclusion.

- `tests/test_derived_judgments.py`  
  Red-first tests for formal/informal, dropout, advisor, agreement-kind, and actor-role judgments.

- `tests/test_review_flags_and_verdicts.py`  
  Red-first tests for review flag materialization and `SOUND` / `REVIEW_REQUIRED` / `UNSOUND` verdict semantics.

- `scripts/reference9_matrix.py`  
  Small local helper that reads latest per-deal run directories and writes a Reference-9 proof matrix without running providers.

Modify:

- `src/sec_graph/schema/models/extraction.py`
- `src/sec_graph/schema/models/judgments.py`
- `src/sec_graph/schema/models/__init__.py`
- `src/sec_graph/schema/__init__.py`
- `src/sec_graph/reconcile/pipeline.py`
- `src/sec_graph/extract/llm/convert.py`
- `src/sec_graph/validate/integrity.py`
- `src/sec_graph/validate/flags.py`
- `src/sec_graph/project/summaries.py`
- `src/sec_graph/project/bidder_rows.py`
- `src/sec_graph/cli/run_cmd.py`
- `tests/test_hard_reset_schema.py`
- `tests/test_coverage_semantics.py`
- `tests/test_validation_semantics.py`
- `tests/test_llm_p8_contract.py`
- `docs/spec.md`
- `docs/llm-interface.md`
- stale plan and calibration paths listed in Task 9.

## Task 0: Preflight

**Files:**
- Read: repository state only

- [ ] **Step 1: Confirm branch and cleanliness**

Run:

```bash
git status --short --branch
git log --oneline -5
```

Expected:

```text
## codex/reference9-correctness-repair
8f1fbc9 docs: design semantic disposition validity refactor
```

If the worktree has unrelated user edits, leave them in place and record them in the implementation notes.

- [ ] **Step 2: Run the focused baseline**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 uv run pytest -q -p no:cacheprovider \
  tests/test_hard_reset_schema.py \
  tests/test_coverage_semantics.py \
  tests/test_validation_semantics.py \
  tests/test_llm_p8_contract.py
```

Expected: existing tests pass before behavior changes. If they fail, inspect the failure and decide whether it is caused by existing branch state before editing.

## Task 1: Schema Contract For Dispositions, Judgments, And Review Flags

**Files:**
- Modify: `src/sec_graph/schema/models/extraction.py`
- Modify: `src/sec_graph/schema/models/judgments.py`
- Modify: `src/sec_graph/schema/models/__init__.py`
- Modify: `src/sec_graph/schema/__init__.py`
- Modify: `tests/test_hard_reset_schema.py`

- [ ] **Step 1: Write failing schema tests**

Append tests to `tests/test_hard_reset_schema.py`:

```python
def test_claim_disposition_enum_uses_support_statuses() -> None:
    conn = connect(":memory:")
    init_schema(conn)
    rows = conn.execute(
        """
        SELECT constraint_text
        FROM duckdb_constraints()
        WHERE table_name = 'claim_dispositions'
        ORDER BY constraint_text
        """
    ).fetchall()
    text = "\n".join(row[0] for row in rows)
    assert "supported" in text
    assert "rejected_unsupported" in text
    assert "queued_ambiguity" in text
    assert "canonicalized" not in text


def test_judgments_and_review_flags_tables_exist() -> None:
    conn = connect(":memory:")
    init_schema(conn)
    table_names = {
        row[0]
        for row in conn.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'main'"
        ).fetchall()
    }
    assert "judgments" in table_names
    assert "review_flags" in table_names

    judgment_columns = {
        row[1]
        for row in conn.execute("PRAGMA table_info('judgments')").fetchall()
    }
    for column in (
        "judgment_key",
        "judgment_value",
        "judgment_status",
        "rule_id",
        "basis_json",
        "current",
    ):
        assert column in judgment_columns

    review_flag_columns = {
        row[1]
        for row in conn.execute("PRAGMA table_info('review_flags')").fetchall()
    }
    for column in (
        "flag_id",
        "run_id",
        "deal_slug",
        "flag_type",
        "severity",
        "reason_code",
        "recommended_review_question",
    ):
        assert column in review_flag_columns
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 uv run pytest -q -p no:cacheprovider \
  tests/test_hard_reset_schema.py::test_claim_disposition_enum_uses_support_statuses \
  tests/test_hard_reset_schema.py::test_judgments_and_review_flags_tables_exist
```

Expected: FAIL because the current disposition enum still includes `canonicalized`, and `review_flags` does not exist.

- [ ] **Step 3: Update extraction schema**

In `src/sec_graph/schema/models/extraction.py`, change the type aliases and DDL to this shape:

```python
ClaimStatus = Literal["validated", "rejected", "disposed"]
Disposition = Literal[
    "supported",
    "merged_duplicate",
    "rejected_unsupported",
    "queued_ambiguity",
    "out_of_scope",
]
CoverageResultKind = Literal[
    "claims_emitted",
    "no_supported_claim",
    "ambiguous_support",
    "missed_supported_obligation",
]
```

Change the `claim_dispositions` table check constraint to:

```sql
disposition VARCHAR NOT NULL CHECK (disposition IN ('supported', 'merged_duplicate', 'rejected_unsupported', 'queued_ambiguity', 'out_of_scope')),
```

- [ ] **Step 4: Replace the judgments model and add review flags**

Replace `src/sec_graph/schema/models/judgments.py` with a narrowed current-contract model:

```python
"""Python-owned derived judgments and review flags."""

from __future__ import annotations

from typing import Iterable, Literal

from pydantic import BaseModel, ConfigDict

JudgmentStatus = Literal["accepted", "review_required", "not_applicable"]
ReviewSeverity = Literal["blocking", "review", "info"]


class Judgment(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    judgment_id: str
    run_id: str
    deal_id: str
    cycle_id: str | None
    target_table: str
    target_id: str
    judgment_key: str
    judgment_value: str | None
    judgment_status: JudgmentStatus
    rule_id: str
    reason_code: str
    reason: str
    basis_json: str
    current: bool = True
    supersedes_judgment_id: str | None = None


class ReviewFlag(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    flag_id: str
    run_id: str
    deal_slug: str
    filing_id: str | None
    region_id: str | None
    obligation_id: str | None
    claim_id: str | None
    judgment_id: str | None
    canonical_table: str | None
    canonical_id: str | None
    flag_type: str
    severity: ReviewSeverity
    reason_code: str
    reason: str
    quote_text: str | None
    source_ref: str | None
    short_source_context: str | None
    recommended_review_question: str
    current: bool = True


def latest_judgments(judgments: Iterable[Judgment]) -> list[Judgment]:
    rows = list(judgments)
    superseded = {
        judgment.supersedes_judgment_id
        for judgment in rows
        if judgment.supersedes_judgment_id is not None
    }
    return [judgment for judgment in rows if judgment.judgment_id not in superseded]


JUDGMENTS_DDL = """
CREATE TABLE judgments (
  judgment_id VARCHAR PRIMARY KEY,
  run_id VARCHAR NOT NULL,
  deal_id VARCHAR NOT NULL,
  cycle_id VARCHAR,
  target_table VARCHAR NOT NULL,
  target_id VARCHAR NOT NULL,
  judgment_key VARCHAR NOT NULL,
  judgment_value VARCHAR,
  judgment_status VARCHAR NOT NULL CHECK (judgment_status IN ('accepted', 'review_required', 'not_applicable')),
  rule_id VARCHAR NOT NULL,
  reason_code VARCHAR NOT NULL,
  reason VARCHAR NOT NULL,
  basis_json VARCHAR NOT NULL,
  current BOOLEAN NOT NULL,
  supersedes_judgment_id VARCHAR,
  FOREIGN KEY (supersedes_judgment_id) REFERENCES judgments(judgment_id)
);

CREATE TABLE review_flags (
  flag_id VARCHAR PRIMARY KEY,
  run_id VARCHAR NOT NULL,
  deal_slug VARCHAR NOT NULL,
  filing_id VARCHAR,
  region_id VARCHAR,
  obligation_id VARCHAR,
  claim_id VARCHAR,
  judgment_id VARCHAR,
  canonical_table VARCHAR,
  canonical_id VARCHAR,
  flag_type VARCHAR NOT NULL,
  severity VARCHAR NOT NULL CHECK (severity IN ('blocking', 'review', 'info')),
  reason_code VARCHAR NOT NULL,
  reason VARCHAR NOT NULL,
  quote_text VARCHAR,
  source_ref VARCHAR,
  short_source_context VARCHAR,
  recommended_review_question VARCHAR NOT NULL,
  current BOOLEAN NOT NULL
);
"""
```

- [ ] **Step 5: Export `ReviewFlag`**

Update `src/sec_graph/schema/models/__init__.py` and `src/sec_graph/schema/__init__.py` so `ReviewFlag` is imported and listed in `__all__`.

- [ ] **Step 6: Run schema tests**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 uv run pytest -q -p no:cacheprovider tests/test_hard_reset_schema.py
```

Expected: PASS.

- [ ] **Step 7: Commit**

Run:

```bash
git add src/sec_graph/schema tests/test_hard_reset_schema.py
git commit -m "feat: define support dispositions and review flags"
```

## Task 2: Pre-Reconcile Claim Disposition Gate

**Files:**
- Create: `src/sec_graph/extract/disposition.py`
- Modify: `src/sec_graph/reconcile/pipeline.py`
- Modify: `src/sec_graph/cli/run_cmd.py`
- Create: `tests/test_claim_disposition_gate.py`
- Modify: `tests/test_validation_semantics.py`

- [ ] **Step 1: Write failing gate tests**

Create `tests/test_claim_disposition_gate.py` with these tests:

```python
from pathlib import Path

import duckdb

from sec_graph.extract.disposition import dispose_claims_for_filing
from sec_graph.reconcile.pipeline import reconcile_filing
from sec_graph.schema import init_schema, quote_hash


def _conn() -> duckdb.DuckDBPyConnection:
    conn = duckdb.connect(":memory:")
    init_schema(conn)
    return conn


def test_unsupported_bid_claim_is_rejected_before_reconcile():
    conn = _conn()
    _seed_minimal_bid_claim(
        conn,
        quote_text="Party A submitted a proposal.",
        bidder_label="Party A",
        bid_date="2024-01-02",
        bid_value=10.0,
    )

    dispose_claims_for_filing(conn, filing_id="deal_filing_1", run_id="run-1")

    row = conn.execute(
        "SELECT disposition, reason_code FROM claim_dispositions WHERE claim_id = 'deal_claim_1'"
    ).fetchone()
    assert row == ("rejected_unsupported", "bid_quote_missing_date_or_value")

    flags = conn.execute("SELECT flag_type, severity FROM review_flags").fetchall()
    assert flags == [("unsupported_claim", "blocking")]


def test_reconcile_refuses_undisposed_claims():
    conn = _conn()
    _seed_minimal_bid_claim(
        conn,
        quote_text="On January 2, 2024, Party A submitted a proposal of $10.00 per share.",
        bidder_label="Party A",
        bid_date="2024-01-02",
        bid_value=10.0,
    )

    try:
        reconcile_filing(conn, filing_id="deal_filing_1", run_id="run-1")
    except ValueError as exc:
        assert "undisposed supported claims" in str(exc)
    else:
        raise AssertionError("reconcile must reject undisposed claims")


def _seed_minimal_bid_claim(
    conn: duckdb.DuckDBPyConnection,
    *,
    quote_text: str,
    bidder_label: str,
    bid_date: str,
    bid_value: float,
) -> None:
    conn.execute(
        "INSERT INTO filings VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        [
            "deal_filing_1",
            "run-1",
            "deal",
            "example.md",
            "raw_md",
            None,
            None,
            "2024-01-01",
        ],
    )
    conn.execute(
        "INSERT INTO paragraphs VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        [
            "deal_para_1",
            "deal_filing_1",
            "Background of the Merger",
            None,
            0,
            len(quote_text),
            quote_text,
            quote_hash(quote_text),
        ],
    )
    conn.execute(
        "INSERT INTO spans VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            "deal_evidence_1",
            "deal_filing_1",
            "deal_para_1",
            "raw_md",
            "llm_extract",
            None,
            "extract",
            0,
            len(quote_text),
            quote_text,
            "hash",
            "fingerprint",
        ],
    )
    conn.execute(
        "INSERT INTO claims VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            "deal_claim_1",
            "run-1",
            "deal_filing_1",
            "deal",
            "deal_region_1",
            "linkflow",
            "bid",
            "high",
            quote_text,
            None,
            quote_text,
            "hash",
            "validated",
            1,
        ],
    )
    conn.execute("INSERT INTO claim_evidence VALUES (?, ?, ?)", ["deal_claim_1", "deal_evidence_1", 1])
    conn.execute(
        "INSERT INTO bid_claims VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ["deal_claim_1", bidder_label, bid_date, bid_value, None, None, "USD_per_share", "cash", "initial"],
    )
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 uv run pytest -q -p no:cacheprovider tests/test_claim_disposition_gate.py
```

Expected: FAIL because `sec_graph.extract.disposition` does not exist.

- [ ] **Step 3: Implement `src/sec_graph/extract/disposition.py`**

Create the module with this minimal entry point:

```python
"""Pre-reconcile claim support dispositions."""

from __future__ import annotations

import re

import duckdb

from sec_graph.schema import make_id


def dispose_claims_for_filing(
    conn: duckdb.DuckDBPyConnection,
    *,
    filing_id: str,
    run_id: str,
) -> None:
    rows = conn.execute(
        """
        SELECT claim_id, claim_type, deal_slug, region_id, quote_text, raw_value
        FROM claims
        WHERE filing_id = ? AND status = 'validated'
        ORDER BY claim_sequence, claim_id
        """,
        [filing_id],
    ).fetchall()
    for sequence, row in enumerate(rows, start=1):
        claim_id, claim_type, deal_slug, region_id, quote_text, raw_value = row
        disposition, reason_code, reason = _classify_claim(conn, claim_id, claim_type, quote_text)
        _insert_disposition(
            conn,
            deal_slug=deal_slug,
            sequence=sequence,
            claim_id=claim_id,
            disposition=disposition,
            reason_code=reason_code,
            reason=reason,
        )
        if disposition in {"rejected_unsupported", "queued_ambiguity"}:
            _insert_review_flag(
                conn,
                deal_slug=deal_slug,
                run_id=run_id,
                filing_id=filing_id,
                region_id=region_id,
                claim_id=claim_id,
                sequence=sequence,
                flag_type="unsupported_claim" if disposition == "rejected_unsupported" else "ambiguous_support",
                severity="blocking" if disposition == "rejected_unsupported" else "review",
                reason_code=reason_code,
                reason=reason,
                quote_text=quote_text,
            )


def _classify_claim(
    conn: duckdb.DuckDBPyConnection,
    claim_id: str,
    claim_type: str,
    quote_text: str,
) -> tuple[str, str, str]:
    if claim_type == "bid":
        row = conn.execute(
            """
            SELECT bidder_label, bid_date, bid_value, bid_value_lower, bid_value_upper
            FROM bid_claims
            WHERE claim_id = ?
            """,
            [claim_id],
        ).fetchone()
        if row is None:
            return "rejected_unsupported", "missing_bid_claim", "Bid claim has no typed bid row."
        bidder_label, bid_date, bid_value, bid_value_lower, bid_value_upper = row
        missing = []
        if not _contains_phrase(quote_text, str(bidder_label)):
            missing.append("bidder")
        if bid_date is not None and str(bid_date)[:4] not in quote_text:
            missing.append("date")
        values = [value for value in (bid_value, bid_value_lower, bid_value_upper) if value is not None]
        if values and not any(_number_appears(quote_text, float(value)) for value in values):
            missing.append("value")
        if missing:
            return (
                "rejected_unsupported",
                "bid_quote_missing_" + "_or_".join(missing),
                "Bid claim quote_text does not support: " + ", ".join(missing),
            )
        return "supported", "bid_quote_supported", "Bid claim quote_text supports typed fields."
    return "supported", f"{claim_type}_support_not_yet_specialized", "Claim passed generic support gate."


def _insert_disposition(
    conn: duckdb.DuckDBPyConnection,
    *,
    deal_slug: str,
    sequence: int,
    claim_id: str,
    disposition: str,
    reason_code: str,
    reason: str,
) -> None:
    conn.execute(
        "DELETE FROM claim_dispositions WHERE claim_id = ? AND current = true",
        [claim_id],
    )
    conn.execute(
        "INSERT INTO claim_dispositions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            make_id(deal_slug, "disposition", sequence),
            claim_id,
            disposition,
            reason_code,
            reason,
            None,
            None,
            None,
            True,
            None,
            None,
        ],
    )


def _insert_review_flag(
    conn: duckdb.DuckDBPyConnection,
    *,
    deal_slug: str,
    run_id: str,
    filing_id: str,
    region_id: str,
    claim_id: str,
    sequence: int,
    flag_type: str,
    severity: str,
    reason_code: str,
    reason: str,
    quote_text: str,
) -> None:
    conn.execute(
        "INSERT INTO review_flags VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            make_id(deal_slug, "reviewflag", sequence),
            run_id,
            deal_slug,
            filing_id,
            region_id,
            None,
            claim_id,
            None,
            None,
            None,
            flag_type,
            severity,
            reason_code,
            reason,
            quote_text,
            None,
            quote_text[:240],
            "Review whether this claim is supported by the quoted source text.",
            True,
        ],
    )


def _contains_phrase(text: str, phrase: str) -> bool:
    return phrase.casefold() in text.casefold()


def _number_appears(text: str, value: float) -> bool:
    candidates = {
        f"{value:g}",
        f"{value:.1f}".rstrip("0").rstrip("."),
        f"{value:.2f}",
    }
    folded = text.casefold().replace("$", " ")
    return any(candidate in folded for candidate in candidates)
```

This initial version is intentionally narrow. Later steps extend relation, count, advisor, and judgment-specific support without broadening provider output.

- [ ] **Step 4: Tighten reconcile input**

In `src/sec_graph/reconcile/pipeline.py`, change `_claim_rows()` to select only claims with supported or merged duplicate dispositions:

```sql
FROM claims
JOIN claim_dispositions
  ON claim_dispositions.claim_id = claims.claim_id
 AND claim_dispositions.current = true
WHERE filing_id = ?
  AND claims.status = 'validated'
  AND claim_dispositions.disposition IN ('supported', 'merged_duplicate')
```

Before reading supported rows, add a check in `reconcile_filing()`:

```python
undisposed = conn.execute(
    """
    SELECT count(*)
    FROM claims
    LEFT JOIN claim_dispositions
      ON claim_dispositions.claim_id = claims.claim_id
     AND claim_dispositions.current = true
    WHERE claims.filing_id = ?
      AND claims.status = 'validated'
      AND claim_dispositions.claim_id IS NULL
    """,
    [filing_id],
).fetchone()[0]
if undisposed:
    raise ValueError(f"filing {filing_id} has undisposed supported claims")
```

- [ ] **Step 5: Call the gate from the run pipeline**

In `src/sec_graph/cli/run_cmd.py`, import and call the gate after extraction and before `reconcile_all`:

```python
from sec_graph.extract.disposition import dispose_claims_for_filing
```

Inside the filing loop after `run_extract(...)`:

```python
dispose_claims_for_filing(conn, filing_id=filing.filing_id, run_id=run_id)
append_progress(
    run_dir,
    run_id=run_id,
    deal_slug=filing.deal_slug,
    stage="dispose",
    state="claims_disposed",
    attempt=1,
    recorded_at=clock.timestamp("dispose", sequence=1),
)
```

- [ ] **Step 6: Run gate tests**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 uv run pytest -q -p no:cacheprovider tests/test_claim_disposition_gate.py
```

Expected: PASS.

- [ ] **Step 7: Run focused integration tests**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 uv run pytest -q -p no:cacheprovider \
  tests/test_validation_semantics.py \
  tests/test_hard_reset_schema.py
```

Expected: PASS after updating old assertions from `canonicalized` / `rejected` to the new support dispositions.

- [ ] **Step 8: Commit**

Run:

```bash
git add src/sec_graph/extract/disposition.py src/sec_graph/reconcile/pipeline.py src/sec_graph/cli/run_cmd.py tests/test_claim_disposition_gate.py tests/test_validation_semantics.py tests/test_hard_reset_schema.py
git commit -m "feat: gate canonicalization on claim support"
```

## Task 3: Coverage Results And Anti-Underextraction Review Flags

**Files:**
- Modify: `src/sec_graph/extract/llm/convert.py`
- Modify: `src/sec_graph/validate/integrity.py`
- Modify: `tests/test_coverage_semantics.py`
- Modify: `tests/test_validation_semantics.py`

- [ ] **Step 1: Write failing coverage status tests**

Add to `tests/test_coverage_semantics.py`:

```python
def test_unlinked_supported_obligation_becomes_missed_supported_obligation(tmp_path):
    conn, request = _request_with_one_obligation(tmp_path, obligation_kind="ioi_count")
    response = _empty_completed_response(request)

    insert_llm_response(conn, request, response, run_id=request.run_id)

    row = conn.execute(
        "SELECT result, reason_code FROM coverage_results WHERE obligation_id = ?",
        [request.coverage_obligations[0].obligation_id],
    ).fetchone()
    assert row == ("missed_supported_obligation", "linkflow_no_linked_claim")


def test_claims_emitted_requires_supported_linked_claim(tmp_path):
    conn, request = _request_with_one_obligation(tmp_path, obligation_kind="final_consideration")
    response = _completed_response_with_bid_claim(request)

    claim_ids = insert_llm_response(conn, request, response, run_id=request.run_id)
    conn.execute(
        "INSERT INTO claim_dispositions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            "deal_disposition_1",
            claim_ids[0],
            "rejected_unsupported",
            "test_rejection",
            "test",
            None,
            None,
            None,
            True,
            None,
            None,
        ],
    )

    result = validate_database(conn)
    details = [failure.detail for failure in result.hard_failures]
    assert any("claims_emitted requires supported linked claims" in item for item in details)
```

Add these helpers below the new tests in `tests/test_coverage_semantics.py`:

```python
from sec_graph.extract.llm.models import BidClaimPayload


def _request_with_one_obligation(tmp_path: Path, *, obligation_kind: str) -> tuple:
    conn = connect(":memory:")
    init_schema(conn)
    _insert_window_source(conn, tmp_path)
    _replace_obligations(
        conn,
        [
            (
                obligation_kind,
                "bid" if obligation_kind == "final_consideration" else "participation_count",
                "Final consideration" if obligation_kind == "final_consideration" else "IOI count",
                "required",
                "positive_source_support",
                ["proposal"],
            )
        ],
    )
    request = LLMWindowRequest(
        request_id="coverage-deal_llmrequest_1",
        deal_slug="coverage-deal",
        deal_id="coverage-deal",
        filing_id="coverage-deal_filing_1",
        region_id="coverage-deal_region_1",
        window_id="coverage-deal_window_1",
        region_kind="sale_process_narrative",
        ordered_paragraphs=[
            WindowParagraph(
                paragraph_id="coverage-deal_para_1",
                source_span_id="coverage-deal_evidence_1",
                char_start=0,
                char_end=89,
                paragraph_text=(
                    "The Board began a sale process. "
                    "The Board later granted exclusivity to Buyer A."
                ),
            )
        ],
        coverage_obligations=[
            WindowObligation(
                obligation_id="coverage-deal_obligation_1",
                expected_claim_type="bid" if obligation_kind == "final_consideration" else "participation_count",
                obligation_label="Final consideration" if obligation_kind == "final_consideration" else "IOI count",
                importance="required",
            )
        ],
        allowed_claim_types=["bid"] if obligation_kind == "final_consideration" else ["participation_count"],
        schema_version=1,
        extract_version=1,
        request_mode=DEFAULT_REQUEST_MODE,
    )
    return conn, request


def _empty_completed_response(request: LLMWindowRequest) -> LLMExtractionResponse:
    payload = SemanticClaimsPayload()
    return LLMExtractionResponse(
        request_id=request.request_id,
        provider_name="linkflow",
        provider_model="gpt-5.5",
        reasoning_effort="medium",
        payload=payload,
        raw_response_sha256=quote_hash(json.dumps(payload.model_dump(mode="json"), sort_keys=True)),
        finish_status="completed",
    )


def _completed_response_with_bid_claim(request: LLMWindowRequest) -> LLMExtractionResponse:
    payload = SemanticClaimsPayload(
        bid_claims=[
            BidClaimPayload(
                claim_type="bid",
                coverage_obligation_id=request.coverage_obligations[0].obligation_id,
                bidder_label="Buyer A",
                bid_date=None,
                bid_value=10.0,
                bid_value_lower=None,
                bid_value_upper=None,
                bid_value_unit="USD_per_share",
                consideration_type="cash",
                bid_stage="final",
                confidence="high",
                quote_text="The Board later granted exclusivity to Buyer A.",
            )
        ]
    )
    return LLMExtractionResponse(
        request_id=request.request_id,
        provider_name="linkflow",
        provider_model="gpt-5.5",
        reasoning_effort="medium",
        payload=payload,
        raw_response_sha256=quote_hash(json.dumps(payload.model_dump(mode="json"), sort_keys=True)),
        finish_status="completed",
    )
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 uv run pytest -q -p no:cacheprovider tests/test_coverage_semantics.py
```

Expected: FAIL because coverage still uses old `missed` / `ambiguous` names and validation does not check disposition support on linked claims.

- [ ] **Step 3: Rename coverage result names in converter**

In `src/sec_graph/extract/llm/convert.py`:

- replace `missed` with `missed_supported_obligation`;
- replace `ambiguous` with `ambiguous_support`;
- keep `no_supported_claim`;
- keep `claims_emitted`.

Update reason constants:

```python
_NO_LINKED_CLAIM_REASON = (
    "Python marked this obligation missed_supported_obligation because "
    "Linkflow returned no supported claim linked to this obligation."
)
_AMBIGUOUS_SUPPORT_REASON = (
    "Python could not safely classify source support for this applicable "
    "obligation after region and applicability review."
)
```

- [ ] **Step 4: Validate support disposition for coverage links**

In `src/sec_graph/validate/integrity.py`, extend `_check_coverage_results()` with a query that fails `claims_emitted` when linked claims lack a current `supported` or `merged_duplicate` disposition:

```sql
SELECT coverage_results.obligation_id, claim_coverage_links.claim_id
FROM coverage_results
JOIN claim_coverage_links
  ON claim_coverage_links.obligation_id = coverage_results.obligation_id
 AND claim_coverage_links.current = true
LEFT JOIN claim_dispositions
  ON claim_dispositions.claim_id = claim_coverage_links.claim_id
 AND claim_dispositions.current = true
WHERE coverage_results.current = true
  AND coverage_results.result = 'claims_emitted'
  AND (
    claim_dispositions.claim_id IS NULL
    OR claim_dispositions.disposition NOT IN ('supported', 'merged_duplicate')
  )
```

Return:

```python
ValidationFailure(
    HardCheck.COVERAGE_RESULT,
    "claim_coverage_links",
    obligation_id,
    f"claims_emitted requires supported linked claims; linked claim {claim_id} is not supported",
)
```

- [ ] **Step 5: Emit review flags for missed and ambiguous coverage**

In `src/sec_graph/extract/llm/convert.py`, after inserting each non-`claims_emitted` coverage result for an important or required obligation, insert a `review_flags` row:

```python
if result in {"missed_supported_obligation", "ambiguous_support"} and obligation.importance in {"required", "important"}:
    _insert_coverage_review_flag(
        conn,
        request=request,
        obligation=obligation,
        sequence=coverage_sequence,
        flag_type=result,
        severity="review",
        reason_code=reason_code,
        reason=reason,
    )
```

Implement `_insert_coverage_review_flag()` in the same module using the `review_flags` DDL column order.

- [ ] **Step 6: Run coverage and validation tests**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 uv run pytest -q -p no:cacheprovider \
  tests/test_coverage_semantics.py \
  tests/test_validation_semantics.py
```

Expected: PASS.

- [ ] **Step 7: Commit**

Run:

```bash
git add src/sec_graph/extract/llm/convert.py src/sec_graph/validate/integrity.py tests/test_coverage_semantics.py tests/test_validation_semantics.py
git commit -m "feat: surface missed supported obligations"
```

## Task 4: Derived Judgment Layer

**Files:**
- Create: `src/sec_graph/judgments/__init__.py`
- Create: `src/sec_graph/judgments/derive.py`
- Modify: `src/sec_graph/cli/run_cmd.py`
- Create: `tests/test_derived_judgments.py`

- [ ] **Step 1: Write failing judgment tests**

Create `tests/test_derived_judgments.py`:

```python
import duckdb

from sec_graph.judgments.derive import derive_judgments
from sec_graph.schema import init_schema


def test_range_bid_derives_informal_judgment():
    conn = duckdb.connect(":memory:")
    init_schema(conn)
    _seed_deal_cycle_actor_and_bid_event(
        conn,
        event_id="deal_event_1",
        bid_value_lower=10.0,
        bid_value_upper=12.0,
        event_subtype="ioi_submitted",
    )

    derive_judgments(conn, run_id="run-1")

    row = conn.execute(
        "SELECT judgment_key, judgment_value, judgment_status, rule_id FROM judgments"
    ).fetchone()
    assert row == ("bid_formality", "informal", "accepted", "bid_formality_v1")


def test_missing_formality_substrate_creates_review_flag():
    conn = duckdb.connect(":memory:")
    init_schema(conn)
    _seed_deal_cycle_actor_and_bid_event(
        conn,
        event_id="deal_event_1",
        bid_value_lower=None,
        bid_value_upper=None,
        event_subtype="final_round_bid",
    )

    derive_judgments(conn, run_id="run-1")

    flag = conn.execute(
        "SELECT flag_type, severity, reason_code FROM review_flags"
    ).fetchone()
    assert flag == ("judgment_substrate_missing", "review", "formality_substrate_missing")


def test_observed_drop_gets_projected_fate_judgment():
    conn = duckdb.connect(":memory:")
    init_schema(conn)
    _seed_deal_cycle_actor_and_event(conn, event_id="deal_event_1", event_subtype="withdrawn_by_bidder")

    derive_judgments(conn, run_id="run-1")

    row = conn.execute(
        "SELECT judgment_key, judgment_value, judgment_status FROM judgments WHERE judgment_key = 'projected_fate'"
    ).fetchone()
    assert row == ("projected_fate", "observed_drop", "accepted")
```

Add these seed helpers at the bottom of `tests/test_derived_judgments.py`:

```python
def _seed_deal_cycle_actor_and_bid_event(
    conn: duckdb.DuckDBPyConnection,
    *,
    event_id: str,
    bid_value_lower: float | None,
    bid_value_upper: float | None,
    event_subtype: str,
) -> None:
    _seed_deal_cycle_actor(conn)
    conn.execute(
        "INSERT INTO events VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            event_id,
            "run-1",
            "deal_deal_1",
            "deal_cycle_1",
            "bid",
            event_subtype,
            "2024-01-02",
            f"{event_subtype} event",
            None,
            bid_value_lower,
            bid_value_upper,
            "USD_per_share",
            "cash",
        ],
    )
    conn.execute(
        "INSERT INTO event_actor_links VALUES (?, ?, ?, ?, ?, ?)",
        ["deal_link_1", "run-1", event_id, "deal_actor_2", "bid_submitter", None],
    )


def _seed_deal_cycle_actor_and_event(
    conn: duckdb.DuckDBPyConnection,
    *,
    event_id: str,
    event_subtype: str,
) -> None:
    _seed_deal_cycle_actor(conn)
    conn.execute(
        "INSERT INTO events VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            event_id,
            "run-1",
            "deal_deal_1",
            "deal_cycle_1",
            "process" if event_subtype != "merger_agreement_executed" else "transaction",
            event_subtype,
            "2024-01-02",
            f"{event_subtype} event",
            None,
            None,
            None,
            None,
            None,
        ],
    )
    conn.execute(
        "INSERT INTO event_actor_links VALUES (?, ?, ?, ?, ?, ?)",
        ["deal_link_1", "run-1", event_id, "deal_actor_2", "bid_submitter", None],
    )


def _seed_deal_cycle_actor(conn: duckdb.DuckDBPyConnection) -> None:
    conn.execute(
        "INSERT INTO deals VALUES (?, ?, ?, ?, ?)",
        ["deal_deal_1", "run-1", "deal", "deal_actor_1", "2024-01-01"],
    )
    conn.execute(
        "INSERT INTO actors VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ["deal_actor_1", "run-1", "deal_deal_1", "Target", "organization", "named", None, None, None, None],
    )
    conn.execute(
        "INSERT INTO actors VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ["deal_actor_2", "run-1", "deal_deal_1", "Party A", "organization", "named", None, None, None, None],
    )
    conn.execute(
        "INSERT INTO process_cycles VALUES (?, ?, ?, ?, ?, ?, ?)",
        ["deal_cycle_1", "run-1", "deal_deal_1", 1, "primary sale process", "2024-01-01", "2024-01-03"],
    )
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 uv run pytest -q -p no:cacheprovider tests/test_derived_judgments.py
```

Expected: FAIL because `sec_graph.judgments.derive` does not exist.

- [ ] **Step 3: Implement judgment module**

Create `src/sec_graph/judgments/__init__.py`:

```python
"""Python-owned derived judgments."""

from .derive import derive_judgments

__all__ = ["derive_judgments"]
```

Create `src/sec_graph/judgments/derive.py` with:

```python
"""Derive research judgments from supported canonical facts."""

from __future__ import annotations

import json

import duckdb

from sec_graph.schema import make_id


def derive_judgments(conn: duckdb.DuckDBPyConnection, *, run_id: str) -> None:
    _clear_current(conn, run_id)
    _derive_bid_formality(conn, run_id)
    _derive_projected_fate(conn, run_id)


def _clear_current(conn: duckdb.DuckDBPyConnection, run_id: str) -> None:
    conn.execute("DELETE FROM judgments WHERE run_id = ?", [run_id])
    conn.execute("DELETE FROM review_flags WHERE run_id = ? AND flag_type LIKE 'judgment_%'", [run_id])


def _derive_bid_formality(conn: duckdb.DuckDBPyConnection, run_id: str) -> None:
    rows = conn.execute(
        """
        SELECT events.event_id, events.deal_id, process_cycles.cycle_id,
               events.event_subtype, events.event_date
        FROM events
        JOIN process_cycles USING (cycle_id)
        WHERE events.run_id = ?
          AND events.event_type = 'bid'
        ORDER BY events.event_date NULLS LAST, events.event_id
        """,
        [run_id],
    ).fetchall()
    for sequence, (event_id, deal_id, cycle_id, event_subtype, event_date) in enumerate(rows, start=1):
        if event_subtype in {"ioi_submitted", "first_round_bid"}:
            _insert_judgment(
                conn,
                sequence=sequence,
                run_id=run_id,
                deal_id=deal_id,
                cycle_id=cycle_id,
                target_table="events",
                target_id=event_id,
                judgment_key="bid_formality",
                judgment_value="informal",
                judgment_status="accepted",
                rule_id="bid_formality_v1",
                reason_code=f"{event_subtype}_is_informal",
                basis={"event_subtype": event_subtype},
            )
        elif event_subtype == "final_round_bid":
            _insert_judgment(
                conn,
                sequence=sequence,
                run_id=run_id,
                deal_id=deal_id,
                cycle_id=cycle_id,
                target_table="events",
                target_id=event_id,
                judgment_key="bid_formality",
                judgment_value="formal",
                judgment_status="accepted",
                rule_id="bid_formality_v1",
                reason_code="final_round_bid_is_formal",
                basis={"event_subtype": event_subtype, "event_date": str(event_date)},
            )
        else:
            _insert_review_flag(
                conn,
                sequence=sequence,
                run_id=run_id,
                deal_slug=_deal_slug(conn, deal_id),
                flag_type="judgment_substrate_missing",
                severity="review",
                reason_code="formality_substrate_missing",
                reason=f"Cannot derive bid formality for event_subtype={event_subtype!r}.",
                canonical_table="events",
                canonical_id=event_id,
                recommended_review_question="Does the source support informal or formal bid treatment for this event?",
            )


def _derive_projected_fate(conn: duckdb.DuckDBPyConnection, run_id: str) -> None:
    rows = conn.execute(
        """
        SELECT events.event_id, events.deal_id, process_cycles.cycle_id,
               events.event_subtype
        FROM events
        JOIN process_cycles USING (cycle_id)
        WHERE events.run_id = ?
          AND events.event_subtype IN ('withdrawn_by_bidder', 'excluded_by_target', 'non_responsive', 'merger_agreement_executed')
        ORDER BY events.event_id
        """,
        [run_id],
    ).fetchall()
    start = _next_judgment_sequence(conn)
    for offset, (event_id, deal_id, cycle_id, event_subtype) in enumerate(rows, start=0):
        value = "signed_transaction" if event_subtype == "merger_agreement_executed" else "observed_drop"
        _insert_judgment(
            conn,
            sequence=start + offset,
            run_id=run_id,
            deal_id=deal_id,
            cycle_id=cycle_id,
            target_table="events",
            target_id=event_id,
            judgment_key="projected_fate",
            judgment_value=value,
            judgment_status="accepted",
            rule_id="projected_fate_v1",
            reason_code=f"{event_subtype}_fate",
            basis={"event_subtype": event_subtype},
        )


def _insert_judgment(
    conn: duckdb.DuckDBPyConnection,
    *,
    sequence: int,
    run_id: str,
    deal_id: str,
    cycle_id: str | None,
    target_table: str,
    target_id: str,
    judgment_key: str,
    judgment_value: str | None,
    judgment_status: str,
    rule_id: str,
    reason_code: str,
    basis: dict[str, object],
) -> None:
    deal_slug = _deal_slug(conn, deal_id)
    conn.execute(
        "INSERT INTO judgments VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            make_id(deal_slug, "judgment", sequence),
            run_id,
            deal_id,
            cycle_id,
            target_table,
            target_id,
            judgment_key,
            judgment_value,
            judgment_status,
            rule_id,
            reason_code,
            reason_code.replace("_", " "),
            json.dumps(basis, sort_keys=True),
            True,
            None,
        ],
    )


def _insert_review_flag(
    conn: duckdb.DuckDBPyConnection,
    *,
    sequence: int,
    run_id: str,
    deal_slug: str,
    flag_type: str,
    severity: str,
    reason_code: str,
    reason: str,
    canonical_table: str,
    canonical_id: str,
    recommended_review_question: str,
) -> None:
    conn.execute(
        "INSERT INTO review_flags VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            make_id(deal_slug, "reviewflag", sequence),
            run_id,
            deal_slug,
            None,
            None,
            None,
            None,
            None,
            canonical_table,
            canonical_id,
            flag_type,
            severity,
            reason_code,
            reason,
            None,
            None,
            None,
            recommended_review_question,
            True,
        ],
    )


def _deal_slug(conn: duckdb.DuckDBPyConnection, deal_id: str) -> str:
    row = conn.execute("SELECT deal_slug FROM deals WHERE deal_id = ?", [deal_id]).fetchone()
    if row is None:
        return deal_id.split("_", maxsplit=1)[0]
    return row[0]


def _next_judgment_sequence(conn: duckdb.DuckDBPyConnection) -> int:
    row = conn.execute("SELECT count(*) FROM judgments").fetchone()
    return int(row[0]) + 1
```

This first implementation should satisfy tests and establish the stage. Later tasks extend rules without changing the interface.

- [ ] **Step 4: Wire judgment stage into run command**

In `src/sec_graph/cli/run_cmd.py`, import:

```python
from sec_graph.judgments import derive_judgments
```

After `reconcile_all(conn, run_id=run_id)` and before validation:

```python
derive_judgments(conn, run_id=run_id)
for filing in filings:
    append_progress(
        run_dir,
        run_id=run_id,
        deal_slug=filing.deal_slug,
        stage="judgments",
        state="judgments_derived",
        attempt=1,
        recorded_at=clock.timestamp("judgments", sequence=1),
    )
```

- [ ] **Step 5: Run judgment tests**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 uv run pytest -q -p no:cacheprovider tests/test_derived_judgments.py
```

Expected: PASS.

- [ ] **Step 6: Commit**

Run:

```bash
git add src/sec_graph/judgments src/sec_graph/cli/run_cmd.py tests/test_derived_judgments.py
git commit -m "feat: derive judgments from canonical facts"
```

## Task 5: Advisor, Counsel, Agreement Kind, And Actor Role Rules

**Files:**
- Modify: `src/sec_graph/judgments/derive.py`
- Modify: `src/sec_graph/extract/llm/linkflow.py`
- Modify: `src/sec_graph/extract/llm/prompt.py`
- Modify: `tests/test_derived_judgments.py`
- Modify: `tests/test_llm_p8_contract.py`

- [ ] **Step 1: Write advisor judgment tests**

Add to `tests/test_derived_judgments.py`:

```python
def test_financial_advisor_relation_gets_process_role_judgment():
    conn = duckdb.connect(":memory:")
    init_schema(conn)
    _seed_advises_relation(conn, relation_id="deal_relation_1", subject_label="Evercore", object_label="Target")

    derive_judgments(conn, run_id="run-1")

    row = conn.execute(
        """
        SELECT judgment_key, judgment_value, judgment_status
        FROM judgments
        WHERE target_table = 'actor_relations'
        """
    ).fetchone()
    assert row == ("process_role", "financial_advisor", "accepted")


def test_advisor_confidentiality_is_not_bidder_nda():
    conn = duckdb.connect(":memory:")
    init_schema(conn)
    _seed_advises_relation(conn, relation_id="deal_relation_1", subject_label="Evercore", object_label="Target")

    derive_judgments(conn, run_id="run-1")

    values = {
        row[0]
        for row in conn.execute(
            "SELECT judgment_value FROM judgments WHERE judgment_key = 'agreement_kind'"
        ).fetchall()
    }
    assert "target_bidder_nda" not in values
```

Add this helper below the existing seed helpers in `tests/test_derived_judgments.py`:

```python
def _seed_advises_relation(
    conn: duckdb.DuckDBPyConnection,
    *,
    relation_id: str,
    subject_label: str,
    object_label: str,
) -> None:
    _seed_deal_cycle_actor(conn)
    conn.execute(
        "INSERT INTO actors VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ["deal_actor_3", "run-1", "deal_deal_1", subject_label, "organization", "named", None, None, None, None],
    )
    conn.execute(
        "INSERT INTO actor_relations VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            relation_id,
            "run-1",
            "deal_deal_1",
            "deal_actor_3",
            "deal_actor_1",
            "advises",
            None,
            "deal_cycle_1",
            None,
            "2024-01-01",
            None,
            "high",
        ],
    )
```

- [ ] **Step 2: Run and verify failure**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 uv run pytest -q -p no:cacheprovider tests/test_derived_judgments.py
```

Expected: FAIL because advisor rules are not implemented.

- [ ] **Step 3: Ensure advisor obligations can produce `advises` relations**

In `src/sec_graph/extract/llm/linkflow.py`, ensure the obligation-to-relation mapping includes:

```python
"Financial advisor for target": ["advises"],
"Legal advisor for target": ["advises"],
```

Keep the P8 response shape unchanged. This only constrains allowed relation enum values for an existing claim family.

- [ ] **Step 4: Keep prompt source-facing**

In `src/sec_graph/extract/llm/prompt.py`, ensure advisor instructions say:

```text
Financial advisor for target: emit an advises relation from the advisor to the target, company, board, or committee named in the quote. Do not emit bidder advisors for this obligation.
Legal advisor for target: emit an advises relation from counsel to the target, company, board, or committee named in the quote. Do not treat counsel as a bidder.
```

- [ ] **Step 5: Add advisor judgments**

Extend `src/sec_graph/judgments/derive.py` with `_derive_actor_relation_roles()`:

```python
def _derive_actor_relation_roles(conn: duckdb.DuckDBPyConnection, run_id: str) -> None:
    rows = conn.execute(
        """
        SELECT actor_relations.relation_id, actor_relations.deal_id,
               process_cycles.cycle_id, actor_relations.relation_type,
               actors.actor_label
        FROM actor_relations
        JOIN process_cycles USING (cycle_id)
        JOIN actors ON actors.actor_id = actor_relations.subject_actor_id
        WHERE actor_relations.run_id = ?
          AND actor_relations.relation_type = 'advises'
        ORDER BY actor_relations.relation_id
        """,
        [run_id],
    ).fetchall()
    start = _next_judgment_sequence(conn)
    for offset, (relation_id, deal_id, cycle_id, relation_type, subject_label) in enumerate(rows):
        lowered = str(subject_label).casefold()
        value = "legal_advisor" if any(term in lowered for term in ("llp", "law", "counsel")) else "financial_advisor"
        _insert_judgment(
            conn,
            sequence=start + offset,
            run_id=run_id,
            deal_id=deal_id,
            cycle_id=cycle_id,
            target_table="actor_relations",
            target_id=relation_id,
            judgment_key="process_role",
            judgment_value=value,
            judgment_status="accepted",
            rule_id="advisor_role_v1",
            reason_code=f"{value}_from_advises_relation",
            basis={"relation_type": relation_type, "subject_label": subject_label},
        )
```

Call it from `derive_judgments()`.

- [ ] **Step 6: Run advisor and contract tests**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 uv run pytest -q -p no:cacheprovider \
  tests/test_derived_judgments.py \
  tests/test_llm_p8_contract.py
```

Expected: PASS and no provider scalar fields are allowed.

- [ ] **Step 7: Commit**

Run:

```bash
git add src/sec_graph/judgments/derive.py src/sec_graph/extract/llm/linkflow.py src/sec_graph/extract/llm/prompt.py tests/test_derived_judgments.py tests/test_llm_p8_contract.py
git commit -m "feat: derive advisor roles from graph relations"
```

## Task 6: Review Flags, Verdicts, And Proof Exports

**Files:**
- Modify: `src/sec_graph/project/summaries.py`
- Modify: `src/sec_graph/validate/integrity.py`
- Modify: `src/sec_graph/validate/flags.py`
- Create: `tests/test_review_flags_and_verdicts.py`

- [ ] **Step 1: Write failing verdict tests**

Create `tests/test_review_flags_and_verdicts.py`:

```python
import duckdb

from sec_graph.project.summaries import proof_summary
from sec_graph.schema import init_schema


def test_review_flag_changes_verdict_to_review_required(tmp_path):
    conn = duckdb.connect(":memory:")
    init_schema(conn)
    _seed_valid_minimal_run(conn)
    conn.execute(
        "INSERT INTO review_flags VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            "deal_reviewflag_1",
            "run-1",
            "deal",
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            "missed_supported_obligation",
            "review",
            "test_review",
            "review needed",
            None,
            None,
            None,
            "Review the missed supported obligation.",
            True,
        ],
    )

    proof = proof_summary(conn, run_id="run-1", projection_name="bidder_cycle_v1")

    assert proof["verdict"] == "REVIEW_REQUIRED"
    assert proof["review_flag_count"] == 1
    assert proof["blocking_flag_count"] == 0


def test_blocking_flag_changes_verdict_to_unsound(tmp_path):
    conn = duckdb.connect(":memory:")
    init_schema(conn)
    _seed_valid_minimal_run(conn)
    conn.execute(
        "INSERT INTO review_flags VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            "deal_reviewflag_1",
            "run-1",
            "deal",
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            "unsupported_claim",
            "blocking",
            "test_blocking",
            "blocking issue",
            None,
            None,
            None,
            "Review the unsupported claim.",
            True,
        ],
    )

    proof = proof_summary(conn, run_id="run-1", projection_name="bidder_cycle_v1")

    assert proof["verdict"] == "UNSOUND"
    assert proof["blocking_flag_count"] == 1
```

Add `_seed_valid_minimal_run()` at the bottom:

```python
def _seed_valid_minimal_run(conn: duckdb.DuckDBPyConnection) -> None:
    conn.execute(
        "INSERT INTO deals VALUES (?, ?, ?, ?, ?)",
        ["deal_deal_1", "run-1", "deal", "deal_actor_1", "2024-01-01"],
    )
    conn.execute(
        "INSERT INTO actors VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ["deal_actor_1", "run-1", "deal_deal_1", "Target", "organization", "named", None, None, None, None],
    )
    conn.execute(
        "INSERT INTO process_cycles VALUES (?, ?, ?, ?, ?, ?, ?)",
        ["deal_cycle_1", "run-1", "deal_deal_1", 1, "primary sale process", "2024-01-01", "2024-01-02"],
    )
```

- [ ] **Step 2: Run and verify failure**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 uv run pytest -q -p no:cacheprovider tests/test_review_flags_and_verdicts.py
```

Expected: FAIL because proof summaries do not include `REVIEW_REQUIRED` semantics or review flag counts.

- [ ] **Step 3: Export `judgments` and `review_flags`**

In `src/sec_graph/project/summaries.py`, add CSV exports for:

```text
judgments.csv
review_flags.csv
```

Use explicit column lists. For `review_flags.csv`, include:

```python
[
    "deal_slug",
    "flag_type",
    "severity",
    "reason_code",
    "claim_id",
    "judgment_id",
    "canonical_table",
    "canonical_id",
    "recommended_review_question",
]
```

- [ ] **Step 4: Add verdict computation**

In `src/sec_graph/project/summaries.py`, update proof summary construction:

```python
def _proof_verdict(conn: duckdb.DuckDBPyConnection, *, validation_passed: bool) -> str:
    blocking_count = _count_query(
        conn,
        "SELECT count(*) FROM review_flags WHERE current = true AND severity = 'blocking'",
    )
    review_count = _count_query(
        conn,
        "SELECT count(*) FROM review_flags WHERE current = true AND severity = 'review'",
    )
    if not validation_passed or blocking_count:
        return "UNSOUND"
    if review_count:
        return "REVIEW_REQUIRED"
    return "SOUND"
```

Also add:

```python
"review_flag_count": _count_query(conn, "SELECT count(*) FROM review_flags WHERE current = true AND severity = 'review'"),
"blocking_flag_count": _count_query(conn, "SELECT count(*) FROM review_flags WHERE current = true AND severity = 'blocking'"),
"judgment_counts": _group_count(conn, "judgments", "judgment_status"),
```

- [ ] **Step 5: Remove stale `soft_flags()` query**

In `src/sec_graph/validate/flags.py`, replace any query against nonexistent `judgments.projection_name`, `actor_id`, or `included` columns with a simple read of current review flags:

```python
def soft_flags(conn):
    return conn.execute(
        """
        SELECT flag_id, flag_type, severity, reason_code, reason
        FROM review_flags
        WHERE current = true
          AND severity IN ('review', 'info')
        ORDER BY flag_id
        """
    ).fetchall()
```

- [ ] **Step 6: Run proof tests**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 uv run pytest -q -p no:cacheprovider tests/test_review_flags_and_verdicts.py
```

Expected: PASS.

- [ ] **Step 7: Run projection and validation tests**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 uv run pytest -q -p no:cacheprovider \
  tests/test_validation_semantics.py \
  tests/test_run_failed_validation_proof.py \
  tests/test_hard_reset_schema.py
```

Expected: PASS.

- [ ] **Step 8: Commit**

Run:

```bash
git add src/sec_graph/project/summaries.py src/sec_graph/validate/integrity.py src/sec_graph/validate/flags.py tests/test_review_flags_and_verdicts.py tests/test_validation_semantics.py tests/test_run_failed_validation_proof.py tests/test_hard_reset_schema.py
git commit -m "feat: export review verdict proof"
```

## Task 7: Projection Consumes Judgments, Not Workbook Labels

**Files:**
- Modify: `src/sec_graph/project/bidder_rows.py`
- Modify: `tests/test_hard_reset_schema.py`
- Modify: `tests/test_validation_semantics.py`

- [ ] **Step 1: Write failing projection test**

Add to `tests/test_validation_semantics.py`:

```python
def test_projection_requires_accepted_judgment_for_dropout_label(tmp_path):
    conn, _source_path = _semantic_db(
        tmp_path,
        bid_quote="On January 2, 2024, Party A submitted a proposal of $10.00 per share.",
        relation_quote="Party A withdrew from the process.",
    )
    conn.execute(
        "INSERT INTO review_flags VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            "semantics-deal_reviewflag_1",
            RUN_ID,
            "semantics-deal",
            None,
            None,
            None,
            None,
            None,
            "events",
            "semantics-deal_event_1",
            "judgment_substrate_missing",
            "review",
            "missing_projected_fate",
            "Projected fate cannot be derived.",
            None,
            None,
            None,
            "Review projected fate for this bidder-cycle row.",
            True,
        ],
    )

    result = validate_database(conn)

    assert any(
        failure.detail.startswith("projection depends on review-required judgment")
        for failure in result.hard_failures
    )
```

- [ ] **Step 2: Run and verify failure**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 uv run pytest -q -p no:cacheprovider tests/test_validation_semantics.py::test_projection_requires_accepted_judgment_for_dropout_label
```

Expected: FAIL because projection validation does not inspect judgment flags yet.

- [ ] **Step 3: Update projection code**

In `src/sec_graph/project/bidder_rows.py`, read accepted judgments for each projection unit:

```sql
SELECT target_id, judgment_key, judgment_value
FROM judgments
WHERE run_id = ?
  AND current = true
  AND judgment_status = 'accepted'
```

Use those values for downstream projection fields. Do not read workbook dropout labels or old `DropTarget` / `DropBelowInf` variants.

- [ ] **Step 4: Update validation**

In `src/sec_graph/validate/integrity.py`, add a projection/judgment check:

```sql
SELECT review_flags.flag_id
FROM review_flags
WHERE review_flags.current = true
  AND review_flags.flag_type IN ('judgment_substrate_missing', 'judgment_conflict', 'projection_trace_failure')
  AND review_flags.severity IN ('blocking', 'review')
```

Return `HardCheck.PROJECTION_UNIT` failures with:

```text
projection depends on review-required judgment
```

- [ ] **Step 5: Run tests**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 uv run pytest -q -p no:cacheprovider \
  tests/test_validation_semantics.py \
  tests/test_hard_reset_schema.py
```

Expected: PASS.

- [ ] **Step 6: Commit**

Run:

```bash
git add src/sec_graph/project/bidder_rows.py src/sec_graph/validate/integrity.py tests/test_validation_semantics.py tests/test_hard_reset_schema.py
git commit -m "feat: project from accepted judgments"
```

## Task 8: Reference-9 Proof Matrix

**Files:**
- Create: `scripts/reference9_matrix.py`
- Modify: `quality_reports/session_logs/README.md`
- Test: manual command output

- [ ] **Step 1: Create matrix script**

Create `scripts/reference9_matrix.py`:

```python
from __future__ import annotations

import argparse
import json
from pathlib import Path

REFERENCE9 = (
    "providence-worcester",
    "medivation",
    "imprivata",
    "zep",
    "petsmart-inc",
    "penford",
    "mac-gray",
    "saks",
    "stec",
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs-dir", default="runs")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    runs_dir = Path(args.runs_dir)
    rows = []
    for slug in REFERENCE9:
        run_dir = _latest_run_dir(runs_dir, slug)
        rows.append(_row_for_slug(slug, run_dir))
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps({"reference9": rows}, indent=2), encoding="utf-8")
    print(f"wrote {output}")
    return 0


def _latest_run_dir(runs_dir: Path, slug: str) -> Path | None:
    candidates = sorted(path for path in runs_dir.glob(f"*{slug}*") if path.is_dir())
    return candidates[-1] if candidates else None


def _row_for_slug(slug: str, run_dir: Path | None) -> dict[str, object]:
    if run_dir is None:
        return {
            "deal_slug": slug,
            "run_dir": None,
            "provider_completed": False,
            "quote_binding_passed": False,
            "claim_dispositions_complete": False,
            "unsupported_claims_rejected": False,
            "coverage_complete_or_reviewed": False,
            "judgments_complete_or_reviewed": False,
            "projection_trace_passed": False,
            "verdict": "MISSING_RUN",
            "review_flag_count": None,
            "blocking_flag_count": None,
        }
    proof = _read_json(run_dir / "proof_summary.json")
    validation = _read_json(run_dir / "validation_report.json")
    failed = _read_json(run_dir / "failed_validation_proof.json")
    source = proof or failed or {}
    return {
        "deal_slug": slug,
        "run_dir": run_dir.as_posix(),
        "provider_completed": bool(source),
        "quote_binding_passed": not _has_failure(validation, "claim_evidence"),
        "claim_dispositions_complete": not _has_failure(validation, "claim_disposition"),
        "unsupported_claims_rejected": not _has_failure(validation, "semantic_claim_evidence"),
        "coverage_complete_or_reviewed": not _has_failure(validation, "coverage_result"),
        "judgments_complete_or_reviewed": True,
        "projection_trace_passed": not _has_failure(validation, "projection_unit"),
        "verdict": source.get("verdict") or ("SOUND" if validation.get("passed") else "UNSOUND"),
        "review_flag_count": source.get("review_flag_count"),
        "blocking_flag_count": source.get("blocking_flag_count"),
    }


def _read_json(path: Path) -> dict[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    if not isinstance(payload, dict):
        return {}
    return payload


def _has_failure(validation: dict[str, object], check: str) -> bool:
    failures = validation.get("hard_failures")
    if not isinstance(failures, list):
        return False
    for failure in failures:
        if isinstance(failure, dict) and failure.get("check") == check:
            return True
    return False


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: Run matrix script**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 uv run python scripts/reference9_matrix.py \
  --runs-dir runs \
  --output quality_reports/session_logs/reference9_latest_matrix.json
```

Expected:

```text
wrote quality_reports/session_logs/reference9_latest_matrix.json
```

- [ ] **Step 3: Inspect output**

Run:

```bash
python -m json.tool quality_reports/session_logs/reference9_latest_matrix.json | sed -n '1,120p'
```

Expected: JSON with nine `reference9` rows and per-deal verdict fields.

- [ ] **Step 4: Update session log README**

Add a short entry to `quality_reports/session_logs/README.md`:

```markdown
## Reference-9 Matrix

`scripts/reference9_matrix.py` summarizes latest per-deal Reference-9 run
directories into `quality_reports/session_logs/reference9_latest_matrix.json`.
It reads proof artifacts only; it does not run Linkflow and does not repair
deals.
```

- [ ] **Step 5: Commit**

Run:

```bash
git add scripts/reference9_matrix.py quality_reports/session_logs/README.md quality_reports/session_logs/reference9_latest_matrix.json
git commit -m "feat: add Reference-9 proof matrix"
```

## Task 9: Stale Plan Cleanup

**Files:**
- Move: `docs/superpowers/specs/2026-05-04-reference9-correctness-repair-design.md`
- Move: `quality_reports/plans/2026-05-04_p8_region_applicability_ref9_plan.md`
- Move: `quality_reports/plans/2026-05-04_reference9_correctness_repair_plan.md`
- Delete: listed obsolete P7/high probe debris

- [ ] **Step 1: Create legacy spec directory**

Run:

```bash
mkdir -p docs/superpowers/specs/legacy quality_reports/plans/legacy quality_reports/session_logs/legacy
```

Expected: command exits 0.

- [ ] **Step 2: Move useful superseded design and plans**

Run:

```bash
git mv docs/superpowers/specs/2026-05-04-reference9-correctness-repair-design.md docs/superpowers/specs/legacy/2026-05-04-reference9-correctness-repair-design.md
git mv quality_reports/plans/2026-05-04_p8_region_applicability_ref9_plan.md quality_reports/plans/legacy/2026-05-04_p8_region_applicability_ref9_plan.md
git mv quality_reports/plans/2026-05-04_reference9_correctness_repair_plan.md quality_reports/plans/legacy/2026-05-04_reference9_correctness_repair_plan.md
```

Expected: files are staged as renames.

- [ ] **Step 3: Move point-in-time session logs to legacy**

Run:

```bash
for path in quality_reports/session_logs/2026-05-02_*.md quality_reports/session_logs/2026-05-03_*.md quality_reports/session_logs/2026-05-04_*.md; do
  git mv "$path" quality_reports/session_logs/legacy/
done
```

Expected: session logs move under `quality_reports/session_logs/legacy/`. Keep `quality_reports/session_logs/README.md` active.

- [ ] **Step 4: Hard-delete obsolete P7/high debris**

Run:

```bash
git rm -r \
  quality_reports/plans/legacy/2026-05-03_full-redesign-plan.md \
  quality_reports/plans/legacy/2026-05-03_linkflow-p7-background-high-implementation-plan.md \
  quality_reports/llm_calibration/legacy/2026-05-03T175805Z_linkflow-p7-matrix_c7a97707aa798218c1bb6ab6204002f87f0955bc6ba14f4fee4864894795f35c \
  quality_reports/llm_calibration/legacy/2026-05-03_linkflow-probe-log.md \
  quality_reports/llm_calibration/legacy/REVIEWER_GUIDE.md \
  quality_reports/llm_calibration/legacy/macgray_agentic_scan_result.txt \
  quality_reports/llm_calibration/legacy/probe_lf_macgray.py \
  quality_reports/llm_calibration/legacy/probe_lf_macgray_background.py \
  quality_reports/llm_calibration/legacy/probe_lf_matrix.py \
  quality_reports/llm_calibration/legacy/probe_lf_scale.py
```

Expected: obsolete files are staged as deletions. If a path is already absent, remove that path from the command and rerun. Do not delete semantic-review ledgers or `data/filings/`.

- [ ] **Step 5: Update active authority references**

In `docs/spec.md`, replace the opening authority sentence:

```markdown
**Execution authority:** `docs/superpowers/specs/2026-05-03-pipeline-hard-reset-design.md`.
```

with:

```markdown
**Execution authority:** `docs/superpowers/specs/2026-05-03-pipeline-hard-reset-design.md`.
**Middle-pipeline authority:** `docs/superpowers/specs/2026-05-05-semantic-disposition-validity-design.md`.
```

In `docs/llm-interface.md`, add this sentence after the status paragraph:

```markdown
The post-response support-disposition, derived-judgment, review-flag, and
verdict contract is governed by
`docs/superpowers/specs/2026-05-05-semantic-disposition-validity-design.md`.
```

Do not change the P8 provider response shape while making these documentation edits.

- [ ] **Step 6: Run freshness guard**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 uv run pytest -q -p no:cacheprovider tests/test_repo_freshness_contract.py
```

Expected: PASS after updating stale-wording guards if they intentionally reference the new authority chain.

- [ ] **Step 7: Commit**

Run:

```bash
git add docs/spec.md docs/llm-interface.md docs/superpowers/specs quality_reports/plans quality_reports/session_logs quality_reports/llm_calibration tests/test_repo_freshness_contract.py
git commit -m "docs: clean stale semantic extraction plans"
```

## Task 10: Full Local Verification

**Files:**
- Read only

- [ ] **Step 1: Run focused suite**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 uv run pytest -q -p no:cacheprovider \
  tests/test_claim_disposition_gate.py \
  tests/test_coverage_semantics.py \
  tests/test_derived_judgments.py \
  tests/test_review_flags_and_verdicts.py \
  tests/test_validation_semantics.py \
  tests/test_hard_reset_schema.py \
  tests/test_llm_p8_contract.py \
  tests/test_run_failed_validation_proof.py \
  tests/test_repo_freshness_contract.py
```

Expected: PASS.

- [ ] **Step 2: Run full suite**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 uv run pytest -q -p no:cacheprovider
```

Expected: PASS. If failures are unrelated to this refactor, document exact failures before deciding whether to fix them.

- [ ] **Step 3: Confirm no secrets or generated source pollution**

Run:

```bash
git status --short
rg -n "sk-[A-Za-z0-9]" .
find . -path './data/filings' -prune -o -path './runs' -prune -o -path './artifacts' -prune -o -path './tmp' -prune -o -name '*.pyc' -print
```

Expected:

- no API keys printed;
- no `.pyc` files under tracked source paths;
- only intentional tracked changes remain.

## Task 11: Live Reference-9 Verification

**Files:**
- Generated ignored runs under `runs/`
- Matrix artifact under `quality_reports/session_logs/reference9_latest_matrix.json`

- [ ] **Step 1: Confirm API key is environment-only**

Run:

```bash
test -n "${LINKFLOW_API_KEY:-}" && echo "LINKFLOW_API_KEY is set"
```

Expected:

```text
LINKFLOW_API_KEY is set
```

Do not print the key.

- [ ] **Step 2: Run Reference-9 deals separately**

Run each deal as a separate command. Use parallel shells or subagents where possible:

```bash
PYTHONDONTWRITEBYTECODE=1 uv run python -m sec_graph run --source filings --slugs providence-worcester --run-id 2026-05-05T000000Z_semantic-disposition-providence-worcester --run-dir runs/2026-05-05T000000Z_semantic-disposition-providence-worcester --llm-provider linkflow --llm-model gpt-5.5 --llm-reasoning-effort medium
PYTHONDONTWRITEBYTECODE=1 uv run python -m sec_graph run --source filings --slugs medivation --run-id 2026-05-05T000000Z_semantic-disposition-medivation --run-dir runs/2026-05-05T000000Z_semantic-disposition-medivation --llm-provider linkflow --llm-model gpt-5.5 --llm-reasoning-effort medium
PYTHONDONTWRITEBYTECODE=1 uv run python -m sec_graph run --source filings --slugs imprivata --run-id 2026-05-05T000000Z_semantic-disposition-imprivata --run-dir runs/2026-05-05T000000Z_semantic-disposition-imprivata --llm-provider linkflow --llm-model gpt-5.5 --llm-reasoning-effort medium
PYTHONDONTWRITEBYTECODE=1 uv run python -m sec_graph run --source filings --slugs zep --run-id 2026-05-05T000000Z_semantic-disposition-zep --run-dir runs/2026-05-05T000000Z_semantic-disposition-zep --llm-provider linkflow --llm-model gpt-5.5 --llm-reasoning-effort medium
PYTHONDONTWRITEBYTECODE=1 uv run python -m sec_graph run --source filings --slugs petsmart-inc --run-id 2026-05-05T000000Z_semantic-disposition-petsmart-inc --run-dir runs/2026-05-05T000000Z_semantic-disposition-petsmart-inc --llm-provider linkflow --llm-model gpt-5.5 --llm-reasoning-effort medium
PYTHONDONTWRITEBYTECODE=1 uv run python -m sec_graph run --source filings --slugs penford --run-id 2026-05-05T000000Z_semantic-disposition-penford --run-dir runs/2026-05-05T000000Z_semantic-disposition-penford --llm-provider linkflow --llm-model gpt-5.5 --llm-reasoning-effort medium
PYTHONDONTWRITEBYTECODE=1 uv run python -m sec_graph run --source filings --slugs mac-gray --run-id 2026-05-05T000000Z_semantic-disposition-mac-gray --run-dir runs/2026-05-05T000000Z_semantic-disposition-mac-gray --llm-provider linkflow --llm-model gpt-5.5 --llm-reasoning-effort medium
PYTHONDONTWRITEBYTECODE=1 uv run python -m sec_graph run --source filings --slugs saks --run-id 2026-05-05T000000Z_semantic-disposition-saks --run-dir runs/2026-05-05T000000Z_semantic-disposition-saks --llm-provider linkflow --llm-model gpt-5.5 --llm-reasoning-effort medium
PYTHONDONTWRITEBYTECODE=1 uv run python -m sec_graph run --source filings --slugs stec --run-id 2026-05-05T000000Z_semantic-disposition-stec --run-dir runs/2026-05-05T000000Z_semantic-disposition-stec --llm-provider linkflow --llm-model gpt-5.5 --llm-reasoning-effort medium
```

Expected: each command exits with `SOUND`, `REVIEW_REQUIRED`, or a clear `UNSOUND` / validation failure artifact. `REVIEW_REQUIRED` is acceptable when the canonical graph is valid and review flags explain misses or ambiguity.

- [ ] **Step 3: Build matrix**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 uv run python scripts/reference9_matrix.py \
  --runs-dir runs \
  --output quality_reports/session_logs/reference9_latest_matrix.json
```

Expected:

```text
wrote quality_reports/session_logs/reference9_latest_matrix.json
```

- [ ] **Step 4: Inspect matrix**

Run:

```bash
python -m json.tool quality_reports/session_logs/reference9_latest_matrix.json | sed -n '1,220p'
```

Expected:

- nine deals present;
- no deal has unsupported canonical facts;
- `REVIEW_REQUIRED` rows have review flag counts and source-facing reasons;
- failures are truthful, not masked.

- [ ] **Step 5: Commit matrix if useful**

Only commit the matrix if it is concise and useful as proof. Do not commit generated run directories.

Run:

```bash
git add quality_reports/session_logs/reference9_latest_matrix.json
git commit -m "test: record Reference-9 semantic disposition matrix"
```

## Task 12: Final Handoff Checks

**Files:**
- Read only

- [ ] **Step 1: Inspect final git history**

Run:

```bash
git log --oneline -12
git status --short --branch
```

Expected: implementation commits are visible, worktree has no untracked or unstaged task files except intentionally ignored `runs/`.

- [ ] **Step 2: Summarize residual risk**

Write a concise implementation summary for the user with:

- what changed;
- tests run;
- live Reference-9 verdict matrix summary;
- whether any deals are `REVIEW_REQUIRED`;
- whether any deals are `UNSOUND`;
- exact next repair scope if review flags remain.

- [ ] **Step 3: Stop**

Do not start out-of-pipeline deal repair in this run. The pipeline must stop at review-ready flags.
