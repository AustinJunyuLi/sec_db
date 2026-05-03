# AGENTS.md - sec_graph

This repository is an independent SEC merger-filing graph extraction project.
Agents working here should treat this folder as a standalone codebase with its
own contracts. Build from first principle instead of add patches. Allow no
fallbacks and build nothing around backward compatibility. I want to watch
things fail loudly.

## Purpose

`sec_graph` explores a canonical graph/data-store architecture for extracting
M&A sale-process narratives from SEC merger filings. The intended representation
has explicit filings, source spans, actors, actor relations, process cycles,
events, event-actor links, participation counts, judgments, and deterministic
projection views.

## Current Authority Chain

These documents form the active authority chain. Read them before any
non-trivial change:

- `docs/superpowers/specs/2026-05-03-pipeline-hard-reset-design.md` is the
  full-pipeline authority for the hard reset.
- `docs/spec.md` is the binding design and schema contract. §1A is the
  deployable-schema authority.
- `docs/llm-interface.md` is the Linkflow typed-claim interface contract.

`docs/prior-pipeline-lessons.md` is failure-mode context from the previous
attempt and informs spec invariants but is not execution authority.

## Source Material

- `docs/spec.md` — binding design, schema invariants, build order, slicing
  rules, fail-loud contracts.
- `docs/llm-interface.md` — Linkflow/LLM typed-claim interface contract.
- `data/examples/` contains four trimmed example filings used for unit-level
  fixtures, not as pipeline proof.
- `data/filings/` contains downloaded EDGAR artifacts produced by the local
  fetcher. This is local research source material; do not delete it.
- `seeds.csv` lists EDGAR filing URLs available for local download.

## Boundaries

- Keep all source code, generated artifacts, and state inside this project
  unless Austin explicitly asks for an import or export.
- Do not modify external repositories or external data directories as part of
  normal project work.
- If this project later compares against another system, use explicit exported
  comparison artifacts under this repo, not shared state.

## Working Rules

- Keep generated outputs out of source directories. Use `runs/`, `artifacts/`,
  or `tmp/` for generated data; all are gitignored.
- Every durable architecture or schema decision belongs in `docs/spec.md`. Plan
  changes go in `quality_reports/plans/`.
- Treat filing text as research data. Preserve exact quotes and provenance.
- Use deterministic IDs where possible so tests and diffs stay stable.
- Add tests for each new parser, schema transform, and projection rule.
- `scripts/fetch_filings.py` is a deliberate root convenience command for EDGAR
  downloads; it is not retained for backward compatibility. Top-level CLI
  dispatch through `python -m sec_graph` is the primary entry point and must
  forward `--fresh` to `ingest`.
- Tender-offer (`SC TO-T`) filings must fail loudly when no
  `EX-99.(A)(1)(A)` "Offer to Purchase" exhibit is selected. No fallback to
  the cover form is allowed.
- Keep provider-specific LLM code isolated under `src/sec_graph/extract/llm/`
  and bound by `docs/llm-interface.md`. No fallback, no backward compatibility,
  no provider-owned source offsets.
- Do not commit secrets. Use environment variables or `.env` files excluded by
  `.gitignore`.

## Current Project Layout

```text
data/examples/                                              Hand-trimmed example filings (fixtures, not pipeline proof).
data/filings/                                               Downloaded EDGAR filings and manifests (local research data).
docs/spec.md                                                Binding design and schema contract.
docs/llm-interface.md                                       Binding LLM interface contract.
docs/prior-pipeline-lessons.md                              Failure-mode postmortem (context only, not authority).
quality_reports/plans/                                      Active and historical execution plans.
quality_reports/session_logs/                               Point-in-time proof logs (see README.md inside).
scripts/fetch_filings.py                                    EDGAR downloader and sec2md converter (root convenience command).
seeds.csv                                                   Filing URL seed table.
src/sec_graph/                                              Implemented Python package.
tests/                                                      Test suite.
```
