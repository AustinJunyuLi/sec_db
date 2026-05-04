# Semantic Disposition And Derived Judgment Layer Design

**Date:** 2026-05-05
**Status:** Approved design for implementation-plan handoff.
**Repository:** `/Users/austinli/Projects/sec_graph`
**Parent authority:** `docs/superpowers/specs/2026-05-03-pipeline-hard-reset-design.md`

## 1. Objective

Refactor the middle of the `sec_graph` pipeline so the canonical graph is
valid by construction, while the extractor still tries hard to capture
source-supported facts.

The end goal is not perfect autonomous extraction. Austin and Alex expect some
deal repair to happen later with AI assistance, outside this pipeline. This
pipeline should make later repair fast by producing compact, source-backed
review flags. It must not hide uncertainty, overfit Reference-9, or mutate
canonical rows through an in-pipeline repair loop.

The new target shape is:

```text
filing text
-> source regions
-> applicability obligations
-> Linkflow typed claims
-> Python quote binding
-> pre-reconcile claim disposition gate
-> canonical graph
-> derived judgment layer
-> deterministic projections
-> review-ready flag bundle
-> proof verdict
```

The core contract is:

```text
try hard at extraction
reject unsupported facts before canonicalization
derive mature judgments from supported canonical facts
surface misses and ambiguity for later review
never produce false canonical certainty
```

## 2. Non-Negotiables

- No fallbacks.
- No backward compatibility paths.
- No patchlike compatibility shims.
- No in-pipeline AI repair.
- No provider-owned source offsets.
- No provider-owned coverage results.
- No provider-owned scalar research judgments.
- No Alex or workbook taxonomy as canonical graph shape.
- No synthetic phantom actors merely to mimic workbook rows.
- No Reference-9-specific rules that do not generalize from source semantics.
- No external advisor-registration lookup in this refactor.
- No secrets in code, docs, artifacts, logs, prompts, or command output.
- `data/filings/` remains local research source material and must not be
  deleted.

Linkflow remains a claim proposer. Python owns quote binding, source spans,
coverage results, claim dispositions, canonicalization, derived judgments,
validation, projection, and proof.

## 3. Scope

This refactor covers the full middle-pipeline contract from validated provider
claims through proof:

1. Authority cleanup.
2. Pre-reconcile claim disposition.
3. Anti-underextraction coverage flags.
4. Reconcile boundary tightening.
5. Derived judgment layer.
6. Advisor and counsel representation.
7. Review flag bundle.
8. Verdict semantics.
9. Projection refactor.
10. Validation and proof.
11. Reference-9 acceptance matrix.

This refactor does not build a reviewer UI, an external registration service,
or an in-pipeline repair loop.

## 4. Authority Cleanup

`docs/superpowers/specs/2026-05-03-pipeline-hard-reset-design.md` remains the
parent hard-reset authority.

This document becomes the active next design for semantic validity,
anti-underextraction, and derived judgments.

After this design is written and committed, the implementation plan should
clean stale planning surfaces:

- Keep active:
  - `docs/superpowers/specs/2026-05-03-pipeline-hard-reset-design.md`
  - this design document
  - `docs/spec.md`
  - `docs/llm-interface.md`
- Move to legacy after this design lands:
  - `docs/superpowers/specs/2026-05-04-reference9-correctness-repair-design.md`
  - `quality_reports/plans/2026-05-04_p8_region_applicability_ref9_plan.md`
  - `quality_reports/plans/2026-05-04_reference9_correctness_repair_plan.md`
- Preserve as useful non-authority evidence:
  - `quality_reports/schema_read/2026-05-03_background-shape-scan.md`
  - semantic-review calibration ledgers under
    `quality_reports/llm_calibration/ref9_schema_calibration_2026-05-04/`
  - point-in-time session logs, preferably under a session-log legacy/archive
    folder if active surfaces need to stay clean.
- Hard-delete stale generated or obsolete P7/high probe debris identified in
  `quality_reports/plans/legacy/` and
  `quality_reports/llm_calibration/legacy/` when it has no current evidentiary
  value.

Cleanup must preserve source material and useful semantic-review ledgers. It
must not delete `data/filings/`, raw filing text, or audit evidence needed to
understand current design decisions.

## 5. Claim Disposition Gate

The pre-reconcile gate is the first major behavioral change.

Today, a provider claim can pass schema checks and quote binding, enter
canonicalization, and only then fail semantic validation. That is too late.
The canonical graph can temporarily contain unsupported facts, and any blind
spot in post-reconcile validation can become false `SOUND`.

The new rule is:

```text
No claim may feed reconcile until Python has assigned a current support
disposition.
```

The gate reads only Python-owned evidence:

```text
claims
typed claim rows
claim_evidence
claim_coverage_links
coverage_obligations
source spans
source paragraph/window text
```

It writes exactly one current disposition per claim before canonicalization.

Allowed current dispositions:

```text
supported
merged_duplicate
rejected_unsupported
queued_ambiguity
out_of_scope
```

Disposition meanings:

- `supported`: the claim's quote and typed fields support the claimed fact.
- `merged_duplicate`: the claim is supported but collapses into an existing
  canonical fact.
- `rejected_unsupported`: the quote or source context does not support the
  typed claim.
- `queued_ambiguity`: Python cannot safely decide support.
- `out_of_scope`: the claim is valid JSON but outside the current extraction
  contract.

Only `supported` and legitimate `merged_duplicate` claims may influence
canonical graph rows. `rejected_unsupported`, `queued_ambiguity`, and
`out_of_scope` stay in the claim ledger and review bundle.

The old idea of `canonicalized` as the main disposition should be removed.
Canonicalization is a mapping outcome, not a proof state. A supported claim may
record `canonical_table` and `canonical_id`, but the disposition itself should
still communicate support status.

## 6. Support Rules

The support gate should be deterministic, narrow, and source-facing.

Bid claims must have quote support for:

- bidder or bidder group;
- bid date or acceptable date expression;
- bid value or value range when claimed;
- proposal or bid context;
- stage context when stage is claimed.

Actor-relation claims must have quote support for:

- subject;
- object;
- relation type;
- direction;
- role detail when present.

Participation-count claims must have quote support for:

- count or count phrase;
- count kind;
- current-process relevance;
- actor class or role when claimed.

Actor and event claims must have support for the entity, action, and date fields
they claim. Missing optional fields are not failures, but present fields must be
supported.

When Python cannot safely classify a contextual judgment, it must queue
ambiguity instead of inventing certainty.

## 7. Anti-Underextraction Coverage

Validity-first must not become conservative-by-default extraction.

The LLM should still be asked to extract broadly inside selected source
regions. Underextraction is controlled by coverage obligations and review
flags, not by narrowing the provider request.

Every applicable obligation must resolve to exactly one current coverage
result:

```text
claims_emitted
missed_supported_obligation
ambiguous_support
no_supported_claim
```

Meanings:

- `claims_emitted`: at least one validated, linked, supported claim satisfies
  the exact obligation.
- `missed_supported_obligation`: source support appears to exist, but no
  linked supported claim was emitted.
- `ambiguous_support`: Python cannot safely decide whether source support
  exists.
- `no_supported_claim`: the obligation was applicable to inspect, but the
  source window does not support a positive claim.

`missed_supported_obligation` is not a soft note. It is a review flag that
protects against underextraction. Required or important missed obligations
produce `REVIEW_REQUIRED` unless the implementation plan defines an even
stricter failure mode for a specific class.

The provider never emits absence judgments. Python alone writes coverage
results after quote binding, claim-to-obligation validation, and support
disposition.

## 8. Reconcile Boundary

Reconcile must consume only supported claims.

The reconcile stage should no longer discover semantic invalidity after it has
already written canonical rows. It should assume that its input set has already
passed support disposition, and it should fail loudly if unsupported or
undisposed claims are present in its input query.

Reconcile remains responsible for:

- stable canonical ids;
- actor alias normalization;
- duplicate merging;
- canonical row creation;
- `row_evidence` links;
- mapping supported claims to canonical rows.

Reconcile is not responsible for:

- accepting unsupported source claims;
- repairing provider misses;
- deriving formal/informal or dropout taxonomy;
- writing projection rows.

## 9. Derived Judgment Layer

The derived judgment layer is the second major behavioral change.

It runs after canonical graph rows exist and before validation/projection. It
derives mature research judgments from supported canonical facts. This keeps
canonical source facts generic while avoiding a review flood for cases where
accepted deterministic rules are good enough.

The layer should live in a small Python-owned module such as:

```text
src/sec_graph/judgments/
```

It should write to a tightened generic `judgments` table, not to per-topic
tables and not to provider payloads.

Required judgment row concepts:

```text
judgment_id
run_id
deal_id
cycle_id
target_table
target_id
judgment_key
judgment_value
judgment_status
rule_id
reason_code
reason
basis_json
current
supersedes_judgment_id
```

Allowed `judgment_status` values:

```text
accepted
review_required
not_applicable
```

The implementation must replace or tighten the current append-only
`judgments` shell. No backward-compatible reader is required.

## 10. Formal And Informal Judgments

Formal/informal is a mature derived judgment, not a provider scalar and not a
canonical event label.

Inputs:

- supported bid events or bid claims;
- supported phase-boundary events;
- bid value shape;
- supported final-round context;
- supported marked-up merger agreement evidence when present;
- source-backed preliminary, IOI, LOI, non-binding, or range cues.

Automatic rules:

- range bid -> `informal`;
- explicit IOI, LOI, preliminary, or non-binding cue -> `informal`;
- before first supported final-round boundary -> `informal`;
- after first supported final-round boundary -> `formal`;
- marked-up merger agreement evidence can promote to `formal`.

Review triggers:

- no supported final-round boundary when one is needed;
- final-round boundary is queued ambiguous;
- negative informal cues conflict with formal promotion;
- marked-up merger agreement evidence appears without a clear boundary;
- source facts needed by the rule are missing or contradictory.

Raw provider formality fields remain prohibited. The provider should preserve
source indicators through ordinary quote-backed claims.

## 11. Dropout Taxonomy

Dropout should not be modeled as workbook event-label variants.

Canonical facts should preserve what the filing says happened. Derived
judgments should classify that fact for research use.

Canonical source-backed event concept:

```text
observed_drop
```

Derived judgment keys:

```text
drop_agency
drop_reason
terminal_value_relation
projected_fate
```

Allowed `drop_agency`:

```text
bidder
target
null
```

`null` means the source substrate does not support automatic agency. It should
produce review when agency matters.

Allowed `drop_reason`:

```text
never_advanced
below_minimum
below_market
no_response
scope_mismatch
target_other
null
```

`target_other` is allowed only for source-backed target-side reasons not
captured by sharper classes, and it should be review-visible.

Allowed `terminal_value_relation`:

```text
at_prior_informal
below_prior_informal
below_signed_price
null
```

Allowed `projected_fate`:

```text
observed_bid
observed_drop
signed_transaction
silent_after_nda
no_projected_fate
```

Rules:

- Drop agency follows the source verb subject when source support is clear.
- Drop reason uses the most specific supported class.
- Terminal value relation is computed from terminal price or comparator
  evidence against the latest prior informal bid, then signed price.
- Comparator evidence must never flip a target exclusion into bidder
  withdrawal.
- `silent_after_nda` is a projection/judgment over a complete source region,
  not a canonical event.

Explicit exclusions from canonical event vocabulary:

```text
DropTarget
DropAtInf
DropBelowInf
DropBelowM
DropSilent
```

Review triggers:

- drop agency ambiguity;
- comparator evidence attached to target exclusion;
- terminal comparator with no prior or signed-price anchor;
- `target_other`;
- silent fate derived from incomplete source coverage;
- exact-count conflict around dropped or advanced bidders.

## 12. Advisor And Counsel Representation

Advisor registration in this refactor means graph registration of advisor and
counsel actors, roles, and relations. It does not mean external FINRA, IAPD,
SEC, law-firm, or other outside lookup.

Financial and legal advisors should be represented as actors and relations:

```text
actor: Evercore
process_role: financial_advisor
relation: Evercore advises Target
```

The existing `advises` relation should be used when quote-backed. Advisor
facts should not be stored as comments on bidder rows, and advisors should not
be counted as bidders merely because they signed a confidentiality agreement.

Legal counsel should usually be a relation-level fact. It becomes an event only
when the filing gives a dated, analytically useful legal-advisor process action.

Agreement classification should be a derived judgment or supported relation
over agreement facts:

```text
target_bidder_nda
bidder_bidder_consortium_ca
advisor_confidentiality
rollover_support
null
```

Review triggers:

- advisor-vs-bidder ambiguity;
- confidentiality agreement kind ambiguity;
- advisor NDA counted as bidder NDA;
- target advisor and bidder advisor confused;
- legal counsel mentioned without enough substrate to place the role.

## 13. Actor Registration And Counts

The canonical graph should use actors, aliases, relations, and evidence links.
It should not import provider-owned bidder registries or bidder numbering as
canonical truth.

Anonymous exact counts should remain in `participation_counts`. The pipeline
must not create canonical phantom actors just to mimic workbook rows.

Projection may later create count units or bidder-row handles when a downstream
export requires them. Those projection units must trace back to
`participation_counts`, source spans, and projection judgments.

Actor class may be derived only when source-backed:

```text
strategic
financial
mixed
null
```

`mixed` means source-backed mixed strategic/financial membership, not
uncertainty.

Process role is actor-cycle scoped, not global actor identity:

```text
bidder
target
acquirer
financial_advisor
legal_advisor
committee
shareholder
financing_source
```

One actor may have different roles across cycles.

## 14. Review Flags

The pipeline should produce compact review artifacts for later human or
AI-assisted repair outside this pipeline.

Every review flag should include:

```text
deal_slug
filing_id
region_id
obligation_id when applicable
claim_id when applicable
judgment_id when applicable
canonical_table when applicable
canonical_id when applicable
flag_type
severity
reason_code
reason
quote_text when applicable
source span or paragraph reference
short source context
recommended review question
```

Flag types:

```text
unsupported_claim
missed_supported_obligation
ambiguous_support
judgment_substrate_missing
judgment_conflict
advisor_role_ambiguous
drop_agency_ambiguous
projection_trace_failure
provider_contract_failure
region_selection_failure
source_binding_failure
```

Severity values:

```text
blocking
review
info
```

Guidance:

- `unsupported_claim` protects graph validity.
- `missed_supported_obligation` protects against underextraction.
- `ambiguous_support` protects against pretending Python understood a
  contextual judgment it did not understand.
- `judgment_conflict` keeps mature derived rules from silently overwriting weak
  substrate.
- `info` flags may appear in a `SOUND` run.
- `review` flags produce `REVIEW_REQUIRED` when they affect required or
  important facts.
- `blocking` flags produce `UNSOUND`.

Review flags must be materialized in a first-class `review_flags` table and
exported as a review-ready artifact such as `review_flags.csv` or
`review_flags.json`. The table may be populated from coverage, dispositions,
judgments, provider failures, source binding failures, and validation failures,
but the final proof surface must not require recomputing flags from scattered
tables.

## 15. Verdicts

The proof surface should use three verdicts:

```text
SOUND
REVIEW_REQUIRED
UNSOUND
```

`SOUND` means:

- live semantic extraction ran when required;
- no unsupported claim entered canonical tables;
- every claim has a current disposition;
- required and important obligations are resolved;
- required derived judgments are accepted or not applicable;
- canonical rows and projection rows trace to source-backed facts;
- no blocking or review-severity flags remain for required or important facts.

`REVIEW_REQUIRED` means:

- canonical graph rows are valid and traceable;
- unsupported claims did not enter canonical rows;
- at least one required or important fact, obligation, or derived judgment
  needs review because of a miss, ambiguity, or judgment conflict.

`UNSOUND` means:

- unsupported or undisposed claims entered canonicalization;
- canonical or projection rows lack source proof;
- provider contract failed;
- quote binding failed;
- validation detected broken proof links;
- a blocking review flag exists.

`REVIEW_REQUIRED` is not failure theater. It is the expected outcome when the
pipeline has done truthful extraction but later repair or human judgment is
needed.

## 16. Projection

Projection should consume canonical facts plus derived judgments.

Projection must not depend on workbook labels as canonical facts. It should not
read `DropTarget`, `DropBelowInf`, `DropBelowM`, `DropAtInf`, or `DropSilent`
as source event labels.

Projection should read:

```text
actors
actor_relations
events
event_actor_links
participation_counts
row_evidence
judgments
projection_judgments
```

Projection can create downstream rows such as bidder-cycle units only when
they trace to canonical actor-cycle evidence, participation counts, and
accepted judgments.

## 17. Validation And Proof

Validation must enforce the new contract:

- every claim has exactly one current disposition;
- reconcile reads only supported or merged duplicate claims;
- unsupported, ambiguous, and out-of-scope claims never create canonical rows;
- coverage results are obligation-specific and agree with
  `claim_coverage_links`;
- required and important missed obligations become review or blocking outcomes;
- derived judgments exist when required by projection or proof;
- derived judgments have source-backed substrate;
- projections trace to canonical rows and accepted judgments;
- review flags are exported and reflected in the proof verdict;
- stale `soft_flags()` or old projection-eligibility queries are removed or
  replaced.

Proof exports should include:

```text
claim_dispositions.csv
coverage_results.csv
claim_coverage_links.csv
judgments.csv
review_flags.csv or review_flags.json
validation_report.json
proof_summary.json
```

Failed-validation runs must still write concise proof metadata before aborting.

## 18. Reference-9 Acceptance Matrix

Reference-9 remains the live acceptance set:

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

The live proof run should run these deals separately and in parallel where
possible. A combined `--slugs` invocation is not enough proof of per-deal
behavior.

Success is not all nine deals having perfect extraction. Success is:

- no unsupported canonical facts;
- every provider claim has a truthful disposition;
- required source-supported misses are surfaced as review flags;
- ambiguous source support is surfaced as review flags;
- mature judgments auto-classify when substrate is strong;
- only genuinely weak or conflicting cases require review;
- every review flag is compact enough for later human or AI-assisted repair.

The proof matrix should show, per deal:

```text
provider_completed
quote_binding_passed
claim_dispositions_complete
unsupported_claims_rejected
coverage_complete_or_reviewed
judgments_complete_or_reviewed
projection_trace_passed
verdict
review_flag_count
blocking_flag_count
```

## 19. Testing Requirements

Tests should be red-first and focused on behavior, not snapshots.

Required unit and integration coverage:

1. Claim disposition gate:
   - unsupported bid claim is rejected before reconcile;
   - unsupported relation claim is rejected before reconcile;
   - ambiguous relation claim becomes review-required;
   - rejected and ambiguous claims never create canonical rows;
   - reconcile fails loudly if an undisposed claim is present.

2. Coverage and anti-underextraction:
   - applicable obligation with source support and no supported linked claim
     becomes `missed_supported_obligation`;
   - topic-only source becomes `ambiguous_support` or `no_supported_claim`,
     depending on source classification;
   - inapplicable obligations do not create false misses;
   - `claims_emitted` requires a linked supported claim.

3. Derived judgments:
   - range bid derives informal;
   - supported final-round boundary derives formal/informal by position;
   - missing final-round substrate creates judgment review;
   - drop agency ambiguity creates review;
   - terminal value relation uses prior informal and signed-price anchors;
   - comparator evidence does not flip target exclusion into bidder withdrawal;
   - advisor confidentiality does not count as bidder NDA.

4. Advisor and actor roles:
   - financial advisor is registered as actor plus `advises` relation;
   - legal counsel is relation-level unless dated process action exists;
   - advisor-vs-bidder ambiguity creates review;
   - actor class `mixed` means source-backed mixed composition.

5. Projection and proof:
   - projection consumes accepted judgments;
   - projection does not read workbook dropout labels;
   - `SOUND`, `REVIEW_REQUIRED`, and `UNSOUND` are distinguishable;
   - review flags include source context and recommended review questions;
   - stale `soft_flags()` behavior is removed or repaired.

6. Reference-9:
   - latest per-deal live runs are recorded in a proof matrix;
   - no invalid canonical row survives;
   - review-required deals remain auditable instead of being forced green.

## 20. Agent Lanes For Implementation

Use parallel subagents where write scopes can stay separate.

Recommended lanes:

```text
Lane A: claim disposition gate and reconcile boundary
Lane B: coverage and anti-underextraction flags
Lane C: derived judgment schema and rules
Lane D: advisor/counsel representation and actor roles
Lane E: proof verdicts and review bundle
Lane F: Reference-9 validation matrix
Lane G: stale-plan cleanup
```

Agents must not revert each other's work. If lanes need the same file, the
implementation plan must sequence those edits or split ownership by function.

## 21. Explicit Non-Goals

- No reviewer UI.
- No in-pipeline AI repair.
- No external advisor-registration lookup.
- No broad provider payload expansion.
- No old request mode reader.
- No old P7, P8-variant, or flat-schema compatibility path.
- No Alex workbook as ground truth.
- No hardcoded PetSmart, Saks, Penford, or other deal-specific repair rules.
- No synthetic canonical `DropSilent` events.
- No canonical workbook dropout labels.
- No canonical bidder registry emitted by Linkflow.

## 22. Implementation Handoff Criteria

This design is ready for implementation planning when:

- it is committed;
- active and legacy authority surfaces are clear;
- the implementation plan names exact write scopes;
- the plan includes red-first tests for the gate, judgments, flags, verdicts,
  and Reference-9 matrix;
- the plan preserves the out-of-pipeline repair boundary.

The implementation plan should be written only after Austin reviews this spec.
