# sec_graph

Independent side project for building a canonical graph-style data pipeline from
SEC merger filing narratives.

## Current Status

This repo currently contains the design source material, example filings, and a
local EDGAR/sec2md ingestion path for downloading raw filing artifacts.

Primary references:

- `docs/design.md` - live project design for agents working here.
- `docs/references/gptpro_v2/plan/` - GPT-Pro greenfield architecture proposal.
- `docs/references/gptpro_v2/derive_views.py` - estimator-view reference from the packet.
- `data/examples/` - four trimmed SEC merger-filing examples.
- `scripts/fetch_filings.py` - EDGAR downloader and sec2md converter for `seeds.csv`.

## Goal

Build a filing-to-canonical-store pipeline that represents deals, cycles,
actors, events, evidence spans, links, and interpretation judgments. Bidder-cycle
estimation rows should be deterministic views over the canonical store rather
than the primary extraction format.

## Non-Goals

- Do not assume compatibility with any external extraction pipeline unless a
  future design doc says so explicitly.
- Do not read from or write to directories outside this project during normal
  operation.
- Do not use live API keys or real LLM calls until the extraction interface is
  designed and reviewed.

## Fetch Filings

Install the package locally, then fetch one filing from `seeds.csv`:

```bash
python -m pip install -e ".[dev]"
python scripts/fetch_filings.py --slug medivation
```

Use `--reference-only` to fetch reference rows and `--all` for every row in
`seeds.csv`. Existing downloaded artifacts are skipped unless `--force` is set.

Fetched artifacts are written under `data/filings/{deal_slug}/`:

- `raw.htm` - downloaded SEC HTML document.
- `raw.md` - sec2md markdown with page markers.
- `pages.json` - structured per-page text payload.
- `manifest.json` - source URL, selected document, fetch timestamp, and hashes.

## Suggested First Work

1. Read `AGENTS.md` and `docs/design.md`.
2. Read `docs/references/gptpro_v2/plan/00_README.md`.
3. Build ingestion and provenance for the four files in `data/examples/`.
4. Add tests before adding extraction or reconciliation logic.
