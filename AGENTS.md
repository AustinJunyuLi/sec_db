# AGENTS.md - sec_graph

This repository is an independent SEC merger-filing graph extraction project.
Agents working here should treat this folder as a standalone codebase with its
own contracts.

## Purpose

`sec_graph` explores a canonical graph/data-store architecture for extracting
M&A sale-process narratives from SEC merger filings. The intended representation
has explicit filings, source spans, actors, process cycles, events,
event-actor links, judgments, and deterministic views.

## Source Material

- `docs/design.md` is the live local design contract.
- `docs/references/gptpro_v2/plan/` is reference material, not executable code.
- `docs/references/gptpro_v2/derive_views.py` defines a reference bidder-cycle
  projection from the GPT-Pro packet.
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
- Every durable architecture or schema decision belongs in `docs/design.md` or a
  versioned design note under `docs/`.
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
data/examples/                  Example filing markdown files.
data/filings/                   Downloaded EDGAR filings and manifests.
docs/design.md                  Live project design.
docs/references/gptpro_v2/      Original GPT-Pro packet and returned plan.
scripts/fetch_filings.py        EDGAR downloader and sec2md converter.
seeds.csv                       Filing URL seed table.
src/sec_graph/                  Python package, currently minimal.
tests/                          Test suite.
```
