# sec_graph

Independent side project for building a canonical graph-style data pipeline
from SEC merger filing narratives.

## Current Status

The repository is mid-cleanse under the executing repair plan
`quality_reports/plans/2026-05-02_stale-scaffold-hard-cleanse-repair-plan.md`.
The pipeline is wired through `python -m sec_graph` against local example
filings, but several fail-loud and within-deal-memory contracts are still
being repaired. Treat `data/examples/` as fixtures, not as pipeline proof;
treat `data/filings/` as local research source material.

The LLM interface exists but is being repaired from paragraph-local requests
to within-deal narrative windows; see `docs/llm-interface.md`.

## Authority Chain

- `docs/spec.md` — binding design and schema contract. §1A is the binding
  deployable schema authority.
- `quality_reports/plans/2026-05-02_stale-scaffold-hard-cleanse-repair-plan.md`
  — executing cleanup-and-repair plan.
- `quality_reports/plans/2026-05-02_deployable-canonical-pipeline-goal.md`
  — goal handoff for live deployable proof, paired with its companion
  implementation plan
  `quality_reports/plans/2026-05-02_deployable-canonical-pipeline-plan.md`.
- `docs/llm-interface.md` — Linkflow/LLM interface contract.
- `docs/prior-pipeline-lessons.md` — failure-mode postmortem (context only,
  not authority).

The earlier `quality_reports/plans/2026-05-02_parallel-execution-plan.md` is
no longer execution authority and is being deleted as part of the hard-cleanse.

## Goal

Build a filing-to-canonical-store pipeline that represents deals, cycles,
actors, actor relations, events, evidence spans, links, participation counts,
and interpretation judgments. Bidder-cycle estimator rows are deterministic
projection views over the canonical store rather than the primary extraction
format, and require a current `projection_eligibility` judgment per row.

## Non-Goals

- Zero fallbacks of any flavor: not for model selection, not for provider,
  not for transport, not for schema, not for payload shape.
- No backward-compatibility readers or migration paths for stale contracts.
- No provider-owned source offsets. Linkflow may emit `quote_text`; Python
  owns substring validation and span derivation.
- No catch-all enum values such as `unknown` or `other`.
- No PetSmart-only or otherwise deal-specific schema surfaces.
- Do not read from or write to directories outside this project during normal
  operation.

## Fetch Filings

Install the package locally, then fetch one filing from `seeds.csv`:

```bash
python -m pip install -e ".[dev]"
python scripts/fetch_filings.py --slug medivation
```

Use `--reference-only` to fetch reference rows and `--all` for every row in
`seeds.csv`. Existing downloaded artifacts are skipped unless `--force` is set.

`scripts/fetch_filings.py` is a deliberate root convenience command for EDGAR
downloads; it is not retained for backward compatibility.

Fetched artifacts are written under `data/filings/{deal_slug}/`:

- `raw.htm` - downloaded SEC HTML document.
- `raw.md` - sec2md markdown with page markers.
- `pages.json` - structured per-page text payload.
- `manifest.json` - source URL, selected document, fetch timestamp, and hashes.

For tender offers (`SC TO-T`), the fetcher must select the
`EX-99.(A)(1)(A)` "Offer to Purchase" exhibit. If no such exhibit is found,
the fetcher fails loudly. There is no fallback to the cover form.

## Run The Pipeline

`python -m sec_graph` is the single entry point. The top-level dispatcher
forwards `--fresh` to the `ingest` subcommand.

```bash
# Ingest example filings into a fresh DuckDB store
python -m sec_graph ingest --input data/examples --db data/pipeline.duckdb --fresh

# Run the full pipeline against named filings into an immutable run directory
RUN_ID="$(date -u +%Y-%m-%dT%H%M%SZ)_petsmart_local"
python -m sec_graph run \
  --source filings \
  --slugs petsmart-inc \
  --run-id "$RUN_ID" \
  --run-dir "runs/$RUN_ID"

# Project an existing canonical store under a named projection
python -m sec_graph project --projection bidder_cycle_baseline_v1 --run-dir "runs/$RUN_ID"
```

No command may overwrite an existing `runs/{run_id}/` directory unless an
explicit fresh-run flag is provided and the docs name the exact behavior.

## Suggested First Work

1. Read `docs/spec.md` (especially §1A) and the executing repair plan.
2. Skim `docs/prior-pipeline-lessons.md` for failure-mode context.
3. Check `quality_reports/session_logs/README.md` for the current proof-log
   index and which historical commands are no longer safe to rerun without
   first checking `python -m sec_graph --help`.
4. Add tests before any extraction or reconciliation logic.
