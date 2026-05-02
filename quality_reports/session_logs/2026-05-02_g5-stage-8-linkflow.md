# Session Log: G5 Stage 8 Linkflow

**Date:** 2026-05-02
**Branch:** `main`
**Gate:** G5 - Stage 8 opt-in Linkflow LLM extraction

## Scope

Implemented and verified the Stage 8 LLM gate from
`quality_reports/plans/2026-05-02_stage-8-llm-linkflow-plan.md`:

- Added the provider-neutral LLM request/response/candidate contract under
  `src/sec_graph/extract/llm/`.
- Kept LLM extraction disabled by default; rules-only output remains hash-locked.
- Added opt-in CLI flags for `extract` and `run`.
- Added a Linkflow adapter for GPT-5.5 Responses calls with reasoning effort
  controls.
- Kept Linkflow-specific code isolated in `src/sec_graph/extract/llm/linkflow.py`.
- Wrote sanitized live artifacts under `artifacts/linkflow/2026-05-02_stage8_live/`.

## Provider Debugging Notes

The final adapter uses prompt-only JSON plus strict local validation. Earlier
provider-schema calls failed before model output was usable, while plain
Responses calls with the same model/reasoning controls succeeded. The adapter
therefore does not rely on provider-enforced structured output.

During live hardening, the provider also returned:

- JSON missing required candidate fields, which now fails as `contract_invalid`
  and writes a sanitized failure artifact;
- a candidate with a mismatched quote offset, which remains a hard local
  conversion failure.

No invalid payload was salvaged into active candidates.

## Offline Verification

Command:

```bash
PATH=.venv/bin:$PATH python -m pytest tests/test_llm_interface.py -q
```

Outcome: exit 0; 5 passed.

Command:

```bash
PATH=.venv/bin:$PATH python -m pytest tests/test_llm_interface.py tests/test_extract_llm_disabled.py tests/test_linkflow_live.py -q
```

Outcome without live env: exit 0; 7 passed, 1 skipped.

## Live Linkflow Matrix

The live pytest gate used a real PetSmart paragraph, narrowed to
`actor_mention` candidates, and inserted returned candidates into local
`candidates` plus extract-stage `spans`.

Command:

```bash
SEC_GRAPH_LIVE_LINKFLOW=1 SEC_GRAPH_LINKFLOW_EFFORTS=low,high PATH=.venv/bin:$PATH python -m pytest tests/test_linkflow_live.py -q
```

Outcome: exit 0; 1 passed in 49.47s.

Command:

```bash
SEC_GRAPH_LIVE_LINKFLOW=1 SEC_GRAPH_LINKFLOW_EFFORTS=low,medium,high,xhigh PATH=.venv/bin:$PATH python -m pytest tests/test_linkflow_live.py -q
```

Outcome: exit 0; 1 passed in 76.92s.

Artifact manifest:

| Artifact | Candidate count | Status |
|----------|-----------------|--------|
| `artifacts/linkflow/2026-05-02_stage8_live/petsmart-inc_llmrequest_30_low_success.json` | 3 | completed |
| `artifacts/linkflow/2026-05-02_stage8_live/petsmart-inc_llmrequest_30_medium_success.json` | 3 | completed |
| `artifacts/linkflow/2026-05-02_stage8_live/petsmart-inc_llmrequest_30_high_success.json` | 3 | completed |
| `artifacts/linkflow/2026-05-02_stage8_live/petsmart-inc_llmrequest_30_xhigh_success.json` | 3 | completed |

Artifact hygiene check:

```bash
rg -n "sk-[A-Za-z0-9]{20,}|Authorization|Bearer|LINKFLOW_API_KEY|output_text|paragraph_text|quote_text" artifacts/linkflow/2026-05-02_stage8_live
```

Outcome: exit 1; no matches.

## Opt-in CLI Smoke

Command:

```bash
PATH=.venv/bin:$PATH python -m sec_graph ingest --all --db tmp/stage8-cli-live.duckdb
```

Outcome: exit 0; ingested 4 filings into `tmp/stage8-cli-live.duckdb`.

Command:

```bash
SEC_GRAPH_LIVE_LINKFLOW=1 PATH=.venv/bin:$PATH python -m sec_graph extract --filing-id petsmart-inc_filing_1 --db tmp/stage8-cli-live.duckdb --llm-provider linkflow --llm-model gpt-5.5 --llm-reasoning-effort high --llm-limit 1
```

Outcome: exit 0; extracted candidates for 1 filing.

Additional artifact:

| Artifact | Candidate count | Status |
|----------|-----------------|--------|
| `artifacts/linkflow/2026-05-02_stage8_live/petsmart-inc_llmrequest_1_high_success.json` | 0 | completed |

## Gate Result

G5 passed:

- Linkflow GPT-5.5 accepted `low`, `medium`, `high`, and `xhigh` reasoning efforts.
- Live tests inserted at least one LLM candidate for every requested reasoning effort.
- LLM candidates remained candidate-only and did not write canonical rows.
- Rules-only extraction remains the default when LLM flags are absent.
- Provider failures and local contract failures remain hard failures.
- Live artifacts contain sanitized metadata only.

## Final Release Verification

Command:

```bash
PATH=.venv/bin:$PATH python -m pytest
```

Outcome: exit 0; 46 passed, 1 skipped.

Command:

```bash
PATH=.venv/bin:$PATH python -m pytest tests/ -x --ff
```

Outcome: exit 0; 46 passed, 1 skipped.

Command:

```bash
PATH=.venv/bin:$PATH python -m pytest tests/ -x --ff
```

Outcome: exit 0; 46 passed, 1 skipped.

Command:

```bash
PATH=.venv/bin:$PATH python scripts/fetch_filings.py --help
```

Outcome: exit 0; help listed `--slug`, `--reference-only`, `--all`, and `--force`.

Command:

```bash
PATH=.venv/bin:$PATH python -m sec_graph --help
```

Outcome: exit 0; help listed `ingest`, `extract`, `reconcile`, `validate`, `project`, and `run`.

Command:

```bash
PATH=.venv/bin:$PATH python -m sec_graph ingest --all
PATH=.venv/bin:$PATH python -m sec_graph extract --all
PATH=.venv/bin:$PATH python -m sec_graph reconcile
PATH=.venv/bin:$PATH python -m sec_graph validate
PATH=.venv/bin:$PATH python -m sec_graph project
PATH=.venv/bin:$PATH python -m sec_graph run --all
```

Outcome: all exit 0. The final `runs/latest/validation_report.json` reports
`passed: true`, `hard_failures: []`, and `soft_flag_count: 8`.

Final projection check:

- `runs/latest/bidder_rows.jsonl`: 15 rows
- Normalized projection SHA-256:
  `0123b0f860b7a515866fd19b9a4d3f693e1a6ce5576e427a4e3eae529431ff9a`
