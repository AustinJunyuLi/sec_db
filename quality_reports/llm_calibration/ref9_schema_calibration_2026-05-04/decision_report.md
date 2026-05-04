# Reference-9 Linkflow Schema Calibration Decision Report

**Date:** 2026-05-04
**Artifact root:** `quality_reports/llm_calibration/ref9_schema_calibration_2026-05-04/`
**Credential handling:** Linkflow credentials were read from environment variables only; no key is written in these artifacts.

## Run Coverage

- Result artifacts recorded: 454
- Results by stage: {'stage1': 131, 'stage2': 251, 'stage4': 72}
- Provider/contract failures recorded: 0

## Aggregate Metrics

| Stage | Candidate | Jobs | OK | OK rate | Mean quote match | Mean claims/job | Expanded fields | Multi-quote claims |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| stage1 | CLAIM_ONLY_P8 | 32 | 32 | 1.0 | 0.9975 | 16.2812 | 30 | 0 |
| stage1 | EXPANDED_CLAIM_ONLY_P8 | 32 | 32 | 1.0 | 0.9854 | 18.2188 | 308 | 0 |
| stage1 | EXPANDED_MULTI_QUOTE_P8 | 32 | 32 | 1.0 | 0.9973 | 18.25 | 377 | 17 |
| stage1 | PLAIN_RECALL_SIDECAR | 3 | 3 | 1.0 | 0.6228 | 0 | 0 | 0 |
| stage1 | V0_P8_BASELINE | 32 | 32 | 1.0 | 0.9919 | 9.9375 | 9 | 0 |
| stage2 | CLAIM_ONLY_P8 | 88 | 88 | 1.0 | 0.9974 | 14.8864 | 101 | 0 |
| stage2 | EXPANDED_CLAIM_ONLY_P8 | 88 | 88 | 1.0 | 0.9935 | 16.625 | 927 | 0 |
| stage2 | EXPANDED_MULTI_QUOTE_P8 | 68 | 68 | 1.0 | 0.9928 | 17.8382 | 743 | 22 |
| stage2 | PLAIN_RECALL_SIDECAR | 7 | 7 | 1.0 | 0.8976 | 0 | 0 | 0 |
| stage4 | CLAIM_ONLY_P8 | 72 | 72 | 1.0 | 0.9937 | 12.6389 | 60 | 0 |

## Decision

**Provisional chosen schema candidate:** `CLAIM_ONLY_P8`.

It removes provider-side negative coverage accounting without adding fields that hurt transport or quote discipline.

## Recommended Defaults

- Schema: `CLAIM_ONLY_P8`.
- Prompt: `P8` validator-aware typed-claim prompt.
- Reasoning effort: `medium`.
- Production windowing: Python-selected `W2_MULTI_REGION` calls, with `W1_SALE_PROCESS` retained as the broad sale-process support window.
- Coverage ownership: Python-only. Linkflow may emit positive `coverage_obligation_id` links but must not emit provider-owned negative coverage verdicts.

## Candidate Observations

- `CLAIM_ONLY_P8` completed full Stage 2 at 88/88 with mean quote match 0.9974 and no provider-owned coverage block.
- `EXPANDED_CLAIM_ONLY_P8` completed full Stage 2 at 88/88 and emitted 1.7386 more claims/job, but quote match was lower by 0.0039. The added source fields are not worth adopting unless manual hard-fact review proves they recover facts Python cannot derive cleanly.
- `V0_P8_BASELINE` is rejected as a production target because it keeps `coverage_results` in the provider response and under-emitted relative to claim-only shapes in Stage 1.
- `EXPANDED_MULTI_QUOTE_P8` is rejected absent a manual-review reason: it adds evidence-identity complexity and did not justify broad promotion beyond the partial Stage 2 evidence.
- `PLAIN_RECALL_SIDECAR` remains useful for reviewer discovery only and is not eligible as a production schema.

## Variance Check

`CLAIM_ONLY_P8` completed Stage 4 at 72/72 on the hard variance set with mean quote match 0.9937 and mean claims/job 12.6389.

This supports keeping `medium` as the default reasoning effort. The remaining review task is semantic: compare accepted core facts across replicas before freezing docs, but there is no transport/schema reason to rerun the same matrix at `xhigh`.

## Rejection Rules Applied

- `PLAIN_RECALL_SIDECAR` is reviewer evidence only and is not eligible as a production schema.
- Higher claim count is not treated as better unless quote binding remains exact and the claims are canonicalizable.
- `EXPANDED_MULTI_QUOTE_P8` requires a manual-review reason to beat `EXPANDED_CLAIM_ONLY_P8`.
- Any candidate with provider or strict-schema instability must be rejected regardless of recall.

## Required Follow-Through

- Update `docs/spec.md` to make claim-only P8 the deployable schema once replica-level hard facts are manually reviewed.
- Update `docs/llm-interface.md` with the final P8 shape, coverage ownership, `medium` default reasoning effort, and Stage 3 escalation rule.
- Keep Python quote binding, source coordinates, coverage verdicts, dispositions, canonicalization, and projections outside provider control.

## Stage 3 Note

The original calibration design listed `medium`, `high`, and `xhigh` for the hard-case reasoning ladder. Because Stage 2 supplied a complete medium baseline for the two serious candidates and Stage 4 verified the winner's reproducibility path, Stage 3 was not run broadly. If manual hard-fact review finds a specific medium miss, Stage 3 should be pruned to `high` for the top candidate and the single serious challenger first. `xhigh` should run only as a narrow spot-check if `high` materially recovers source-backed hard facts that medium misses. Do not run broad `xhigh` calls merely to increase row count.
