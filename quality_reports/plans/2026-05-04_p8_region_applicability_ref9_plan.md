# P8 Region Applicability Ref-9 Plan

**Status:** Active on 2026-05-04.

**Goal:** Make the frozen P8 claim-only Linkflow contract production-useful by
replacing the current single-Background/static-obligation map with validated
evidence regions, Python-owned applicability, relation-aware windows, and
Reference-9 proof gates.

This plan is intentionally lighter than the prior schema-freeze handoff. It is
still concrete enough for multiple agents to execute, but it should not be
treated as a rigid ceremony. The important rule is to keep P8 frozen and move
the next work into region selection, applicability, coverage semantics, and
proof.

## Authority

Read these before implementation:

```text
docs/spec.md
docs/llm-interface.md
docs/superpowers/specs/2026-05-03-pipeline-hard-reset-design.md
```

Useful but non-authoritative context:

```text
docs/prior-pipeline-lessons.md
quality_reports/schema_read/2026-05-03_background-shape-scan.md
quality_reports/plans/legacy/2026-05-03_ref9_schema_refactor_goal_spec.md
quality_reports/plans/legacy/2026-05-03_ref9_schema_refactor_implementation_plan.md
quality_reports/plans/legacy/2026-05-04_relation_revised_claim_only_p8_implementation_plan.md
quality_reports/llm_calibration/ref9_schema_calibration_2026-05-04/
```

The legacy Ref-9 plan still has good region/applicability ideas, but its
provider contract is stale wherever it says `high`, provider-owned
`coverage_results`, P7, provider scalar research fields, or old relation labels.

## Frozen P8 Boundary

Do not reopen these decisions in this plan:

- Request mode stays `claim_only_p8_relation_v1`.
- Default Linkflow reasoning stays `medium`.
- Provider output stays five positive claim arrays only:
  - `actor_claims`
  - `event_claims`
  - `bid_claims`
  - `participation_count_claims`
  - `actor_relation_claims`
- Each provider claim names exactly one scalar `coverage_obligation_id`.
- Provider output does not include `coverage_results`.
- Provider output does not include source offsets, canonical ids, projections,
  `actor_class`, `bid_formality`, `proposal_scope`, dropout fields, or other
  scalar research judgments.
- Python owns quote binding, source coordinates, coverage results,
  applicability, dispositions, canonical graph rows, validation, and
  projections.

Any change that widens the provider payload is out of scope unless the authority
docs are explicitly rewritten first.

## Current State From Multi-Agent Scan

The code has a good P8 claim-only boundary, but the upstream evidence map is
too narrow:

- `src/sec_graph/extract/evidence_map.py` selects paragraphs whose section is
  exactly `Background of the Merger`, creates one `sale_process_narrative`
  region, and attaches the same ten obligations to every filing.
- `src/sec_graph/ingest/sections.py` and
  `src/sec_graph/ingest/section_vocabulary.py` have basic section assignment,
  including the styled Zep heading fix, but no high-recall region-candidate
  scanner.
- `src/sec_graph/extract/llm/requests.py` mirrors `evidence_regions` into one
  LLM request per region. It does not plan semantic windows beyond the current
  region rows.
- `src/sec_graph/extract/llm/convert.py` writes `claims_emitted` when a
  validated claim links to an obligation and `missed` otherwise. The
  `coverage_results` table already allows `no_supported_claim` and `ambiguous`,
  but the conversion path does not yet assign them.
- `src/sec_graph/validate/integrity.py` requires exactly one current coverage
  result for every current obligation.
- All nine Reference-9 local filing directories exist under `data/filings/`.
  Committed examples cover only four slugs, so the offline Ref-9 gate is not
  yet durable enough.

The immediate next step is therefore not another schema freeze. It is to make
the pipeline choose the right source windows, ask obligations only when they
are applicable, and prove that behavior across the nine reference filings.

## Reference-9 Acceptance Set

Use the same nine local reference deals:

```text
providence-worcester
medivation
imprivata
zep
petsmart-inc
penford
mac-gray
saks
stec
```

`medivation` is the tender-offer stress case and must continue to use the
selected `EX-99.(A)(1)(A)` Offer to Purchase exhibit. No cover-form fallback is
allowed.

## Out Of Scope

- Full-corpus execution beyond Reference-9.
- Replacing DuckDB or the project layout.
- Reintroducing compatibility shims for P7, `semantic_claims_v1`, provider
  coverage, old relation labels, or broad scalar provider judgments.
- Deleting `data/filings/` or the schema-calibration evidence.
- Committing generated run payloads from `runs/`, `artifacts/`, or `tmp/`.

## Agent Lanes

Use parallel agents when implementing. Keep write scopes separate.

```text
Lane A: Section and region selection.
  Owns ingest heading vocabulary, evidence-region candidate scanning, false-hit
  rejection, and Reference-9 region audit fixtures.

Lane B: Applicability and obligation generation.
  Owns Python-owned applicability signals, obligation families, importance
  rules, and tests that optional/inapplicable obligations do not become false
  misses.

Lane C: LLM request and P8 boundary.
  Owns request-window construction, prompt wording, allowed claim types, and
  strict proof that the provider payload remains P8 claim-only.

Lane D: Coverage, validation, and dispositions.
  Owns Python-owned `claims_emitted`, `missed`, `no_supported_claim`, and
  `ambiguous` assignment plus validation rules that block false `SOUND`.

Lane E: Reference-9 proof and docs cleanup.
  Owns offline Ref-9 gates, tracked proof logs, stale-doc scans, and final
  handoff hygiene.
```

Agents are not isolated from the rest of the codebase. They must not revert
each other's changes. If two lanes need the same file, coordinate around the
smallest patch.

## Phase 0 - Preflight

Before code changes:

- Confirm the branch and worktree are clean enough to distinguish task changes.
- Run the current fast test baseline.
- Confirm `quality_reports/plans/` contains this active plan and `legacy/`, not
  executed active-looking plans.
- Confirm all nine Reference-9 directories exist under `data/filings/`.
- Confirm the P8 contract tests are green before modifying region or
  applicability behavior.

Recommended commands:

```bash
git status --short --branch
find quality_reports/plans -maxdepth 1 -type f | sort
python - <<'PY'
from pathlib import Path
slugs = [
    "providence-worcester", "medivation", "imprivata", "zep",
    "petsmart-inc", "penford", "mac-gray", "saks", "stec",
]
missing = [slug for slug in slugs if not (Path("data/filings") / slug / "raw.md").exists()]
if missing:
    raise SystemExit(f"missing Reference-9 filings: {missing}")
print("Reference-9 filings present")
PY
PYTHONDONTWRITEBYTECODE=1 uv run pytest -q -p no:cacheprovider tests/test_llm_p8_contract.py tests/test_coverage_semantics.py tests/test_hard_reset_schema.py
```

## Phase 1 - Region Selection

Replace the single exact-Background path with a validated region builder.

Implementation targets:

```text
src/sec_graph/ingest/sections.py
src/sec_graph/ingest/section_vocabulary.py
src/sec_graph/extract/evidence_map.py
tests/test_ingest_examples.py
tests/test_hard_reset_schema.py
tests/test_section_selection.py
```

Required behavior:

- Preserve the current fail-loud behavior when no sale-process source region is
  found.
- Detect sale-process sections across common heading variants, including:
  - `Background of the Merger`
  - `Background of the Offer`
  - `Background of the Offer and Merger`
  - `Past Contacts, Transactions, Negotiations and Agreements`
  - styled or wrapper-modified heading lines
- Reject table-of-contents hits, cross-reference paragraphs, and non-narrative
  summaries.
- Keep exact paragraph ids, raw quote provenance, and trigger phrases for every
  selected region.
- Allow more than one evidence region when the filing has genuinely distinct
  sale-process material, but keep deterministic priority/order.

Schema guidance:

- Use the existing `evidence_regions` table unless a new table is necessary.
- If adding region-candidate audit state, prefer a small explicit table over
  stuffing opaque JSON into source columns.
- Keep `paragraph_ids_json`, `trigger_phrases_json`, and
  `expected_claim_types_json` deterministic and easy to diff.

Acceptance:

- The four committed examples still ingest and assign sections correctly.
- Each Reference-9 local filing can produce at least one validated
  sale-process evidence region offline.
- False-heading fixtures prove that TOC/cross-reference hits are rejected.

## Phase 2 - Applicability-Aware Obligations

Replace the static ten-obligation bundle with Python-owned applicability and
obligation generation.

Implementation targets:

```text
src/sec_graph/extract/evidence_map.py
src/sec_graph/extract/applicability.py
src/sec_graph/schema/models/extraction.py
src/sec_graph/extract/llm/models.py
tests/test_applicability_obligations.py
tests/test_coverage_semantics.py
tests/test_validation_semantics.py
docs/spec.md
docs/llm-interface.md
```

Obligation families:

```text
Universal sale-process obligations:
  process initiation, target board, target financial advisor, target legal
  advisor, final transaction price or consideration, final approval event.

Conditional obligations:
  IOI/first-round/final-round counts, exclusivity, go-shop, buyer group,
  rollover, voting support, special committee, recusal, tender-offer contacts,
  prior-cycle material, financing, amendment.

Calibration obligations:
  narrow obligations needed to stress known Reference-9 failure modes. These
  must be source-signal driven, not hard-coded per slug.
```

Required behavior:

- Applicability is assigned before the LLM request.
- Inapplicable obligations should not be inserted as current blocking
  obligations.
- Conditional obligations require explicit source signals or a documented
  region-level inference.
- Applicability reason codes must be Python-owned and traceable to section,
  heading, paragraph, or text-pattern signals.
- Do not ask Linkflow to emit absence judgments.

Storage decision:

- Add an explicit Python-owned applicability audit surface. The simplest
  acceptable version is either:
  - new columns on `coverage_obligations` such as `applicability`,
    `applicability_reason_code`, and `applicability_basis_json`; or
  - a small `coverage_applicability` table keyed by obligation id.
- Choose the less disruptive option during implementation, but tests must prove
  the audit trail exists and is deterministic.
- `coverage_results.result` remains one of `claims_emitted`,
  `no_supported_claim`, `ambiguous`, or `missed`; do not add `not_applicable`
  there.

Acceptance:

- Required obligations still block validation when unsupported.
- Conditional obligations are present only when applicable.
- Optional applicable obligations can be missed without pretending the filing is
  complete.
- Inapplicable concepts do not create false `missed` rows.

## Phase 3 - Relation-Aware P8 Windows

Make LLM windows reflect region and obligation semantics without widening the
provider schema.

Implementation targets:

```text
src/sec_graph/extract/llm/requests.py
src/sec_graph/extract/llm/prompt.py
src/sec_graph/extract/llm/linkflow.py
src/sec_graph/extract/llm/models.py
tests/test_llm_p8_contract.py
tests/test_hard_reset_schema.py
```

Required behavior:

- Each window includes only applicable current obligations for its region.
- `allowed_claim_types` is derived from the obligations in that window.
- Actor-relation obligations are generated when source signals justify them,
  especially:
  - buyer-group composition relations using the active enum values
    `member_of`, `affiliate_of`, `controls`, and `acquisition_vehicle_of`
  - `rollover_holder_for`
  - `voting_support_for`
  - `committee_member_of`
  - `recused_from`
- Prompt text remains positive-claim oriented: return quote-backed claims only.
  Do not ask the provider to say a fact is absent.
- The strict Linkflow schema still rejects provider coverage, old relation
  labels, obligation lists, and scalar research fields.

Acceptance:

- Existing P8 tests remain green.
- New tests prove relation obligations constrain the provider to relation
  claims and scalar `coverage_obligation_id`.
- Request construction fails loudly if a region has no applicable obligations.

## Phase 4 - Coverage Result Semantics

Upgrade Python-owned coverage classification beyond the current binary
`claims_emitted`/`missed` behavior.

Implementation targets:

```text
src/sec_graph/extract/llm/convert.py
src/sec_graph/validate/integrity.py
tests/test_coverage_semantics.py
tests/test_validation_semantics.py
```

Required behavior:

- `claims_emitted`: at least one validated claim links to the exact obligation.
- `missed`: the obligation was applicable and the provider failed to return a
  validated linked claim when a claim was expected.
- `no_supported_claim`: Python can prove the window was relevant but contains no
  source support for that applicable obligation.
- `ambiguous`: Python cannot safely classify support after quote binding or
  region/applicability review.
- Coverage result assignment remains transactional. Bad claim/obligation links
  leave no partial claims or coverage rows.

Acceptance:

- Same-family exact-obligation semantics still hold.
- Every current obligation has exactly one current coverage result.
- Validation blocks `SOUND` when required or important coverage is unresolved.
- Tests cover all four result states.

## Phase 5 - Reference-9 Offline Gate

Create a durable offline gate before any live Linkflow spend.

Implementation targets:

```text
tests/test_reference9_offline_regions.py
tests/fixtures/reference9_region_expectations.json
tests/fixtures/reference9_applicability_expectations.json
quality_reports/session_logs/
```

Required behavior:

- The offline test can run from local `data/filings/` without committing full
  filings.
- Expectations store compact, auditable facts: expected source section labels,
  required region kind, selected paragraph count/range, applicable obligation
  families, and key trigger phrases.
- If a local Reference-9 filing is missing, the failure should say exactly which
  slug is missing and how to fetch it.
- The gate must be deterministic and not depend on Linkflow credentials.

Recommended command:

```bash
PYTHONDONTWRITEBYTECODE=1 uv run pytest -q -p no:cacheprovider tests/test_reference9_offline_regions.py
```

Acceptance:

- All nine Reference-9 filings build validated regions and applicable
  obligations offline.
- The tender-offer exhibit rule is covered by `medivation`.
- The new gate fails loudly on missing source regions or unsupported heading
  variants.

## Phase 6 - Live P8 Proof

Run this only after the offline gate is green and Linkflow credentials are
available through environment variables.

Rules:

- Run separate per-deal jobs or parallel deal groups, not one opaque combined
  invocation.
- Use `--llm-reasoning-effort medium`.
- Use `--request-mode claim_only_p8_relation_v1`.
- Put generated payloads under ignored run/proof directories.
- Track only concise session logs and proof summaries under
  `quality_reports/session_logs/`.
- Do not retry by widening schemas, switching providers, or changing reasoning
  to `high`/`xhigh`.

Proof summary should include:

```text
deal_slug
selected region ids and kinds
obligation counts by family and importance
coverage result counts by state
validated claim counts by type
validation verdict
runtime and provider request metadata
known unresolved obligations
```

Acceptance:

- At least one clean live smoke run completes before escalating to all nine.
- The final Reference-9 proof is reproducible from committed code plus local
  filings and env credentials.
- Failures point to region, applicability, quote binding, provider contract, or
  validation, not vague "LLM quality" language.

## Phase 7 - Docs And Stale Cleanup

Update docs after the implementation behavior is real.

Targets:

```text
docs/spec.md
docs/llm-interface.md
docs/prior-pipeline-lessons.md
quality_reports/plans/legacy/README.md
quality_reports/session_logs/
```

Cleanup scan:

```bash
rg -n "P7|semantic_claims_v1|provider-owned coverage|provider.*coverage_results|coverage_results.*provider|Default live Linkflow reasoning effort is `high`|rollover_holder_of|test_llm_p7_contract" docs src tests quality_reports/plans
```

Allowed matches:

- Legacy archived plans that explicitly say they are stale.
- Current docs explaining that provider coverage and P7/high are superseded.
- Python-owned `coverage_results` table references.

Acceptance:

- `quality_reports/plans/` contains only this active plan plus `legacy/`.
- Active docs describe region/applicability as Python-owned.
- The P8 provider boundary remains unchanged in active docs and tests.
- Full tests pass:

```bash
PYTHONDONTWRITEBYTECODE=1 uv run pytest -q -p no:cacheprovider
```

## Completion Bar

This plan is complete when:

- Region selection is robust enough to run all nine Reference-9 local filings
  offline.
- Applicability prevents false missing obligations without hiding real misses.
- Linkflow still receives and returns only the frozen P8 claim-only contract.
- Python writes auditable coverage results for every current obligation.
- Validation prevents incomplete required/important coverage from passing.
- A tracked session log records the Ref-9 offline proof, and live proof exists
  when credentials are available.
- Stale active plan/doc surfaces are cleaned or explicitly archived.
