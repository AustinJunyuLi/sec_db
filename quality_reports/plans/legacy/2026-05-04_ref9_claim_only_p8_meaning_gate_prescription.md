# Reference-9 Claim-Only P8 Meaning Gate Prescription

**Date:** 2026-05-04
**Status:** Active narrowed prescription for the next reviewer.
**Supersedes:** `quality_reports/plans/2026-05-04_ref9_linkflow_schema_calibration_test_design.md`
**Evidence root:** `quality_reports/llm_calibration/ref9_schema_calibration_2026-05-04/`

## Goal

Decide whether `CLAIM_ONLY_P8` is good enough to freeze as the deployable
Linkflow schema, or whether a very small source-fact addition is required before
`docs/spec.md` and `docs/llm-interface.md` are finalized.

This is not another broad schema search. The broad probe is done. The remaining
test is a meaning review over the existing results.

The governing split is:

```text
Python selects source regions.
Linkflow emits source-backed positive claims.
Python binds quotes, checks source coordinates, decides coverage, records claim
dispositions, builds the canonical graph, validates outputs, and creates
projection views.
```

No provider-owned coverage verdicts. No fallback path. No backward
compatibility layer. No schema growth just because a field is tempting.

## Decision Already Settled

The calibration report provisionally chose `CLAIM_ONLY_P8`.

Use these report facts as settled unless the reviewer finds direct contradictory
evidence in the result artifacts:

- `CLAIM_ONLY_P8` completed Stage 2 at 88/88.
- `CLAIM_ONLY_P8` had mean quote match `0.9974` in Stage 2.
- `CLAIM_ONLY_P8` completed Stage 4 variance work at 72/72.
- `V0_P8_BASELINE` is rejected as a production target.
- `PLAIN_RECALL_SIDECAR` is not production output.
- `EXPANDED_MULTI_QUOTE_P8` is rejected for this prescription. Do not reopen it
  during this gate.
- `medium` reasoning is the default. Do not run broad `high` or `xhigh`.

The active report is:

```text
quality_reports/llm_calibration/ref9_schema_calibration_2026-05-04/decision_report.md
```

## Only Live Question

Does `CLAIM_ONLY_P8` preserve enough source facts for the research questions, or
does `EXPANDED_CLAIM_ONLY_P8` recover necessary facts that claim-only loses?

The answer must be based on exact source-backed claims, not on aggregate claim
counts.

The reviewer should focus on facts needed for:

- formal versus informal bid boundary;
- dropout mode and dropout reason;
- initiation side;
- strategic versus financial actor classification;
- proposal scope;
- support, rollover, committee, and recusal relations.

## Slashed Stale Work

Do not continue these older paths:

- Do not rerun the five-candidate matrix.
- Do not compare candidates by total claim count.
- Do not promote `V0_P8_BASELINE`.
- Do not promote `PLAIN_RECALL_SIDECAR`.
- Do not promote `EXPANDED_MULTI_QUOTE_P8`.
- Do not ask Linkflow to emit negative coverage results.
- Do not run broad `xhigh`.
- Do not update `docs/spec.md` or `docs/llm-interface.md` until this meaning
  gate is signed off.
- Do not treat the old three deals as acceptance. They are only the first
  priority subset inside Reference-9.

## Reference-9 Deals

The acceptance set remains exactly:

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

Review all nine. Prioritize the old three first because they are known hard
cases:

```text
petsmart-inc
mac-gray
providence-worcester
```

Old-three success is not acceptance. It is a quick way to find obvious failure
before spending reviewer time on the full set.

## Candidate Pair To Compare

Only compare these two schemas:

```text
quality_reports/llm_calibration/ref9_schema_calibration_2026-05-04/schemas/CLAIM_ONLY_P8.json
quality_reports/llm_calibration/ref9_schema_calibration_2026-05-04/schemas/EXPANDED_CLAIM_ONLY_P8.json
```

Use Stage 2 results as the main comparison set:

```text
quality_reports/llm_calibration/ref9_schema_calibration_2026-05-04/results/stage2/CLAIM_ONLY_P8/
quality_reports/llm_calibration/ref9_schema_calibration_2026-05-04/results/stage2/EXPANDED_CLAIM_ONLY_P8/
```

Use Stage 4 only to check whether a `CLAIM_ONLY_P8` fact is stable across
replicas:

```text
quality_reports/llm_calibration/ref9_schema_calibration_2026-05-04/results/stage4/CLAIM_ONLY_P8/
```

## Schema Deltas Under Review

The expanded candidate adds these obvious fields:

```text
actor_claims.actor_class
bid_claims.bid_formality
bid_claims.proposal_scope
event_claims.drop_agency
event_claims.drop_reason
event_claims.initiation_side
```

It also changes relation labels. This must be reviewed separately:

```text
CLAIM_ONLY_P8 relation labels:
member_of
affiliate_of
controls
acquisition_vehicle_of
advises
finances
supports
rollover_holder_of

EXPANDED_CLAIM_ONLY_P8 relation labels:
member_of
affiliate_of
controls
acquisition_vehicle_of
advises
finances
voting_support_for
rollover_holder_for
committee_member_of
recused_from
supports
```

The final schema should not use cryptic names like `s` and `f` unless the docs
spell out their meaning. If actor classification survives this review, prefer
plain labels in the final contract, such as `strategic`, `financial`, and
`mixed`.

## Review Outputs

Create this directory:

```text
quality_reports/llm_calibration/ref9_schema_calibration_2026-05-04/semantic_review/
```

The reviewer must write these files:

```text
semantic_fact_ledger.csv
schema_delta_decisions.md
claim_only_failure_cases.jsonl
final_recommendation.md
```

### `semantic_fact_ledger.csv`

One row per reviewed source fact. Use this exact header:

```csv
slug,window_id,question,fact_label,source_quote,claim_only_job_id,claim_only_present,claim_only_claim_path,expanded_job_id,expanded_present,expanded_field,expanded_value,python_derivable_from_claim_only,recommended_action,reviewer_note
```

Allowed values:

```text
claim_only_present: yes | no | partial
expanded_present: yes | no | partial
python_derivable_from_claim_only: yes | no | unclear
recommended_action: keep_claim_only | add_minimal_field | fix_region_selection | fix_prompt_instruction | no_action_needed | needs_human_decision
```

### `schema_delta_decisions.md`

Write one short decision section for each field or relation-label delta:

```text
actor_claims.actor_class
bid_claims.bid_formality
bid_claims.proposal_scope
event_claims.drop_agency
event_claims.drop_reason
event_claims.initiation_side
relation label: voting_support_for
relation label: rollover_holder_for / rollover_holder_of
relation label: committee_member_of
relation label: recused_from
```

Each section must answer:

```text
Adopt, reject, or revise?
What exact hard facts support the decision?
Can Python derive the fact from claim-only output?
Would adding this field create a provider-owned research judgment?
What exact docs/spec change would be needed if adopted?
```

### `claim_only_failure_cases.jsonl`

Write one JSON object per real `CLAIM_ONLY_P8` miss:

```json
{"slug":"petsmart-inc","window_id":"w2_rollover","question":"rollover relation","source_quote":"Copy the exact quote text from the reviewed result here","claim_only_job_id":"stage2__petsmart-inc__CLAIM_ONLY_P8__W2_MULTI_REGION__w2_rollover__medium__r1","expanded_job_id":"stage2__petsmart-inc__EXPANDED_CLAIM_ONLY_P8__W2_MULTI_REGION__w2_rollover__medium__r1","failure_type":"missing_source_fact","proposed_fix":"add relation label voting_support_for","why_region_selection_is_not_the_issue":"The selected window contains the source quote, so this is not a region-selection miss"}
```

Allowed `failure_type` values:

```text
missing_source_fact
wrong_claim_type
too_weak_description
missing_relation_label
missing_context_for_python_derivation
region_selection_gap
prompt_instruction_gap
```

### `final_recommendation.md`

Use this structure:

```markdown
# Claim-Only P8 Meaning Gate Final Recommendation

## Recommendation

Choose exactly one:

- Freeze `CLAIM_ONLY_P8` as-is.
- Freeze `CLAIM_ONLY_P8` with specific prompt wording changes only.
- Freeze a minimally revised claim-only schema with named field additions.
- Do not freeze; rerun a narrow targeted extraction test.

## Evidence

Summarize the hard facts reviewed across all nine deals.

## Schema Changes

List exact fields or relation labels to adopt, reject, or revise.

## Remaining Risk

Describe any facts that still need human judgment.

## Required Follow-Through

List exact files that should change next.
```

## Parallel Review Model

Use deal-owned review lanes. Do not split by field first, because the meaning of
formal bids, dropout, initiation, and relations depends on within-deal context.

Recommended lanes:

```text
Lane A: petsmart-inc, mac-gray, providence-worcester
Lane B: medivation, imprivata, zep
Lane C: penford, saks, stec
Lane D: coordinator only; merge ledgers, check schema deltas, write final recommendation
```

Rules for the lanes:

- Each lane reads both Stage 2 candidate outputs for its assigned deals.
- Each lane writes rows to the shared ledger format, but not to the final
  recommendation.
- Lane D checks consistency across lanes.
- Lane D owns the final decision, not the deal lanes.
- No lane should edit `docs/spec.md`, `docs/llm-interface.md`, or source code.

## Review Method

For each assigned deal:

1. List the Stage 2 result files for `CLAIM_ONLY_P8` and
   `EXPANDED_CLAIM_ONLY_P8`.
2. Match files by slug and `window_id`.
3. Read the expanded output first and identify non-null expanded-only fields.
4. For each expanded-only field, inspect the exact `quote_text`.
5. Find the paired claim-only output for the same slug/window.
6. Decide whether claim-only contains the same source fact through another
   field, quote, event subtype, description, actor role, bid value, or relation.
7. If claim-only contains enough source fact for deterministic Python handling,
   mark `keep_claim_only`.
8. If expanded recovers a source fact that claim-only truly lacks, mark
   `add_minimal_field` or `fix_prompt_instruction`.
9. If neither candidate contains the source fact but the source window should
   contain it, mark `fix_prompt_instruction`.
10. If the source fact is outside the selected window, mark
    `fix_region_selection`.

The reviewer must not decide based on whether the expanded value "looks useful."
The reviewer must decide whether the value is required to preserve a fact that
the pipeline otherwise cannot recover.

## Field-Specific Decision Rules

### Actor Class

Reject `actor_claims.actor_class` unless the reviewer finds repeated cases
where the filing states enough about an actor to classify it as strategic,
financial, or mixed, and claim-only does not preserve that evidence anywhere.

If adopted, do not keep `s` or `f` as final public schema values. Spell the
values out.

### Bid Formality

Reject `bid_claims.bid_formality` as a final provider-owned judgment unless
claim-only misses the source language needed to determine formality.

Prefer preserving source indicators over asking Linkflow to own the final
formal/informal label. Useful indicators include:

```text
non-binding indication
preliminary proposal
written proposal
final proposal
best and final
definitive proposal
markup submitted
financing committed
```

If the claim-only bid quote and event context already preserve these indicators,
keep `CLAIM_ONLY_P8`.

### Proposal Scope

Adopt a scope field only if a deal contains material non-whole-company proposals
and claim-only does not preserve that fact through the bid quote or event
description.

Do not add proposal scope merely because it is convenient.

### Drop Agency and Drop Reason

The review must distinguish these cases:

```text
bidder withdrew
target excluded bidder
bidder did not respond
bidder failed to submit a later bid
process cohort closed
bidder remained active but did not win
```

If claim-only event subtypes and descriptions preserve this distinction, reject
the added fields.

If claim-only collapses materially different dropout paths into a vague event,
add the smallest source-fact field needed. Do not let Linkflow create a final
research projection row.

### Initiation Side

Reject `event_claims.initiation_side` if claim-only already preserves who moved
first through actor role, event subtype, and quote.

Consider a minimal addition only if the filing context is repeatedly lost, for
example:

```text
unsolicited buyer approach
target-authorized outreach
advisor contacted parties at board direction
management-led contact
mutual approach
```

The final initiation judgment should remain Python-owned when it can be derived
from source-backed event facts.

### Relation Labels

Review support, rollover, committee, and recusal facts separately from the six
expanded fields.

Adopt a relation label only if the generic claim-only labels hide a source fact
that matters for the graph. For example, `supports` may be too vague if the
filing clearly says a shareholder entered a voting agreement.

If adopted, choose one direction and one name. Do not keep both
`rollover_holder_of` and `rollover_holder_for` unless the docs define an
explicit direction rule.

## Commands For The Administering Agent

Set the root:

```bash
ROOT=quality_reports/llm_calibration/ref9_schema_calibration_2026-05-04
OUT="$ROOT/semantic_review"
mkdir -p "$OUT"
```

Verify candidate result counts:

```bash
find "$ROOT/results/stage2/CLAIM_ONLY_P8" -name '*.json' | wc -l
find "$ROOT/results/stage2/EXPANDED_CLAIM_ONLY_P8" -name '*.json' | wc -l
find "$ROOT/results/stage4/CLAIM_ONLY_P8" -name '*.json' | wc -l
```

Expected counts:

```text
88
88
72
```

Create an expanded-only field inventory:

```bash
jq -r '
  ["job_id","input_path","array","field","value","label","quote_text"],
  (
    . as $r
    | (
        $r.parsed.actor_claims[]?
        | select(.actor_class != null)
        | [$r.job_id,$r.input_path,"actor_claims","actor_class",.actor_class,.actor_label,.quote_text]
      ),
      (
        $r.parsed.bid_claims[]?
        | select(.bid_formality != null)
        | [$r.job_id,$r.input_path,"bid_claims","bid_formality",.bid_formality,.bidder_label,.quote_text]
      ),
      (
        $r.parsed.bid_claims[]?
        | select(.proposal_scope != null)
        | [$r.job_id,$r.input_path,"bid_claims","proposal_scope",.proposal_scope,.bidder_label,.quote_text]
      ),
      (
        $r.parsed.event_claims[]?
        | select(.drop_agency != null)
        | [$r.job_id,$r.input_path,"event_claims","drop_agency",.drop_agency,.actor_label,.quote_text]
      ),
      (
        $r.parsed.event_claims[]?
        | select(.drop_reason != null)
        | [$r.job_id,$r.input_path,"event_claims","drop_reason",.drop_reason,.actor_label,.quote_text]
      ),
      (
        $r.parsed.event_claims[]?
        | select(.initiation_side != null)
        | [$r.job_id,$r.input_path,"event_claims","initiation_side",.initiation_side,.actor_label,.quote_text]
      )
  )
  | @csv
' "$ROOT"/results/stage2/EXPANDED_CLAIM_ONLY_P8/*.json \
  > "$OUT/expanded_only_field_inventory.csv"
```

Create a relation-label inventory:

```bash
jq -r '
  ["candidate","job_id","input_path","relation_type","subject_label","object_label","quote_text"],
  (
    . as $r
    | $r.parsed.actor_relation_claims[]?
    | [$r.candidate,$r.job_id,$r.input_path,.relation_type,.subject_label,.object_label,.quote_text]
  )
  | @csv
' "$ROOT"/results/stage2/CLAIM_ONLY_P8/*.json \
  "$ROOT"/results/stage2/EXPANDED_CLAIM_ONLY_P8/*.json \
  > "$OUT/relation_label_inventory.csv"
```

Create a blank ledger with the required header:

```bash
printf '%s\n' 'slug,window_id,question,fact_label,source_quote,claim_only_job_id,claim_only_present,claim_only_claim_path,expanded_job_id,expanded_present,expanded_field,expanded_value,python_derivable_from_claim_only,recommended_action,reviewer_note' \
  > "$OUT/semantic_fact_ledger.csv"
```

## Success Gate

The gate passes with `CLAIM_ONLY_P8` if all of the following are true:

- Every old-three hard fact reviewed is recoverable from claim-only output.
- Every Reference-9 deal has been reviewed for the live schema deltas.
- Expanded-only fields do not recover a necessary source fact that claim-only
  loses.
- Relation-label differences are either rejected or converted into a minimal,
  clearly named relation set.
- Any remaining uncertainty is listed as a human judgment issue, not hidden in
  the schema.

The gate fails if any of the following are true:

- Claim-only repeatedly misses source facts needed for formality, dropout,
  initiation, actor class, proposal scope, support, rollover, committee, or
  recusal.
- A missing fact cannot be fixed by region selection or prompt wording.
- The reviewer cannot explain how Python would derive the needed research label
  from claim-only source facts.

## If The Gate Fails

Do not reopen the broad matrix.

Write the smallest possible proposed schema change in `final_recommendation.md`.
Then run only the affected candidate and affected windows. The rerun must have a
specific reason tied to `claim_only_failure_cases.jsonl`.

Allowed narrow rerun examples:

```text
high reasoning for CLAIM_ONLY_P8 and EXPANDED_CLAIM_ONLY_P8 on one disputed window
medium reasoning for a minimally revised claim-only schema on one disputed window
```

Disallowed rerun examples:

```text
full five-candidate matrix
broad xhigh
plain recall as production evidence
full-filing extraction as acceptance proof
```

## What Is Done

This narrowed test is done when:

- `semantic_fact_ledger.csv` covers all nine deals.
- `schema_delta_decisions.md` has a decision for every listed field and relation
  delta.
- `claim_only_failure_cases.jsonl` contains only real failures, not preference
  notes.
- `final_recommendation.md` makes one concrete schema recommendation.
- The recommendation states exactly whether `docs/spec.md` and
  `docs/llm-interface.md` should freeze `CLAIM_ONLY_P8` as-is, freeze it with
  prompt wording changes, or freeze a minimally revised claim-only schema.

Only after that should another agent update the binding docs and implementation
plan.
