# Agentic Review Compiler Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the clean-slate SEC merger-filing agentic review compiler described by the two specs, using the completed Linkflow probe as the provider contract gate.

**Architecture:** Implement a new Python package, `sec_review_compiler`, rather than reviving archived source trees. The system is filing-first and deal-room-first: raw filing packages become atlases and retrieval indexes; agents propose claim attempts through Linkflow tool loops; deterministic Python owns source spans, evidence binding, verdict aggregation, coverage, canonical compilation, exports, and publication. The committed Linkflow probe run `runs/linkflow-probe/20260508T123815Z/` is the evidence that Tier 1 Linkflow capabilities are usable.

**Tech Stack:** Python 3.12, Pydantic v2, DuckDB, OpenAI Python SDK pointed at Linkflow, pytest, local filesystem run directories, CSV/JSONL audit artifacts.

---

## 0. `/goal` Objective To Paste

Use this as the top-level `/goal` objective:

```text
Implement the clean-slate SEC filing agentic review compiler in /Users/austinli/Projects/sec_graph on branch clean-slate/agentic-review-compiler.

Read first:
- docs/superpowers/specs/2026-05-08-agentic-review-compiler-design.md
- docs/superpowers/specs/2026-05-08-linkflow-api-probe-spec.md
- runs/linkflow-probe/20260508T123815Z/README.md
- runs/linkflow-probe/20260508T123815Z/capability_matrix.json

Treat the prior pipeline as out of scope. Do not inspect or restore archived source code unless Austin explicitly asks for donor analysis. Implement a new package named sec_review_compiler.

Required constraints:
- Use Linkflow direct SDK calls only for model calls.
- Do not write, print, commit, or persist API keys.
- Accept Linkflow credentials only through environment variables.
- Use strict structured outputs for extractor and verifier responses.
- Use a plain Python orchestrator for V1.
- Do not add fallback extraction modes, legacy readers, loose JSON parsers, or compatibility shims.
- Filing text is truth. Python owns source coordinates, evidence identity, state transitions, canonical rows, and publication.
- Agents emit proposals only. They never write DuckDB directly.
- Verifier partial corrections create new claim attempts; they do not mutate accepted claims.
- No latest-verdict-wins behavior.
- Coverage gaps are first-class records.
- Every accepted canonical row must trace to exact evidence.

Use parallel subagents where useful:
- Lane A: package skeleton, run kernel, CLI, config, artifact IO.
- Lane B: filing package, atlas, source spans, retrieval index, deterministic tools.
- Lane C: deal-room DuckDB schema, lifecycle, coverage, conflicts, human decisions.
- Lane D: Linkflow adapter, tool loop, agent prompts, extractor/verifier structured outputs.
- Lane E: orchestrator, vertical slice, canonical compiler, exports.
- Lane F: tests, security scan, docs, final acceptance audit.

Commit after each completed phase. Stop and report before moving past any failed phase gate.
```

## 1. Current Starting State

The repository is intentionally small and clean:

- specs:
  - `docs/superpowers/specs/2026-05-08-agentic-review-compiler-design.md`
  - `docs/superpowers/specs/2026-05-08-linkflow-api-probe-spec.md`
- Linkflow probe harness:
  - `linkflow_probe/`
  - `tests/test_sanitize.py`
  - `tests/test_schema_transforms.py`
  - `tests/test_matrix_report.py`
- committed probe evidence:
  - `runs/linkflow-probe/20260508T123815Z/capability_matrix.json`
  - `runs/linkflow-probe/20260508T123815Z/probe_manifest.json`
  - `runs/linkflow-probe/20260508T123815Z/README.md`

The probe gate is `GO`. Tier 1 support is recorded for SDK connectivity, reasoning levels, strict structured output, nested schemas, single tool call, multi-turn tool loops, tool loop plus final structured output, error taxonomy, and bounded concurrency through 8 synthetic calls.

## 2. Target File Structure

Create this package structure. Keep files small and responsibility-bounded.

```text
src/sec_review_compiler/
  __init__.py
  __main__.py
  cli.py
  config.py
  errors.py
  run/
    __init__.py
    ids.py
    manifest.py
    io.py
  filing/
    __init__.py
    package.py
    atlas.py
    spans.py
    examples.py
  retrieval/
    __init__.py
    index.py
    tools.py
  store/
    __init__.py
    schema.py
    migrations.py
    repository.py
    lifecycle.py
  llm/
    __init__.py
    linkflow.py
    schemas.py
    tool_loop.py
  agents/
    __init__.py
    roles.py
    prompts.py
    outputs.py
  orchestration/
    __init__.py
    orchestrator.py
    coverage.py
    verifier.py
    consistency.py
  canonical/
    __init__.py
    models.py
    compiler.py
  exports/
    __init__.py
    review.py
    human_decisions.py
tests/
  fixtures/
    synthetic_filing.txt
  test_run_kernel.py
  test_filing_atlas.py
  test_retrieval_tools.py
  test_deal_room_schema.py
  test_lifecycle.py
  test_linkflow_adapter.py
  test_tool_loop_offline.py
  test_orchestrator_vertical_slice.py
  test_canonical_compile.py
  test_exports.py
```

## 3. Phase Gates

Each phase must end with:

```bash
python3 -m pytest -q
git status --short --branch
git grep -n 'sk-\|LINKFLOW_API_KEY=.*sk\|Authorization: Bearer' HEAD -- \
  ':!docs/superpowers/plans/2026-05-08-agentic-review-compiler-goal-implementation.md' || true
```

Expected:

- pytest exits 0;
- no unexpected dirty files except the current phase changes before commit;
- secret scan returns no real credential.

After each phase passes:

```bash
git add <phase files>
git commit -m "<phase commit message>"
git push
```

## 4. Phase 0 - Freeze Provider Evidence And Update Authority

**Purpose:** Convert the Linkflow `GO` probe from an external fact into implementation authority.

**Files:**

- Modify: `docs/superpowers/specs/2026-05-08-agentic-review-compiler-design.md`
- Modify: `docs/superpowers/specs/2026-05-08-linkflow-api-probe-spec.md`
- Create: `docs/superpowers/plans/2026-05-08-agentic-review-compiler-goal-implementation.md` if this file is absent in the execution branch

- [ ] Record in the compiler spec that probe run `20260508T123815Z` returned `GO`.
- [ ] Replace any wording that says Tier 1 Linkflow support is unknown with wording that says Tier 1 is proven for the committed run, while long-context and corpus-scale behavior remain unproven.
- [ ] Keep the Linkflow probe as a reusable regression harness; do not delete it.
- [ ] Run:

```bash
python3 -m linkflow_probe summarize runs/linkflow-probe/20260508T123815Z
python3 -m pytest -q tests/test_sanitize.py tests/test_schema_transforms.py tests/test_matrix_report.py
```

Expected:

- summary prints `Gate: GO`;
- tests pass.

- [ ] Commit:

```bash
git add docs/superpowers/specs docs/superpowers/plans
git commit -m "docs: record Linkflow GO gate for compiler implementation"
```

## 5. Phase 1 - Package Skeleton, CLI, Run Kernel

**Purpose:** Establish the new package, deterministic run ids, run manifests, atomic writes, and CLI shell without extraction behavior.

**Files:**

- Modify: `pyproject.toml`
- Create: all files under `src/sec_review_compiler/run/`
- Create: `src/sec_review_compiler/__init__.py`
- Create: `src/sec_review_compiler/__main__.py`
- Create: `src/sec_review_compiler/cli.py`
- Create: `src/sec_review_compiler/config.py`
- Create: `src/sec_review_compiler/errors.py`
- Test: `tests/test_run_kernel.py`

- [ ] Add package metadata in `pyproject.toml` for `src` layout and dependencies: `duckdb`, `pydantic`, `openai`, `pytest`.
- [ ] Implement `RunId` parsing in `run/ids.py`. Required accepted shape: `YYYYMMDDTHHMMSSZ_<slug>_<8hex>`.
- [ ] Implement `RunClock` in `run/ids.py`; it returns deterministic timestamps derived from the run id unless explicitly created for a live run.
- [ ] Implement atomic JSON/text writes in `run/io.py` using temp file plus replace.
- [ ] Implement `RunManifest` in `run/manifest.py` with `run_id`, `started_at`, `config_hash`, `linkflow_probe_run_id`, and `package_version`.
- [ ] Implement `python3 -m sec_review_compiler init-run --deal-slug synthetic-demo --run-root runs/dev`.
- [ ] Write tests that assert:
  - invalid run ids fail;
  - manifests include `linkflow_probe_run_id="20260508T123815Z"`;
  - atomic write leaves only the final file;
  - CLI creates `runs/dev/<run_id>/run_manifest.json`.
- [ ] Run:

```bash
python3 -m pytest -q tests/test_run_kernel.py
python3 -m sec_review_compiler init-run --deal-slug synthetic-demo --run-root runs/dev
```

Expected:

- tests pass;
- CLI prints the created run directory;
- manifest exists under `runs/dev/`.

- [ ] Commit:

```bash
git add pyproject.toml src/sec_review_compiler tests/test_run_kernel.py
git commit -m "feat: add compiler package and run kernel"
```

## 6. Phase 2 - Filing Package, Source Spans, Atlas

**Purpose:** Make filing text the immutable source unit before any agent exists.

**Files:**

- Create: `src/sec_review_compiler/filing/package.py`
- Create: `src/sec_review_compiler/filing/atlas.py`
- Create: `src/sec_review_compiler/filing/spans.py`
- Create: `src/sec_review_compiler/filing/examples.py`
- Create: `tests/fixtures/synthetic_filing.txt`
- Test: `tests/test_filing_atlas.py`

- [ ] Add a synthetic filing fixture containing:
  - a transaction heading;
  - a background section;
  - two paragraphs with dates and Buyer A;
  - one table-like block;
  - one exhibit marker.
- [ ] Implement `FilingPackage` with `filing_id`, `raw_text`, `raw_sha256`, `normalized_text`, and `paragraphs`.
- [ ] Implement paragraph splitting that preserves paragraph order and character start/end offsets.
- [ ] Implement `SourceSpan.identity()` as `sha256(filing_id + char_start + char_end + quote_text_hash)`.
- [ ] Implement `Atlas` records for `sections`, `paragraphs`, `tables`, `source_spans`, `section_candidates`, and `atlas_warnings`.
- [ ] Ensure atlas construction never drops ambiguous sections; it records an `atlas_warning`.
- [ ] Write tests that assert:
  - source span offsets slice the original text exactly;
  - text-only duplicate quotes produce distinct evidence ids when coordinates differ;
  - ambiguous headings create warnings, not silent skips;
  - a missing substantive tender-offer exhibit raises a typed error.
- [ ] Run:

```bash
python3 -m pytest -q tests/test_filing_atlas.py
```

Expected: all atlas tests pass.

- [ ] Commit:

```bash
git add src/sec_review_compiler/filing tests/fixtures tests/test_filing_atlas.py
git commit -m "feat: add filing package and atlas"
```

## 7. Phase 3 - Retrieval Index And Deterministic Tools

**Purpose:** Give agents deterministic local tools instead of asking them to rely on memory or hidden reasoning.

**Files:**

- Create: `src/sec_review_compiler/retrieval/index.py`
- Create: `src/sec_review_compiler/retrieval/tools.py`
- Test: `tests/test_retrieval_tools.py`

- [ ] Implement `RetrievalIndex.from_atlas(atlas)` with literal lookup, regex lookup, BM25-style token scoring, section fetch, paragraph fetch, neighborhood fetch, and table fetch.
- [ ] Implement `verify_quote(filing_id, quote_text)` returning `verbatim_present`, `positions`, `paragraph_ids`, and `ambiguity`.
- [ ] Implement `parse_date`, `parse_money`, and `parse_count` with deterministic conservative outputs.
- [ ] Implement `normalize_actor_label` as filing-local canonicalization only; cross-deal actor pooling is not in this phase.
- [ ] Write tests that assert:
  - exact quote lookup returns paragraph ids and coordinates;
  - ambiguous duplicate quotes are flagged;
  - regex search cannot mutate source text;
  - `parse_date("early March 2026")` returns an ambiguous structured value, not a fake exact date;
  - `parse_money("$14.00 per share")` preserves unit;
  - `parse_count("between 20 and 25 parties")` returns min 20 and max 25.
- [ ] Run:

```bash
python3 -m pytest -q tests/test_retrieval_tools.py
```

Expected: all retrieval/tool tests pass.

- [ ] Commit:

```bash
git add src/sec_review_compiler/retrieval tests/test_retrieval_tools.py
git commit -m "feat: add retrieval index and deterministic tools"
```

## 8. Phase 4 - Deal-Room DuckDB Schema And Lifecycle

**Purpose:** Store claim attempts, evidence bindings, verdicts, coverage, conflicts, and human decisions as first-class append-oriented records.

**Files:**

- Create: `src/sec_review_compiler/store/schema.py`
- Create: `src/sec_review_compiler/store/migrations.py`
- Create: `src/sec_review_compiler/store/repository.py`
- Create: `src/sec_review_compiler/store/lifecycle.py`
- Test: `tests/test_deal_room_schema.py`
- Test: `tests/test_lifecycle.py`

- [ ] Define DuckDB tables:
  - `source_records`;
  - `claim_attempts`;
  - `evidence_bindings`;
  - `normalized_values`;
  - `verifier_verdicts`;
  - `verdict_aggregates`;
  - `coverage_checks`;
  - `conflicts`;
  - `human_decisions`;
  - `canonical_rows`;
  - `canonical_row_evidence`.
- [ ] Define lifecycle states:
  - `proposed`;
  - `binding_failed`;
  - `bound`;
  - `verified_confirmed`;
  - `verified_partial`;
  - `verified_rejected`;
  - `escalated`;
  - `consistent`;
  - `accepted`;
  - `superseded`.
- [ ] Enforce append-oriented attempts: inserting a correction creates a new `attempt_id`.
- [ ] Implement aggregation policy:
  - `confirm` with no conflict can become `consistent`;
  - `partial` creates a corrected attempt or escalates;
  - `reject` quarantines unless human decision overrides;
  - disagreement escalates;
  - recency alone never decides.
- [ ] Write tests that assert:
  - `attempt_id` and `claim_fingerprint` are distinct;
  - duplicate semantic facts from two agents are separate attempts;
  - partial correction creates a new attempt;
  - latest-verdict-wins is impossible;
  - `failed_to_check` coverage blocks trusted publication.
- [ ] Run:

```bash
python3 -m pytest -q tests/test_deal_room_schema.py tests/test_lifecycle.py
```

Expected: schema and lifecycle tests pass.

- [ ] Commit:

```bash
git add src/sec_review_compiler/store tests/test_deal_room_schema.py tests/test_lifecycle.py
git commit -m "feat: add deal-room schema and claim lifecycle"
```

## 9. Phase 5 - Linkflow Adapter, Tool Loop, Structured Agent Outputs

**Purpose:** Convert the probe's proven Linkflow behavior into production-grade adapter code for compiler agents.

**Files:**

- Create: `src/sec_review_compiler/llm/linkflow.py`
- Create: `src/sec_review_compiler/llm/schemas.py`
- Create: `src/sec_review_compiler/llm/tool_loop.py`
- Create: `src/sec_review_compiler/agents/roles.py`
- Create: `src/sec_review_compiler/agents/prompts.py`
- Create: `src/sec_review_compiler/agents/outputs.py`
- Test: `tests/test_linkflow_adapter.py`
- Test: `tests/test_tool_loop_offline.py`

- [ ] Reuse the provider-safe schema transformer from `linkflow_probe.schemas`; if moving code, keep `linkflow_probe` tests passing.
- [ ] Implement `LinkflowClientConfig` that reads `LINKFLOW_API_KEY`, `LINKFLOW_BASE_URL`, `LINKFLOW_MODEL`, `LINKFLOW_REASONING_EFFORT`, and concurrency from environment.
- [ ] Make missing `LINKFLOW_API_KEY` a pre-network failure.
- [ ] Implement structured output schemas for:
  - scout region maps;
  - extractor claim attempts;
  - verifier verdicts;
  - consistency checker findings.
- [ ] Implement a plain Python tool loop using explicit conversation history and `function_call_output`.
- [ ] Implement offline fake Linkflow responses for tests.
- [ ] Write tests that assert:
  - missing key fails before a network client call;
  - strict schemas forbid extra fields;
  - malformed tool arguments fail loudly;
  - final structured verifier output validates;
  - agent code cannot write directly to DuckDB.
- [ ] Run:

```bash
python3 -m pytest -q tests/test_linkflow_adapter.py tests/test_tool_loop_offline.py
python3 -m pytest -q tests/test_sanitize.py tests/test_schema_transforms.py tests/test_matrix_report.py
```

Expected: adapter tests and probe-harness tests pass.

- [ ] Optional live smoke, only when the operator has supplied env vars:

```bash
python3 -m linkflow_probe run --tier 1
```

Expected: `Gate: GO`.

- [ ] Commit:

```bash
git add src/sec_review_compiler/llm src/sec_review_compiler/agents tests/test_linkflow_adapter.py tests/test_tool_loop_offline.py linkflow_probe tests/test_schema_transforms.py
git commit -m "feat: add Linkflow agent loop adapter"
```

## 10. Phase 6 - Orchestrator And First Vertical Slice

**Purpose:** Run one synthetic deal through atlas, one specialist, evidence binding, verifier, lifecycle aggregation, and review export.

**Files:**

- Create: `src/sec_review_compiler/orchestration/orchestrator.py`
- Create: `src/sec_review_compiler/orchestration/coverage.py`
- Create: `src/sec_review_compiler/orchestration/verifier.py`
- Create: `src/sec_review_compiler/orchestration/consistency.py`
- Create: `src/sec_review_compiler/exports/review.py`
- Test: `tests/test_orchestrator_vertical_slice.py`
- Test: `tests/test_exports.py`

- [ ] Implement `Orchestrator.run_synthetic_vertical_slice(run_dir, filing_path)`.
- [ ] Use the synthetic filing fixture from Phase 2.
- [ ] Produce at least one claim attempt for a confidentiality-agreement event.
- [ ] Bind the quote with deterministic `verify_quote`.
- [ ] Run the verifier through the Linkflow adapter if env vars are supplied; otherwise use the offline fake verifier for unit tests.
- [ ] Aggregate the verdict without recency rules.
- [ ] Export:
  - `claim_cards.csv`;
  - `review_queue.csv`;
  - `human_decisions_template.csv`;
  - `provider_calls.jsonl`;
  - `tool_calls.jsonl`.
- [ ] Write tests that assert:
  - accepted claim has exact evidence;
  - rejected claim does not enter canonical eligibility;
  - partial correction creates a new attempt;
  - review queue contains escalated or rejected attempts;
  - all artifacts are under `runs/<run_id>/<deal_slug>/`.
- [ ] Run:

```bash
python3 -m pytest -q tests/test_orchestrator_vertical_slice.py tests/test_exports.py
```

Expected: vertical-slice and export tests pass.

- [ ] Commit:

```bash
git add src/sec_review_compiler/orchestration src/sec_review_compiler/exports tests/test_orchestrator_vertical_slice.py tests/test_exports.py
git commit -m "feat: add first review-compiler vertical slice"
```

## 11. Phase 7 - Canonical Compiler

**Purpose:** Deterministically compile accepted, source-backed attempts into canonical graph rows and row-evidence links.

**Files:**

- Create: `src/sec_review_compiler/canonical/models.py`
- Create: `src/sec_review_compiler/canonical/compiler.py`
- Test: `tests/test_canonical_compile.py`

- [ ] Define minimal canonical models for the vertical slice:
  - `deal`;
  - `filing`;
  - `source_span`;
  - `actor`;
  - `event`;
  - `event_actor_link`;
  - `canonical_row_evidence`.
- [ ] Compile only from attempts with accepted lifecycle state and valid evidence bindings.
- [ ] Make canonical ids deterministic from run id, deal slug, source ids, and payload keys.
- [ ] Refuse compile when:
  - a canonical row lacks row evidence;
  - evidence coordinates are missing;
  - a coverage check is `failed_to_check`;
  - a blocking conflict exists.
- [ ] Write tests that assert:
  - unbound claim attempts never compile;
  - accepted event compiles with row evidence;
  - deleting canonical rows and recompiling produces identical rows;
  - model-owned source offsets are impossible because compiler reads only evidence bindings.
- [ ] Run:

```bash
python3 -m pytest -q tests/test_canonical_compile.py
```

Expected: canonical compile tests pass.

- [ ] Commit:

```bash
git add src/sec_review_compiler/canonical tests/test_canonical_compile.py
git commit -m "feat: add deterministic canonical compiler"
```

## 12. Phase 8 - Human Decision Import And Coverage Ledger

**Purpose:** Make hand review part of the data model without building a UI.

**Files:**

- Create: `src/sec_review_compiler/exports/human_decisions.py`
- Modify: `src/sec_review_compiler/orchestration/coverage.py`
- Modify: `src/sec_review_compiler/store/lifecycle.py`
- Test: `tests/test_exports.py`
- Test: `tests/test_lifecycle.py`

- [ ] Implement CSV import for `human_decisions_template.csv`.
- [ ] Accept decisions:
  - `accept`;
  - `reject`;
  - `correct`;
  - `defer`.
- [ ] Make `correct` create a new claim attempt.
- [ ] Implement coverage states:
  - `checked_found`;
  - `checked_absent`;
  - `ambiguous`;
  - `not_applicable`;
  - `failed_to_check`.
- [ ] Make `failed_to_check` block trusted canonical publication.
- [ ] Write tests that assert:
  - human correction does not mutate original attempt;
  - human reject quarantines the attempt;
  - `failed_to_check` blocks compile;
  - `checked_absent` remains review-visible but does not invent a fact.
- [ ] Run:

```bash
python3 -m pytest -q tests/test_exports.py tests/test_lifecycle.py tests/test_canonical_compile.py
```

Expected: human decision and coverage tests pass.

- [ ] Commit:

```bash
git add src/sec_review_compiler/exports src/sec_review_compiler/orchestration src/sec_review_compiler/store tests/test_exports.py tests/test_lifecycle.py tests/test_canonical_compile.py
git commit -m "feat: add human decisions and coverage ledger"
```

## 13. Phase 9 - Full Agent Team Skeleton

**Purpose:** Add the complete role surface without overexpanding the canonical schema beyond the vertical slice.

**Files:**

- Modify: `src/sec_review_compiler/agents/roles.py`
- Modify: `src/sec_review_compiler/agents/prompts.py`
- Modify: `src/sec_review_compiler/agents/outputs.py`
- Modify: `src/sec_review_compiler/orchestration/orchestrator.py`
- Test: `tests/test_orchestrator_vertical_slice.py`
- Create: `tests/test_agent_roles.py`

- [ ] Define roles:
  - `scout`;
  - `party_relation_extractor`;
  - `timeline_bid_extractor`;
  - `count_coverage_extractor`;
  - `omission_inspector`;
  - `verifier`;
  - `consistency_checker`.
- [ ] Give every role an output schema.
- [ ] Ensure all agent outputs are proposals, verdicts, coverage checks, or conflicts. No role writes truth directly.
- [ ] Implement omission inspector as coverage-ledger output, not free-form prose.
- [ ] Write tests that assert:
  - every role has a strict output schema;
  - every role has a prompt hash;
  - no role exposes a comparison or answer-key tool;
  - omission inspector emits coverage checks only.
- [ ] Run:

```bash
python3 -m pytest -q tests/test_agent_roles.py tests/test_orchestrator_vertical_slice.py
```

Expected: role-surface tests pass.

- [ ] Commit:

```bash
git add src/sec_review_compiler/agents src/sec_review_compiler/orchestration tests/test_agent_roles.py tests/test_orchestrator_vertical_slice.py
git commit -m "feat: add full agent role surface"
```

## 14. Phase 10 - Live Vertical Slice

**Purpose:** Prove the V1 architecture with Linkflow live calls on synthetic text. A public filing fixture may be added later, but this phase must not depend on external source material.

**Files:**

- Modify: `src/sec_review_compiler/cli.py`
- Modify: `src/sec_review_compiler/orchestration/orchestrator.py`
- Create: `quality_reports/session_logs/2026-05-08_live_vertical_slice.md`

- [ ] Add CLI command:

```bash
python3 -m sec_review_compiler run-synthetic --run-root runs/dev --deal-slug synthetic-demo
```

- [ ] Add CLI command:

```bash
python3 -m sec_review_compiler summarize-run runs/dev/<run_id>/synthetic-demo
```

- [ ] Run without credentials and verify it fails before network if live mode is requested.
- [ ] Run with credentials supplied through environment only. Do not print the credential.
- [ ] Record in the session log:
  - command used with the key redacted;
  - run directory;
  - number of agent calls;
  - number of claim attempts;
  - accepted/rejected/escalated counts;
  - canonical row count;
  - open review queue count.
- [ ] Run:

```bash
python3 -m pytest -q
python3 -m sec_review_compiler run-synthetic --run-root runs/dev --deal-slug synthetic-demo
```

Expected:

- tests pass;
- live synthetic run produces a deal-room DuckDB, review exports, tool logs, provider logs, and canonical output.

- [ ] Commit:

```bash
git add src/sec_review_compiler quality_reports/session_logs
git commit -m "feat: prove live synthetic vertical slice"
```

## 15. Phase 11 - Calibration Seed

**Purpose:** Create the first verifier calibration artifact from raw filing facts and adversarial planted errors.

**Files:**

- Create: `calibration/verifier_seed.jsonl`
- Create: `src/sec_review_compiler/orchestration/calibration.py`
- Create: `tests/test_calibration.py`

- [ ] Create at least 12 seed cards:
  - 3 confirmed-correct;
  - 3 single-field errors;
  - 2 multi-field errors;
  - 2 plausible hallucinations;
  - 1 genuinely ambiguous;
  - 1 coverage gap.
- [ ] Use synthetic or locally available public filing text only.
- [ ] Implement calibration runner that sends cards through the verifier and computes category metrics.
- [ ] Make calibration fail closed if all cards are rubber-stamped `confirm`.
- [ ] Write tests that assert planted wrong dates and wrong actors are not counted as confirmed-correct.
- [ ] Run:

```bash
python3 -m pytest -q tests/test_calibration.py
```

Expected: calibration tests pass.

- [ ] Commit:

```bash
git add calibration src/sec_review_compiler/orchestration/calibration.py tests/test_calibration.py
git commit -m "feat: add verifier calibration seed"
```

## 16. Phase 12 - Final Acceptance Audit

**Purpose:** Verify the implementation against the specs and prevent stale surfaces or secret leakage.

**Files:**

- Create: `quality_reports/session_logs/2026-05-08_agentic_review_compiler_acceptance.md`
- Modify: `README.md` if a README exists by this phase; create it if absent

- [ ] Run full tests:

```bash
python3 -m pytest -q
```

Expected: all tests pass.

- [ ] Run provider gate summary:

```bash
python3 -m linkflow_probe summarize runs/linkflow-probe/20260508T123815Z
```

Expected: `Gate: GO`.

- [ ] Run source-tree stale-surface scan:

```bash
git grep -n 'bids_try\|old pipeline\|previous pipeline\|P8\|Reference 9\|disposition.py\|docs/spec.md' HEAD -- \
  ':!docs/superpowers/plans/2026-05-08-agentic-review-compiler-goal-implementation.md' || true
```

Expected: no live authority references. Mentions are allowed only inside explicitly archived/probe evidence if the executor intentionally added such an archive, which this plan does not require.

- [ ] Run secret scan:

```bash
git grep -n 'sk-\|LINKFLOW_API_KEY=.*sk\|Authorization: Bearer' HEAD -- \
  ':!docs/superpowers/plans/2026-05-08-agentic-review-compiler-goal-implementation.md' || true
```

Expected: no real credential. Test fixtures may contain dummy strings like `sk-test`.

- [ ] Run file inventory check:

```bash
git ls-tree -r --name-only HEAD | sort
```

Expected: no `.env`, `.venv`, `__pycache__`, `.pytest_cache`, `.DS_Store`, or raw provider secret file.

- [ ] Write the acceptance log with:
  - exact test command outputs;
  - Linkflow probe run id;
  - live vertical slice run id;
  - known limitations;
  - next recommended extension.

- [ ] Commit:

```bash
git add README.md quality_reports/session_logs
git commit -m "docs: record compiler acceptance audit"
git push
```

## 17. Hard Stop Conditions

Stop and report instead of improvising if any of these occur:

- Linkflow Tier 1 regression changes the gate from `GO` to `NO_GO`.
- Strict structured output becomes unreliable.
- Tool calls cannot be combined with final structured output.
- A model response is accepted through loose JSON parsing.
- Any API key appears in a tracked file or command output.
- An agent writes DuckDB directly.
- A canonical row compiles without exact evidence binding.
- Coverage `failed_to_check` is treated as trusted output.
- A correction mutates a claim attempt in place.
- The implementation starts importing archived source code without explicit user approval.

## 18. Definition Of Done

The `/goal` run is complete only when:

- all committed specs remain present;
- Linkflow probe evidence remains committed and says `GO`;
- `src/sec_review_compiler` implements the V1 vertical slice;
- synthetic live run produces deal-room state, review exports, and canonical rows;
- every accepted canonical row has row evidence;
- no external pipeline output is used;
- no pre-clean-slate source or docs have been restored;
- full pytest passes;
- acceptance log exists;
- branch is pushed.
