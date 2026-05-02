# Session Log: G4 Stage 7 Reconcile Real

**Date:** 2026-05-02
**Branch:** `main`
**Gate:** G4 - Stage 7 real reconciliation

## Scope

Implemented Phase 4 / Stage 7 from `quality_reports/plans/2026-05-02_parallel-execution-plan.md`:

- Added deterministic candidate-to-canonical reconciliation under `src/sec_graph/reconcile/`.
- Added alias/subtype policy, cycle-window assignment, boundary selection, canonical row emission, and participation-count pass-through.
- Added `python -m sec_graph reconcile`.
- Added `python -m sec_graph run --all` for ingest -> extract -> reconcile -> validate -> project.
- Updated bidder-row projection to emit rows for actor-cycle memberships evidenced by event links or actor-cycle judgments, instead of cross-joining every bidder actor to every cycle.
- Added exact bidder-row golden hash coverage in `tests/fixtures/reconcile/real_bidder_rows_golden.json`.

## RED Evidence

Command:

```bash
PATH=.venv/bin:$PATH python -m pytest tests/test_reconcile_real.py -q
```

Outcome before implementation: exit 2 during collection; `ModuleNotFoundError: No module named 'sec_graph.cli.run_cmd'`.

## Golden Projection Contract

The real bidder-row projection is exact-hash locked by test:

| Artifact | Rows | SHA-256 |
|----------|------|---------|
| `bidder_rows` | 15 | `0123b0f860b7a515866fd19b9a4d3f693e1a6ce5576e427a4e3eae529431ff9a` |

Visible required rows cover:

- PetSmart: `Buyer Group`, `Bidder 2`
- Providence: `G&W`, `Party B`
- Saks: `Hudson\u2019s Bay`, `Sponsor A`, `Sponsor E`
- Zep: `Party X`, `New Mountain Capital`

## Verification

Command:

```bash
PATH=.venv/bin:$PATH python -m pytest tests/test_reconcile_real.py tests/test_validate_project.py -q
```

Outcome: exit 0; 7 passed.

Command:

```bash
PATH=.venv/bin:$PATH python -m pytest
```

Outcome: exit 0; 39 passed.

Command:

```bash
PATH=.venv/bin:$PATH python -m pytest tests/ -x --ff
```

Outcome: exit 0; 39 passed.

Command:

```bash
PATH=.venv/bin:$PATH python -m pytest tests/ -x --ff
```

Outcome: exit 0; 39 passed.

Command:

```bash
PATH=.venv/bin:$PATH python -m sec_graph --help
```

Outcome: exit 0; help listed `ingest`, `extract`, `reconcile`, `validate`, `project`, and `run`.

Command:

```bash
PATH=.venv/bin:$PATH python -m sec_graph run --all --run-dir runs/g4-main
```

Outcome: exit 0; run completed and wrote artifacts under `runs/g4-main`.

Run artifact checks:

- `validation_passed`: true
- `hard_failures`: 0
- `soft_flag_count`: 8
- `bidder_rows`: 15
- `bidder_rows_sha256`: `0123b0f860b7a515866fd19b9a4d3f693e1a6ce5576e427a4e3eae529431ff9a`
- `ambiguity_queue.csv` flag types: `alternative_value`, `low_confidence_judgment`

Standalone CLI checks:

```bash
PATH=.venv/bin:$PATH python -m sec_graph reconcile
```

Outcome: exit 0; reconciled canonical rows for 4 deals.

```bash
PATH=.venv/bin:$PATH python -m sec_graph validate --run-dir runs/g4-validate
```

Outcome: exit 0; validation passed.

```bash
PATH=.venv/bin:$PATH python -m sec_graph project --run-dir runs/g4-project
```

Outcome: exit 0; projection artifacts written.

`runs/g4-project/bidder_rows.jsonl` matched the same 15-row hash as the end-to-end run.

## Gate Result

G4 passed for Stage 7:

- All four example filings produce canonical `deals`.
- The reconciled database passes hard validation with zero hard failures.
- Required judgments exist for every process cycle by validation.
- Every canonical row has evidence IDs by validation.
- Bidder rows match the exact 15-row golden projection hash.
- `python -m sec_graph run --all` runs the deterministic pipeline end to end.
