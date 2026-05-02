# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Status

`sec_graph` is in early scaffolding. Today the package contains only the EDGAR fetcher (`src/sec_graph/edgar.py`). The full architecture (7-module pipeline, DuckDB canonical store, evidence-bound graph schema) is specified but **not yet implemented** — see "Living design contracts" below.

When asked to add code, check whether you are working inside the active stage. Stage 1 (schema scaffolding) is the current critical-path work.

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
```

`pyproject.toml` puts `src/` on the pytest path, so tests import `sec_graph` directly without any extra setup.

## Architecture: Big Picture

### Living design contracts

The architecture is governed by two documents — read these before making non-trivial changes:

- `docs/design.md` — Live local design contract. Defines canonical objects (`CleanFiling`, `SourceSpan`, `Actor`, `ProcessCycle`, `Event`, `EventActorLink`, `Judgment`, `ParticipationCount`), data flow, evidence policy, and first-milestone scope.
- `docs/superpowers/specs/2026-05-02-sec-graph-modular-architecture.md` — Full modular architecture spec (7 modules, storage substrate, run model, parallelization tracks, build order Stages 0-9). The current implementation plan is `docs/superpowers/plans/2026-05-02-stage-1-schema-scaffolding.md`.

`AGENTS.md` defines repository boundaries and working rules.

### Pipeline shape (target architecture)

Filing → 7 sequential layers, each with its own module under `src/sec_graph/`:

1. **fetch** — EDGAR HTML download + sec2md conversion (currently `edgar.py`; will move to `src/sec_graph/fetch/edgar.py` in Stage 1 Task 1).
2. **ingest** — markdown → `CleanFiling` + paragraphs + page markers + source-span seeds.
3. **extract** — deterministic patterns first; LLM later (Stage 8) behind a provider interface.
4. **reconcile** — extraction candidates → canonical records (deals, cycles, actors, events, links, judgments) with deterministic IDs and alias resolution.
5. **validate** — referential integrity, evidence binding, projection eligibility.
6. **project** — deterministic views (e.g. bidder-cycle rows). Bidder-cycle rows are NOT primary outputs — they are projections from the canonical store.
7. **schema** — Pydantic v2 models + DuckDB DDL shared across layers.

### Storage substrate

Hybrid: raw text artifacts as files, all structured tables in a single DuckDB file.

- `data/filings/{deal_slug}/` — `raw.htm`, `raw.md`, `pages.json`, `manifest.json` (already produced by the fetcher today).
- `pipeline.duckdb` (planned) — every structured table from paragraphs through canonical through `run_metadata`. Rewritten per pipeline run.
- `runs/{run_id}/canonical.duckdb` (planned) — frozen per-run snapshot for reproducibility.

`runs/`, `artifacts/`, `tmp/` are gitignored — never commit generated outputs.

### Determinism and evidence are non-negotiable contracts

- **Deterministic IDs**: form `{slug}_{type}_{sequence}` (helpers in the planned `schema/ids.py`). Tests must demonstrate stable reruns.
- **Evidence binding**: any canonical fact must reference one or more `SourceSpan` ids whose `quote_hash` resolves to exact filing text. Python code owns offsets and quote hashing — never trust span text from an LLM without re-resolving.
- **Append-only judgments**: reviewer overrides chain via `supersedes_judgment_id`. Cross-run persistence is an open Stage 9 problem flagged in the spec — Stage 1 schema must accommodate either resolution.
- **Per-stage version counters**: PARSER / INGEST / EXTRACT / RECONCILE / VALIDATE / PROJECT versions stamp every artifact. Bump them when changing the corresponding layer's behavior.

### Fetch module conventions

`src/sec_graph/edgar.py` enforces SEC etiquette and substantive-document selection:

- `USER_AGENT` is hardcoded with contact info per SEC requirements; throttled at `MIN_DELAY_SEC` with exponential backoff on 429/403.
- `PRIMARY_FORM_TYPES` whitelists DEFM14A / PREM14A / SC TO-T / S-4 (and amendments). `EXCLUDED_FORM_TYPES` rejects 425.
- For `SC TO-T` filings, the fetcher prefers the EX-99.(A)(1)(A) "Offer to Purchase" exhibit over the cover form (see `OFFER_TO_PURCHASE_EXHIBIT_PATTERN`). Test coverage in `tests/test_edgar.py::test_resolve_substantive_document_picks_offer_to_purchase_for_tender_offer`.
- Manifests record sha256 hashes for `raw.htm`, `raw.md`, `pages.json` plus the sec2md version — preserve this when modifying the fetcher.

## Working Rules (project-specific)

- **Generated outputs stay outside source dirs.** Use `runs/`, `artifacts/`, `tmp/` (all gitignored).
- **Architecture/schema decisions go in docs/**, not in code comments. Update `docs/design.md` or write a versioned note under `docs/`.
- **Preserve quotes and provenance exactly.** Treat filing text as research data.
- **Tests before extraction logic.** Add tests for parsers, schema transforms, and projection rules as they land.
- **Do not add LLM provider code** until the provider interface is designed in docs (Stage 8 territory).
- **No external repo edits.** Keep all source, state, and artifacts inside this project unless explicitly asked.

## Reference Material (read-only)

- `docs/references/gptpro_v2/plan/` — original GPT-Pro greenfield proposal. Reference, not contract.
- `docs/references/gptpro_v2/derive_views.py` — bidder-cycle projection reference; the planned `project` layer should align with it.
- `docs/architecture/lessons-from-prior-extraction-pipeline.md` — postmortem context.
- `data/examples/` — four trimmed example filings (petsmart, providence-worcester, saks, zep).
- `seeds.csv` — 401 filing rows with `deal_slug,target_name,acquirer,date_announced,primary_url,is_reference`.
