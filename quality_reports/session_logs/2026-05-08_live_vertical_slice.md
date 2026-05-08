# Live synthetic vertical slice — 2026-05-08

**Story:** US-011 (Phase 10 — Live Vertical Slice)
**Branch:** `clean-slate/agentic-review-compiler`
**Linkflow probe gate:** `runs/linkflow-probe/20260508T123815Z/` → `Gate: GO`

## Command (key redacted)

```bash
set -a; source ~/.config/sec_graph/linkflow.env; set +a
# Env now carries LINKFLOW_API_KEY=<REDACTED>, LINKFLOW_BASE_URL=https://www.linkflow.run/v1,
# LINKFLOW_MODEL=gpt-5.5, LINKFLOW_DEFAULT_REASONING=medium.
PYTHONPATH=src python3 -m sec_review_compiler run-synthetic \
    --run-root runs/live \
    --deal-slug synthetic-demo \
    --mode live
```

The credential is sourced from `~/.config/sec_graph/linkflow.env` (chmod 600,
gitignored by location) and never appears on the command line, in stdout, or
in any committed artifact.

## Run directory

```
runs/live/20260508T142803Z_synthetic-demo_d1ad89b4/synthetic-demo/
├── deal_room.duckdb
├── exports/
│   ├── claim_cards.csv
│   ├── human_decisions_template.csv
│   └── review_queue.csv
├── filing_package_manifest.json
├── provider_calls.jsonl
└── tool_calls.jsonl
```

## Counts

| Metric                            | Value |
|-----------------------------------|-------|
| Provider (Linkflow) calls         | 13    |
| Tool dispatches                   | 24    |
| Claim attempts proposed           | 12    |
| Accepted attempts                 | 4     |
| Escalated attempts                | 8     |
| Superseded attempts               | 0     |
| Corrections created               | 0     |
| Verifier verdicts: confirm        | 4     |
| Verifier verdicts: ambiguous      | 8     |
| Canonical rows: deal              | 1     |
| Canonical rows: filing            | 1     |
| Canonical rows: source_span       | 4     |
| Canonical rows: event             | 4     |
| Open review queue size            | 8     |
| `can_publish_trusted`             | `true` |

## Reasoning effort

- **Extractor (`timeline_bid_extractor`):** `low` — tracked by
  `LiveExtractorConfig.reasoning_effort`. With higher effort the model
  exceeded the 16-turn cap by chaining redundant tool calls; `low` is
  decisive enough for the synthetic fixture and is the default per the
  Ralph prompt's reasoning-effort policy.
- **Verifier (`verifier`):** `high` — adjudication-class call. Recorded
  per `LiveLinkflowVerifier(reasoning_effort='high')`.

## Notes

- 12 attempts come from the timeline-bid extractor's first-turn batch. 4
  attempts (NDA, IOI, two final bids) cited verbatim quotes from the
  fixture and the verifier returned `confirm`. The other 8 cited quotes
  the verifier could not unambiguously locate, so it returned
  `ambiguous`. The aggregator then escalated those without inventing a
  verdict (no latest-wins).
- `provider_calls.jsonl` records summarised request/response shapes
  only — no prompts, no completions, no credentials.
- `tool_calls.jsonl` records each tool dispatch by name + arg keys
  + result-summary keys + latency. No filing text body is duplicated.
- Filing text was preserved verbatim end-to-end: the binding test
  `raw_text[start:end] == quote` continues to pass for every accepted
  attempt.
- No fallback path was used. The live mode strictly required
  `LINKFLOW_API_KEY` (verified by `test_live_mode_without_key_fails_
  before_network`).
