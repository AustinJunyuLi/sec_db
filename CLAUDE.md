# CLAUDE.md - sec_graph

This repository is an independent SEC merger-filing graph extraction project.
Treat this folder as a standalone codebase with its own contracts. Build from
first principles instead of adding compatibility patches. Allow no fallbacks and
build nothing around backward compatibility.

## Current Authority Chain

Read these before any non-trivial change:

- `docs/superpowers/specs/2026-05-03-pipeline-hard-reset-design.md` is the
  full-pipeline authority for the hard reset.
- `docs/spec.md` is the binding design and schema contract.
- `docs/llm-interface.md` is the Linkflow typed-claim interface contract.

`docs/prior-pipeline-lessons.md` is failure-mode context only, not execution
authority.

## Working Rules

- Keep generated outputs out of source directories. Use gitignored `runs/`,
  `artifacts/`, or `tmp/`.
- Preserve exact filing quotes and provenance. Treat filing text as research
  data.
- Use deterministic IDs where possible so tests and diffs stay stable.
- Add tests for every parser, schema transform, projection rule, and LLM
  contract change.
- Keep provider-specific LLM code isolated under
  `src/sec_graph/extract/llm/` and bound by `docs/llm-interface.md`.
- Do not commit secrets. Use environment variables or `.env` files excluded by
  `.gitignore`.

## Current Pipeline Shape

The pipeline is a hard reset around:

```text
SEC filing
-> run kernel
-> ingest exact text and paragraph spans
-> evidence map
-> Linkflow GPT-5.5 typed semantic claims
-> Python quote validation
-> claim disposition ledger
-> canonical graph
-> semantic validation
-> actor-cycle projection
-> proof and cost/runtime artifacts
```

Production Linkflow extraction uses one full `Background of the Merger` /
sale-process section region per filing, strict V0 typed claims, Responses API
streaming, and default `high` reasoning. Python owns source coordinates and
rejects absent, ambiguous, or mismatched quote binding.

## Commands

```bash
UV_CACHE_DIR=/private/tmp/uv-cache PYTHONDONTWRITEBYTECODE=1 uv run pytest -q -p no:cacheprovider
```

```bash
python -m sec_graph run \
  --source filings \
  --slugs petsmart-inc \
  --run-id 2026-05-03T010203Z_petsmart_deadbeef \
  --run-dir runs/2026-05-03T010203Z_petsmart_deadbeef \
  --llm-provider linkflow \
  --llm-model gpt-5.5 \
  --llm-reasoning-effort high
```

`scripts/fetch_filings.py` is a deliberate root convenience command for EDGAR
downloads. Top-level CLI dispatch through `python -m sec_graph` is the primary
entry point and must forward `--fresh` to `ingest`.

Tender-offer (`SC TO-T`) filings must fail loudly when no `EX-99.(A)(1)(A)`
Offer to Purchase exhibit is selected. No fallback to the cover form is
allowed.
