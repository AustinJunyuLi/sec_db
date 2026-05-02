# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with
code in this repository. Build from first principle instead of add patches.
Allow no fallbacks and build nothing around backward compatibility. I want to
watch things fail loudly.

## Project Status

The repository is mid-cleanse. The pipeline modules (`fetch`, `ingest`,
`extract`, `reconcile`, `validate`, `project`, `schema`) are wired end to end
through `python -m sec_graph`, but several contract violations are being
repaired under
`quality_reports/plans/2026-05-02_stale-scaffold-hard-cleanse-repair-plan.md`.

The deployable schema authority is `docs/spec.md` §1A. The LLM interface exists
but is being repaired from paragraph-local requests to within-deal narrative
windows; see `docs/llm-interface.md` for the in-progress contract.

When asked to add code, check `docs/spec.md` first, then check the executing
hard-cleanse repair plan for any open phase.

## Current Authority Chain

- `docs/spec.md` is the binding design and schema authority. §1A is the
  binding deployable schema contract.
- `quality_reports/plans/2026-05-02_stale-scaffold-hard-cleanse-repair-plan.md`
  is the executing cleanup-and-repair plan until every phase inside it is
  complete.
- `quality_reports/plans/2026-05-02_deployable-canonical-pipeline-goal.md` is
  the goal-handoff document for live proof, read alongside its companion
  implementation plan
  `quality_reports/plans/2026-05-02_deployable-canonical-pipeline-plan.md`.
- `docs/prior-pipeline-lessons.md` is failure-mode context only, not execution
  authority.

The earlier `quality_reports/plans/2026-05-02_parallel-execution-plan.md` is
no longer execution authority and is being deleted as part of the hard-cleanse.

## Common Commands

```bash
# Editable install with dev extras (pytest)
python -m pip install -e ".[dev]"

# Run the full test suite
pytest

# Run a single test file or test
pytest tests/test_edgar.py
pytest tests/test_edgar.py::test_parse_accession_accepts_compact_nested_and_direct_urls -v

# Fetch filings from EDGAR (one of --slug / --reference-only / --all is required)
python scripts/fetch_filings.py --slug medivation
python scripts/fetch_filings.py --reference-only
python scripts/fetch_filings.py --all --force

# Ingest example filings into a fresh DuckDB store
python -m sec_graph ingest --input data/examples --db data/pipeline.duckdb --fresh

# Run the full pipeline against named filings into an immutable run directory
python -m sec_graph run \
  --source filings \
  --slugs petsmart-inc \
  --run-id "$(date -u +%Y-%m-%dT%H%M%SZ)_petsmart_local" \
  --run-dir runs/$RUN_ID

# Project an existing canonical store under a named projection
python -m sec_graph project --projection bidder_cycle_baseline_v1 --run-dir runs/$RUN_ID
```

`pyproject.toml` puts `src/` on the pytest path, so tests import `sec_graph`
directly without any extra setup.

`python -m sec_graph` is the single entry point. The top-level dispatcher must
forward `--fresh` to the `ingest` subcommand. `scripts/fetch_filings.py` is a
deliberate root convenience command; it is not retained for backward
compatibility.

## Architecture: Big Picture

### Sources of truth

- `docs/spec.md` is the binding design and schema authority. Canonical objects,
  schema invariants, module catalog, storage substrate, determinism contract,
  build order, fail-loud contracts. §1A is the deployable schema contract.
- `docs/llm-interface.md` is the binding LLM interface contract. The interface
  is being repaired from paragraph-local requests to within-deal narrative
  windows.
- `quality_reports/plans/2026-05-02_stale-scaffold-hard-cleanse-repair-plan.md`
  is the active repair plan.
- `docs/prior-pipeline-lessons.md` is failure-mode postmortem context.

The module-table ownership policy is in `docs/spec.md` §3.8. Treat it as
binding: no module writes another module's tables without changing the spec
first.

### Pipeline shape

Filing → 7 sequential layers, each with its own module under `src/sec_graph/`:

1. **fetch** — EDGAR HTML download + sec2md conversion
   (`src/sec_graph/fetch/edgar.py`). Tender-offer filings must fail loudly if
   no `EX-99.(A)(1)(A)` Offer to Purchase exhibit is selected; no fallback to
   the cover form is allowed.
2. **ingest** — Markdown → `CleanFiling` + paragraphs + page markers +
   source-span seeds, written to evidence tables. `--fresh` is forwarded by
   top-level dispatch.
3. **extract** — Default deterministic regex path (golden-hash locked); opt-in
   live Linkflow GPT-5.5 adapter at `src/sec_graph/extract/llm/linkflow.py`.
   The request contract is being moved from single paragraphs to within-deal
   narrative windows.
4. **reconcile** — Candidates → canonical records (deals, actors,
   actor_relations, process_cycles, events, event_actor_links,
   participation_counts, judgments) with deterministic IDs and alias
   resolution.
5. **validate** — Referential integrity, evidence-binding source-truth checks,
   projection-eligibility checks against the canonical store.
6. **project** — Deterministic views over canonical tables. Bidder-cycle rows
   are NOT primary outputs — they are projections over the canonical store and
   require a current `projection_eligibility` judgment per actor-cycle row.
7. **schema** — Pydantic v2 models + DuckDB DDL shared across layers.

### Storage substrate

Hybrid: raw text artifacts as files, structured tables in DuckDB.

- `data/filings/{deal_slug}/` — `raw.htm`, `raw.md`, `pages.json`,
  `manifest.json` (produced by the fetcher).
- `data/pipeline.duckdb` — working canonical store. May only be wiped under an
  explicit fresh-run path.
- `runs/{run_id}/canonical.duckdb` — immutable per-run snapshot. No command
  may overwrite an existing `runs/{run_id}/` directory unless an explicit
  fresh-run flag is provided and the docs name the exact behavior.

`runs/`, `artifacts/`, `tmp/` are gitignored — never commit generated outputs.

### Determinism and evidence are non-negotiable contracts

- **Deterministic IDs**: form `{slug}_{type}_{sequence}`. Tests must
  demonstrate stable reruns.
- **Evidence binding**: any canonical fact must reference one or more
  `SourceSpan` ids whose `quote_hash` resolves to exact filing text and whose
  coordinates verify against the source bytes. Python code owns offsets and
  quote hashing — never trust span text from an LLM without re-resolving.
- **Append-only judgments**: reviewer overrides chain via
  `supersedes_judgment_id`. No stage may unconditionally wipe `judgments`.
- **Closed enums**: every enum is closed. No `unknown`/`other`/fallback values.
- **Per-stage version counters**: PARSER / INGEST / EXTRACT / RECONCILE /
  VALIDATE / PROJECT versions stamp every artifact. Bump them when changing
  the corresponding layer's behavior.

### Fetch module conventions

`src/sec_graph/fetch/edgar.py` enforces SEC etiquette and substantive-document
selection:

- `USER_AGENT` is hardcoded with contact info per SEC requirements; throttled
  at `MIN_DELAY_SEC` with exponential backoff on 429/403.
- `PRIMARY_FORM_TYPES` whitelists DEFM14A / PREM14A / SC TO-T / S-4 (and
  amendments). `EXCLUDED_FORM_TYPES` rejects 425.
- For `SC TO-T` filings, the fetcher must prefer the EX-99.(A)(1)(A) "Offer to
  Purchase" exhibit. If no such exhibit is selected, the fetcher must fail
  loudly. There is no fallback to the cover form.
- Manifests record sha256 hashes for `raw.htm`, `raw.md`, `pages.json` plus
  the sec2md version — preserve this when modifying the fetcher.

## Working Rules (project-specific)

- **Generated outputs stay outside source dirs.** Use `runs/`, `artifacts/`,
  `tmp/` (all gitignored).
- **Architecture/schema decisions go in `docs/spec.md`**, not in code
  comments. Plan-level changes go in `quality_reports/plans/`.
- **Preserve quotes and provenance exactly.** Treat filing text as research
  data.
- **Tests before extraction logic.** Add tests for parsers, schema transforms,
  and projection rules as they land.
- **Do not change LLM provider behavior** without first updating
  `docs/llm-interface.md`. No fallback, no backward compatibility, no
  provider-owned source offsets.
- **Do not promote provider-incomplete responses to completed.** Linkflow
  responses without an explicit `response.completed` event must not be
  promoted to `finish_status="completed"`.
- **No external repo edits.** Keep all source, state, and artifacts inside
  this project unless explicitly asked.

## Local Reference Data (read-only)

- `docs/prior-pipeline-lessons.md` — postmortem context from the prior
  extraction attempt.
- `data/examples/` — four trimmed example filings (petsmart, providence-worcester, saks, zep).
- `data/filings/` — downloaded EDGAR filings; local research data.
- `seeds.csv` — 401 filing rows with `deal_slug,target_name,acquirer,date_announced,primary_url,is_reference`.
