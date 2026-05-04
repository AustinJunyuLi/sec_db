# Session Log: P8 Region Applicability — Phase 2

**Date:** 2026-05-04
**Branch:** `main`
**Plan:** `quality_reports/plans/2026-05-04_p8_region_applicability_ref9_plan.md`

## Scope

Phase 2 from the active plan: replace the static ten-obligation bundle
with a Python-owned applicability engine. Linkflow's frozen P8 contract
is not touched. The provider still returns five positive claim arrays;
Python now decides which obligations are applicable per region before
asking.

## What Changed

### Schema (`src/sec_graph/schema/models/extraction.py`)

`coverage_obligations` gained four columns:

```text
obligation_kind            VARCHAR  stable taxonomy id (e.g., process_initiation)
applicability              VARCHAR  applicable | not_applicable
applicability_reason_code  VARCHAR  deterministic short reason
applicability_basis_json   VARCHAR  JSON list of trigger phrases / scope values
```

`Applicability = Literal["applicable", "not_applicable"]` is the new
typed alias on the Pydantic model. No new table was needed; the
columns-on-existing-table option from the plan was simpler than a side
table.

### Applicability engine (`src/sec_graph/extract/applicability.py`)

A single pure-Python module declares the obligation taxonomy and decides
applicability for a region given its text and the filing's process scope.
Three families:

- **Universal** (6, all required): `process_initiation`, `target_board`,
  `target_financial_advisor`, `target_legal_advisor`,
  `final_consideration`, `final_approval_event`. Always applicable.
- **Conditional** (14, important or optional): `contacted_count`,
  `ioi_count`, `first_round_count`, `final_round_count`,
  `final_round_bid_event`, `exclusivity_grant`, `go_shop_period`,
  `buyer_group_composition`, `rollover_holder`, `voting_support`,
  `special_committee`, `recusal`, `financing_committed`, `amendment`.
  Each carries `tuple[re.Pattern, ...]` triggers; applicable only when
  at least one trigger matches the region text.
- **Scope-driven** (1): `tender_offer_prior_contacts` applies only when
  `process_scope == "bidder_partial_schedule_to"` (medivation today).

`decide_applicability(region_text=..., process_scope=...)` returns one
deterministic `ApplicabilityDecision` per kind in the canonical order of
`ALL_OBLIGATION_KINDS`. Reason codes are stable strings:
`universal_sale_process`, `trigger_phrase_match`, `trigger_phrase_absent`,
`process_scope:<scope>`, `process_scope_mismatch`.

### Evidence map (`src/sec_graph/extract/evidence_map.py`)

Now per region:

1. Concatenate the region's paragraphs.
2. Look up the filing's `process_scope`.
3. Call `decide_applicability`.
4. Insert one `coverage_obligations` row for every kind in the taxonomy
   (applicable + inapplicable) with `applicability_*` columns populated.
5. Compute `expected_claim_types_json` from the **applicable** subset only.
6. Fail loud if a region has zero applicable obligations (universal
   obligations make this unreachable in practice; the guard is there as
   a contract).

### Request building (`src/sec_graph/extract/llm/requests.py`)

Window obligations now filter `WHERE current = true AND applicability =
'applicable'`. Linkflow never sees an inapplicable obligation. The
`allowed_claim_types` field is derived from the applicable rows, so a
region whose only relation evidence is missing will not invite
`actor_relation` claims.

### Validation (`src/sec_graph/validate/integrity.py`)

`_check_coverage_results` now requires a current result only for
applicable obligations. Inapplicable rows are audit-only and never fail
validation. Required obligations still block `SOUND` when unsupported.

### Proof (`src/sec_graph/project/summaries.py`)

- `row_counts["applicable_coverage_obligations"]` exposed for assertions.
- `insufficient_required` only counts applicable obligations.
- `thin_live` heuristic uses applicable obligation count, so a tender
  offer with 21 total / 7 applicable obligations does not artificially
  inflate the threshold.

## Reference-9 Applicability Snapshot

Probed with the new engine against local filings:

| Slug | Region | Applicable | Inapplicable | Notable triggers |
|------|--------|-----------:|-------------:|------------------|
| petsmart-inc | Background of the Merger | 14 | 8 | contacted_count, ioi_count, final_round_count, buyer_group, rollover, voting_support, financing_committed |
| medivation | Background of the Offer | 8 | 14 | ioi_count, final_round_count, **tender_offer_prior_contacts** |
| medivation | Past Contacts, ... | 7 | 15 | (cross-reference; only universals + tender_offer_prior_contacts) |
| stec | Background of the Merger | 13 | 9 | ioi_count, final_round_count, exclusivity, buyer_group, voting_support, special_committee |

Universal obligations (6) appear in every region. Tender-offer prior
contacts is the only scope-driven kind today; it correctly fires only
on `medivation` and is `process_scope_mismatch` on the eight full-proxy
filings.

## Tests

### Updated

- `tests/test_hard_reset_schema.py::test_evidence_map_builds_one_full_background_sale_process_region`
  now asserts the universal obligation block in canonical order, that
  `exclusivity_grant` is applicable when the source text says
  "exclusivity", that several conditional kinds are recorded as
  inapplicable rather than dropped, and that windows only carry the
  applicable subset.
- `tests/test_hard_reset_schema.py::test_typed_claims_reconcile_to_source_backed_projection`
  swaps the old `coverage_results == coverage_obligations` invariant for
  `coverage_results == applicable_coverage_obligations` and asserts the
  inapplicable rows are present in `coverage_obligations`.
- `tests/test_reference9_offline_regions.py` no longer hard-codes the
  five-claim-type list; it now requires `{event, actor, bid}` (universal
  coverage) and validates that `allowed_claim_types` is a subset of the
  five legal claim types.
- `tests/test_coverage_semantics.py` fixture extended to populate the
  four new columns on its hand-rolled obligations.

### Added

`tests/test_applicability_obligations.py` (10 cases):
- Universal obligations always applicable, independent of region text.
- Conditional `exclusivity_grant` flips on/off with the trigger phrase.
- Scope-driven `tender_offer_prior_contacts` applies only to
  `bidder_partial_schedule_to`, otherwise `process_scope_mismatch`.
- `decide_applicability` is deterministic and produces one decision per
  taxonomy entry in the canonical order.
- Evidence-map writes inapplicable rows; the LLM window only contains
  applicable obligations.
- Live medivation filing exercises both regions and confirms tender-offer
  prior contacts applies in each.
- petsmart-inc filing confirms the inverse: tender-offer obligation is
  marked `process_scope_mismatch` for full-proxy scope.
- Taxonomy invariants: unique kinds, families exactly cover {universal,
  conditional, scope}, conditional kinds carry triggers, scope kinds
  declare scopes.

## Verification

```bash
UV_CACHE_DIR=/private/tmp/uv-cache PYTHONDONTWRITEBYTECODE=1 uv run pytest \
  -q -p no:cacheprovider tests/test_applicability_obligations.py
# 10 passed in 2.24s

UV_CACHE_DIR=/private/tmp/uv-cache PYTHONDONTWRITEBYTECODE=1 uv run pytest \
  -q -p no:cacheprovider
# 96 passed in 15.45s
```

## Frozen P8 Boundary — Untouched

- Request mode `claim_only_p8_relation_v1`, default reasoning `medium`.
- Provider response shape unchanged: five positive claim arrays, no
  `coverage_results`, no scalar judgments.
- `tests/test_llm_p8_contract.py` still green.
- No live Linkflow call attempted; that remains Phase 6 work.

## Open Questions / Phase 3 Hand-Off

- The conditional-trigger regexes (e.g., `voting agreement`, `rollover`)
  were tuned against Reference-9 text. They are intentionally short and
  will need a calibration pass when the corpus expands; false-positive
  triggers can over-apply obligations and produce extra `missed` rows.
- Phase 3 should derive per-window `allowed_claim_types` directly from the
  filtered applicable obligations, not from the region's stored
  `expected_claim_types_json`, so request construction cannot drift from
  Python-owned applicability.
- The `coverage_results.csv` projection continues to LEFT JOIN obligations
  to results. Inapplicable rows now show as null result; downstream
  consumers that filter on `applicability = 'applicable'` get the same
  view as Linkflow.
- No live Linkflow run was attempted; Phase 6 remains gated on the full Phase 5
  offline gate. Phase 1 proved all-nine region selection, but the durable
  all-nine applicability fixture still needed to be added after this Phase 2
  log.
