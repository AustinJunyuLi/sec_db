# sec_graph

Independent SEC merger-filing graph extraction project.

## Current Authority

- `docs/superpowers/specs/2026-05-03-pipeline-hard-reset-design.md`
- `docs/spec.md`
- `docs/llm-interface.md`

The pipeline is a hard reset around a run kernel, evidence map, Linkflow
GPT-5.5 P8 claim-only extraction, quote validation, Python-owned coverage,
claim dispositions, relational evidence links, a canonical graph, semantic
validation, actor-cycle projection, cost/runtime artifacts, and a corpus
skeleton.

## Rules

- No fallbacks.
- No backward compatibility.
- No legacy provider payload readers.
- No provider-owned source offsets.
- No canonical rows written by the model.
- No rules-only `SOUND` proof.
- No secrets in code, docs, artifacts, logs, or command output.

## Data

- `data/examples/` contains hand-trimmed fixtures.
- `data/filings/` contains local downloaded EDGAR artifacts and must not be
  deleted by cleanup work.
- `seeds.csv` lists filing URLs available for local download.

Fetch filings with:

```bash
python scripts/fetch_filings.py --slug petsmart-inc
```

Tender-offer filings must select the `EX-99.(A)(1)(A)` Offer to Purchase
exhibit or fail loudly.

## Run

Use the top-level dispatcher:

```bash
python -m sec_graph run \
  --source filings \
  --slugs petsmart-inc mac-gray providence-worcester \
  --run-id 2026-05-03T010203Z_3-deals_deadbeef \
  --run-dir runs/2026-05-03T010203Z_3-deals_deadbeef \
  --llm-provider linkflow \
  --llm-model gpt-5.5 \
  --llm-reasoning-effort medium
```

`--resume` is explicit and conservative. It refuses changed input or run
configuration.

Offline verification:

```bash
PYTHONDONTWRITEBYTECODE=1 uv run pytest -q -p no:cacheprovider
```
