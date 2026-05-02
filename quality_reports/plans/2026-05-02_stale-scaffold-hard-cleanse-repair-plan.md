# Stale Scaffold Hard-Cleanse Repair Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:test-driven-development` before source-code contract repairs, `superpowers:systematic-debugging` before changing failing behavior, and `superpowers:verification-before-completion` before reporting success. This repo allows no stale authority, no fallback paths, and no backward-compatibility path.

**Goal:** remove stale scaffolds and stale docs, repair fail-loud contract violations, and replace paragraph-local extraction with within-deal narrative-window extraction. The result must be a standalone `sec_graph` repo whose active docs, tests, source code, and generated-output policy all agree.

**Architecture:** `docs/spec.md` is the binding product and schema contract. Current execution authority is `quality_reports/plans/2026-05-02_deployable-canonical-pipeline-goal.md` plus the current deployable plan until this hard-cleanse plan supersedes its stale-cleanup sections. Historical notes may remain only when clearly marked as non-authoritative proof or failure context. Active code must fail loudly instead of silently falling back, guessing, or accepting old shapes.

**Tech stack:** Python 3.11+, Pydantic v2, DuckDB, pytest through `uv run pytest`, Linkflow provider code isolated under `src/sec_graph/extract/llm/`.

**Critical clarification:** the extraction-memory repair is within one deal only. It must let facts in paragraph 1 affect interpretation of paragraph 40 inside the same filing. It must not create cross-deal linkage.

---

## Findings From The Parallel Scan

Four read-only lanes reported the same shape of problem:

1. **Authority docs are stale:** `AGENTS.md`, `CLAUDE.md`, `README.md`, `docs/llm-interface.md`, `quality_reports/plans/2026-05-02_parallel-execution-plan.md`, `quality_reports/plans/2026-05-02_stage-8-llm-linkflow-plan.md`, and `quality_reports/session_logs/2026-05-02_parallel-execution-plan.md` still point to the old parallel plan or old Stage 8 plan as if they are active.
2. **Generated proof artifacts are half-tracked:** `artifacts/linkflow/2026-05-02_stage8_live/` is ignored by `.gitignore` but still has five tracked JSON files. `runs/` and `tmp/` hold stale run scaffolds.
3. **Registered worktrees are stale scaffolds:** `.worktrees/track-a-ingest`, `.worktrees/track-b-validate-project`, `.worktrees/track-c-extract-real`, and `.worktrees/track-c-extract-smoke` are still registered and contain old orientation docs.
4. **Source code still has soft paths:** Linkflow stream salvage can promote incomplete provider status to completed, tender fetch falls back to cover form, top-level CLI loses `--fresh`, and reconcile can discard or fabricate facts.
5. **Production extractors contain deal-specific scaffolding:** rule extractors and reconcile aliases contain PetSmart/example names, hardcoded buyer-group facts, fallback labels, and smoke run IDs.
6. **LLM extraction is paragraph-myopic:** request models, builders, prompts, and tests send one paragraph at a time and reward skipping most paragraphs. This is too weak for within-deal narrative dependencies.
7. **Evidence validation is not source-truth validation:** current validation checks stored quote text against stored hash but does not prove the quote matches the referenced source bytes and coordinates.

---

## Phase 0 - Safety Baseline

**Purpose:** capture the dirty tree and registered worktree state before deleting scaffolds.

Run from `/Users/austinli/Projects/sec_graph`:

```bash
git status --short --branch
git worktree list --porcelain
git ls-files artifacts runs tmp data/filings quality_reports/plans quality_reports/specs quality_reports/session_logs
git ls-files --others --ignored --exclude-standard artifacts runs tmp
git ls-files --others --exclude-standard data/filings
```

Expected:

- Main worktree is dirty already; do not revert unrelated edits.
- Four registered `.worktrees/*` entries exist.
- `data/filings/` exists as untracked local research source material and must be kept.
- Only `artifacts/linkflow/2026-05-02_stage8_live/*.json` appears as tracked generated proof under ignored `artifacts/`.

---

## Phase 1 - Delete Disposable Scaffolds And Generated State

**Purpose:** remove stale local state that should never guide future agents.

### 1.1 Remove registered worktrees

Verify clean status first:

```bash
git -C .worktrees/track-a-ingest status --short
git -C .worktrees/track-b-validate-project status --short
git -C .worktrees/track-c-extract-real status --short
git -C .worktrees/track-c-extract-smoke status --short
```

Each command must print no modified files. Then remove registered worktrees with git:

```bash
git worktree remove .worktrees/track-a-ingest
git worktree remove .worktrees/track-b-validate-project
git worktree remove .worktrees/track-c-extract-real
git worktree remove .worktrees/track-c-extract-smoke
git worktree prune
```

Do not use `rm -rf .worktrees/*` for registered worktrees.

Expected:

```bash
git worktree list --porcelain
```

shows only `/Users/austinli/Projects/sec_graph`.

### 1.2 Untrack and delete stale Linkflow proof artifacts

```bash
git rm -r --ignore-unmatch artifacts/linkflow/2026-05-02_stage8_live
rm -rf artifacts/linkflow/2026-05-02_stage8_live
```

Expected:

```bash
git ls-files artifacts/linkflow/2026-05-02_stage8_live
```

prints nothing.

### 1.3 Delete stale run, temp, and interpreter caches

```bash
rm -rf runs tmp .pytest_cache .ruff_cache
find . -path './.git' -prune -o -path './.venv' -prune -o -name '__pycache__' -type d -prune -exec rm -rf {} +
find . -path './.git' -prune -o -path './.venv' -prune -o -name '*.pyc' -type f -delete
find . -path './.git' -prune -o -path './.venv' -prune -o -name '.DS_Store' -type f -delete
```

Expected:

```bash
find . -path './.git' -prune -o -path './.venv' -prune -o \( -name '__pycache__' -o -name '*.pyc' -o -name '.DS_Store' -o -name '.pytest_cache' -o -name '.ruff_cache' \) -print
```

prints nothing.

### 1.4 Preserve local filing source material

Do not delete `data/filings/`. It contains downloaded EDGAR source artifacts for:

```text
imprivata
mac-gray
medivation
penford
petsmart-inc
providence-worcester
saks
stec
zep
```

Each deal folder should retain `raw.htm`, `raw.md`, `pages.json`, and `manifest.json`.

---

## Phase 2 - Repair Active Authority Docs

**Purpose:** remove stale execution authority. Active docs must have one chain of command.

### 2.1 Rewrite top-level orientation docs

Modify:

- `AGENTS.md`
- `CLAUDE.md`
- `README.md`
- `docs/llm-interface.md`

Required content changes:

- Replace every active statement that `quality_reports/plans/2026-05-02_parallel-execution-plan.md` is the executing plan.
- Name this file, `quality_reports/plans/2026-05-02_stale-scaffold-hard-cleanse-repair-plan.md`, as the executing cleanup and repair plan until complete.
- Keep `docs/spec.md` as binding design authority.
- Keep `quality_reports/plans/2026-05-02_deployable-canonical-pipeline-goal.md` as goal context.
- Replace stale commands:
  - `python -m sec_graph run` must include `--run-dir` and `--run-id`.
  - `python -m sec_graph project` must include `--projection`.
  - `python -m sec_graph ingest --input data/examples --db data/pipeline.duckdb --fresh` must be documented as supported and forwarded by top-level dispatch.
- Replace "no real LLM calls until interface designed" with "LLM interface exists but is being repaired from paragraph-local requests to within-deal narrative windows."

Verification:

```bash
rg -n "sole source of truth for execution|THE executing plan|Begin Phase 0|no real LLM calls until|parallel-execution-plan.md.*execut" AGENTS.md CLAUDE.md README.md docs
```

Expected: no active-authority hits.

### 2.2 Clean the binding spec

Modify `docs/spec.md`.

Required content changes:

- Remove "compatibility shim" language. If `scripts/fetch_filings.py` remains, document it as a root convenience command or delete it after adding the replacement CLI command.
- Resolve run-state contradiction:
  - no stage may unconditionally wipe `judgments`;
  - no command may overwrite an existing `runs/{run_id}/` directory unless an explicit fresh-run flag is provided and the docs name the exact behavior.
- Replace old staged-build status language with the current cleanup state.
- Add a subsection that defines stale-doc policy:
  - active docs may not reference superseded plans as execution authority;
  - proof logs are point-in-time evidence only;
  - historical notes cannot contain executable next steps unless the header says they are rejected historical instructions.
- Add a subsection that defines within-deal narrative memory:
  - deal windows are built from ordered paragraphs in one filing;
  - no cross-deal memory is allowed;
  - every quote must still map back to exact source coordinates.

Verification:

```bash
rg -n "compatibility shim|Begin Phase 0|planned, not yet implemented|unconditionally clears|parallel-execution-plan.md.*exec" docs/spec.md
```

Expected: no stale active-contract hits.

### 2.3 Delete or quarantine superseded plan docs

Delete active-looking stale plan docs after folding any still-live invariant into `docs/spec.md` or this plan:

```bash
git rm quality_reports/plans/2026-05-02_parallel-execution-plan.md
git rm quality_reports/plans/2026-05-02_stage-8-llm-linkflow-plan.md
git rm quality_reports/session_logs/2026-05-02_parallel-execution-plan.md
```

If a worker believes one of these must be kept, the replacement is not to leave it active. The replacement is a one-page historical note with:

```text
Status: superseded historical note. This file is not execution authority.
Current authority: docs/spec.md and quality_reports/plans/2026-05-02_stale-scaffold-hard-cleanse-repair-plan.md.
No instructions below may be executed without revalidation against the current spec.
```

The preferred path is deletion because the user requested no stale docs.

### 2.4 Fold and remove superseded spec notes

Inspect and fold any still-valid invariant into `docs/spec.md`, then remove:

```bash
git rm quality_reports/specs/2026-05-02_pipeline-gaps-and-buyer-group-atomization.md
git rm quality_reports/specs/2026-05-02_schema-direction-overfit-and-overengineering.md
```

Required folded invariants:

- generic `actor_relations` is first-class;
- no fallback enum values;
- no row-shaped downstream bidder identities in canonical tables;
- no overfit PetSmart-only schema surface.

### 2.5 Keep proof logs only behind a current status index

Create `quality_reports/session_logs/README.md`.

Required content:

- A table that labels each retained log as point-in-time proof, not current authority.
- A "current authority" line pointing to `docs/spec.md` and this hard-cleanse plan.
- A warning that stale commands inside retained logs must not be rerun without checking current CLI help.

Keep proof logs that only record passed gates:

- `quality_reports/session_logs/2026-05-02_g0-stage-1a.md`
- `quality_reports/session_logs/2026-05-02_g1-stage-1b.md`
- `quality_reports/session_logs/2026-05-02_g2-phase-2-merge.md`
- `quality_reports/session_logs/2026-05-02_g3-track-c2-real-extraction.md`
- `quality_reports/session_logs/2026-05-02_g4-stage-7-reconcile-real.md`
- `quality_reports/session_logs/2026-05-02_g5-stage-8-linkflow.md`
- `quality_reports/session_logs/2026-05-02_reference9_offline-proof.md`

Rewrite or delete `quality_reports/session_logs/2026-05-02_reference-deal-development-note.md`. If kept, it must begin with a status banner that says old schema sketches and old role vocabulary are rejected historical context.

---

## Phase 3 - Add Automated Staleness Guards

**Purpose:** prevent the repo from drifting back into stale authority, fallback, or backward-compatibility language.

Create `tests/test_repo_freshness_contract.py`.

Required checks:

1. Active docs do not name superseded plans as execution authority.
2. Active docs do not contain stale kickoff phrases such as `Begin Phase 0`.
3. Source files do not contain `compatibility shim`.
4. Generated-output directories do not contain tracked files unless explicitly allowlisted by a current proof plan.
5. Top-level source and tests do not contain Python caches or `.DS_Store`.

Use a small explicit allowlist for:

- `docs/prior-pipeline-lessons.md` when it discusses failure history.
- retained session logs listed in `quality_reports/session_logs/README.md`.
- tests that intentionally assert fallback enum values are rejected.

Verification:

```bash
uv run pytest tests/test_repo_freshness_contract.py -q
```

Expected: all checks pass after Phase 1 and Phase 2.

---

## Phase 4 - Repair Evidence Source-Truth Contracts

**Purpose:** make evidence validation prove source truth, not just internal self-consistency.

Write failing tests first:

- `tests/test_evidence_source_truth.py::test_validate_database_rejects_span_coordinates_that_do_not_match_raw_source`
- `tests/test_evidence_source_truth.py::test_split_paragraphs_does_not_mark_cleaned_noncontiguous_text_as_raw_md`
- `tests/test_evidence_source_truth.py::test_extract_spans_require_parent_paragraph_seed`

Modify:

- `src/sec_graph/validate/integrity.py`
- `src/sec_graph/ingest/paragraphs.py`
- `src/sec_graph/ingest/spans.py`
- `src/sec_graph/schema/models/filings.py`
- DDL/schema init files if constraints live outside Pydantic models.

Required behavior:

- `validate_database()` loads the referenced source bytes/text for each span and verifies `span_basis`, `char_start`, `char_end`, `quote_text`, and `quote_hash` together.
- A span marked `raw_md` must point to a contiguous raw slice whose text equals `quote_text`.
- Cleaned or joined paragraph text must either keep a coordinate map to raw source or use a separate basis that cannot masquerade as raw markdown.
- Sentence, clause, phrase, and LLM extract spans must have `parent_evidence_id` pointing to a paragraph seed span.
- Validation fails loudly with row identifiers when any invariant is violated.

Verification:

```bash
uv run pytest tests/test_evidence_source_truth.py tests/test_stage1a_evidence_store.py tests/test_ingest_examples.py -q
```

Expected: all tests pass and the new tests fail before the implementation.

---

## Phase 5 - Repair Reconcile And Projection Semantics

**Purpose:** stop the canonical pipeline from fabricating admissions, boundary doctrine, participation-class semantics, or deleting append-only judgments.

Write failing tests first:

- `tests/test_reconcile_no_fabrication.py::test_boundary_event_subtype_must_come_from_evidence_not_cycle_boundary_selection`
- `tests/test_reconcile_no_fabrication.py::test_post_boundary_bid_does_not_imply_projection_admission`
- `tests/test_reconcile_no_fabrication.py::test_participation_count_preserves_actor_class_and_stage_semantics`
- `tests/test_reconcile_no_fabrication.py::test_reconcile_refuses_to_delete_existing_judgments`
- `tests/test_reconcile_no_fabrication.py::test_unresolved_actor_relation_is_rejected_not_silently_skipped`

Modify:

- `src/sec_graph/reconcile/pipeline.py`
- `src/sec_graph/reconcile/boundaries.py`
- `src/sec_graph/reconcile/cycles.py`
- `src/sec_graph/project/bidder_rows.py`
- `src/sec_graph/schema/models/judgments.py`
- `src/sec_graph/validate/integrity.py`
- tests and fixtures that currently bless fabricated rows.

Required behavior:

- Boundary events use the event subtype supported by evidence. If evidence does not establish an admissive boundary event, no `advancement_admitted` event may be fabricated.
- Projection eligibility comes only from explicit current `projection_eligibility` judgments or equivalent canonical evidence defined in `docs/spec.md`.
- A post-boundary proposal is not enough to set `admitted=True`.
- Participation counts preserve `actor_class`, `process_stage`, exact-vs-at-least semantics, and anonymous remainder limits from the source.
- `reconcile_all()` may clear derived canonical tables for a fresh run only under explicit run-state policy. It must not silently delete reviewer/proof judgments.
- Unresolved relation candidates produce hard validation failures or explicit rejected judgments, not `continue`.

Verification:

```bash
uv run pytest tests/test_reconcile_no_fabrication.py tests/test_reconcile_real.py tests/test_validate_project.py -q
```

Expected: no fixture passes by relying on fabricated admission, financial-only count conversion, or judgment deletion.

---

## Phase 6 - Remove Deal-Specific Production Scaffolds

**Purpose:** separate real general logic from temporary example-specific scaffolding.

Write failing tests first:

- `tests/test_no_deal_specific_scaffolds.py::test_rule_extractors_do_not_hardcode_reference_deal_names`
- `tests/test_no_deal_specific_scaffolds.py::test_reconcile_aliases_do_not_fallback_to_slug_labels`
- `tests/test_no_deal_specific_scaffolds.py::test_run_ids_are_explicit_not_historical_smoke_defaults`
- `tests/test_no_deal_specific_scaffolds.py::test_hand_authored_petsmart_fixture_is_not_pipeline_proof`

Modify or delete:

- `src/sec_graph/extract/rules/actors.py`
- `src/sec_graph/extract/rules/relations.py`
- `src/sec_graph/reconcile/aliases.py`
- `src/sec_graph/reconcile/pipeline.py`
- `src/sec_graph/extract/pipeline.py`
- `src/sec_graph/extract/rules/__init__.py`
- `src/sec_graph/cli/reconcile_cmd.py`
- `tests/fixtures/canonical/petsmart.json`
- `tests/fixtures/canonical/petsmart_bidder_rows.jsonl`
- `tests/test_validate_project.py`
- `tests/test_extract_rules_real_examples.py`

Required behavior:

- Actor extraction must use general, source-derived patterns or LLM/window extraction. It must not ship a hardcoded list of example actors as production logic.
- PetSmart buyer-group, Longview, rollover, and financing facts must come from source evidence or test fixtures scoped as fixtures, not production rule constants.
- Unknown target labels must fail unless sourced from filing metadata, manifest data, or canonical evidence.
- Default run IDs such as `extract-smoke`, `reconcile-real`, and `track-b-petsmart` must not be production defaults.
- Hand-authored PetSmart fixtures may remain only as minimal schema unit fixtures. They must not be described as pipeline proof.

Verification:

```bash
uv run pytest tests/test_no_deal_specific_scaffolds.py tests/test_extract_rules_real_examples.py tests/test_validate_project.py -q
```

Expected: tests prove the production path is not hardcoded to the current examples.

---

## Phase 7 - Repair LLM Extraction To Use Within-Deal Narrative Windows

**Purpose:** fix slow paragraph-by-paragraph extraction and prevent loss of long-range within-deal implications.

This is not cross-deal linkage. It is a single-filing memory model.

### 7.1 Replace paragraph request contract

Write failing tests first:

- `tests/test_llm_windows.py::test_llm_requests_are_deal_windows_not_single_paragraphs`
- `tests/test_llm_windows.py::test_window_contains_ordered_paragraph_refs_and_source_span_refs`
- `tests/test_llm_windows.py::test_window_carries_prior_actor_alias_and_event_memory`
- `tests/test_llm_windows.py::test_quotes_from_window_candidates_validate_against_source_spans`
- `tests/test_llm_windows.py::test_no_cross_deal_context_is_included`

Modify:

- `src/sec_graph/extract/llm/models.py`
- `src/sec_graph/extract/llm/requests.py`
- `src/sec_graph/extract/llm/prompt.py`
- `src/sec_graph/extract/llm/convert.py`
- `src/sec_graph/extract/pipeline.py`
- `docs/llm-interface.md`
- `docs/spec.md`
- `tests/test_llm_interface.py`
- `tests/test_linkflow_live.py`

Required request fields:

- `deal_id`
- `filing_id`
- `window_id`
- `window_kind`
- ordered paragraph references with `paragraph_id`, `source_span_id`, `char_start`, `char_end`
- compact prior deal memory for actor aliases, prior events, active cycle candidates, and unresolved references
- extraction task list for the window
- strict source-coordinate ownership by Python, not the provider

Delete or replace:

- public paragraph-only `build_llm_requests` contract;
- prompt language that says "one SEC merger filing paragraph";
- tests that reward skipping nearly all paragraphs based only on local surfaces;
- single-short-paragraph Linkflow proof as the live proof.

### 7.2 Decide and implement Linkflow stream completion policy

Write failing tests first:

- `tests/test_llm_interface.py::test_linkflow_incomplete_stream_is_not_completed`
- `tests/test_llm_interface.py::test_linkflow_missing_completed_event_fails_loudly`

Modify:

- `src/sec_graph/extract/llm/linkflow.py`
- `docs/llm-interface.md`
- stale tests around missing `response.completed`

Required behavior:

- A provider response without completed status must not produce `LLMExtractionResponse(finish_status="completed")`.
- If strict streamed-body recovery remains allowed, the finish status must be explicit and non-completed unless the provider status proves completion. Under the current no-fallback policy, preferred behavior is to raise a provider contract error.

### 7.3 Remove stale relation payload surface

Modify:

- `src/sec_graph/extract/llm/models.py`
- `src/sec_graph/extract/llm/convert.py`
- `src/sec_graph/extract/llm/linkflow.py`
- `src/sec_graph/schema/models/extraction.py`
- related tests.

Required behavior:

- Either remove LLM `actor_relation` entirely from flat candidate types, or define a first-class typed relation payload.
- Do not keep JSON-in-string relation payloads as a hidden legacy surface.

Verification:

```bash
uv run pytest tests/test_llm_windows.py tests/test_llm_interface.py tests/test_linkflow_live.py -q
```

Expected: no paragraph-only request contract remains, no provider-incomplete response is promoted to completed, and live proof exercises a multi-paragraph within-deal window.

---

## Phase 8 - Repair Fetch And CLI Fail-Loud Contracts

**Purpose:** remove remaining fallback and command-surface mismatches.

Write failing tests first:

- `tests/test_edgar.py::test_tender_offer_without_offer_to_purchase_fails_loudly`
- `tests/test_cli_dispatch.py::test_top_level_ingest_forwards_fresh`
- `tests/test_cli_dispatch.py::test_fetch_script_is_not_documented_as_backward_compatibility`

Modify:

- `src/sec_graph/fetch/edgar.py`
- `src/sec_graph/cli/__init__.py`
- `src/sec_graph/cli/ingest_cmd.py`
- `scripts/fetch_filings.py`
- `docs/spec.md`
- `README.md`
- `CLAUDE.md`

Required behavior:

- Tender-offer filings must fail loudly if no offer-to-purchase exhibit is selected.
- The top-level dispatcher must preserve `--fresh`.
- If `scripts/fetch_filings.py` remains, it is documented as a deliberate root command, not a backward-compatibility shim. If a full `python -m sec_graph fetch` command exists, delete the script instead of maintaining a duplicate compatibility layer.

Verification:

```bash
uv run pytest tests/test_edgar.py tests/test_cli_dispatch.py -q
```

Expected: fetch and CLI tests pass without fallback semantics.

---

## Phase 9 - Full Verification Gate

Run from `/Users/austinli/Projects/sec_graph`:

```bash
uv run pytest -q
rg -n --glob '!quality_reports/plans/2026-05-02_stale-scaffold-hard-cleanse-repair-plan.md' "compatibility shim|Begin Phase 0|THE executing plan|sole source of truth for execution|fallback provider|fallback model|backward-compatible reader|track-b-petsmart|hand_authored|extract-smoke|reconcile-real" AGENTS.md CLAUDE.md README.md docs quality_reports src tests
git ls-files artifacts runs tmp
git worktree list --porcelain
git status --short --branch
```

Expected:

- `uv run pytest -q` passes.
- The `rg` scan has no active stale-authority or stale-scaffold hits. Hits in rejection tests or historical failure notes must be explicitly allowlisted in `tests/test_repo_freshness_contract.py`.
- `git ls-files artifacts runs tmp` prints nothing unless a current proof plan force-adds sanitized proof files by exact path.
- `git worktree list --porcelain` shows only the main worktree.
- `data/filings/` remains present.

Run a secret and provider-output hygiene scan before staging:

```bash
rg -n "sk-[A-Za-z0-9]|LINKFLOW_API_KEY|Authorization:|Bearer |raw_response|provider_body" .
```

Expected: no secrets and no raw provider payload dumps in tracked files.

---

## Phase 10 - Commit Boundaries

Use separate commits so failures are easy to isolate:

1. `hard-clean generated scaffolds`
   - worktree removal;
   - stale `artifacts/linkflow/2026-05-02_stage8_live` untracked/deleted;
   - `runs/`, `tmp/`, caches removed.
2. `repair authority docs`
   - `AGENTS.md`, `CLAUDE.md`, `README.md`, `docs/spec.md`, `docs/llm-interface.md`;
   - superseded plan/spec/session files deleted or quarantined;
   - `quality_reports/session_logs/README.md`.
3. `add freshness contract tests`
   - `tests/test_repo_freshness_contract.py`.
4. `repair evidence source truth`
   - source-span validation and parent evidence chain.
5. `repair reconcile semantics`
   - no fabricated boundaries/admission/counts;
   - no append-only judgment deletion.
6. `remove deal-specific production scaffolds`
   - production extractors and fixtures cleaned.
7. `replace paragraph llm extraction with deal windows`
   - LLM models, request builder, prompt, Linkflow policy, docs, tests.
8. `repair fetch and cli fail-loud contracts`
   - tender resolver and `--fresh` dispatch.

Never stage unrelated dirty files. Use `git status --short` before each commit and stage exact paths.

---

## Completion Definition

The repair is complete only when:

- no registered stale worktrees remain;
- no tracked generated artifacts remain under ignored output directories;
- active docs name exactly one current authority chain;
- old execution plans and stale scaffold docs are deleted or impossible to confuse with current instructions;
- source validation proves quote coordinates against source bytes;
- reconciliation does not fabricate admissions, boundaries, count classes, or delete append-only judgments;
- LLM extraction uses within-deal narrative windows, not single-paragraph requests;
- Linkflow cannot promote incomplete provider status to completed;
- fetch and CLI paths fail loudly instead of falling back;
- `uv run pytest -q` passes;
- freshness and secret scans pass.
