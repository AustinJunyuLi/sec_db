# Reference-Nine Offline Proof

Date: 2026-05-02

## Command

```bash
UV_CACHE_DIR=/private/tmp/uv-cache uv run python -m sec_graph run \
  --source filings \
  --slugs imprivata mac-gray medivation penford petsmart-inc providence-worcester saks stec zep \
  --run-id 2026-05-02T133000Z_reference9_rules \
  --run-dir runs/2026-05-02T133000Z_reference9_rules \
  --projection bidder_cycle_baseline_v1
```

## Result

- Exit status: 0.
- Validation: passed; hard failures: 0; soft flags: 16.
- Snapshot: `runs/2026-05-02T133000Z_reference9_rules/canonical.duckdb`.
- Manifest: `runs/2026-05-02T133000Z_reference9_rules/run_manifest.json`.
- Projection rows by deal: petsmart-inc 2, providence-worcester 1, saks 4,
  stec 3, zep 1.

## Canonical Counts

| deal | candidates | actors | relations | events | links | counts | judgments |
|---|---:|---:|---:|---:|---:|---:|---:|
| imprivata | 425 | 5 | 1 | 20 | 2 | 0 | 2 |
| mac-gray | 484 | 8 | 1 | 23 | 17 | 0 | 4 |
| medivation | 33 | 2 | 0 | 5 | 0 | 0 | 0 |
| penford | 375 | 10 | 1 | 32 | 5 | 0 | 1 |
| petsmart-inc | 637 | 19 | 11 | 16 | 7 | 0 | 2 |
| providence-worcester | 109 | 9 | 0 | 20 | 13 | 0 | 6 |
| saks | 636 | 14 | 1 | 18 | 21 | 0 | 4 |
| stec | 444 | 11 | 0 | 64 | 12 | 0 | 4 |
| zep | 308 | 8 | 2 | 17 | 7 | 1 | 3 |

## Evidence Checks

- PetSmart buyer-group membership is represented through generic relation rows
  for BC Partners, La Caisse de depot et placement du Quebec, GIC Special
  Investments, StepStone Group, and Longview Asset Management.
- PetSmart acquisition vehicles are represented as generic vehicle relations:
  Argos Merger Sub Inc. to Argos Holdings Inc., and Argos Holdings Inc. to Buyer
  Group.
- PetSmart Longview support and late membership are represented separately.
- Zep aggregate go-shop contact count is represented as a participation-count
  row, not as projected bidder rows.
- Projection excludes relation-only actors such as Longview and acquisition
  vehicles such as Merger Sub; only actors with current projection-eligibility
  judgments and bid evidence appear.

## Remaining Limits Before Live Proof

The offline rules path is operational proof, not a final soundness verdict. Some
deal-specific evidence cases still have sparse relation/count coverage and must
be judged from the live Linkflow run artifacts before the goal can proceed past
PetSmart and then reference-nine soundness gates.
