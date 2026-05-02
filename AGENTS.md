# AGENTS.md - sec_graph

This repository is an independent SEC merger-filing graph extraction project.
Agents working here should treat this folder as a standalone codebase with its
own contracts. Build from first principle instead of add patches. Allow no fallbacks and build nothing around backward compatibility. I want to watch things fail loudly.

## Purpose

`sec_graph` explores a canonical graph/data-store architecture for extracting
M&A sale-process narratives from SEC merger filings. The intended representation
has explicit filings, source spans, actors, process cycles, events,
event-actor links, judgments, and deterministic views.

## Source Material

- `docs/spec.md` is THE binding spec — design, schema invariants, build order, and slicing rules.
- `quality_reports/plans/2026-05-02_parallel-execution-plan.md` is THE executing plan — phases, tracks, sync gates.
- `docs/prior-pipeline-lessons.md` is failure-mode context from the previous attempt.
- `data/examples/` contains the current example filings.
- `seeds.csv` lists EDGAR filing URLs available for local download.
- `data/filings/` contains downloaded EDGAR artifacts produced by the local
  fetcher.

## Boundaries

- Keep all source code, generated artifacts, and state inside this project
  unless Austin explicitly asks for an import or export.
- Do not modify external repositories or external data directories as part of
  normal project work.
- If this project later compares against another system, use explicit exported
  comparison artifacts under this repo, not shared state.

## Working Rules

- Keep generated outputs out of source directories. Use `runs/`, `artifacts/`,
  or `tmp/` for generated data.
- Every durable architecture or schema decision belongs in `docs/spec.md`. Plan
  changes go in `quality_reports/plans/`.
- Treat filing text as research data. Preserve exact quotes and provenance.
- Use deterministic IDs where possible so tests and diffs stay stable.
- Add tests for each new parser, schema transform, and projection rule.
- Use `scripts/fetch_filings.py` for EDGAR downloads. It resolves the
  substantive filing document, stores raw SEC HTML, converts with sec2md, and
  writes a manifest under `data/filings/{deal_slug}/`.
- Do not add provider-specific LLM code until the provider interface is
  designed in docs first.
- Do not commit secrets. Use environment variables or `.env` files excluded by
  `.gitignore`.

## Current Project Layout

```text
data/examples/                                              Example filing markdown files.
data/filings/                                               Downloaded EDGAR filings and manifests.
docs/spec.md                                                Sole source of truth for design.
docs/prior-pipeline-lessons.md                              Failure-mode postmortem from prior attempt.
quality_reports/plans/                                      Sole source of truth for execution.
quality_reports/session_logs/                               Incremental session logs.
scripts/fetch_filings.py                                    EDGAR downloader and sec2md converter.
seeds.csv                                                   Filing URL seed table.
src/sec_graph/                                              Python package, currently minimal.
tests/                                                      Test suite.
```
