# Reference-9 Schema Freeze Session Log

## Decision Implemented

Relation-revised claim-only P8 contract.

Provider `coverage_results` were removed from the Linkflow response contract.
Python-owned `coverage_results` were retained as DuckDB extraction/proof rows.
Default live Linkflow reasoning is `medium`. The only active request mode is
`claim_only_p8_relation_v1`.

## Pre-Existing Dirty Worktree

Task 0 found an already-dirty worktree in the target migration area. Existing
dirty paths included active docs, LLM contract code, validation tests, deleted
historical plan files, untracked calibration evidence under
`quality_reports/llm_calibration/ref9_schema_calibration_2026-05-04/`,
untracked `quality_reports/plans/legacy/`, and untracked
`quality_reports/schema_read/`. No competing pytest/sec_graph/linkflow process
was running.

## Files Changed

Docs:

- `README.md`
- `CLAUDE.md`
- `docs/spec.md`
- `docs/llm-interface.md`
- `docs/superpowers/specs/2026-05-03-pipeline-hard-reset-design.md`
- `quality_reports/2026-05-04_ref9_schema_freeze_session_log.md`
- `quality_reports/session_logs/README.md`
- `quality_reports/llm_calibration/README.md`
- `quality_reports/llm_calibration/legacy/README.md`

Code:

- `src/sec_graph/extract/llm/models.py`
- `src/sec_graph/extract/llm/convert.py`
- `src/sec_graph/extract/llm/linkflow.py`
- `src/sec_graph/extract/llm/prompt.py`
- `src/sec_graph/extract/llm/requests.py`
- `src/sec_graph/extract/pipeline.py`
- `src/sec_graph/cli/extract_cmd.py`
- `src/sec_graph/cli/run_cmd.py`
- `src/sec_graph/schema/models/extraction.py`
- `src/sec_graph/schema/models/canonical.py`
- `src/sec_graph/validate/integrity.py`

Tests:

- `tests/test_llm_p7_contract.py` renamed to `tests/test_llm_p8_contract.py`
- `tests/test_coverage_semantics.py`
- `tests/test_hard_reset_schema.py`
- `tests/test_validation_semantics.py`
- `tests/test_run_kernel.py`

Stale cleanup:

- Active `quality_reports/plans/` contains only
  `2026-05-04_relation_revised_claim_only_p8_implementation_plan.md` and
  `legacy/`.
- Historical active-plan files were removed from the active plan surface and
  retained only under `quality_reports/plans/legacy/`.
- Superseded P7/V0/high calibration files were moved under
  `quality_reports/llm_calibration/legacy/`.
- `README.md`, `CLAUDE.md`, and `quality_reports/session_logs/README.md` were
  refreshed to point at the P8/medium authority chain.
- `quality_reports/plans/.DS_Store` was removed.
- Generated `__pycache__` and `.pyc` files were removed.

## Verification

```bash
git status --short
```

Result: dirty worktree preserved; no unrelated reset was performed.

```bash
ps -axo pid,command | rg "pytest|sec_graph|linkflow|uv run"
```

Result: no competing process beyond the check itself.

```bash
find quality_reports/plans -maxdepth 1 -type f -print | sort
```

Result: only
`quality_reports/plans/2026-05-04_relation_revised_claim_only_p8_implementation_plan.md`.

```bash
rg -n 'P7|V0|coverage_results.*provider|provider.*coverage_results|CoverageResultPayload|semantic_claims_v1|rollover_holder_of|Default live Linkflow reasoning effort is `high`|test_llm_p7_contract|EXPANDED_CLAIM_ONLY_P8.*production|PLAIN_RECALL.*production|V0_P8_BASELINE.*production' docs src tests
```

Result: only the intentional dated supersession note in the hard-reset spec.

```bash
rg -n 'bid_formality|proposal_scope|drop_agency|drop_reason|initiation_side|actor_claims\.actor_class' docs src tests
```

Result: only the provider-prohibited list in `docs/llm-interface.md`.

```bash
PYTHONDONTWRITEBYTECODE=1 uv run pytest -q -p no:cacheprovider tests/test_llm_p8_contract.py
```

Result: `10 passed in 0.15s`.

```bash
PYTHONDONTWRITEBYTECODE=1 uv run pytest -q -p no:cacheprovider tests/test_coverage_semantics.py tests/test_hard_reset_schema.py tests/test_validation_semantics.py
```

Result: `19 passed in 0.93s`.

```bash
PYTHONDONTWRITEBYTECODE=1 uv run pytest -q -p no:cacheprovider tests/test_llm_p8_contract.py tests/test_coverage_semantics.py tests/test_hard_reset_schema.py tests/test_validation_semantics.py tests/test_run_kernel.py
```

Result: `35 passed in 0.63s`.

```bash
PYTHONDONTWRITEBYTECODE=1 uv run pytest -q -p no:cacheprovider
```

Result: `60 passed in 5.07s`.

```bash
find . -name '__pycache__' -o -name '*.pyc'
```

Result: no output after bytecode cleanup and final test run.

## Live Smoke

Skipped. `LINKFLOW_API_KEY` was not set in the environment. No secret was
requested, printed, or written.

## Remaining Work

No local blocker remains for the schema freeze. A live Linkflow smoke remains
available when credentials are present.

## Final Handoff Facts

Provider `coverage_results` removed.
Python-owned `coverage_results` retained.
Default Linkflow reasoning is `medium`.
Request mode is `claim_only_p8_relation_v1`.
`rollover_holder_of` removed.
`rollover_holder_for` added.
`voting_support_for`, `committee_member_of`, and `recused_from` added.
Scalar expanded fields rejected.
