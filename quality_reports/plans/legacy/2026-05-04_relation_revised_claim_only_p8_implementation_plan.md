# Relation-Revised Claim-Only P8 Implementation Plan

**Status:** Executed on 2026-05-04 and archived under `legacy/`. Do not execute
this file as the active plan. Internal references to the former active path are
historical. The current active handoff is
`quality_reports/plans/2026-05-04_p8_region_applicability_ref9_plan.md`.
Current binding authority is `docs/spec.md`, `docs/llm-interface.md`, and
`docs/superpowers/specs/2026-05-03-pipeline-hard-reset-design.md`.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Freeze and implement the settled Reference-9 Linkflow contract: claim-only P8 at `medium`, Python-owned coverage, and relation-label additions without scalar provider judgments.

**Architecture:** Linkflow returns only positive, quote-backed typed claims. Python owns quote binding, source coordinates, coverage results, claim dispositions, canonical graph rows, validation, and projections. This is a breaking reset: remove old provider coverage output, old P7/high wording, old rollover label, and stale plan/code surfaces instead of preserving compatibility.

**Tech Stack:** Python, Pydantic, DuckDB, pytest, Linkflow GPT-5.5 strict JSON schema, local docs under `docs/` and `quality_reports/`.

---

## Execution Contract

Implement this as the active schema freeze. Do not treat this as a patch over
the old V0/P7/high path.

Non-negotiable decisions:

- Default Linkflow reasoning effort is `medium`.
- Provider response schema contains claim arrays only:
  - `actor_claims`
  - `event_claims`
  - `bid_claims`
  - `participation_count_claims`
  - `actor_relation_claims`
- Provider response schema does not contain `coverage_results`.
- The DuckDB `coverage_results` table stays, but Python alone writes it.
- Missing linked claims become Python-owned `missed` coverage results unless a
  later Python applicability component assigns another Python-owned result.
- No provider-owned scalar research fields:
  - no `actor_claims.actor_class`
  - no `bid_claims.bid_formality`
  - no `bid_claims.proposal_scope`
  - no `event_claims.drop_agency`
  - no `event_claims.drop_reason`
  - no `event_claims.initiation_side`
- Add relation labels:
  - `voting_support_for`
  - `committee_member_of`
  - `recused_from`
- Replace `rollover_holder_of` with `rollover_holder_for`.
- Do not keep both rollover labels.
- Rename the active request mode from `semantic_claims_v1` to
  `claim_only_p8_relation_v1`. Do not accept both.
- Rename P7 tests/docs to P8 where they remain active.
- Keep stale historical plans out of the active plan directory. They may exist
  only under `quality_reports/plans/legacy/`.

## Source Evidence

The settled evidence lives here:

```text
quality_reports/llm_calibration/ref9_schema_calibration_2026-05-04/decision_report.md
quality_reports/llm_calibration/ref9_schema_calibration_2026-05-04/semantic_review/final_recommendation.md
quality_reports/llm_calibration/ref9_schema_calibration_2026-05-04/semantic_review/schema_delta_decisions.md
quality_reports/llm_calibration/ref9_schema_calibration_2026-05-04/semantic_review/semantic_fact_ledger.csv
quality_reports/llm_calibration/ref9_schema_calibration_2026-05-04/semantic_review/claim_only_failure_cases.jsonl
```

Do not delete calibration evidence. It is the proof for the schema decision.

## Subagent Lanes

Use separate workers if running this under `/goal`.

```text
Lane A: Docs authority and stale-doc cleanup.
Lane B: LLM contract models, request mode, Linkflow schema, and prompt.
Lane C: Extraction/canonical schema relation labels and conversion.
Lane D: Validation/reconcile/projection tests.
Lane E: Final stale scan, Ref-9 smoke instructions, and handoff proof.
```

Workers are not alone in the codebase. They must not revert unrelated dirty
work. Each worker must touch only its owned files unless the coordinator
assigns a conflict resolution.

## Target File Map

Docs to modify:

```text
docs/spec.md
docs/llm-interface.md
docs/superpowers/specs/2026-05-03-pipeline-hard-reset-design.md
quality_reports/2026-05-04_ref9_schema_freeze_session_log.md
```

Code to modify:

```text
src/sec_graph/extract/llm/models.py
src/sec_graph/extract/llm/convert.py
src/sec_graph/extract/llm/linkflow.py
src/sec_graph/extract/llm/prompt.py
src/sec_graph/extract/llm/requests.py
src/sec_graph/extract/pipeline.py
src/sec_graph/cli/extract_cmd.py
src/sec_graph/cli/run_cmd.py
src/sec_graph/schema/models/extraction.py
src/sec_graph/schema/models/canonical.py
src/sec_graph/validate/integrity.py
src/sec_graph/reconcile/pipeline.py
```

Tests to modify or rename:

```text
tests/test_llm_p7_contract.py -> tests/test_llm_p8_contract.py
tests/test_hard_reset_schema.py
tests/test_coverage_semantics.py
tests/test_validation_semantics.py
tests/test_run_kernel.py
```

Historical plans already moved to `quality_reports/plans/legacy/`:

```text
quality_reports/plans/legacy/2026-05-03_combined-taxonomy-region-design.md
quality_reports/plans/legacy/2026-05-03_full-redesign-plan.md
quality_reports/plans/legacy/2026-05-03_linkflow-p7-background-high-implementation-plan.md
quality_reports/plans/legacy/2026-05-03_ref9_schema_refactor_goal_spec.md
quality_reports/plans/legacy/2026-05-03_ref9_schema_refactor_implementation_plan.md
quality_reports/plans/legacy/2026-05-03_taxonomy-refactor-plan.md
quality_reports/plans/legacy/2026-05-04_ref9_acceptance_context_and_success_gate.md
quality_reports/plans/legacy/2026-05-04_ref9_claim_only_p8_meaning_gate_prescription.md
```

Active plan directory should contain only:

```text
quality_reports/plans/2026-05-04_relation_revised_claim_only_p8_implementation_plan.md
quality_reports/plans/legacy/
```

Keep outside `quality_reports/plans/`:

```text
quality_reports/llm_calibration/ref9_schema_calibration_2026-05-04/
docs/prior-pipeline-lessons.md
```

Rationale:

- `quality_reports/llm_calibration/ref9_schema_calibration_2026-05-04/`
  is evidence, not stale instruction.
- `docs/prior-pipeline-lessons.md` is explicitly context only.

## Task 0: Protect The Dirty Worktree

**Files:** no code changes.

- [ ] Run:

```bash
git status --short
```

Expected: a dirty worktree is allowed. Record existing dirty files in the final
session log.

- [ ] Confirm no background process is still editing the same files:

```bash
ps -axo pid,command | rg "pytest|sec_graph|linkflow|uv run" || true
```

Expected: either no matching process or only commands intentionally started by
the current executor.

- [ ] If another active process is writing the same source files, stop and ask
the user. Do not race it.

## Task 1: Update Binding Docs To The Settled Contract

**Files:**

- Modify: `docs/spec.md`
- Modify: `docs/llm-interface.md`
- Modify: `docs/superpowers/specs/2026-05-03-pipeline-hard-reset-design.md`

- [ ] In `docs/spec.md`, update the active architecture and schema authority so
  the deployable LLM contract says:

```text
Linkflow returns positive claim arrays only. Linkflow does not return coverage
results, canonical ids, source offsets, projection rows, or scalar research
judgments. Python alone writes coverage_results after quote binding and
claim-to-obligation validation.
```

- [ ] In `docs/spec.md`, keep `coverage_results` in the extraction tables, but
  define it as a Python-owned table. Remove any sentence that says Linkflow may
  return `coverage_results`.

- [ ] In `docs/spec.md`, replace "V0 binder" wording with "P8 quote binder".
  The binder still accepts one contiguous exact quote from one ordered
  paragraph.

- [ ] In `docs/spec.md`, define the final relation enum exactly:

```text
member_of
affiliate_of
controls
acquisition_vehicle_of
advises
finances
supports
voting_support_for
rollover_holder_for
committee_member_of
recused_from
```

- [ ] In `docs/spec.md`, define relation directions:

```text
voting_support_for: subject is the shareholder, officer, director, trust, or
supporting party; object is the buyer, parent, transaction, merger agreement,
or voting proposal named in the quote.

rollover_holder_for: subject is the holder rolling, contributing, or retaining
equity; object is the buyer vehicle, surviving company, target, transaction, or
rolled-security context named in the quote.

committee_member_of: subject is the person, director, representative, or named
member group; object is the committee or board named in the quote.

recused_from: subject is the recused or excluded person; object is the board,
committee, meeting, process, negotiation, evaluation, or transaction context
named in the quote.
```

- [ ] In `docs/spec.md`, state that formal/informal, dropout mode, initiation
  side, proposal scope, and strategic/financial labels are Python-owned
  judgments derived from source-backed claims. Linkflow must preserve source
  indicators in ordinary quote-backed claims.

- [ ] In `docs/llm-interface.md`, update status to the settled P8 contract and
  default reasoning to `medium`.

- [ ] In `docs/llm-interface.md`, remove `coverage_results` from provider
  response shape.

- [ ] In `docs/llm-interface.md`, add a provider-prohibited list:

```text
coverage_results
actor_claims.actor_class
bid_claims.bid_formality
bid_claims.proposal_scope
event_claims.drop_agency
event_claims.drop_reason
event_claims.initiation_side
source offsets
canonical ids
projection rows
```

- [ ] In `docs/llm-interface.md`, document request mode
  `claim_only_p8_relation_v1`.

- [ ] In the hard-reset design spec, add a short dated update near the top:

```text
2026-05-04 schema-freeze update: Reference-9 calibration chose a
relation-revised claim-only P8 contract. The binding details now live in
docs/spec.md and docs/llm-interface.md. Older mentions of provider
coverage_results, P7/high defaults, or rollover_holder_of are superseded.
```

- [ ] Run:

```bash
rg -n "Linkflow may only return `coverage_results`|Default live Linkflow reasoning effort is `high`|V0 binder|rollover_holder_of|P7" docs/spec.md docs/llm-interface.md docs/superpowers/specs/2026-05-03-pipeline-hard-reset-design.md
```

Expected: no matches except intentional historical note wording in the hard
reset dated update.

## Task 2: Remove Provider Coverage Results From The LLM Payload

**Files:**

- Modify: `src/sec_graph/extract/llm/models.py`
- Modify: `src/sec_graph/extract/llm/convert.py`
- Modify: `src/sec_graph/extract/llm/linkflow.py`

- [ ] In `models.py`, delete `CoverageResultPayload`.

- [ ] In `models.py`, remove `coverage_results` from
  `SemanticClaimsPayload`.

- [ ] In `models.py`, change the default provider reasoning effort:

```python
reasoning_effort: ReasoningEffort = "medium"
```

- [ ] In `convert.py`, remove the `CoverageResultPayload` import.

- [ ] In `convert.py`, delete `_provider_coverage_results_by_obligation`.

- [ ] In `_insert_llm_response_rows`, remove `provider_results` entirely and
  replace the coverage loop with Python-only coverage logic:

```text
if validated linked claims exist for an obligation:
    result = claims_emitted
    reason_code = linkflow_claims_linked
else:
    result = missed
    reason_code = linkflow_no_linked_claim
```

Use this exact no-claim reason text:

```text
Python marked this obligation missed because Linkflow returned no validated
claim linked to this obligation.
```

- [ ] In `linkflow.py`, remove schema code that constrains
  `coverage_results[*].obligation_id`.

- [ ] In `linkflow.py`, update provider artifact metadata so it does not read
  `response.payload.coverage_results`. Replace `coverage_result_count` with a
  Python-side name only if needed, such as `coverage_obligation_count`, sourced
  from the request, not the provider response.

- [ ] Run:

```bash
rg -n "CoverageResultPayload|payload\\.coverage_results|coverage_result_count|provider_results|provider coverage result" src/sec_graph/extract/llm tests
```

Expected: no matches, except test names or comments that explicitly assert the
provider no longer has coverage results.

## Task 3: Rename Request Mode And Default Reasoning

**Files:**

- Modify: `src/sec_graph/extract/llm/requests.py`
- Modify: `src/sec_graph/extract/pipeline.py`
- Modify: `src/sec_graph/cli/extract_cmd.py`
- Modify: `src/sec_graph/cli/run_cmd.py`
- Modify: `tests/test_run_kernel.py`
- Modify: affected tests that construct `LLMWindowRequest`.

- [ ] Replace the old fixed request mode:

```text
semantic_claims_v1
```

with:

```text
claim_only_p8_relation_v1
```

- [ ] In CLI parser choices, accept only `claim_only_p8_relation_v1`.
  Do not accept the old name.

- [ ] In `LLMProviderConfig`, CLI defaults, and tests, use `medium` as the
  default reasoning effort.

- [ ] Rename tests that mention high defaults to medium defaults. For example:

```text
test_default_linkflow_reasoning_effort_is_medium
```

- [ ] Run:

```bash
rg -n "semantic_claims_v1|reasoning_effort.*high|Default live Linkflow reasoning effort is `high`|test_default_linkflow_reasoning_effort_is_high" src tests docs
```

Expected: no matches except explicit tests that pass `reasoning_effort="high"`
to check non-default behavior.

## Task 4: Replace Relation Enum Everywhere

**Files:**

- Modify: `src/sec_graph/schema/models/extraction.py`
- Modify: `src/sec_graph/schema/models/canonical.py`
- Modify: `src/sec_graph/validate/integrity.py`
- Modify: `src/sec_graph/reconcile/pipeline.py` only if current logic assumes
  the old enum.

- [ ] In extraction `RelationType`, replace the enum with:

```python
RelationType = Literal[
    "member_of",
    "affiliate_of",
    "controls",
    "acquisition_vehicle_of",
    "advises",
    "finances",
    "supports",
    "voting_support_for",
    "rollover_holder_for",
    "committee_member_of",
    "recused_from",
]
```

- [ ] In extraction DDL `actor_relation_claims.relation_type`, use the same
  values and remove `rollover_holder_of`.

- [ ] In canonical `RelationType` and `actor_relations.relation_type` DDL, use
  the same values and remove `rollover_holder_of`.

- [ ] In `validate/integrity.py`, update `_relation_supported_by_quote`
  synonyms:

```python
relation_synonyms = {
    "acquisition_vehicle_of": ("acquisition vehicle", "vehicle of"),
    "member_of": ("member of", "part of", "together we refer", "who together", "together as"),
    "affiliate_of": ("affiliate of", "affiliated with"),
    "controls": ("controls", "controlled by", "purchased by", "acquired by", "owned by"),
    "advises": ("advisor", "adviser", "advises"),
    "finances": ("financing", "finances", "provide capital", "capital required", "financing letter"),
    "supports": ("support", "supports", "guarantee", "guarantees"),
    "voting_support_for": ("voting agreement", "support agreement", "vote in favor", "agreed to vote", "voting and support"),
    "rollover_holder_for": ("rollover", "rolled", "contribute", "retain equity", "equity rollover"),
    "committee_member_of": ("committee", "member", "composed of", "appointed", "added"),
    "recused_from": ("recuse", "recused", "exclude", "excluded", "not participate"),
}
```

- [ ] Do not make the validator parse final research labels. It should only
  check that subject, object, relation, and source quote are coherent enough to
  support the typed claim.

- [ ] Run:

```bash
rg -n "rollover_holder_of" src tests docs
```

Expected: no matches outside calibration evidence or stale-deletion lists.

## Task 5: Update Prompt To P8 Claim-Only With Source Indicators

**Files:**

- Modify: `src/sec_graph/extract/llm/prompt.py`
- Modify: `tests/test_llm_p8_contract.py`

- [ ] Replace system prompt opening:

```text
You extract relation-revised claim-only P8 sale-process semantic claims from SEC merger filing text.
```

- [ ] Remove all instructions asking Linkflow to emit `coverage_results`.

- [ ] Add this instruction:

```text
If an obligation has no supported positive claim in the window, emit no claim
for that obligation. Python will mark missing coverage.
```

- [ ] Add relation-specific instruction:

```text
For actor_relation claims, prefer the most specific source-backed relation
label. Use voting_support_for for voting/support agreements requiring a party
to vote shares or support adoption. Use rollover_holder_for for equity rollover
or retained-equity facts. Use committee_member_of for board or special
committee membership. Use recused_from for recusal or exclusion from a process,
meeting, negotiation, evaluation, or committee context. Use supports only when
the source states support but does not support a more specific relation label.
```

- [ ] Add scalar-source-indicator instruction:

```text
Do not emit scalar research labels for formality, initiation side, dropout
agency, dropout reason, proposal scope, or actor class. Instead preserve the
exact source language in ordinary actor, event, bid, count, or relation claims.
Important source indicators include written, oral, non-binding, preliminary,
revised, final, best and final, definitive, withdrew, did not respond, was not
advanced, was excluded, contacted at board direction, unsolicited approach,
financial buyer, strategic buyer, private equity, industry participant, and
whole-company or asset proposal language.
```

- [ ] Keep exact quote requirements unchanged: one contiguous quote from one
  ordered paragraph, copied character-for-character, no ellipses, no source
  offsets.

- [ ] Run:

```bash
rg -n "coverage_result|coverage_results|V0|P7|high" src/sec_graph/extract/llm/prompt.py
```

Expected: no matches.

## Task 6: Update Linkflow Strict Schema Tests

**Files:**

- Rename: `tests/test_llm_p7_contract.py` to `tests/test_llm_p8_contract.py`
- Modify: `tests/test_llm_p8_contract.py`

- [ ] Use `git mv` for the test rename:

```bash
git mv tests/test_llm_p7_contract.py tests/test_llm_p8_contract.py
```

- [ ] Remove `CoverageResultPayload` imports and the provider coverage-result
  test.

- [ ] Add a test that provider schema top-level properties are exactly:

```python
{
    "actor_claims",
    "event_claims",
    "bid_claims",
    "participation_count_claims",
    "actor_relation_claims",
}
```

- [ ] Add a test that `coverage_results` is absent from the strict schema.

- [ ] Add a test that the full actor-relation enum includes:

```python
[
    "member_of",
    "affiliate_of",
    "controls",
    "acquisition_vehicle_of",
    "advises",
    "finances",
    "supports",
    "voting_support_for",
    "rollover_holder_for",
    "committee_member_of",
    "recused_from",
]
```

- [ ] Add a test that `rollover_holder_of` is rejected by Pydantic.

- [ ] Keep the obligation-family enum tests. Coverage obligation ids must still
  be constrained by claim family.

- [ ] Update buyer-group-only constraint if it remains. It may still narrow
  buyer-group composition requests to:

```python
["member_of", "affiliate_of", "controls", "acquisition_vehicle_of"]
```

Only keep this narrowing when the request has only the `Buyer group composition`
actor-relation obligation.

- [ ] Run:

```bash
PYTHONDONTWRITEBYTECODE=1 uv run pytest -q -p no:cacheprovider tests/test_llm_p8_contract.py
```

Expected: pass.

## Task 7: Update Coverage Semantics Tests

**Files:**

- Modify: `tests/test_coverage_semantics.py`
- Modify: `tests/test_hard_reset_schema.py`
- Modify: `tests/test_validation_semantics.py`

- [ ] Remove all construction of `CoverageResultPayload`.

- [ ] Update tests so provider payloads omit `coverage_results`.

- [ ] In the coverage semantics test that previously expected provider
  `no_supported_claim`, expect Python `missed` for obligations with no linked
  claim.

Expected coverage rows for the two-obligation test:

```python
[
    ("coverage-deal_obligation_1", "claims_emitted", 1),
    ("coverage-deal_obligation_2", "missed", 0),
]
```

- [ ] Add a rollback test that verifies no `coverage_results` rows survive when
  a claim has the wrong obligation family.

- [ ] Update hard-reset schema test so strict provider schema no longer has
  `coverage_results`, while DuckDB tables still include `coverage_results`.

- [ ] Add a hard-reset test inserting relation claims with:

```text
voting_support_for
rollover_holder_for
committee_member_of
recused_from
```

and assert they insert, reconcile, validate, and canonicalize.

- [ ] Add a test that `rollover_holder_of` fails Pydantic validation or DuckDB
  insertion.

- [ ] Run:

```bash
PYTHONDONTWRITEBYTECODE=1 uv run pytest -q -p no:cacheprovider \
  tests/test_coverage_semantics.py \
  tests/test_hard_reset_schema.py \
  tests/test_validation_semantics.py
```

Expected: pass.

## Task 8: Update Reconcile, Validation, And Projection Behavior

**Files:**

- Modify: `src/sec_graph/reconcile/pipeline.py`
- Modify: `src/sec_graph/validate/integrity.py`
- Modify: projection code only if tests show enum-specific assumptions.

- [ ] Confirm `_canonicalize_relation` passes new relation labels through to
  `actor_relations` without label-specific branching.

- [ ] If actor kind inference remains generic, do not expand it in this task.
  This plan is relation-label schema freeze, not actor-class taxonomy.

- [ ] Confirm validator accepts source-supported examples:

```text
voting agreement
agreed to vote
voting and support agreement
equity rollover
special committee composed of
added to the special committee
recused himself
excluded from the Board's evaluation
```

- [ ] Confirm validator rejects a relation quote that contains only a subject
  or object but not relation support.

- [ ] Run:

```bash
PYTHONDONTWRITEBYTECODE=1 uv run pytest -q -p no:cacheprovider tests/test_validation_semantics.py
```

Expected: pass.

## Task 9: Aggressive Stale Cleanup

**Files:**

- Verify active stale plan docs remain outside the active plan directory.
- Modify or delete tests/code that preserve old provider coverage behavior.
- Do not delete calibration evidence or source filings.

- [ ] Confirm active `quality_reports/plans/` has only the current
  implementation plan and `legacy/`:

```bash
find quality_reports/plans -maxdepth 1 -type f -print | sort
```

Expected:

```text
quality_reports/plans/2026-05-04_relation_revised_claim_only_p8_implementation_plan.md
```

- [ ] If any other active plan file is present, move it to
  `quality_reports/plans/legacy/` if it is historical, or delete it if it is a
  temporary generated artifact.

- [ ] Search for stale contract language:

```bash
rg -n "P7|V0|coverage_results.*provider|provider.*coverage_results|CoverageResultPayload|semantic_claims_v1|rollover_holder_of|Default live Linkflow reasoning effort is `high`|test_llm_p7_contract|EXPANDED_CLAIM_ONLY_P8.*production|PLAIN_RECALL.*production|V0_P8_BASELINE.*production" \
  docs src tests
```

Expected: no matches except:

- Python-owned DuckDB `coverage_results` table and proof output references;
- historical context in `docs/prior-pipeline-lessons.md`, if the grep includes it.

- [ ] Search for forbidden scalar provider fields:

```bash
rg -n "bid_formality|proposal_scope|drop_agency|drop_reason|initiation_side|actor_claims\\.actor_class" \
  docs src tests
```

Expected: no active-code matches. Active docs may mention these only to say
they are rejected provider fields.

## Task 10: Run Local Verification

**Files:** no additional edits unless failures require fixes.

- [ ] Run focused tests:

```bash
PYTHONDONTWRITEBYTECODE=1 uv run pytest -q -p no:cacheprovider \
  tests/test_llm_p8_contract.py \
  tests/test_coverage_semantics.py \
  tests/test_hard_reset_schema.py \
  tests/test_validation_semantics.py \
  tests/test_run_kernel.py
```

Expected: pass.

- [ ] Run full tests:

```bash
PYTHONDONTWRITEBYTECODE=1 uv run pytest -q -p no:cacheprovider
```

Expected: pass.

- [ ] Run a no-bytecode stale scan:

```bash
find . -name '__pycache__' -o -name '*.pyc'
```

Expected: no output.

## Task 11: Optional Tiny Live Linkflow Smoke

Only run this if credentials are available through the environment. Do not ask
for or write secrets.

The goal is not another broad calibration. The goal is to confirm Linkflow
accepts the final strict schema and can emit at least one new relation label.

- [ ] Check for key presence without printing it:

```bash
test -n "${LINKFLOW_API_KEY:-}" && echo "LINKFLOW_API_KEY set" || echo "LINKFLOW_API_KEY missing"
```

- [ ] If no key is set, skip this task and state that live smoke was not run.

- [ ] If a key is set, run one small relation-focused window only. Prefer an
  existing local CLI path if the implementation has one. If no single-window CLI
  exists, use the smallest project command that runs one known local deal and
  one run directory.

Example shape:

```bash
RUN_ID="$(date -u +%Y-%m-%dT%H%M%SZ)_petsmart_relation_p8_smoke"
RUN_DIR="runs/$RUN_ID"
PYTHONDONTWRITEBYTECODE=1 uv run python -m sec_graph run \
  --source filings \
  --slugs petsmart-inc \
  --run-id "$RUN_ID" \
  --run-dir "$RUN_DIR" \
  --llm-provider linkflow \
  --llm-reasoning-effort medium \
  --request-mode claim_only_p8_relation_v1
```

Expected: the run either completes with proof artifacts or fails loudly with a
specific source/provider/schema error. Do not retry with broad `high` or
`xhigh`. Do not switch providers.

## Task 12: Final Session Log And Handoff

**Files:**

- Create: `quality_reports/2026-05-04_ref9_schema_freeze_session_log.md`

- [ ] Write the session log with this structure:

```markdown
# Reference-9 Schema Freeze Session Log

## Decision Implemented

Relation-revised claim-only P8 contract.

## Files Changed

List docs, code, tests, and deleted stale docs.

## Verification

Paste exact commands run and pass/fail result.

## Live Smoke

State whether it ran. If skipped, state that credentials were unavailable or
that local-only verification was the intended gate.

## Remaining Work

List only real blockers. Do not include stale wish-list items.
```

- [ ] Run final status:

```bash
git status --short
```

- [ ] The final handoff must explicitly state:

```text
Provider coverage_results removed.
Python-owned coverage_results retained.
Default Linkflow reasoning is medium.
Request mode is claim_only_p8_relation_v1.
rollover_holder_of removed.
rollover_holder_for added.
voting_support_for, committee_member_of, recused_from added.
Scalar expanded fields rejected.
```

## Full `/goal` Prompt

Copy this into `/goal` for execution:

```text
Implement the Reference-9 relation-revised claim-only P8 schema freeze in /Users/austinli/Projects/sec_graph.

Follow quality_reports/plans/2026-05-04_relation_revised_claim_only_p8_implementation_plan.md exactly.

Hard rules:
- no fallbacks;
- no backward compatibility;
- no stale provider coverage_results path;
- no old semantic_claims_v1 request mode;
- no P7/high active contract;
- no rollover_holder_of compatibility alias;
- no scalar provider fields for actor_class, bid_formality, proposal_scope, drop_agency, drop_reason, or initiation_side;
- no broad xhigh reruns;
- no provider switch;
- no secret printing;
- preserve unrelated dirty work.

Use subagent lanes:
Lane A docs authority and stale-doc cleanup.
Lane B LLM contract models, request mode, Linkflow schema, and prompt.
Lane C extraction/canonical schema relation labels and conversion.
Lane D validation/reconcile/projection tests.
Lane E final stale scan, verification, and session log.

Acceptance:
- docs/spec.md and docs/llm-interface.md describe the settled P8 claim-only contract;
- provider SemanticClaimsPayload has no coverage_results;
- Python still writes coverage_results table rows;
- default Linkflow reasoning is medium;
- request mode is claim_only_p8_relation_v1 only;
- relation labels are member_of, affiliate_of, controls, acquisition_vehicle_of, advises, finances, supports, voting_support_for, rollover_holder_for, committee_member_of, recused_from;
- rollover_holder_of is gone from active docs/code/tests;
- tests/test_llm_p8_contract.py replaces tests/test_llm_p7_contract.py;
- stale plan docs are absent from active `quality_reports/plans/` and historical plans live only under `quality_reports/plans/legacy/`;
- PYTHONDONTWRITEBYTECODE=1 uv run pytest -q -p no:cacheprovider passes;
- quality_reports/2026-05-04_ref9_schema_freeze_session_log.md records files changed, stale cleanup, verification, and any live smoke result.
```

## What Is Done

This work is complete only when:

- all active docs agree with the relation-revised claim-only P8 contract;
- provider coverage output is removed from models, prompt, strict schema,
  Linkflow adapter, tests, and docs;
- Python coverage tables and proof outputs still exist and pass tests;
- relation labels are updated consistently in extraction schema, canonical
  schema, validation, reconcile, and tests;
- stale active plans and P7/high/P8-baseline instructions are absent from the
  active `quality_reports/plans/` surface;
- full local tests pass;
- session log is written;
- live smoke is either run or explicitly skipped with reason.
