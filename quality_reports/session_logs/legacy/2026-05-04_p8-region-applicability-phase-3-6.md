# Session Log: P8 Region Applicability - Phases 3-6

**Date:** 2026-05-04
**Branch:** `main`
**Plan:** `quality_reports/plans/2026-05-04_p8_region_applicability_ref9_plan.md`

## Scope

Phases 3-6 from the active P8 plan:

- relation-aware P8 windows with the provider schema still frozen;
- Python-owned coverage classification across all four result states;
- durable offline Reference-9 applicability gate;
- live Linkflow proof using separate per-deal jobs in parallel.

Generated run payloads stayed under ignored `runs/`, `artifacts/`, and `tmp/`.
No credentials are recorded here.

## Phase 3 - Relation-Aware P8 Windows

`build_llm_windows` now derives each window's `allowed_claim_types` directly
from current applicable obligations, not from the stored region
`expected_claim_types_json`. Request construction fails loudly when a region has
no applicable obligations.

The Linkflow schema generator constrains `actor_relation_claims.relation_type`
from the current relation obligations:

| Obligation label | Allowed relation enum values |
|---|---|
| `Buyer group composition` | `member_of`, `affiliate_of`, `controls`, `acquisition_vehicle_of` |
| `Voting support agreement` | `voting_support_for` |
| `Rollover holder` | `rollover_holder_for` |
| `Special committee membership` | `committee_member_of` |
| `Recusal from sale process` | `recused_from` |

Unmapped actor-relation obligation labels now fail loudly instead of widening
the schema back to the full relation enum.

## Phase 4 - Coverage Semantics

Python writes all four `coverage_results.result` states:

- `claims_emitted` when a validated claim links to the exact obligation id;
- `missed` when source support is present but Linkflow emits no validated linked
  claim;
- `no_supported_claim` when Python cannot find source support for an applicable
  obligation in the window;
- `ambiguous` when support cannot be safely classified after region and
  applicability review.

Validation now hard-fails current applicable required or important obligations
whose result is not `claims_emitted`. This is separate from the proof-summary
verdict downgrade and prevents unresolved required/important coverage from
passing validation merely because a row exists.

## Phase 5 - Offline Reference-9 Gate

The offline Reference-9 gate now pins both region selection and applicability:

- all nine local filings under `data/filings/`;
- compact region expectations including `region_kind`, section label, and
  paragraph-count bands;
- compact applicability expectations including applicable kinds, claim-type
  families, important/required kinds, reason-code families, and trigger basis;
- command-grade missing-filing messages;
- Medivation selected-document proof for the `EX-99.(A)(1)(A)` Offer to
  Purchase exhibit.

Verification:

```bash
UV_CACHE_DIR=/private/tmp/uv-cache PYTHONDONTWRITEBYTECODE=1 uv run pytest \
  -q -p no:cacheprovider tests/test_llm_p8_contract.py \
  tests/test_coverage_semantics.py tests/test_validation_semantics.py \
  tests/test_reference9_offline_regions.py tests/test_applicability_obligations.py
# 46 passed in 10.96s
```

## Phase 6 - Live P8 Proof

Environment credentials were available, so the live gate was executed. The
jobs were separate per-deal runs launched in parallel, not one combined
invocation. All used:

```text
--source filings
--llm-provider linkflow
--llm-model gpt-5.5
--llm-reasoning-effort medium
--request-mode claim_only_p8_relation_v1
```

All ten Linkflow requests completed with sanitized `_medium_success.json`
artifacts: one request for each single-region deal and two requests for
Medivation's two selected sale-process regions. Every per-deal run reached
`reconcile` and then failed the stricter validation gate, which was the
intended fail-loud behavior for unresolved required/important coverage or
semantically unsupported relation claims.

This table is a point-in-time P8 proof snapshot, not current Reference-9
authority. It predates the 2026-05-04 correctness repair that rejected
cross-reference-only regions, removed several false-positive obligation
triggers, and added persisted failed-validation proof metadata. The listed runs
produced validation reports and sanitized Linkflow artifacts; projection proof
artifacts are only produced after validation passes, while failed validation is
now represented by `failed_validation_proof.json`.

| Deal | Run id | Regions | Applicable obligations | Claims imported | Coverage states | Validation failures |
|---|---|---:|---:|---:|---|---|
| `providence-worcester` | `2026-05-04T032500Z_p8-live-providence_a1b2c3d4` | 1 | 12 | 16 | 11 emitted, 1 missed | 1 coverage, 2 semantic relation |
| `medivation` | `2026-05-04T032500Z_p8-live-medivation_b2c3d4e5` | 2 | 16 | 10 | 7 emitted, 3 missed, 5 no-supported, 1 ambiguous | 9 coverage |
| `imprivata` | `2026-05-04T032500Z_p8-live-imprivata_c3d4e5f6` | 1 | 14 | 20 | 12 emitted, 2 missed | 2 coverage |
| `zep` | `2026-05-04T032500Z_p8-live-zep_d4e5f6a7` | 1 | 13 | 10 | 9 emitted, 4 missed | 2 coverage |
| `petsmart-inc` | `2026-05-04T032500Z_p8-live-petsmart_e5f6a7b8` | 1 | 14 | 18 | 13 emitted, 1 missed | 1 coverage, 1 semantic relation |
| `penford` | `2026-05-04T032500Z_p8-live-penford_f6a7b8c9` | 1 | 10 | 7 | 7 emitted, 3 missed | 2 coverage |
| `mac-gray` | `2026-05-04T032500Z_p8-live-macgray_a7b8c9d0` | 1 | 16 | 40 | 15 emitted, 1 missed | 1 coverage, 2 semantic relation |
| `saks` | `2026-05-04T032500Z_p8-live-saks_b8c9d0e1` | 1 | 10 | 18 | 9 emitted, 1 missed | 8 semantic relation |
| `stec` | `2026-05-04T032500Z_p8-live-stec_c9d0e1f2` | 1 | 12 | 13 | 10 emitted, 2 missed | 2 coverage, 2 semantic relation |

Representative unresolved obligations:

| Deal | Unresolved coverage |
|---|---|
| `imprivata` | `exclusivity_grant`, `voting_support` |
| `mac-gray` | `rollover_holder` |
| `medivation` | second-region universal obligations, final approval, tender-offer prior contacts, IOI/final-round counts |
| `penford` | `exclusivity_grant`, `ioi_count` |
| `petsmart-inc` | `buyer_group_composition` |
| `providence-worcester` | `exclusivity_grant` |
| `stec` | `exclusivity_grant`, `buyer_group_composition` |
| `zep` | `final_round_count`, `financing_committed` |

The failures point to coverage/applicability and actor-relation semantic
validation, not transport, credentials, provider schema widening, or secret
handling.

## Stale Scan

Command:

```bash
rg -n 'P7|semantic_claims_v1|provider-owned coverage|provider.*coverage_results|coverage_results.*provider|Default live Linkflow reasoning effort is `high`|rollover_holder_of|test_llm_p7_contract' docs src tests quality_reports/plans
```

Active-code hits are limited to current P8 rejection tests and current plan
wording that names superseded terms. Remaining historical hits are under
`quality_reports/plans/legacy/`, whose README marks the folder as archived and
warns not to revive P7/high, provider-owned coverage results, scalar provider
taxonomy fields, or `rollover_holder_of`.
