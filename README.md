# sec_graph — clean-slate SEC merger filing agentic review compiler

A filing-grounded extraction and review compiler for SEC merger filings.
Agents propose claim cards through Linkflow tool loops; deterministic
Python owns evidence binding, lifecycle, canonical compilation, and
publication. The first goal is reviewable accuracy, not speed.

## Authorities

- **Design spec:** [`docs/superpowers/specs/2026-05-08-agentic-review-compiler-design.md`](docs/superpowers/specs/2026-05-08-agentic-review-compiler-design.md)
- **Linkflow probe spec:** [`docs/superpowers/specs/2026-05-08-linkflow-api-probe-spec.md`](docs/superpowers/specs/2026-05-08-linkflow-api-probe-spec.md)
- **Ralph implementation plan:** [`docs/superpowers/plans/2026-05-08-agentic-review-compiler-ralph-implementation.md`](docs/superpowers/plans/2026-05-08-agentic-review-compiler-ralph-implementation.md)
- **Story list:** [`ralph/prd.json`](ralph/prd.json)

## Provider gate

Direct Linkflow SDK calls only. Tier 1 capabilities are proven by the
committed probe run [`runs/linkflow-probe/20260508T123815Z/`](runs/linkflow-probe/20260508T123815Z/),
gate `GO`, covering: SDK connectivity, reasoning levels (low/medium/high),
strict structured output (minimal + nested), single tool call, multi-turn
tool loop, tool-loop + final structured output, error/retry taxonomy,
bounded concurrency 1–8, streaming event shapes.

## Doctrine

Binding throughout the build: no fallbacks, no backward-compatibility
shims, no overengineering, no overfitting to fixtures, no patchlike
workarounds, always first principles. Filing text is truth. Python owns
evidence identity, lifecycle, and canonical compile. Agents emit
proposals only; they never write DuckDB or other persistent stores
directly. Append-only attempts; no latest-verdict-wins; coverage
`failed_to_check` blocks publication. Credentials are environment-only
and never printed, committed, or persisted in any artifact.

## Layout

```
src/sec_review_compiler/
├── __init__.py
├── __main__.py
├── cli.py
├── config.py
├── errors.py
├── run/                 # run kernel: ids, manifest, atomic IO
├── filing/              # FilingPackage, Atlas, SourceSpan
├── retrieval/           # RetrievalIndex + deterministic tools
├── store/               # deal-room DuckDB schema + lifecycle + repository
├── llm/                 # Linkflow adapter + tool loop + strict schemas
├── agents/              # role surface, prompts, output models, tool allowlists
├── orchestration/       # orchestrator, live extractor/verifier, calibration
├── exports/             # CSV / JSONL exports + human-decision import
└── canonical/           # deterministic canonical compiler
```

```
calibration/             # adversarial verifier seed cards
linkflow_probe/          # capability probe harness (not the compiler)
runs/                    # gitignored run output (probe + dev + live)
quality_reports/
└── session_logs/        # acceptance + live-slice logs
tests/                   # pytest suite (246 passing)
```

## Setup

Python 3.12 with `duckdb`, `openai`, `pydantic`, `pytest`. Credentials
live in `~/.config/sec_graph/linkflow.env` (chmod 600, gitignored by
location):

```
LINKFLOW_API_KEY=<your-key>
LINKFLOW_BASE_URL=https://www.linkflow.run/v1
LINKFLOW_MODEL=gpt-5.5
LINKFLOW_DEFAULT_REASONING=medium
```

## Commands

Tests:

```bash
python3 -m pytest -q
```

Probe gate summary (already committed):

```bash
python3 -m linkflow_probe summarize runs/linkflow-probe/20260508T123815Z
```

Initialise a run directory:

```bash
PYTHONPATH=src python3 -m sec_review_compiler init-run \
    --deal-slug synthetic-demo --run-root runs/dev
```

Synthetic vertical slice (offline; no credentials required):

```bash
PYTHONPATH=src python3 -m sec_review_compiler run-synthetic \
    --run-root runs/dev --deal-slug synthetic-demo --mode offline
```

Synthetic vertical slice (live; requires `LINKFLOW_API_KEY`):

```bash
set -a; source ~/.config/sec_graph/linkflow.env; set +a
PYTHONPATH=src python3 -m sec_review_compiler run-synthetic \
    --run-root runs/live --deal-slug synthetic-demo --mode live
```

Summarise a deal-room:

```bash
PYTHONPATH=src python3 -m sec_review_compiler summarize-run \
    runs/live/<run_id>/synthetic-demo
```

## Outputs

Every run produces, under `runs/<run_id>/<deal_slug>/`:

- `deal_room.duckdb` — the queryable authority for the deal
- `filing_package_manifest.json` — filing identity + sha256s
- `provider_calls.jsonl` — Linkflow request/response summaries
- `tool_calls.jsonl` — agent tool dispatch records
- `exports/claim_cards.csv` — every attempt + status + evidence
- `exports/review_queue.csv` — escalated / rejected / binding-failed
- `exports/human_decisions_template.csv` — empty form for hand review

After canonical compile, `canonical_rows` and `canonical_row_evidence`
hold deterministic projections of accepted attempts.

## Acceptance status

Stories US-001 through US-013 in `ralph/prd.json` carry verification
notes. Latest acceptance log:
[`quality_reports/session_logs/2026-05-08_agentic_review_compiler_acceptance.md`](quality_reports/session_logs/2026-05-08_agentic_review_compiler_acceptance.md).
