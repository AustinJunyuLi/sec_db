# Validation Review Status And Parallel Region Extraction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor `sec_graph` so validation behaves like a mature extraction pipeline: structurally bad runs fail loudly, but source-backed runs with missing or ambiguous facts still publish trusted graph artifacts plus first-class review rows. In the same refactor, run independent Linkflow region requests concurrently and keep all DuckDB writes deterministic.

**Architecture:** Keep the provider claim-only. Python owns evidence binding, claim disposition, coverage, validation, derived judgments, projections, review rows, run status, and latest-trusted pointers. Provider calls fan out with bounded `asyncio.gather`; completed responses fan back into one sequential DuckDB writer. Immutable run directories stay the proof source. Mutable latest pointers only index the newest attempted run and the newest trusted run.

**Tech Stack:** Python 3.12, DuckDB, Pydantic, AsyncOpenAI/Linkflow, pytest, `uv`, existing `sec_graph` run kernel.

---

## Locked Decisions

This plan is the sole authority for the validation, review-output, and
parallel-region refactor. All prior specs, vocabularies, DuckDB tables,
helper modules, code paths, and artifacts that contradict this plan are
hard-deleted. No compatibility shims, no dual writes, no aliases, no
old/new code coexistence, no rename-with-redirect.

### Run statuses (four values)

A *run record* carries exactly one status:

- `passed_clean`: trusted graph and review output, zero open review rows.
- `needs_review`: trusted graph and review output, 1 to 10 open review rows.
- `high_burden`: trusted graph and review output, more than 10 open review rows.
- `failed_system`: runtime, schema, artifact, or graph-integrity failure.

### Pointer statuses (five values)

`runs/latest/{slug}.json` carries `pointer_status` taking one of:

- `passed_clean`, `needs_review`, `high_burden`: mirror a trusted `latest_attempt`.
- `failed_system`: latest attempt failed and no prior trusted run exists.
- `stale_after_failure`: latest attempt failed but a prior trusted run remains preserved in `latest_trusted`.

`stale_after_failure` is a pointer-only label. A run record never carries it.

### Hard-deleted on this refactor

- `docs/superpowers/specs/2026-05-05-semantic-disposition-validity-design.md`
  is moved to `docs/superpowers/specs/legacy/`. The AGENTS.md and CLAUDE.md
  authority chains drop it.
- Verdict vocabulary `SOUND`, `SUSPECT`, `BLOCKED`, `REVIEW_REQUIRED`, and
  `UNSOUND` is removed from live code, docs, tests, scripts, fixtures, and
  proof artifacts. The proof field `verdict` is renamed to `status`.
- The `review_flags` DuckDB table and its DDL are dropped. A new `review_rows`
  table replaces it. No view, no shim, no parallel write.
- The duplicate post-canonical semantic gate in `validate/integrity.py`
  (`_check_semantic_claim_evidence`, `_check_bid_claim_semantics`,
  `_check_actor_relation_claim_semantics`, and the helpers used only by them:
  `_relation_supported_by_quote`, `_bid_context_supported_by_quote`,
  `_date_supported_by_quote`, `_number_supported_by_quote`) is deleted.
  `extract/disposition.py` is the single semantic gate.
- The pre-disposition coverage write in `extract/llm/convert.py`
  (`coverage_results` INSERT inside `_insert_llm_response_rows`) is deleted.
  Coverage is written once, after disposition.
- `artifacts/linkflow/{run_id}/...` is deleted from the codebase. Provider
  artifacts live only under `{run_dir}/linkflow/{deal_slug}/{request_id}/`.
  The fallback glob in `cli/run_cmd.py:_write_failed_validation_proof` is
  deleted; counts come from `stage_artifacts.jsonl`.
- Rules-only LLM mode is deleted. `extract/pipeline.py:run_extract` requires a
  non-None `llm_config`. Tests that exercised rules-only proof are deleted.
- The `thin_live_claim_warning` field and the live-claim threshold in
  `project/summaries.py` are deleted. Status is computed from open review-row
  count, period.
- `validate/integrity.HardCheck.RULES_ONLY_SOUND` and any code that emits it
  are deleted.
- Any test fixtures or generated outputs under `runs/`, `artifacts/`, or
  `tests/fixtures/` that encode the old vocabulary are regenerated under the
  new contract or deleted.

### Other locked decisions

- Do not introduce a target/reference release gate in `sec_graph`.
- Missed, ambiguous, or thin extraction of required obligations is review burden when the graph rows that do exist remain source-backed.
- Unsupported or bad-evidence claims must not enter canonical graph rows. They may become review rows if the run can quarantine them cleanly.
- Provider payload shape failures, runtime failures, broken source hashes/spans, duplicate or missing proof rows, unsupported claims entering canonical rows, projection traceability failures, and artifact digest failures are `failed_system`.
- Projection incompleteness is review burden. Projection traceability failure is system failure.
- Bidder rows remain in the same run, but they are derived output, not canonical authority.
- One consolidated `review_rows` table is the reviewer-facing artifact. Every row carries `review_status`. There is no second review surface.
- Parallelize provider region calls only. Do not parallelize DuckDB writes.
- `SEC_GRAPH_REGION_MAX_CONCURRENCY=2` is the per-filing default. The outer per-filing loop in `run_pipeline` stays sequential, so total live provider calls equal `SEC_GRAPH_REGION_MAX_CONCURRENCY` at any instant.
- If any region request fails after its retries, the whole attempt is `failed_system`. Successful region artifacts from that failed attempt remain on disk under `{run_dir}/linkflow/...` for audit, but no claim, coverage, canonical, judgment, or projection row is written from that attempt.
- Coverage finalization is DELETE + INSERT. The pre-existing `coverage_results` write path is removed; a single post-disposition writer is the only producer. UPDATE-in-place is forbidden.
- `final_round_boundary` is defined as the `cycle_id` of the process cycle whose canonical rows include at least one event with `event_subtype='final_round_bid'` or whose `participation_counts` rows include `process_stage='final_round'`. There is no separate boundary table.

## Donor Lessons To Borrow, Not Authority

The mature donor pipeline is useful for operational shape, not for wholesale taxonomy import.

Borrow:

- Claim-only provider output.
- Exact quote/evidence binding before canonicalization.
- Python-owned canonical IDs, offsets, dispositions, coverage, validation, review output, and status.
- Review burden as a trusted-but-needs-human state instead of a failed run.
- Source-backed group/buyer-unit doctrine: preserve the filing's bidding unit and do not atomize groups without quote support.
- `participation_count.actor_class = "unknown"` when a filing gives a count without saying financial, strategic, or mixed.

Do not borrow:

- M&A workbook row labels as canonical event taxonomy.
- Provider-owned projection fields such as bidder row status, `T`, `bI`, `bF`, admitted, or dropout outcome.
- Broad relation labels without raw filing examples.
- A progress-file-centered state architecture.

## Review Pass Findings

The parallel review lanes found changes that are required under the new validation method.

Validation/status:

- `docs/spec.md` and `docs/llm-interface.md` still describe older verdict and disposition names. Replace old verdict language with the new five run statuses.
- `src/sec_graph/validate/integrity.py` currently treats unresolved required/important coverage as hard failure. Split these into hard system failures and review items.
- `src/sec_graph/project/summaries.py` currently derives `SOUND`, `REVIEW_REQUIRED`, and `UNSOUND`. Replace this with review-count status derivation.
- `src/sec_graph/cli/run_cmd.py` currently aborts before projection on any validation failure. Review-only burden must continue through projection and artifact publication.
- `src/sec_graph/run/progress.py` and `src/sec_graph/schema/models/runtime.py` need run-status vocabulary and latest-trusted pointer support.

Rules/taxonomy/derivation:

- Count obligations are too broad. `ioi_count`, `first_round_count`, and `final_round_count` should not trigger only because text says "preliminary proposal", "first round", or "best and final"; they need count language.
- `participation_count.actor_class` must allow `unknown` because many filings say only "potential buyers" or "parties".
- Event obligations include `go_shop_period` and `amendment`, but the closed event subtype enum lacks matching values.
- `src/sec_graph/extract/disposition.py` only checks bid claims deeply; non-bid claims fall through as supported. Relation, count, and event claims need semantic disposition before coverage finalization.
- Coverage is currently written before disposition. Final coverage should depend on supported or merged-supported claims, not raw emitted claims.
- `src/sec_graph/judgments/derive.py` is too thin for formal/informal and final-round boundaries. Expand it before bidder-row projection relies on it.
- `src/sec_graph/project/bidder_rows.py` uses raw min/max bid values and `admitted=True` too directly. It should consume accepted judgments and mark missing substrate as review burden.

Async loop:

- Build all Linkflow windows first, run independent provider calls under one event loop with a shared `AsyncOpenAI` client and a semaphore, then insert all successful responses in original window order.
- Keep retry inside each window call.
- If any window fails, write current-run failure artifacts and import no claims for that filing attempt.
- Provider artifacts should become attempt-scoped and run-dir-centered so retries and stale files cannot pollute summaries.

Latest pointer:

- Add `runs/latest/{slug}.json` as a mutable index over immutable run dirs.
- The pointer separates `latest_attempt` from `latest_trusted`.
- A new trusted run advances both. A failed run with a prior trusted run yields `stale_after_failure` and preserves `latest_trusted`. A failed run without a prior trusted run yields `failed_system`.

## Files To Expect

Create:

- `src/sec_graph/project/review_rows.py`
- `src/sec_graph/run/latest.py`
- `src/sec_graph/extract/quote_support.py` (only if a quote-support helper is shared between modules; see Task 3)
- `tests/test_review_rows.py`
- `tests/test_latest_pointer.py`
- `tests/test_linkflow_parallel.py`

Modify:

- `AGENTS.md`
- `CLAUDE.md`
- `docs/spec.md`
- `docs/llm-interface.md`
- `src/sec_graph/corpus.py`
- `src/sec_graph/schema/models/extraction.py`
- `src/sec_graph/schema/models/runtime.py`
- `src/sec_graph/schema/models/__init__.py` (DDL composition)
- `src/sec_graph/extract/applicability.py`
- `src/sec_graph/extract/source_support.py`
- `src/sec_graph/extract/disposition.py`
- `src/sec_graph/extract/llm/convert.py`
- `src/sec_graph/extract/llm/linkflow.py`
- `src/sec_graph/extract/pipeline.py`
- `src/sec_graph/reconcile/pipeline.py`
- `src/sec_graph/judgments/derive.py`
- `src/sec_graph/project/bidder_rows.py`
- `src/sec_graph/project/summaries.py`
- `src/sec_graph/validate/integrity.py`
- `src/sec_graph/cli/run_cmd.py`
- `src/sec_graph/run/io.py` only if a missing atomic helper is needed.
- `scripts/reference9_matrix.py`

Move:

- `docs/superpowers/specs/2026-05-05-semantic-disposition-validity-design.md` → `docs/superpowers/specs/legacy/`.

Delete:

- `tests/test_review_flags_and_verdicts.py` (replaced by `tests/test_review_rows.py`).
- The `review_flags` table DDL block (wherever it lives).
- `_check_semantic_claim_evidence`, `_check_bid_claim_semantics`, `_check_actor_relation_claim_semantics`, `_relation_supported_by_quote`, `_bid_context_supported_by_quote`, `_date_supported_by_quote`, `_number_supported_by_quote` from `validate/integrity.py`.
- `HardCheck.SEMANTIC_CLAIM_EVIDENCE` and `HardCheck.RULES_ONLY_SOUND` enum values.
- `_proof_verdict` and `thin_live_claim_warning` paths in `project/summaries.py`.
- The pre-disposition coverage write loop in `extract/llm/convert.py:_insert_llm_response_rows` and the helpers it owns (`_classify_unlinked_obligation`, `_window_supports_obligation`, `_metadata_basis`, `_folded_window_text`, `_insert_coverage_review_flag`, `_obligation_metadata` if no other caller).
- The `_ARTIFACT_ROOT = Path("artifacts/linkflow")` constant and all helpers that wrote there in `extract/llm/linkflow.py`.
- The `llm_config is None` branch in `extract/pipeline.py:run_extract`.
- The `artifacts/linkflow/{run_id}` glob in `cli/run_cmd.py:_write_failed_validation_proof`.
- Any other test that asserts `verdict`, `SOUND`, `SUSPECT`, `BLOCKED`, `REVIEW_REQUIRED`, `UNSOUND`, or rules-only proof behavior. Identify by Task 0 baseline failures and the Task 9 acceptance greps.

## Task 0: Preflight And Baseline

- [ ] **Confirm repo state.**

Run:

```bash
git status --short --branch
git log --oneline -5
```

If unrelated user edits exist, leave them in place and record them in the implementation notes.

- [ ] **Read current authority.**

Run:

```bash
sed -n '1,220p' AGENTS.md
sed -n '1,320p' docs/spec.md
sed -n '1,260p' docs/llm-interface.md
sed -n '1,360p' docs/superpowers/specs/2026-05-05-semantic-disposition-validity-design.md
```

- [ ] **Run focused baseline tests.**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 uv run pytest -q -p no:cacheprovider \
  tests/test_hard_reset_schema.py \
  tests/test_validation_semantics.py \
  tests/test_review_flags_and_verdicts.py \
  tests/test_run_failed_validation_proof.py \
  tests/test_llm_p8_contract.py \
  tests/test_run_kernel.py \
  tests/test_derived_judgments.py
```

Record failures before editing. Do not rewrite expected behavior until the failing assertion is tied to this plan.

## Task 1: Authority Hard Reset

**Files:**

- Move: `docs/superpowers/specs/2026-05-05-semantic-disposition-validity-design.md` to `docs/superpowers/specs/legacy/`.
- Modify: `AGENTS.md`
- Modify: `CLAUDE.md`
- Modify: `docs/spec.md`
- Modify: `docs/llm-interface.md`

This task lands first and on its own commit. It declares the new contract before any code changes.

- [ ] **Move the superseded spec.**

Run:

```bash
git mv docs/superpowers/specs/2026-05-05-semantic-disposition-validity-design.md \
       docs/superpowers/specs/legacy/2026-05-05-semantic-disposition-validity-design.md
```

The legacy file is preserved for historical reference only. No live doc may
reference it as authority.

- [ ] **Update authority chains.**

In `AGENTS.md` and `CLAUDE.md`, the authority chain becomes:

```text
docs/superpowers/specs/2026-05-03-pipeline-hard-reset-design.md
docs/spec.md
docs/llm-interface.md
quality_reports/plans/2026-05-07_validation_review_status_parallel_regions_plan.md
```

The 2026-05-05 spec is removed from the chain. No "see also" line.

- [ ] **Rewrite the verdict section in `docs/spec.md`.**

Replace the "Validation And Verdicts" section with the four run statuses
and the five pointer statuses from this plan's Locked Decisions. Old
vocabulary (`SOUND`, `SUSPECT`, `BLOCKED`, `REVIEW_REQUIRED`, `UNSOUND`,
`verdict`) does not appear in the rewritten section.

- [ ] **Rewrite the contract reference in `docs/llm-interface.md`.**

Replace the line that points to `2026-05-05-semantic-disposition-validity-design.md`
with a pointer to this plan. Drop any verdict vocabulary the file inherited
from the legacy spec.

- [ ] **Acceptance.**

After this task:

```bash
rg -n "SOUND|SUSPECT|BLOCKED|UNSOUND|REVIEW_REQUIRED|2026-05-05-semantic" \
   AGENTS.md CLAUDE.md docs --glob '!docs/superpowers/specs/legacy/**'
```

prints zero matches. The next tasks may now reference the new contract as
already-canonical.

## Task 2: Contract And Schema For Statuses And Review Rows

**Files:**

- Modify: `src/sec_graph/schema/models/runtime.py`
- Modify: `src/sec_graph/schema/models/__init__.py` (if it composes DDL)
- Modify: `src/sec_graph/schema/models/extraction.py` (only if `review_flags` DDL lives there)
- Create: `src/sec_graph/project/review_rows.py`
- Create: `tests/test_review_rows.py`
- Delete: `tests/test_review_flags_and_verdicts.py` (its semantics are reborn in `tests/test_review_rows.py`).
- Modify or delete: any other test asserting the old `verdict` field or the `review_flags` table.

- [ ] **Drop `review_flags` and add the new contract in one DDL pass.**

In the module that owns the runtime/projection DDL (currently `schema/models/runtime.py` for run metadata; the `review_flags` DDL is split between modules — locate it via `rg "CREATE TABLE review_flags" src`), delete the `review_flags` CREATE TABLE block and any FK references to it. Add the `review_rows` CREATE TABLE in its place.

```sql
CREATE TABLE review_rows (
  review_row_id VARCHAR PRIMARY KEY,
  run_id VARCHAR NOT NULL,
  deal_slug VARCHAR NOT NULL,
  review_status VARCHAR NOT NULL CHECK (review_status IN ('open', 'accepted', 'rejected', 'deferred')),
  review_type VARCHAR NOT NULL CHECK (review_type IN ('coverage', 'claim_disposition', 'judgment', 'projection', 'validation')),
  source_table VARCHAR NOT NULL,
  source_id VARCHAR NOT NULL,
  severity VARCHAR NOT NULL CHECK (severity IN ('review', 'info')),
  reason_code VARCHAR NOT NULL,
  message VARCHAR NOT NULL,
  review_question VARCHAR NOT NULL,
  claim_id VARCHAR,
  obligation_id VARCHAR,
  judgment_id VARCHAR,
  canonical_table VARCHAR,
  canonical_id VARCHAR,
  evidence_json VARCHAR,
  resolution_notes VARCHAR,
  resolved_by VARCHAR,
  resolved_at VARCHAR,
  created_at VARCHAR NOT NULL
);
```

There is no `review_flags` view, no compatibility column, and no `current` flag. Each row is created once with `review_status='open'` and is mutated only by reviewer action.

- [ ] **Add runtime status vocabulary.**

Add typed status models. `RunStatus` has exactly four values; `PointerStatus` extends it with `stale_after_failure`.

```python
RunStatus = Literal[
    "passed_clean",
    "needs_review",
    "high_burden",
    "failed_system",
]

PointerStatus = Literal[
    "passed_clean",
    "needs_review",
    "high_burden",
    "failed_system",
    "stale_after_failure",
]

TRUSTED_STATUSES = {"passed_clean", "needs_review", "high_burden"}


def status_from_open_review_count(open_review_count: int) -> RunStatus:
    if open_review_count == 0:
        return "passed_clean"
    if open_review_count <= 10:
        return "needs_review"
    return "high_burden"
```

A run record never carries `stale_after_failure`. Only `runs/latest/{slug}.json` may carry it.

- [ ] **Define one review-row artifact.**

The reviewer-facing rows should cover coverage misses, quarantined claims, judgment issues, projection issues, and structural review warnings in one shape:

```python
class ReviewRow(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    review_row_id: str
    run_id: str
    deal_slug: str
    review_status: Literal["open", "accepted", "rejected", "deferred"]
    review_type: Literal[
        "coverage",
        "claim_disposition",
        "judgment",
        "projection",
        "validation",
    ]
    source_table: str
    source_id: str
    severity: Literal["review", "info"]
    reason_code: str
    message: str
    review_question: str
    claim_id: str | None = None
    obligation_id: str | None = None
    judgment_id: str | None = None
    canonical_table: str | None = None
    canonical_id: str | None = None
    evidence_json: str | None = None
    resolution_notes: str | None = None
    resolved_by: str | None = None
    resolved_at: str | None = None
```

Persist it as JSONL and CSV in each run directory. Keep older diagnostic CSVs only if they remain internal proof artifacts; the review table is the user-facing surface.

- [ ] **Write red tests first.**

Add tests that assert:

- A run with zero review rows derives `passed_clean`.
- A run with 1 to 10 open review rows derives `needs_review`.
- A run with more than 10 open review rows derives `high_burden`.
- Review rows contain `review_status` on every row.
- Coverage, disposition, judgment, and projection issues all project into the same review table.

## Task 3: Claim Disposition Before Coverage Finalization

**Files:**

- Modify: `src/sec_graph/extract/disposition.py`
- Modify: `src/sec_graph/extract/llm/convert.py`
- Modify: `src/sec_graph/reconcile/pipeline.py`
- Modify: `src/sec_graph/validate/integrity.py` (delete duplicate semantic checks)
- Modify: `tests/test_validation_semantics.py`
- Modify or add: `tests/test_claim_disposition_gate.py`

- [ ] **Disposition is the single semantic gate.**

`extract/disposition.py` becomes the only place that evaluates whether a claim's `quote_text` supports its typed fields. The duplicate post-canonical helpers in `validate/integrity.py` (`_check_semantic_claim_evidence`, `_check_bid_claim_semantics`, `_check_actor_relation_claim_semantics`, `_relation_supported_by_quote`, `_bid_context_supported_by_quote`, `_date_supported_by_quote`, `_number_supported_by_quote`) are deleted in this task. The `HardCheck.SEMANTIC_CLAIM_EVIDENCE` enum value is deleted. Tests that asserted `HardCheck.SEMANTIC_CLAIM_EVIDENCE` are rewritten to assert disposition outcomes instead.

If a quote-support helper is genuinely shared between disposition and a structural integrity check (e.g., source-fingerprint validation), it lives in a new private module under `extract/` (e.g., `extract/quote_support.py`) and is imported once. No second copy.

- [ ] **Move semantic support decisions into disposition.**

`disposition.py` must evaluate bids, events, relations, and participation counts. Do not let non-bid claims fall through as supported.

Required behavior:

- A bid claim is supported only when the quote supports bidder, bid action/subtype, value when present, and date when present.
- A bid date may be null if the quote does not contain an explicit date. Do not invent a date from "later that day" unless the evidence window contains the antecedent date.
- An actor relation claim is supported only when the quote supports subject actor, relation meaning, and object actor or group.
- A `member_of` object must be a named actor/group, not a proposal description such as "joint acquisition proposal".
- A participation count claim is supported only when the quote contains count language plus the class/scope being claimed. If class is not specified, use `unknown`.
- An event claim is supported only when the quote supports the event subtype and the claimed date/window when present.

- [ ] **Delete the pre-disposition coverage write.**

In `extract/llm/convert.py:_insert_llm_response_rows`, the `coverage_results` INSERT loop (the block that walks `request.coverage_obligations` and writes `claims_emitted` / `missed_supported_obligation` / `no_supported_claim` / `ambiguous_support` rows inside the same transaction as claim insertion) is deleted in full. The companion `_classify_unlinked_obligation`, `_window_supports_obligation`, and `_metadata_basis` helpers used solely by that loop are deleted. `convert.py` after this task only writes `spans`, `claims`, `claim_coverage_links`, `claim_evidence`, and the typed claim row.

- [ ] **Write coverage exactly once, after disposition.**

A new `extract/disposition.py:finalize_coverage_after_disposition(conn, *, run_id, filing_id)` is the only producer of `coverage_results` rows for the run. It runs after `dispose_claims_for_filing` in the per-filing loop in `cli/run_cmd.py:run_pipeline`.

Mechanics: DELETE then INSERT. No UPDATE-in-place.

```python
def finalize_coverage_after_disposition(
    conn: duckdb.DuckDBPyConnection,
    *,
    run_id: str,
    filing_id: str,
) -> None:
    # Drop any prior coverage rows for this filing's applicable obligations.
    conn.execute(
        """
        DELETE FROM coverage_results
        WHERE obligation_id IN (
            SELECT obligation_id
            FROM coverage_obligations
            WHERE filing_id = ?
              AND applicability = 'applicable'
              AND current = true
        )
        """,
        [filing_id],
    )
    # For each applicable obligation, compute supported claim count and emit
    # exactly one coverage_results row.
    obligations = conn.execute(
        """
        SELECT obligation_id, importance, applicability_reason_code
        FROM coverage_obligations
        WHERE filing_id = ?
          AND applicability = 'applicable'
          AND current = true
        ORDER BY obligation_id
        """,
        [filing_id],
    ).fetchall()
    for obligation_id, importance, applicability_reason_code in obligations:
        supported_count = int(
            conn.execute(
                """
                SELECT count(*)
                FROM claim_coverage_links
                JOIN claim_dispositions
                  ON claim_dispositions.claim_id = claim_coverage_links.claim_id
                 AND claim_dispositions.current = true
                WHERE claim_coverage_links.obligation_id = ?
                  AND claim_coverage_links.current = true
                  AND claim_dispositions.disposition IN ('supported', 'merged_duplicate')
                """,
                [obligation_id],
            ).fetchone()[0]
        )
        result, reason_code, reason = _classify_obligation(
            obligation_id, supported_count, applicability_reason_code, conn
        )
        conn.execute(
            "INSERT INTO coverage_results VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [
                _next_coverage_id(conn, obligation_id),
                run_id,
                obligation_id,
                result,
                reason_code,
                reason,
                supported_count,
                True,
            ],
        )
```

The final implementation must use the repo's deterministic ID helpers (`make_id`) and existing table names. Obligations with `applicability='not_applicable'` get no row, matching the existing structural check.

- [ ] **`claim_coverage_links` for rejected claims stays as audit.**

Rows in `claim_coverage_links` for claims later disposed `rejected_unsupported` or `queued_ambiguity` are not deleted. They remain as link audit. `coverage_results.claim_count` counts only supported claims, and the integrity check at line 200 in `validate/integrity.py` (claims_emitted requires supported linked claims) continues to hold because supported_count drives the result.

- [ ] **Keep all-review empty graphs explicit.**

If no supported claims remain for a filing, choose `failed_system` only when required structural artifacts cannot be built. If the run can build a valid empty/minimal graph with review rows explaining the missing support, publish it as `needs_review` or `high_burden`.

- [ ] **Test the concrete failure examples.**

Add fixture-level tests for:

- A relation quote that does not name the subject actor is quarantined and becomes a review row.
- A bid quote saying only "later that same day" cannot support an explicit `bid_date` unless the evidence includes the date.
- A count obligation does not become covered through an unsupported count claim.

## Task 4: Validation Split

**Files:**

- Modify: `src/sec_graph/validate/integrity.py`
- Modify: `tests/test_validation_semantics.py`
- Modify: `tests/test_run_failed_validation_proof.py`

By the time this task runs, Task 3 has already deleted the post-canonical semantic helpers and `HardCheck.SEMANTIC_CLAIM_EVIDENCE`. This task only handles the structural side. Also delete `HardCheck.RULES_ONLY_SOUND`; it is unreachable once rules-only mode is removed in Task 8's preamble.

- [ ] **Split validation output into hard failures and review items.**

Change validation from one failure list into a shape like:

```python
class ValidationResult(BaseModel):
    passed: bool
    system_failures: list[ValidationFinding]
    review_items: list[ValidationFinding]

    @property
    def open_review_count(self) -> int:
        return len(self.review_items)
```

`passed` means `len(system_failures) == 0`.

- [ ] **Classify coverage findings.**

`missed_supported_obligation`, `ambiguous_support`, and `no_supported_claim` for required or important obligations become review items when source proof and canonical tables remain structurally valid.

- [ ] **Classify claim findings.**

Rejected or queued claims are review items when they are quarantined. They are system failures if they leak into canonical tables, projection rows, or `claims_emitted` coverage proof.

- [ ] **Classify projection findings.**

Review-severity projection flags are review items. A projection row with missing evidence, unsupported claim dependency, or unaccepted judgment dependency is a system failure.

- [ ] **Keep structural failures hard.**

These remain `failed_system`:

- Invalid provider payload shape.
- Broken source hash or quote span.
- Missing required run artifact.
- Duplicate IDs in proof tables.
- Missing coverage result rows for applicable obligations.
- `claims_emitted` links to unsupported claims.
- Unsupported claims in canonical tables.
- Row evidence gaps.
- Artifact digest mismatch.
- Bad resume/config identity.

## Task 5: Rule And Taxonomy Repairs

**Files:**

- Modify: `src/sec_graph/schema/models/extraction.py`
- Modify: `src/sec_graph/extract/source_support.py`
- Modify: `src/sec_graph/extract/applicability.py`
- Modify: `docs/spec.md`
- Modify: `docs/llm-interface.md`
- Modify: prompt/rule text if present in this repo.
- Modify tests that encode old taxonomy expectations.

- [ ] **Tighten count applicability.**

Count obligations must require count language. Stage words alone are not enough.

Target behavior:

```python
def has_count_language(text: str) -> bool:
    return bool(COUNT_WORD_OR_NUMBER_RE.search(text) and PARTICIPATION_NOUN_RE.search(text))
```

Count cues should include numeric digits and ordinary written counts. Keep the regex conservative so vague stage descriptions do not create false obligations.

- [ ] **Allow unknown count actor class.**

Extend `participation_count.actor_class` to include `"unknown"` and update docs/tests/prompt text:

```python
ActorClass = Literal["financial", "strategic", "mixed", "unknown"]
```

Use `"unknown"` when the quote says parties, buyers, bidders, or potential acquirors without class.

- [ ] **Add missing event subtypes required by obligations.**

Add narrow event subtypes for:

- `go_shop_period`
- `amendment`

Do not add workbook-style outcome/dropout labels as event subtypes.

- [ ] **Fix buyer-group and coalition rules.**

Provider-facing rules should say:

- Create a group actor only when the filing treats the group as the bidding unit.
- Use `member_of` only when both sides are actors or actor groups.
- Do not use proposal descriptions as relation objects.
- If a filing describes a joint proposal but not a stable group actor, leave the relation unclaimed or create a review row after source-backed disposition rejects the malformed relation.

Do not add broad new relation labels until raw filing examples justify them.

## Task 6: Derived Judgments And Bidder Projection

**Files:**

- Modify: `src/sec_graph/judgments/derive.py`
- Modify: `src/sec_graph/project/bidder_rows.py`
- Modify: `src/sec_graph/project/summaries.py`
- Modify: `tests/test_derived_judgments.py`
- Modify or add: bidder projection tests.

- [ ] **Expand derived judgment rules.**

Formal/informal judgments must consider event subtype, final-round boundary, bid value, explicit final/best-and-final source cues, and process context. Do not classify solely from subtype and raw value.

Accepted judgment example:

```python
Judgment(
    judgment_key="bid_formality",
    judgment_value="formal",
    judgment_status="accepted",
    rule_id="bid_formality_final_round_with_value_v1",
    basis_json=json.dumps(
        {
            "bid_id": bid_id,
            "event_subtype": event_subtype,
            "has_value": True,
            "final_round_boundary": final_round_boundary_id,
            "source_cues": source_cues,
        },
        sort_keys=True,
    ),
)
```

- [ ] **Make missing judgment substrate review burden.**

When a bidder row cannot determine formality, admitted status, or projected fate from accepted judgments, emit a review row instead of filling in an invented value.

- [ ] **Stop projecting directly from raw bid min/max when accepted judgment is required.**

Bidder projection may use canonical bid facts, but row-level interpretation must point to accepted judgments or create review rows explaining the missing substrate.

## Task 7: Consolidated Review Output And Status Publication

**Files:**

- Create: `src/sec_graph/project/review_rows.py`
- Modify: `src/sec_graph/project/summaries.py`
- Modify: `src/sec_graph/cli/run_cmd.py`
- Create: `src/sec_graph/run/latest.py`
- Create: `tests/test_review_rows.py`
- Create: `tests/test_latest_pointer.py`
- Modify: `scripts/reference9_matrix.py`

- [ ] **Project consolidated review rows.**

Build review rows from:

- unresolved applicable coverage results,
- rejected or queued claim dispositions,
- review-required judgments,
- projection review flags,
- non-hard validation review items.

Write:

- `{run_dir}/review_rows.jsonl`
- `{run_dir}/review_rows.csv`

- [ ] **Derive run status after review rows are written.**

The run record is one of four statuses. `stale_after_failure` is never produced here.

```python
def classify_completed_run(validation: ValidationResult, open_review_count: int) -> RunStatus:
    if validation.system_failures:
        return "failed_system"
    return status_from_open_review_count(open_review_count)
```

- [ ] **Let review-only runs finish.**

`run_cmd.py` should only raise before projection for system failures. For review-only burden, it should write canonical artifacts, projection artifacts, review rows, proof summary, and latest pointer.

- [ ] **Add latest pointer files.**

Use `sec_graph.run.io.atomic_write_json` to write `runs/latest/{slug}.json`:

```json
{
  "schema_version": "sec_graph_latest_pointer_v1",
  "deal_slug": "mac-gray",
  "pointer_status": "needs_review",
  "latest_attempt": {
    "run_id": "20260507T120000Z_mac-gray",
    "run_dir": "runs/20260507T120000Z_mac-gray",
    "status": "needs_review"
  },
  "latest_trusted": {
    "run_id": "20260507T120000Z_mac-gray",
    "run_dir": "runs/20260507T120000Z_mac-gray",
    "status": "needs_review"
  },
  "updated_at": "2026-05-07T12:00:00Z"
}
```

Pointer-status decision tree:

| Latest attempt status | Prior trusted run | `pointer_status`        | `latest_attempt`     | `latest_trusted`             |
|-----------------------|-------------------|-------------------------|----------------------|------------------------------|
| trusted (3 cases)     | any               | mirrors attempt status  | new attempt          | new attempt                  |
| `failed_system`       | none              | `failed_system`         | new attempt          | absent                       |
| `failed_system`       | exists            | `stale_after_failure`   | new attempt          | preserved (unchanged)        |

Before promoting a prior trusted run, verify its `run_dir` exists on disk and its `stage_artifacts.jsonl` digest still validates. If verification fails, the pointer is treated as if no prior trusted run exists and the new pointer is `failed_system`. The verified-but-missing case is itself a `failed_system` artifact integrity issue and is recorded as such on the failing run.

- [ ] **Update reference matrix script.**

`scripts/reference9_matrix.py` must read `runs/latest/{slug}.json` instead of choosing the lexicographically newest run directory.

## Task 8: Parallel Linkflow Region Requests

**Files:**

- Modify: `src/sec_graph/extract/llm/linkflow.py`
- Modify: `src/sec_graph/extract/pipeline.py` (delete rules-only branch)
- Modify: `src/sec_graph/cli/run_cmd.py`
- Create: `tests/test_linkflow_parallel.py`
- Modify: `tests/test_hard_reset_schema.py`
- Modify: `tests/test_run_kernel.py`
- Modify: `tests/test_run_failed_validation_proof.py`
- Delete: any test that exercised rules-only proof or asserted the legacy `artifacts/linkflow/{run_id}` path.

- [ ] **Delete rules-only LLM mode.**

In `extract/pipeline.py:run_extract`, drop the `llm_config is None` branch. The signature becomes:

```python
def run_extract(
    conn: duckdb.DuckDBPyConnection,
    *,
    filing_id: str,
    run_id: str,
    llm_config: LLMProviderConfig,
    request_mode: str = DEFAULT_REQUEST_MODE,
) -> list[str]:
```

`llm_config` is required. The function builds the evidence map, then delegates to the new batch helper in `linkflow.py`. Its return shape stays `list[str]` (claim_ids in original window order) so `run_pipeline`'s `append_progress(... artifact_digest=str(len(claim_ids)))` call is unchanged.

- [ ] **Delete the legacy provider artifact path.**

Delete the module-level constant `_ARTIFACT_ROOT = Path("artifacts/linkflow")` in `extract/llm/linkflow.py` and every code path that wrote to it (`_artifact_dir`, `_write_failure_artifact`, `_write_contract_failure`, `_write_success_artifact`'s old base path). Their replacements write under `{run_dir}/linkflow/{deal_slug}/{request_id}/` and call `record_artifact` for each artifact so they appear in `stage_artifacts.jsonl`.

In `cli/run_cmd.py:_write_failed_validation_proof`, delete the `artifacts/linkflow/{run_id}` glob. The `artifact_counts` block reads counts from `stage_artifacts.jsonl` filtered by `artifact_kind='linkflow_attempt'`.

- [ ] **Replace per-request event loops with one batch event loop.**

Add an async batch helper under `linkflow.py`:

```python
class WindowBundle(BaseModel):
    sequence: int
    request_id: str
    request: LLMRequest
    response: LLMResponse | None = None
    error_message: str | None = None
    artifact_path: str | None = None


async def extract_linkflow_windows(
    windows: Sequence[LLMRequest],
    config: LLMConfig,
    run_id: str,
    max_concurrency: int,
) -> list[WindowBundle]:
    semaphore = asyncio.Semaphore(max_concurrency)
    async with make_async_openai_client(config) as client:
        tasks = [
            _extract_one_window(sequence, request, client, semaphore, config, run_id)
            for sequence, request in enumerate(windows, start=1)
        ]
        bundles = await asyncio.gather(*tasks)
    return sorted(bundles, key=lambda bundle: bundle.sequence)
```

The final code should use the repo's current request/response model names.

- [ ] **Keep retries inside each window.**

Use the existing retry/backoff logic for each `_extract_one_window`.

- [ ] **Bound concurrency with an environment variable.**

Default:

```python
SEC_GRAPH_REGION_MAX_CONCURRENCY = 2
```

Validate that the value is a positive integer. Cap high-cost reasoning modes lower if the existing config already has a model-cost boundary.

- [ ] **Insert only after all provider calls succeed.**

After `asyncio.gather` returns:

- If any bundle has an error, write failure artifacts and raise a system failure. Import no claims for that filing attempt.
- If all bundles succeeded, open one DuckDB transaction.
- Insert responses sorted by `sequence`.
- Commit once.
- Write success artifacts after commit with inserted claim counts.

- [ ] **Make artifacts attempt-scoped and run-dir-centered.**

Use a path like:

```text
{run_dir}/linkflow/{deal_slug}/{request_id}/attempt-001_success.json
{run_dir}/linkflow/{deal_slug}/{request_id}/attempt-001_failure.json
```

Do not count old globbed provider artifacts in current-run summaries. Count only current-run ledgered artifacts.

- [ ] **Test concurrency and deterministic import.**

Add tests that prove:

- Two windows can complete out of order but insert in original window order.
- `SEC_GRAPH_REGION_MAX_CONCURRENCY=1` serializes provider calls.
- `SEC_GRAPH_REGION_MAX_CONCURRENCY=2` allows two concurrent calls.
- A failed window imports no claims.
- DuckDB writes happen on one caller thread after all provider calls complete.
- Failed-validation proof counts only ledgered current-run artifacts.

## Task 9: Final Hard-Delete Sweep

**Files:**

- Any file in `AGENTS.md`, `CLAUDE.md`, `docs/` (excluding `docs/superpowers/specs/legacy/**`), `src/`, `tests/`, `scripts/`, `quality_reports/` (excluding `quality_reports/plans/legacy/**`) that still names old vocabulary, old tables, old artifact paths, or old code paths.

This task is acceptance-by-grep. The previous tasks did targeted edits; this task confirms nothing was missed.

- [ ] **Acceptance grep 1 — vocabulary.**

```bash
rg -n "SOUND|SUSPECT|BLOCKED|UNSOUND|REVIEW_REQUIRED|\\bverdict\\b" \
   AGENTS.md CLAUDE.md docs src tests scripts quality_reports \
   --glob '!docs/superpowers/specs/legacy/**' \
   --glob '!quality_reports/plans/legacy/**'
```

Must print zero matches. `verdict` is renamed to `status` everywhere it was a field name. Every match is hard-deleted or renamed; no comment retains the old word.

- [ ] **Acceptance grep 2 — deleted code paths.**

```bash
rg -n "review_flags|RULES_ONLY_SOUND|SEMANTIC_CLAIM_EVIDENCE|thin_live_claim_warning|artifacts/linkflow|rules-only|rules only" \
   src tests scripts
```

Must print zero matches in live code. Every match is deleted, including imports, helper definitions, comments, and CLI flags.

- [ ] **Acceptance grep 3 — corpus skeleton.**

`src/sec_graph/corpus.py` currently emits a `verdict` field with value `"BLOCKED"`. Replace with the `status` field carrying the new four-status vocabulary. If the corpus skeleton produces "we have nothing to say yet" rows, use `failed_system` for those rows and accept that the per-deal corpus integration will be re-evaluated after this refactor lands.

- [ ] **Acceptance grep 4 — generated artifacts.**

Tracked artifacts (anything in `tests/fixtures/` or committed JSON snapshots) that contain old vocabulary are regenerated against the new contract or deleted. Gitignored `runs/` and `artifacts/` directories are wiped:

```bash
rm -rf runs artifacts
```

These directories are gitignored; reruns produce fresh content under the new contract. There is no migration path for in-flight runs.

- [ ] **Acceptance grep 5 — `__init__.py` exports.**

Confirm no module re-exports `review_flags`, `verdict`, `_proof_verdict`, `_check_semantic_claim_evidence`, or any other deleted name.

```bash
rg -n "review_flags|verdict|_proof_verdict|SEMANTIC_CLAIM_EVIDENCE" \
   src/sec_graph/**/__init__.py
```

Must print zero matches.

## Task 10: Verification

- [ ] **Run focused tests.**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 uv run pytest -q -p no:cacheprovider \
  tests/test_hard_reset_schema.py \
  tests/test_claim_disposition_gate.py \
  tests/test_validation_semantics.py \
  tests/test_review_rows.py \
  tests/test_latest_pointer.py \
  tests/test_linkflow_parallel.py \
  tests/test_run_failed_validation_proof.py \
  tests/test_run_kernel.py \
  tests/test_derived_judgments.py \
  tests/test_llm_p8_contract.py
```

- [ ] **Run full suite.**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 uv run pytest -q -p no:cacheprovider
```

- [ ] **Run a local no-provider proof path if fixtures support it.**

Use the repo's existing no-live-provider tests or fixture CLI path to prove a review-only run publishes canonical artifacts, review rows, proof summary, and latest pointer.

- [ ] **Run live Linkflow smoke only when runtime secrets are already available.**

Do not print secrets. Use environment variables only. The smoke target should contain at least two independent regions so the parallel window path is exercised.

Expected live outcome:

- Provider requests overlap up to `SEC_GRAPH_REGION_MAX_CONCURRENCY`.
- DB import order is deterministic.
- Review-only issues produce `needs_review` or `high_burden`, not `failed_system`.
- A forced provider failure produces `failed_system` or `stale_after_failure` according to latest pointer state.

## Stop Conditions

Stop and report instead of guessing if:

- A raw filing example shows that a proposed taxonomy change would encode a deal-specific workaround.
- The implementation needs a new canonical relation label beyond `member_of` and existing source-backed relations.
- A run can only publish by accepting unsupported claims into canonical rows.
- Parallel provider code would require sharing one DuckDB connection across async tasks.
- Existing run-kernel digest verification is insufficient to trust latest pointers and the missing check cannot be implemented in the same refactor.

## Completion Criteria

The refactor is complete when all of the following hold simultaneously:

- Live docs describe only the new run-status and pointer-status contract. The 2026-05-05 spec lives under `docs/superpowers/specs/legacy/` and no live doc references it.
- The `review_flags` DuckDB table no longer exists. `review_rows` is the only review surface.
- `extract/disposition.py` is the sole semantic gate. The deleted helpers in `validate/integrity.py` no longer exist; `HardCheck.SEMANTIC_CLAIM_EVIDENCE` no longer exists.
- `coverage_results` is written exactly once per applicable obligation, after disposition, by `finalize_coverage_after_disposition`. The pre-disposition coverage write in `convert.py` no longer exists.
- Validation distinguishes `system_failures` from review burden.
- Review-only runs publish canonical graph artifacts, bidder projections, `review_rows.jsonl` and `review_rows.csv`, proof summary, and `runs/latest/{slug}.json`.
- System failures do not overwrite `latest_trusted`. `stale_after_failure` is observable in a tested pointer scenario; no run record carries that value.
- Rules-only LLM mode is gone. `extract/pipeline.py:run_extract` requires `llm_config`.
- Provider artifacts live only under `{run_dir}/linkflow/...` and are recorded in `stage_artifacts.jsonl`. The `artifacts/linkflow/{run_id}` path no longer exists in source.
- Count applicability, `unknown` count class, go-shop and amendment subtypes, relation support, bid-date support, and judgment substrate behavior are covered by tests.
- Linkflow region calls run concurrently within a filing under bounded concurrency. The outer per-filing loop is sequential. DuckDB writes happen on one caller thread after all provider calls complete.
- All Task 9 acceptance greps return zero matches.
- The full test suite passes:

```bash
PYTHONDONTWRITEBYTECODE=1 uv run pytest -q -p no:cacheprovider
```
