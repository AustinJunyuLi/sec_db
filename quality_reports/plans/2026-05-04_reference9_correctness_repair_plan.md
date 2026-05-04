# Reference-9 Correctness Repair Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the Reference-9 offline gate source-truthful, auditable, and hard to fool before relying on any live P8 proof.

**Architecture:** Keep the P8 Linkflow provider contract frozen and repair Python-owned source windows, applicability, proof links, validation, and proof metadata. The main change is to separate "this topic appears" from "the filing supports the positive fact", then persist claim-to-obligation proof so coverage can be audited from DuckDB.

**Tech Stack:** Python 3, DuckDB, Pydantic models, pytest, local `data/filings/` Reference-9 raw markdown, Linkflow only for optional live proof.

---

## Required Context

Read these first:

- `AGENTS.md`
- `docs/superpowers/specs/2026-05-03-pipeline-hard-reset-design.md`
- `docs/superpowers/specs/2026-05-04-reference9-correctness-repair-design.md`
- `docs/spec.md`
- `docs/llm-interface.md`
- `quality_reports/plans/2026-05-04_p8_region_applicability_ref9_plan.md`

Rules:

- No fallbacks.
- No backward compatibility.
- Do not widen the provider payload.
- Do not commit secrets.
- Do not delete `data/filings/`.
- The bounded local-agent fact-check suite reads only the nine Reference-9 deals, not the 400-deal corpus.

Reference-9 slugs:

```text
providence-worcester
medivation
imprivata
zep
petsmart-inc
penford
mac-gray
saks
stec
```

## File Structure

Create:

- `tests/fixtures/reference9_fact_ledger.json`
  - Compact source-truth ledger for the nine Reference-9 deals.
- `src/sec_graph/extract/source_support.py`
  - Source-text support classifier shared by applicability and coverage classification.
- `tests/test_source_support_semantics.py`
  - Positive/negative support tests for fragile obligations.
- `tests/test_run_failed_validation_proof.py`
  - CLI-level proof metadata test for validation-failing runs.
- `quality_reports/session_logs/2026-05-04_reference9-correctness-fact-check.md`
  - Human-readable bounded local-agent fact-check summary.

Modify:

- `src/sec_graph/extract/applicability.py`
  - Use source-support classification instead of broad trigger-only matching for fragile conditional obligations.
- `src/sec_graph/extract/evidence_map.py`
  - Build contiguous sale-process regions and reject non-substantive candidates.
- `src/sec_graph/extract/llm/convert.py`
  - Insert persisted claim-to-obligation links and derive coverage counts from them.
- `src/sec_graph/ingest/pipeline.py`
  - Fail loudly when SC TO-T manifests do not select `EX-99.(A)(1)(A)`.
- `src/sec_graph/schema/models/extraction.py`
  - Add `ClaimCoverageLink` model and `claim_coverage_links` DDL.
- `src/sec_graph/schema/models/__init__.py`
  - Export `ClaimCoverageLink`.
- `src/sec_graph/schema/__init__.py`
  - Export `ClaimCoverageLink`.
- `src/sec_graph/validate/integrity.py`
  - Add coverage-link and not-applicable coverage-result checks.
- `src/sec_graph/project/summaries.py`
  - Filter current rows or expose current/history fields; include coverage-link audit output.
- `src/sec_graph/cli/run_cmd.py`
  - Record resolved commit and write failed-validation proof metadata before aborting.
- `tests/test_reference9_offline_regions.py`
  - Check the new source-truth ledger and rejected region candidates.
- `tests/test_applicability_obligations.py`
  - Add false-positive applicability tests.
- `tests/test_coverage_semantics.py`
  - Add persisted coverage-link tests.
- `tests/test_validation_semantics.py`
  - Add validation hard-failure tests.
- `tests/test_hard_reset_schema.py`
  - Update schema/table expectations and contiguous region expectations.
- `tests/test_repo_freshness_contract.py`
  - Add stale wording guards for active docs/plans.
- `quality_reports/plans/2026-05-04_p8_region_applicability_ref9_plan.md`
  - Correct active-plan wording from "current obligations" to "current applicable obligations" where needed.
- `quality_reports/session_logs/README.md`
  - Fix stale authority references.
- `quality_reports/session_logs/2026-05-04_p8-region-applicability-phase-3-6.md`
  - Clarify what artifacts failed-validation live runs actually produced.

## Task 1: Preflight And Bounded Local-Agent Fact Check

**Files:**
- Create: `quality_reports/session_logs/2026-05-04_reference9-correctness-fact-check.md`
- Read: `data/filings/*/raw.md` only for the nine Reference-9 slugs
- Read: `tests/fixtures/reference9_applicability_expectations.json`
- Read: `tests/fixtures/reference9_region_expectations.json`

- [ ] **Step 1: Confirm clean target state**

Run:

```bash
git status --short --branch
git log -5 --oneline --decorate
```

Expected:

```text
## main...origin/main [ahead 4]
b07c0cb ... docs: design Reference-9 correctness repair
```

If local state differs, record it in the session log before editing.

- [ ] **Step 2: Confirm Reference-9 local filing availability**

Run:

```bash
python - <<'PY'
from pathlib import Path
slugs = [
    "providence-worcester", "medivation", "imprivata", "zep",
    "petsmart-inc", "penford", "mac-gray", "saks", "stec",
]
missing = [
    slug for slug in slugs
    if not (Path("data/filings") / slug / "raw.md").exists()
]
if missing:
    raise SystemExit(f"missing Reference-9 filings: {missing}")
print("Reference-9 filings present")
PY
```

Expected:

```text
Reference-9 filings present
```

- [ ] **Step 3: Dispatch read-only local-agent fact-check lanes**

Use separate read-only agents. Do not ask them to read the 400-deal corpus.

Agent prompt for raw fact ledger:

```text
Read-only fact check for /Users/austinli/Projects/sec_graph.
Scope: only the nine Reference-9 deals under data/filings/.
Do not edit files, do not run live providers, do not inspect any 400-deal corpus.

Read tests/fixtures/reference9_applicability_expectations.json and
tests/fixtures/reference9_region_expectations.json. Then inspect raw.md for:
providence-worcester, medivation, imprivata, zep, petsmart-inc, penford,
mac-gray, saks, stec.

Return a compact ledger with:
- selected substantive sale-process regions;
- cross-reference-only or heading-only sale-process candidates;
- positive source facts for fragile obligations;
- negative source facts for fragile obligations;
- exact file:line references or short snippets.

Focus especially on Penford exclusivity/recusal, Zep committee, Saks recusal,
and Medivation Past Contacts.
```

Agent prompt for applicability false positives:

```text
Read-only applicability false-positive review for /Users/austinli/Projects/sec_graph.
Scope: only Reference-9 raw.md files and current applicability fixtures.
Do not edit files and do not inspect any 400-deal corpus.

For each conditional obligation in src/sec_graph/extract/applicability.py, check
whether current trigger patterns can fire on negated, declined, hypothetical,
requested-only, or unrelated text in Reference-9.

Return actionable findings with file:line references. Focus on exclusivity,
committee, recusal, voting support, rollover, buyer group, and financing.
```

Agent prompt for region substance:

```text
Read-only region substance review for /Users/austinli/Projects/sec_graph.
Scope: only Reference-9 raw.md files and current region fixtures.
Do not edit files and do not inspect any 400-deal corpus.

Classify every selected sale-process region as substantive narrative,
cross-reference-only, heading-only, duplicated/non-contiguous, or ambiguous.
Return file:line evidence and any fixture rows that should change.
```

Agent prompt for coverage/audit schema:

```text
Read-only coverage/audit schema review for /Users/austinli/Projects/sec_graph.
Do not edit files and do not run live providers.

Review whether coverage_results can be audited from DuckDB back to exact claims,
quotes, and source spans. Focus on src/sec_graph/schema/models/extraction.py,
src/sec_graph/extract/llm/convert.py, src/sec_graph/validate/integrity.py, and
src/sec_graph/project/summaries.py.

Return required schema or validation changes with file:line references.
```

Agent prompt for proof/docs:

```text
Read-only proof/docs review for /Users/austinli/Projects/sec_graph.
Do not edit files and do not run live providers.

Review active docs, plans, and session logs for stale claims after the
Reference-9 correctness repair design. Check whether failed-validation live runs
have enough committed metadata to reproduce and audit the failure.

Return actionable doc/proof fixes with file:line references.
```

- [ ] **Step 4: Write the fact-check summary log**

Create `quality_reports/session_logs/2026-05-04_reference9-correctness-fact-check.md` with this structure:

```markdown
# Session Log: Reference-9 Correctness Fact Check

**Date:** 2026-05-04
**Scope:** Bounded local-agent fact-check suite over the nine Reference-9 deals only.

## Boundary

This fact check read only the nine Reference-9 local filings under `data/filings/`.
It did not inspect or characterize any 400-deal corpus.

## Confirmed False Positives

| Deal | Current expectation | Source truth | Evidence |
|---|---|---|---|

## Region Substance Findings

| Deal | Candidate section | Classification | Evidence |
|---|---|---|---|

## Coverage/Audit Findings

## Proof/Docs Findings

## Implementation Consequences
```

Fill the tables from the local-agent findings.

- [ ] **Step 5: Commit the fact-check log**

Run:

```bash
git add quality_reports/session_logs/2026-05-04_reference9-correctness-fact-check.md
git commit -m "docs: record Reference-9 correctness fact check"
```

Expected:

```text
git prints a one-line commit summary for "docs: record Reference-9 correctness fact check"
```

## Task 2: Source-Truth Fixture And Red Tests

**Files:**
- Create: `tests/fixtures/reference9_fact_ledger.json`
- Modify: `tests/test_reference9_offline_regions.py`
- Modify: `tests/test_applicability_obligations.py`

- [ ] **Step 1: Add a compact source-truth fixture**

Create `tests/fixtures/reference9_fact_ledger.json`:

```json
{
  "schema_version": "2026-05-04",
  "description": "Compact source-truth ledger for the bounded Reference-9 correctness gate. Snippets are short and local to the expected fact; full filings remain under data/filings/.",
  "deals": {
    "penford": {
      "negative_facts": [
        {
          "kind": "exclusivity_grant",
          "snippet_must_contain": "not justified",
          "expected_applicability": "not_applicable",
          "reason_code": "negative_or_requested_only"
        },
        {
          "kind": "exclusivity_grant",
          "snippet_must_contain": "declined",
          "expected_applicability": "not_applicable",
          "reason_code": "negative_or_requested_only"
        },
        {
          "kind": "recusal",
          "snippet_must_contain": "disclaimed",
          "expected_applicability": "not_applicable",
          "reason_code": "conditional_or_disclaimed"
        }
      ]
    },
    "zep": {
      "negative_facts": [
        {
          "kind": "special_committee",
          "snippet_must_contain": "not to form a transaction committee",
          "expected_applicability": "not_applicable",
          "reason_code": "negative_or_not_formed"
        }
      ]
    },
    "saks": {
      "negative_facts": [
        {
          "kind": "recusal",
          "snippet_must_contain": "did not participate",
          "expected_applicability": "not_applicable",
          "reason_code": "unrelated_bidder_nonparticipation"
        }
      ]
    },
    "medivation": {
      "rejected_regions": [
        {
          "section": "Past Contacts, Transactions, Negotiations and Agreements",
          "classification": "cross_reference_only",
          "snippet_must_contain": "The information set forth in"
        }
      ]
    }
  }
}
```

If fact-check agents produce better exact snippets, use those exact short snippets but preserve the schema.

- [ ] **Step 2: Add red Reference-9 ledger assertions**

Modify `tests/test_reference9_offline_regions.py` with helpers:

```python
FACT_LEDGER_PATH = REPO_ROOT / "tests" / "fixtures" / "reference9_fact_ledger.json"


def _load_fact_ledger() -> dict[str, dict]:
    return json.loads(FACT_LEDGER_PATH.read_text(encoding="utf-8"))["deals"]


@pytest.fixture(scope="module")
def fact_ledger() -> dict[str, dict]:
    return _load_fact_ledger()
```

Add this test:

```python
@pytest.mark.parametrize("slug", ("penford", "zep", "saks"))
def test_reference9_negative_facts_do_not_become_applicable(
    slug: str, fact_ledger: dict[str, dict]
) -> None:
    if slug in _missing_filings():
        pytest.fail(
            f"Reference-9 slug {slug!r} has no data/filings/{slug}/raw.md; "
            f"fetch it with: {FETCH_COMMAND.format(slug=slug)}"
        )
    conn = connect(":memory:")
    init_schema(conn)
    [source] = filing_sources([slug], filings_dir=FILINGS_DIR)
    filing = ingest_source(conn, source)
    build_evidence_map(conn, filing_id=filing.filing_id, run_id=RUN_ID)

    rows = {
        kind: applicability
        for kind, applicability in conn.execute(
            """
            SELECT obligation_kind, applicability
            FROM coverage_obligations
            WHERE filing_id = ?
              AND current = true
            """,
            [filing.filing_id],
        ).fetchall()
    }
    for fact in fact_ledger[slug].get("negative_facts", []):
        assert rows[fact["kind"]] == fact["expected_applicability"], (
            f"{slug}: {fact['kind']} should be {fact['expected_applicability']} "
            f"because source snippet contains {fact['snippet_must_contain']!r}"
        )
```

Add this test:

```python
def test_medivation_cross_reference_only_past_contacts_region_is_rejected(
    fact_ledger: dict[str, dict]
) -> None:
    slug = "medivation"
    if slug in _missing_filings():
        pytest.fail(
            f"Reference-9 slug {slug!r} has no data/filings/{slug}/raw.md; "
            f"fetch it with: {FETCH_COMMAND.format(slug=slug)}"
        )
    conn = connect(":memory:")
    init_schema(conn)
    [source] = filing_sources([slug], filings_dir=FILINGS_DIR)
    filing = ingest_source(conn, source)
    build_evidence_map(conn, filing_id=filing.filing_id, run_id=RUN_ID)

    selected_sections = [
        json.loads(row[0])[0]
        for row in conn.execute(
            """
            SELECT trigger_phrases_json
            FROM evidence_regions
            WHERE filing_id = ?
            ORDER BY priority
            """,
            [filing.filing_id],
        ).fetchall()
    ]
    rejected = fact_ledger[slug]["rejected_regions"][0]["section"]
    assert rejected not in selected_sections
```

- [ ] **Step 3: Add red synthetic applicability tests**

Modify `tests/test_applicability_obligations.py`:

```python
@pytest.mark.parametrize(
    ("text", "kind"),
    [
        ("Buyer A requested exclusivity, but the board declined exclusivity.", "exclusivity_grant"),
        ("The board determined not to form a transaction committee.", "special_committee"),
        ("Company F did not participate in a buyer offer.", "recusal"),
    ],
)
def test_negative_or_unrelated_mentions_do_not_trigger_conditional_applicability(
    text: str, kind: str
) -> None:
    decision = next(
        item
        for item in decide_applicability(region_text=text, process_scope="target_full_proxy")
        if item.obligation_kind.kind == kind
    )
    assert decision.applicability == "not_applicable"
    assert decision.reason_code in {
        "negative_or_requested_only",
        "negative_or_not_formed",
        "unrelated_bidder_nonparticipation",
        "trigger_phrase_absent",
    }
```

- [ ] **Step 4: Run red tests and record failures**

Run:

```bash
UV_CACHE_DIR=/private/tmp/uv-cache PYTHONDONTWRITEBYTECODE=1 uv run pytest -q -p no:cacheprovider \
  tests/test_reference9_offline_regions.py \
  tests/test_applicability_obligations.py
```

Expected before implementation:

```text
FAILED tests/test_reference9_offline_regions.py::test_reference9_negative_facts_do_not_become_applicable...
FAILED tests/test_reference9_offline_regions.py::test_medivation_cross_reference_only_past_contacts_region_is_rejected
FAILED tests/test_applicability_obligations.py::test_negative_or_unrelated_mentions_do_not_trigger_conditional_applicability...
```

- [ ] **Step 5: Commit red tests**

Run:

```bash
git add tests/fixtures/reference9_fact_ledger.json tests/test_reference9_offline_regions.py tests/test_applicability_obligations.py
git commit -m "test: pin Reference-9 false-positive facts"
```

## Task 3: Source Support Classifier

**Files:**
- Create: `src/sec_graph/extract/source_support.py`
- Create: `tests/test_source_support_semantics.py`
- Modify: `src/sec_graph/extract/applicability.py`

- [ ] **Step 1: Write source-support tests**

Create `tests/test_source_support_semantics.py`:

```python
import pytest

from sec_graph.extract.source_support import SupportState, classify_obligation_support


@pytest.mark.parametrize(
    ("kind", "text", "basis"),
    [
        ("exclusivity_grant", "The board granted exclusivity to Buyer A.", "granted exclusivity"),
        ("special_committee", "The board formed a special committee of independent directors.", "formed a special committee"),
        ("recusal", "Director C recused himself from the board's evaluation.", "recused himself"),
    ],
)
def test_positive_support(kind: str, text: str, basis: str) -> None:
    decision = classify_obligation_support(kind, text)
    assert decision.state == SupportState.POSITIVE
    assert basis.casefold() in " ".join(decision.basis).casefold()


@pytest.mark.parametrize(
    ("kind", "text", "reason"),
    [
        ("exclusivity_grant", "Buyer A requested exclusivity, and the board declined exclusivity.", "negative_or_requested_only"),
        ("exclusivity_grant", "The board concluded that exclusivity was not justified.", "negative_or_requested_only"),
        ("special_committee", "The board determined not to form a transaction committee.", "negative_or_not_formed"),
        ("recusal", "Company F did not participate in a buyer offer.", "unrelated_bidder_nonparticipation"),
    ],
)
def test_negative_or_unrelated_support(kind: str, text: str, reason: str) -> None:
    decision = classify_obligation_support(kind, text)
    assert decision.state == SupportState.NEGATIVE
    assert decision.reason_code == reason
```

- [ ] **Step 2: Run source-support tests to verify red**

Run:

```bash
UV_CACHE_DIR=/private/tmp/uv-cache PYTHONDONTWRITEBYTECODE=1 uv run pytest -q -p no:cacheprovider tests/test_source_support_semantics.py
```

Expected before implementation:

```text
ModuleNotFoundError: No module named 'sec_graph.extract.source_support'
```

- [ ] **Step 3: Implement source-support classifier**

Create `src/sec_graph/extract/source_support.py`:

```python
"""Source-text support classification for applicability and coverage proof."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum


class SupportState(StrEnum):
    POSITIVE = "positive"
    NEGATIVE = "negative"
    ABSENT = "absent"
    AMBIGUOUS = "ambiguous"


@dataclass(frozen=True)
class SupportDecision:
    obligation_kind: str
    state: SupportState
    reason_code: str
    basis: tuple[str, ...]


def classify_obligation_support(obligation_kind: str, text: str) -> SupportDecision:
    folded = _fold(text)
    negative = _first_match(folded, _NEGATIVE_PATTERNS.get(obligation_kind, ()))
    if negative is not None:
        return SupportDecision(obligation_kind, SupportState.NEGATIVE, negative[0], (negative[1],))
    positive = _first_match(folded, _POSITIVE_PATTERNS.get(obligation_kind, ()))
    if positive is not None:
        return SupportDecision(obligation_kind, SupportState.POSITIVE, "positive_source_support", (positive[1],))
    topic = _first_match(folded, _TOPIC_PATTERNS.get(obligation_kind, ()))
    if topic is not None:
        return SupportDecision(obligation_kind, SupportState.AMBIGUOUS, "topic_only_or_ambiguous", (topic[1],))
    return SupportDecision(obligation_kind, SupportState.ABSENT, "source_support_absent", ())


def is_substantive_sale_process_text(text: str) -> bool:
    folded = _fold(text)
    if len(folded.split()) < 25:
        return False
    if _looks_cross_reference_only(folded):
        return False
    return any(
        marker in folded
        for marker in (
            "board",
            "committee",
            "proposal",
            "offer",
            "buyer",
            "party",
            "negotiat",
            "merger agreement",
            "contacted",
            "indication of interest",
        )
    )


def _fold(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().casefold()


def _first_match(text: str, patterns: tuple[tuple[str, str], ...]) -> tuple[str, str] | None:
    for reason_code, pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match is not None:
            return reason_code, match.group(0)
    return None


def _looks_cross_reference_only(text: str) -> bool:
    cross_ref_markers = (
        "the information set forth in",
        "is incorporated herein by reference",
        "see section",
        "see the section",
        "set forth under",
    )
    return any(marker in text for marker in cross_ref_markers) and len(text.split()) < 80


_POSITIVE_PATTERNS: dict[str, tuple[tuple[str, str], ...]] = {
    "exclusivity_grant": (
        ("positive_source_support", r"\b(granted|provided|entered into|agreed to)\b.{0,80}\bexclusiv"),
        ("positive_source_support", r"\bexclusivity agreement\b"),
        ("positive_source_support", r"\bexclusive negotiations?\b"),
    ),
    "special_committee": (
        ("positive_source_support", r"\b(formed|established|created|appointed)\b.{0,80}\b(special|transaction) committee\b"),
        ("positive_source_support", r"\b(special|transaction) committee\b.{0,80}\b(composed of|members?|appointed)\b"),
    ),
    "recusal": (
        ("positive_source_support", r"\brecused?\b.{0,120}\b(board|committee|process|evaluation|negotiation|transaction)\b"),
        ("positive_source_support", r"\bdid not participate\b.{0,120}\b(board|committee|process|evaluation|negotiation|transaction)\b"),
    ),
}

_NEGATIVE_PATTERNS: dict[str, tuple[tuple[str, str], ...]] = {
    "exclusivity_grant": (
        ("negative_or_requested_only", r"\b(requested|sought)\b.{0,80}\bexclusiv"),
        ("negative_or_requested_only", r"\b(declined|rejected|refused|would not grant)\b.{0,80}\bexclusiv"),
        ("negative_or_requested_only", r"\bexclusiv.{0,80}\b(not justified|declined|rejected|refused)\b"),
    ),
    "special_committee": (
        ("negative_or_not_formed", r"\bnot to form\b.{0,80}\b(special|transaction) committee\b"),
        ("negative_or_not_formed", r"\bdid not form\b.{0,80}\b(special|transaction) committee\b"),
    ),
    "recusal": (
        ("unrelated_bidder_nonparticipation", r"\bcompany [a-z]\b.{0,80}\bdid not participate\b"),
        ("unrelated_bidder_nonparticipation", r"\bbidder\b.{0,80}\bdid not participate\b"),
        ("conditional_or_disclaimed", r"\bif\b.{0,80}\brecus"),
        ("conditional_or_disclaimed", r"\bdisclaim.{0,80}\binterest\b"),
    ),
}

_TOPIC_PATTERNS: dict[str, tuple[tuple[str, str], ...]] = {
    "exclusivity_grant": (("topic_only_or_ambiguous", r"\bexclusiv"),),
    "special_committee": (("topic_only_or_ambiguous", r"\b(special|transaction) committee\b"),),
    "recusal": (("topic_only_or_ambiguous", r"\b(recus|did not participate|abstain)"),),
}
```

- [ ] **Step 4: Wire applicability to source-support classifier**

In `src/sec_graph/extract/applicability.py`, import:

```python
from sec_graph.extract.source_support import SupportState, classify_obligation_support
```

Replace conditional handling in `decide_applicability()` with:

```python
        elif kind.family == "conditional":
            support = classify_obligation_support(kind.kind, region_text)
            if support.state == SupportState.POSITIVE:
                decisions.append(
                    ApplicabilityDecision(
                        obligation_kind=kind,
                        applicability="applicable",
                        reason_code="positive_source_support",
                        basis=support.basis,
                    )
                )
            elif support.state in {SupportState.NEGATIVE, SupportState.AMBIGUOUS}:
                decisions.append(
                    ApplicabilityDecision(
                        obligation_kind=kind,
                        applicability="not_applicable",
                        reason_code=support.reason_code,
                        basis=support.basis,
                    )
                )
            else:
                decisions.append(
                    ApplicabilityDecision(
                        obligation_kind=kind,
                        applicability="not_applicable",
                        reason_code="source_support_absent",
                        basis=(),
                    )
                )
```

Keep the existing trigger patterns only for obligation kinds not yet covered by
`source_support.py`, or migrate them into `_POSITIVE_PATTERNS` before deleting
dead pattern code. Do not preserve a broad `\bexclusivity\b` positive trigger.

- [ ] **Step 5: Run tests**

Run:

```bash
UV_CACHE_DIR=/private/tmp/uv-cache PYTHONDONTWRITEBYTECODE=1 uv run pytest -q -p no:cacheprovider \
  tests/test_source_support_semantics.py \
  tests/test_applicability_obligations.py
```

Expected:

```text
passed
```

- [ ] **Step 6: Commit source-support classifier**

Run:

```bash
git add src/sec_graph/extract/source_support.py src/sec_graph/extract/applicability.py tests/test_source_support_semantics.py tests/test_applicability_obligations.py
git commit -m "fix: classify Reference-9 source support"
```

## Task 4: Contiguous And Substantive Region Selection

**Files:**
- Modify: `src/sec_graph/extract/evidence_map.py`
- Modify: `tests/test_hard_reset_schema.py`
- Modify: `tests/test_reference9_offline_regions.py`
- Modify: `tests/fixtures/reference9_region_expectations.json`
- Modify: `tests/fixtures/reference9_applicability_expectations.json`

- [ ] **Step 1: Add failing contiguous-region test**

Update `tests/test_hard_reset_schema.py` so the existing repeated-heading fixture expects two contiguous regions or one accepted region plus one rejected candidate, not one merged region with paragraphs `2,3,5`.

Use this assertion shape:

```python
def test_evidence_map_does_not_merge_repeated_headings_across_other_sections() -> None:
    conn = connect(":memory:")
    init_schema(conn)
    filing_id = _insert_sectioned_filing(
        conn,
        [
            ("unknown_section", "Cover."),
            ("Background of the Merger", "The Company contacted bidders."),
            ("Background of the Merger", "The Board reviewed a final proposal."),
            ("Reasons for the Merger", "The board considered fairness."),
            ("Background of the Merger", "The parties granted exclusivity."),
        ],
    )

    region_ids = build_evidence_map(conn, filing_id=filing_id, run_id=RUN_ID)

    rows = conn.execute(
        """
        SELECT paragraph_ids_json
        FROM evidence_regions
        WHERE filing_id = ?
        ORDER BY priority
        """,
        [filing_id],
    ).fetchall()
    paragraph_groups = [json.loads(row[0]) for row in rows]
    assert ["sectioned-deal_para_2", "sectioned-deal_para_3"] in paragraph_groups
    assert ["sectioned-deal_para_5"] in paragraph_groups
    assert ["sectioned-deal_para_2", "sectioned-deal_para_3", "sectioned-deal_para_5"] not in paragraph_groups
    assert len(region_ids) == len(paragraph_groups)
```

- [ ] **Step 2: Add failing Medivation region expectation**

Update `tests/fixtures/reference9_region_expectations.json` to remove the
Medivation `Past Contacts, Transactions, Negotiations and Agreements` selected
region. Move the same section into `tests/fixtures/reference9_fact_ledger.json`
under `rejected_regions`.

Update `tests/fixtures/reference9_applicability_expectations.json` so Medivation
has only the substantive `Background of the Offer` selected region.

- [ ] **Step 3: Run red region tests**

Run:

```bash
UV_CACHE_DIR=/private/tmp/uv-cache PYTHONDONTWRITEBYTECODE=1 uv run pytest -q -p no:cacheprovider \
  tests/test_hard_reset_schema.py::test_evidence_map_does_not_merge_repeated_headings_across_other_sections \
  tests/test_reference9_offline_regions.py::test_medivation_cross_reference_only_past_contacts_region_is_rejected
```

Expected before implementation:

```text
FAILED
```

- [ ] **Step 4: Implement contiguous sale-process runs**

In `src/sec_graph/extract/evidence_map.py`, replace global `section_paragraphs`
grouping with contiguous runs:

```python
def _sale_process_runs(rows: list[ParagraphRow]) -> list[tuple[str, list[ParagraphRow]]]:
    runs: list[tuple[str, list[ParagraphRow]]] = []
    current_section: str | None = None
    current_rows: list[ParagraphRow] = []
    for row in rows:
        if row.section not in SALE_PROCESS_SECTIONS:
            if current_rows and current_section is not None:
                runs.append((current_section, current_rows))
            current_section = None
            current_rows = []
            continue
        if row.section != current_section:
            if current_rows and current_section is not None:
                runs.append((current_section, current_rows))
            current_section = row.section
            current_rows = [row]
        else:
            current_rows.append(row)
    if current_rows and current_section is not None:
        runs.append((current_section, current_rows))
    return runs
```

Use it in `build_evidence_map()`:

```python
    candidate_runs = _sale_process_runs(rows)
    substantive_runs: list[tuple[str, list[ParagraphRow]]] = []
    for section, paragraphs in candidate_runs:
        region_text = "\n".join(p.paragraph_text for p in paragraphs)
        if is_substantive_sale_process_text(region_text):
            substantive_runs.append((section, paragraphs))

    if not substantive_runs:
        raise ValueError(
            f"filing {filing_id} has no substantive sale-process paragraphs "
            "(recognized headings were absent or cross-reference-only)"
        )
```

Then iterate over `substantive_runs` instead of `section_order`.

- [ ] **Step 5: Run region tests**

Run:

```bash
UV_CACHE_DIR=/private/tmp/uv-cache PYTHONDONTWRITEBYTECODE=1 uv run pytest -q -p no:cacheprovider \
  tests/test_hard_reset_schema.py \
  tests/test_reference9_offline_regions.py
```

Expected:

```text
passed
```

- [ ] **Step 6: Commit region repair**

Run:

```bash
git add src/sec_graph/extract/evidence_map.py tests/test_hard_reset_schema.py tests/test_reference9_offline_regions.py tests/fixtures/reference9_region_expectations.json tests/fixtures/reference9_applicability_expectations.json tests/fixtures/reference9_fact_ledger.json
git commit -m "fix: require substantive contiguous Reference-9 regions"
```

## Task 5: Tender-Offer Ingest Guard

**Files:**
- Modify: `src/sec_graph/ingest/pipeline.py`
- Modify: `tests/test_reference9_offline_regions.py`

- [ ] **Step 1: Add failing negative ingest test**

Add to `tests/test_reference9_offline_regions.py`:

```python
def test_sc_to_t_manifest_without_offer_to_purchase_exhibit_fails_loudly(tmp_path: Path) -> None:
    from sec_graph.ingest.pipeline import IngestSource, ingest_source

    source_dir = tmp_path / "bad-tender"
    source_dir.mkdir()
    raw_path = source_dir / "raw.md"
    manifest_path = source_dir / "manifest.json"
    raw_path.write_text("Background of the Offer\n\nThe offer materials say nothing useful.", encoding="utf-8")
    manifest_path.write_text(
        json.dumps(
            {
                "source": {
                    "filing_form_type": "SC TO-T",
                    "selected_document_form_type": "SC TO-T",
                    "primary_document_name": "cover.htm",
                }
            }
        ),
        encoding="utf-8",
    )
    conn = connect(":memory:")
    init_schema(conn)
    with pytest.raises(ValueError) as excinfo:
        ingest_source(
            conn,
            IngestSource(
                slug="bad-tender",
                source_path=raw_path,
                manifest_path=manifest_path,
            ),
        )
    message = str(excinfo.value)
    assert "SC TO-T" in message
    assert "EX-99.(A)(1)(A)" in message
```

- [ ] **Step 2: Run red tender test**

Run:

```bash
UV_CACHE_DIR=/private/tmp/uv-cache PYTHONDONTWRITEBYTECODE=1 uv run pytest -q -p no:cacheprovider \
  tests/test_reference9_offline_regions.py::test_sc_to_t_manifest_without_offer_to_purchase_exhibit_fails_loudly
```

Expected before implementation:

```text
FAILED
```

- [ ] **Step 3: Implement ingest guard**

In `src/sec_graph/ingest/pipeline.py`, add:

```python
import re
```

Add near `_process_scope`:

```python
_TENDER_PARENT_FORMS = {"SC TO-T", "SC TO-T/A"}
_OFFER_TO_PURCHASE_RE = re.compile(r"^EX-99\.\(?A\)?\(?1\)?\(?A\)?", re.IGNORECASE)


def _require_offer_to_purchase_for_tender(source: IngestSource, manifest: dict) -> None:
    source_info = manifest.get("source", {})
    parent_form = str(
        source_info.get("filing_form_type")
        or source_info.get("form_type")
        or ""
    ).upper()
    selected_form = str(source_info.get("selected_document_form_type") or "").upper()
    selected_name = str(source_info.get("primary_document_name") or "").casefold()
    if parent_form not in _TENDER_PARENT_FORMS:
        return
    if _OFFER_TO_PURCHASE_RE.match(selected_form):
        return
    if "ex99a1a" in selected_name or "ex-99" in selected_name and "a1a" in selected_name:
        return
    raise ValueError(
        f"{source.slug}: SC TO-T source must select EX-99.(A)(1)(A) Offer to Purchase exhibit; "
        f"selected_document_form_type={selected_form!r}, primary_document_name={selected_name!r}"
    )
```

Update `_process_scope()`:

```python
    manifest = json.loads(source.manifest_path.read_text(encoding="utf-8"))
    _require_offer_to_purchase_for_tender(source, manifest)
```

- [ ] **Step 4: Run tender tests**

Run:

```bash
UV_CACHE_DIR=/private/tmp/uv-cache PYTHONDONTWRITEBYTECODE=1 uv run pytest -q -p no:cacheprovider \
  tests/test_reference9_offline_regions.py::test_sc_to_t_manifest_without_offer_to_purchase_exhibit_fails_loudly \
  tests/test_reference9_offline_regions.py::test_medivation_reference9_uses_offer_to_purchase_exhibit
```

Expected:

```text
passed
```

- [ ] **Step 5: Commit ingest guard**

Run:

```bash
git add src/sec_graph/ingest/pipeline.py tests/test_reference9_offline_regions.py
git commit -m "fix: enforce tender offer exhibit at ingest"
```

## Task 6: Persist Claim-To-Obligation Coverage Links

**Files:**
- Modify: `src/sec_graph/schema/models/extraction.py`
- Modify: `src/sec_graph/schema/models/__init__.py`
- Modify: `src/sec_graph/schema/__init__.py`
- Modify: `src/sec_graph/extract/llm/convert.py`
- Modify: `tests/test_hard_reset_schema.py`
- Modify: `tests/test_coverage_semantics.py`

- [ ] **Step 1: Add failing schema and conversion tests**

In `tests/test_hard_reset_schema.py`, update the table-existence assertion to include:

```python
"claim_coverage_links",
```

In `tests/test_coverage_semantics.py`, add:

```python
def test_inserted_claim_persists_coverage_obligation_link(tmp_path: Path) -> None:
    conn = connect(":memory:")
    init_schema(conn)
    _insert_window_source(conn, tmp_path)
    window = LLMWindowRequest(
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
                paragraph_text="The Board began a sale process. The Board later granted exclusivity to Buyer A.",
            )
        ],
        coverage_obligations=[
            WindowObligation(
                obligation_id="coverage-deal_obligation_1",
                expected_claim_type="event",
                obligation_label="Sales process initiation",
                importance="required",
            )
        ],
        allowed_claim_types=["event"],
        schema_version=1,
        extract_version=1,
        request_mode=DEFAULT_REQUEST_MODE,
    )
    payload = SemanticClaimsPayload(
        event_claims=[
            EventClaimPayload(
                claim_type="event",
                coverage_obligation_id="coverage-deal_obligation_1",
                event_type="process",
                event_subtype="contact_initial",
                event_date=None,
                description="The Board began a sale process.",
                actor_label=None,
                actor_role=None,
                confidence="high",
                quote_text="The Board began a sale process.",
            )
        ]
    )
    response = LLMExtractionResponse(
        request_id=window.request_id,
        provider_name="linkflow",
        provider_model="gpt-5.5",
        reasoning_effort="medium",
        payload=payload,
        raw_response_sha256=quote_hash(json.dumps(payload.model_dump(mode="json"), sort_keys=True)),
        finish_status="completed",
    )

    [claim_id] = insert_llm_response(conn, window, response, run_id=RUN_ID)

    assert conn.execute(
        """
        SELECT claim_id, obligation_id, run_id, current
        FROM claim_coverage_links
        """
    ).fetchall() == [
        (claim_id, "coverage-deal_obligation_1", RUN_ID, True)
    ]
```

- [ ] **Step 2: Run red coverage-link tests**

Run:

```bash
UV_CACHE_DIR=/private/tmp/uv-cache PYTHONDONTWRITEBYTECODE=1 uv run pytest -q -p no:cacheprovider \
  tests/test_hard_reset_schema.py::test_hard_reset_tables_exist \
  tests/test_coverage_semantics.py::test_inserted_claim_persists_coverage_obligation_link
```

Expected before implementation:

```text
Catalog Error: Table with name claim_coverage_links does not exist
```

- [ ] **Step 3: Add schema model and table**

In `src/sec_graph/schema/models/extraction.py`, add after `Claim`:

```python
class ClaimCoverageLink(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    claim_id: str
    obligation_id: str
    run_id: str
    deal_slug: str
    claim_type: ClaimType
    current: bool = True
```

Add DDL after `claims`:

```sql
CREATE TABLE claim_coverage_links (
  claim_id VARCHAR PRIMARY KEY,
  obligation_id VARCHAR NOT NULL,
  run_id VARCHAR NOT NULL,
  deal_slug VARCHAR NOT NULL,
  claim_type VARCHAR NOT NULL CHECK (claim_type IN ('actor', 'event', 'bid', 'participation_count', 'actor_relation')),
  current BOOLEAN NOT NULL,
  FOREIGN KEY (claim_id) REFERENCES claims(claim_id),
  FOREIGN KEY (obligation_id) REFERENCES coverage_obligations(obligation_id)
);
```

Export `ClaimCoverageLink` from `src/sec_graph/schema/models/__init__.py` and `src/sec_graph/schema/__init__.py`.

- [ ] **Step 4: Insert coverage links in converter**

In `src/sec_graph/extract/llm/convert.py`, after inserting each claim and before `_insert_typed_claim()`:

```python
        conn.execute(
            "INSERT INTO claim_coverage_links VALUES (?, ?, ?, ?, ?, ?)",
            [
                claim_id,
                payload.coverage_obligation_id,
                run_id,
                request.deal_slug,
                payload.claim_type,
                True,
            ],
        )
```

Keep `coverage_claim_counts` for now, but add a follow-up validation task to cross-check it against links.

- [ ] **Step 5: Run coverage-link tests**

Run:

```bash
UV_CACHE_DIR=/private/tmp/uv-cache PYTHONDONTWRITEBYTECODE=1 uv run pytest -q -p no:cacheprovider \
  tests/test_hard_reset_schema.py \
  tests/test_coverage_semantics.py
```

Expected:

```text
passed
```

- [ ] **Step 6: Commit coverage-link persistence**

Run:

```bash
git add src/sec_graph/schema/models/extraction.py src/sec_graph/schema/models/__init__.py src/sec_graph/schema/__init__.py src/sec_graph/extract/llm/convert.py tests/test_hard_reset_schema.py tests/test_coverage_semantics.py
git commit -m "feat: persist claim coverage links"
```

## Task 7: Validation And Proof Audit Hardening

**Files:**
- Modify: `src/sec_graph/validate/integrity.py`
- Modify: `src/sec_graph/project/summaries.py`
- Modify: `tests/test_validation_semantics.py`
- Modify: `tests/test_coverage_semantics.py`

- [ ] **Step 1: Add failing validation tests**

In `tests/test_validation_semantics.py`, add:

```python
def test_not_applicable_obligation_with_current_coverage_result_fails(tmp_path: Path) -> None:
    conn, _source_path = _semantic_db(
        tmp_path,
        bid_quote="On January 1, 2020, Party A submitted a final proposal of $10.00 per share",
        relation_quote="Parent was an acquisition vehicle of Buyer Group",
    )
    obligation_id = conn.execute(
        """
        SELECT obligation_id
        FROM coverage_obligations
        WHERE applicability = 'not_applicable'
        ORDER BY obligation_id
        LIMIT 1
        """
    ).fetchone()[0]
    conn.execute(
        "INSERT INTO coverage_results VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        [
            "bad_coverage_result",
            RUN_ID,
            obligation_id,
            "missed",
            "bad_not_applicable_result",
            "not_applicable obligations must not carry coverage results",
            0,
            True,
        ],
    )

    validation = validate_database(conn)

    assert any(
        failure.check == HardCheck.COVERAGE_RESULT
        and failure.row_id == obligation_id
        and "not_applicable" in failure.detail
        for failure in validation.hard_failures
    )
```

Add:

```python
def test_claims_emitted_without_coverage_link_fails_validation(tmp_path: Path) -> None:
    conn, _source_path = _semantic_db(
        tmp_path,
        bid_quote="On January 1, 2020, Party A submitted a final proposal of $10.00 per share",
        relation_quote="Parent was an acquisition vehicle of Buyer Group",
    )
    obligation_id = conn.execute(
        """
        SELECT obligation_id
        FROM coverage_results
        WHERE result = 'claims_emitted'
        ORDER BY obligation_id
        LIMIT 1
        """
    ).fetchone()[0]
    conn.execute("DELETE FROM claim_coverage_links WHERE obligation_id = ?", [obligation_id])

    validation = validate_database(conn)

    assert any(
        failure.check == HardCheck.COVERAGE_RESULT
        and failure.row_id == obligation_id
        and "claims_emitted has no linked claims" in failure.detail
        for failure in validation.hard_failures
    )
```

- [ ] **Step 2: Run red validation tests**

Run:

```bash
UV_CACHE_DIR=/private/tmp/uv-cache PYTHONDONTWRITEBYTECODE=1 uv run pytest -q -p no:cacheprovider \
  tests/test_validation_semantics.py::test_not_applicable_obligation_with_current_coverage_result_fails \
  tests/test_validation_semantics.py::test_claims_emitted_without_coverage_link_fails_validation
```

Expected before implementation:

```text
FAILED
```

- [ ] **Step 3: Implement validation checks**

In `_check_coverage_results()` in `src/sec_graph/validate/integrity.py`, add before `return failures`:

```python
    bad_not_applicable_rows = conn.execute(
        """
        SELECT coverage_obligations.obligation_id, coverage_results.coverage_result_id
        FROM coverage_obligations
        JOIN coverage_results
          ON coverage_results.obligation_id = coverage_obligations.obligation_id
         AND coverage_results.current = true
        WHERE coverage_obligations.current = true
          AND coverage_obligations.applicability = 'not_applicable'
        ORDER BY coverage_obligations.obligation_id
        """
    ).fetchall()
    failures.extend(
        ValidationFailure(
            HardCheck.COVERAGE_RESULT,
            "coverage_obligations",
            obligation_id,
            f"not_applicable obligation has current coverage result {coverage_result_id}",
        )
        for obligation_id, coverage_result_id in bad_not_applicable_rows
    )
    unlinked_claims_emitted = conn.execute(
        """
        SELECT coverage_results.obligation_id
        FROM coverage_results
        LEFT JOIN claim_coverage_links
          ON claim_coverage_links.obligation_id = coverage_results.obligation_id
         AND claim_coverage_links.current = true
        WHERE coverage_results.current = true
          AND coverage_results.result = 'claims_emitted'
        GROUP BY coverage_results.obligation_id, coverage_results.claim_count
        HAVING count(claim_coverage_links.claim_id) = 0
           OR count(claim_coverage_links.claim_id) <> coverage_results.claim_count
        """
    ).fetchall()
    failures.extend(
        ValidationFailure(
            HardCheck.COVERAGE_RESULT,
            "coverage_results",
            obligation_id,
            "claims_emitted has no linked claims or claim_count does not match persisted links",
        )
        for (obligation_id,) in unlinked_claims_emitted
    )
```

- [ ] **Step 4: Filter proof summaries to current rows**

In `src/sec_graph/project/summaries.py`, update `_group_count()` call sites or `_group_count()` itself so `coverage_results`, `claim_dispositions`, and final CSV rows use `current = true` where the table has a `current` column.

Update `_coverage_rows()` columns to include:

```python
"coverage_result_id",
"coverage_current",
"obligation_current",
"linked_claim_ids_json",
```

Use SQL:

```sql
SELECT coverage_obligations.deal_slug, obligation_id, obligation_kind,
       expected_claim_type, importance, applicability,
       applicability_reason_code, applicability_basis_json,
       coverage_results.coverage_result_id, result, claim_count, reason_code,
       coverage_results.current AS coverage_current,
       coverage_obligations.current AS obligation_current,
       COALESCE(
         to_json(list(claim_coverage_links.claim_id ORDER BY claim_coverage_links.claim_id)
           FILTER (WHERE claim_coverage_links.claim_id IS NOT NULL)),
         '[]'
       ) AS linked_claim_ids_json
FROM coverage_obligations
LEFT JOIN coverage_results
  ON coverage_results.obligation_id = coverage_obligations.obligation_id
 AND coverage_results.current = true
LEFT JOIN claim_coverage_links
  ON claim_coverage_links.obligation_id = coverage_obligations.obligation_id
 AND claim_coverage_links.current = true
WHERE coverage_obligations.current = true
GROUP BY coverage_obligations.deal_slug, obligation_id, obligation_kind,
         expected_claim_type, importance, applicability,
         applicability_reason_code, applicability_basis_json,
         coverage_results.coverage_result_id, result, claim_count, reason_code,
         coverage_results.current, coverage_obligations.current
ORDER BY coverage_obligations.deal_slug, obligation_id
```

- [ ] **Step 5: Run validation/proof tests**

Run:

```bash
UV_CACHE_DIR=/private/tmp/uv-cache PYTHONDONTWRITEBYTECODE=1 uv run pytest -q -p no:cacheprovider \
  tests/test_validation_semantics.py \
  tests/test_hard_reset_schema.py \
  tests/test_coverage_semantics.py
```

Expected:

```text
passed
```

- [ ] **Step 6: Commit validation hardening**

Run:

```bash
git add src/sec_graph/validate/integrity.py src/sec_graph/project/summaries.py tests/test_validation_semantics.py tests/test_hard_reset_schema.py tests/test_coverage_semantics.py
git commit -m "fix: harden coverage validation audit"
```

## Task 8: Failed-Validation Proof Metadata

**Files:**
- Modify: `src/sec_graph/cli/run_cmd.py`
- Create: `tests/test_run_failed_validation_proof.py`
- Modify: `tests/test_repo_freshness_contract.py`

- [ ] **Step 1: Add failing proof metadata tests**

Create `tests/test_run_failed_validation_proof.py`:

```python
import json
from pathlib import Path

import pytest

from sec_graph.cli.run_cmd import run_pipeline
from sec_graph.extract.llm.models import DEFAULT_REQUEST_MODE


def test_failed_validation_run_writes_failed_validation_proof(tmp_path: Path) -> None:
    run_id = "2026-05-04T120000Z_failed-validation_deadbeef"
    run_dir = tmp_path / run_id

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
```

- [ ] **Step 2: Implement resolved commit helper**

In `src/sec_graph/cli/run_cmd.py`, replace `_git_head()` with:

```python
def _git_head() -> str | None:
    import subprocess

    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:
        return None
```

- [ ] **Step 3: Implement failed-validation proof writer**

Add in `src/sec_graph/cli/run_cmd.py`:

```python
def _write_failed_validation_proof(
    *,
    run_dir: Path,
    run_id: str,
    manifest: dict[str, object],
    validation_report: dict[str, object],
    llm_config: LLMProviderConfig | None,
    request_mode: str,
) -> None:
    artifact_root = Path("artifacts/linkflow") / run_id
    success_count = len(list(artifact_root.glob("*_success.json"))) if artifact_root.exists() else 0
    failure_count = len(list(artifact_root.glob("*_failure.json"))) if artifact_root.exists() else 0
    atomic_write_json(
        run_dir / "failed_validation_proof.json",
        {
            "run_id": run_id,
            "resolved_commit": manifest.get("code_identity"),
            "validation_passed": bool(validation_report.get("passed")),
            "validation_failure_count": len(validation_report.get("hard_failures", [])),
            "provider": llm_config.provider_name if llm_config else None,
            "model": llm_config.model if llm_config else None,
            "reasoning_effort": llm_config.reasoning_effort if llm_config else None,
            "request_mode": request_mode,
            "artifact_counts": {
                "linkflow_success": success_count,
                "linkflow_failure": failure_count,
            },
        },
    )
```

In `run_pipeline()`, before raising on failed validation:

```python
        if not report["passed"]:
            _write_failed_validation_proof(
                run_dir=run_dir,
                run_id=run_id,
                manifest=manifest,
                validation_report=report,
                llm_config=llm_config,
                request_mode=request_mode,
            )
            record_artifact(
                run_dir,
                run_id=run_id,
                path=run_dir / "failed_validation_proof.json",
                artifact_kind="json_report",
                owning_stage="validate",
                deal_slug=None,
                created_by="_write_failed_validation_proof",
            )
            raise RuntimeError(f"run failed validation; artifacts: {run_dir}")
```

- [ ] **Step 4: Run proof metadata tests**

Run:

```bash
UV_CACHE_DIR=/private/tmp/uv-cache PYTHONDONTWRITEBYTECODE=1 uv run pytest -q -p no:cacheprovider \
  tests/test_run_failed_validation_proof.py \
  tests/test_repo_freshness_contract.py
```

Expected:

```text
passed
```

- [ ] **Step 5: Commit failed-validation proof metadata**

Run:

```bash
git add src/sec_graph/cli/run_cmd.py tests/test_run_failed_validation_proof.py tests/test_repo_freshness_contract.py
git commit -m "fix: write failed validation proof metadata"
```

## Task 9: Active Docs And Session Log Cleanup

**Files:**
- Modify: `quality_reports/plans/2026-05-04_p8_region_applicability_ref9_plan.md`
- Modify: `quality_reports/session_logs/README.md`
- Modify: `quality_reports/session_logs/2026-05-04_p8-region-applicability-phase-3-6.md`
- Modify: `docs/spec.md`
- Modify: `docs/llm-interface.md`
- Modify: `tests/test_repo_freshness_contract.py`

- [ ] **Step 1: Add stale wording tests**

In `tests/test_repo_freshness_contract.py`, add:

```python
def test_active_ref9_plan_uses_applicable_coverage_obligation_language() -> None:
    text = Path("quality_reports/plans/2026-05-04_p8_region_applicability_ref9_plan.md").read_text(encoding="utf-8")
    assert "Every current obligation has exactly one current coverage result" not in text
    assert "every current obligation has exactly one current coverage result" not in text
    assert "current applicable obligation" in text


def test_session_logs_do_not_reference_missing_spec_section() -> None:
    text = Path("quality_reports/session_logs/README.md").read_text(encoding="utf-8")
    assert "§1A" not in text
```

- [ ] **Step 2: Run red freshness tests**

Run:

```bash
UV_CACHE_DIR=/private/tmp/uv-cache PYTHONDONTWRITEBYTECODE=1 uv run pytest -q -p no:cacheprovider tests/test_repo_freshness_contract.py
```

Expected before docs cleanup:

```text
FAILED
```

- [ ] **Step 3: Clean active docs and logs**

Make these exact edits:

- In `quality_reports/plans/2026-05-04_p8_region_applicability_ref9_plan.md`, change every active acceptance sentence that says every current obligation needs a result to every current applicable obligation.
- In `quality_reports/session_logs/README.md`, replace stale `docs/spec.md §1A` wording with `docs/spec.md Schema Authority`.
- In `quality_reports/session_logs/2026-05-04_p8-region-applicability-phase-3-6.md`, clarify that failed live runs produced validation reports and sanitized Linkflow artifacts, while projection proof artifacts are only produced after validation passes or through the new failed-validation proof metadata.
- In `docs/spec.md` and `docs/llm-interface.md`, add one sentence that claim-to-obligation links are persisted in `claim_coverage_links`.

- [ ] **Step 4: Run freshness tests**

Run:

```bash
UV_CACHE_DIR=/private/tmp/uv-cache PYTHONDONTWRITEBYTECODE=1 uv run pytest -q -p no:cacheprovider tests/test_repo_freshness_contract.py
```

Expected:

```text
passed
```

- [ ] **Step 5: Commit docs cleanup**

Run:

```bash
git add quality_reports/plans/2026-05-04_p8_region_applicability_ref9_plan.md quality_reports/session_logs/README.md quality_reports/session_logs/2026-05-04_p8-region-applicability-phase-3-6.md docs/spec.md docs/llm-interface.md tests/test_repo_freshness_contract.py
git commit -m "docs: align Reference-9 proof language"
```

## Task 10: Final Verification And Optional Live Proof

**Files:**
- No production edits unless tests expose a bug.
- Generated outputs stay under ignored `runs/`, `artifacts/`, or `tmp/`.

- [ ] **Step 1: Run targeted Reference-9 repair suite**

Run:

```bash
UV_CACHE_DIR=/private/tmp/uv-cache PYTHONDONTWRITEBYTECODE=1 uv run pytest -q -p no:cacheprovider \
  tests/test_source_support_semantics.py \
  tests/test_reference9_offline_regions.py \
  tests/test_applicability_obligations.py \
  tests/test_coverage_semantics.py \
  tests/test_validation_semantics.py \
  tests/test_hard_reset_schema.py \
  tests/test_repo_freshness_contract.py
```

Expected:

```text
passed
```

- [ ] **Step 2: Run full suite**

Run:

```bash
UV_CACHE_DIR=/private/tmp/uv-cache PYTHONDONTWRITEBYTECODE=1 uv run pytest -q -p no:cacheprovider
```

Expected:

```text
passed
```

- [ ] **Step 3: Run diff hygiene**

Run:

```bash
git diff --check
git diff --cached --check
git status --short
```

Expected:

```text
git diff --check: no output
git diff --cached --check: no output
git status --short: no unstaged task changes
```

- [ ] **Step 4: Optional live proof only if credentials are available**

If `LINKFLOW_API_KEY` and any required Linkflow environment variables are already available, run separate per-deal jobs in parallel. Do not echo secrets. Do not switch to `high` or `xhigh`.

Use this exact launcher shape. It generates deterministic run ids from the slug
and runs separate per-deal jobs in parallel:

```bash
set -a; . ./.env; set +a
export SEC_GRAPH_LIVE_LINKFLOW=1
export UV_CACHE_DIR=/private/tmp/uv-cache
for slug in providence-worcester medivation imprivata zep petsmart-inc penford mac-gray saks stec; do
  hash8=$(python -c "import hashlib,sys; print(hashlib.sha256(sys.argv[1].encode()).hexdigest()[:8])" "$slug")
  run_id="2026-05-04T210000Z_p8-correctness-${slug}_${hash8}"
  PYTHONDONTWRITEBYTECODE=1 uv run python -m sec_graph run \
    --source filings \
    --slugs "$slug" \
    --run-id "$run_id" \
    --run-dir "runs/$run_id" \
    --projection bidder_cycle_baseline_v1 \
    --llm-provider linkflow \
    --llm-model gpt-5.5 \
    --llm-reasoning-effort medium \
    --request-mode claim_only_p8_relation_v1 &
done
wait
```

Acceptance for live proof:

- Red validation is acceptable if the failure is honest and `failed_validation_proof.json` is present.
- Do not tune prompts merely to make validation green.
- Do not commit generated `runs/` or `artifacts/`.

- [ ] **Step 5: Final commit if verification changed tracked docs**

Only if Step 4 produced a tracked session-log update, use this path and commit it:

```bash
git add quality_reports/session_logs/2026-05-04_reference9-correctness-live-proof.md
git commit -m "docs: record Reference-9 correctness verification"
```

## Final Handoff Checklist

- [ ] Fact-check log exists and states the nine-deal-only boundary.
- [ ] `tests/fixtures/reference9_fact_ledger.json` exists.
- [ ] Medivation cross-reference-only region is not sent to Linkflow.
- [ ] Penford/Zep/Saks false positives are rejected.
- [ ] Regions are contiguous.
- [ ] `claim_coverage_links` exists and is populated.
- [ ] Validation fails on not-applicable obligations with coverage results.
- [ ] Validation fails on `claims_emitted` without linked claims.
- [ ] Failed-validation runs write proof metadata.
- [ ] Active docs do not claim unsupported proof.
- [ ] Targeted tests pass.
- [ ] Full suite passes.
- [ ] `git status --short` is clean.
