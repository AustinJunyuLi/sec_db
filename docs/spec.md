# sec_graph Specification

**Status:** Approved hard-reset contract, updated for the 2026-05-04 P8
schema freeze.
**Execution authority:** `docs/superpowers/specs/2026-05-03-pipeline-hard-reset-design.md`.
**Middle-pipeline authority:** `docs/superpowers/specs/2026-05-05-semantic-disposition-validity-design.md`.

This repository implements a source-backed SEC merger-filing extraction
pipeline. The active architecture is:

```text
SEC filing
-> run kernel
-> ingest exact text and paragraph spans
-> evidence map
-> Linkflow GPT-5.5 relation-revised claim-only P8 typed semantic claims
-> Python P8 quote binding and validation
-> Python coverage results and claim disposition ledger
-> canonical graph
-> semantic validation
-> actor-cycle projection
-> proof and cost/runtime artifacts
```

The May 3 design is a breaking reset. There are no fallbacks, no backward
compatibility paths, and no legacy payload readers.

## Evidence Map And Live LLM Scope

The evidence map routes production Linkflow extraction to one coherent
sale-process section region per recognized heading. A filing may produce
more than one region when it carries genuinely distinct sale-process
material (for example, a tender-offer Offer to Purchase typically yields a
`Background of the Offer` region and a `Past Contacts, Transactions,
Negotiations and Agreements` region). Each region preserves source
paragraph order and carries Python-owned coverage obligations.

Coverage obligations are produced by a Python applicability engine. There
are three families:

- Universal obligations (process initiation, target board, target
  financial advisor, target legal advisor, final transaction price, final
  approval event) are always applicable in any sale-process region.
- Conditional obligations (IOI/first-round/final-round counts,
  exclusivity, go-shop, buyer-group composition, rollover holders, voting
  support, special committee, recusal, financing commitment, amendment,
  and similar) are applicable only when the region text emits a
  documented trigger phrase.
- Scope-driven obligations (such as tender-offer prior contacts) are
  applicable only when the filing's `process_scope` matches.

Inapplicable obligations are still inserted into `coverage_obligations`
with `applicability = 'not_applicable'`, `applicability_reason_code`, and
`applicability_basis_json`, so the audit ledger records every decision.
Linkflow only ever sees the applicable obligations.

Production LLM extraction uses request mode `claim_only_p8_relation_v1` and
default Linkflow reasoning effort `medium`.

Single-paragraph request surfaces and bounded snippets are not production LLM
extraction scope. Whole filing extraction is also not production mode and must
not be used as a fallback. Python owns source coordinates: Linkflow returns
positive typed-claim arrays only, with exact quote text and one explicit
`coverage_obligation_id` per claim. Linkflow does not return coverage results,
canonical ids, source offsets, projection rows, or scalar research judgments.
Python rejects absent, mismatched, ambiguous, or wrongly attributed quote
binding before any claim can become canonical source proof. The P8 quote binder
accepts one contiguous exact quote copied from one ordered paragraph.

## Schema Authority

Durable source proof is relational. `spans` stores exact source coordinates,
`quote_text_hash`, and a location-aware `evidence_fingerprint`:

```text
sha256(filing_id + char_start + char_end + quote_text_hash)
```

Canonical proof uses link rows:

```text
claim_evidence(claim_id, evidence_id, ordinal)
row_evidence(row_table, row_id, evidence_id, ordinal)
```

Extraction-stage truth is claims, not canonical rows. The required extraction
tables are:

```text
evidence_regions
coverage_obligations
coverage_results
claims
claim_coverage_links
actor_claims
event_claims
bid_claims
participation_count_claims
actor_relation_claims
claim_evidence
claim_dispositions
```

`coverage_results` remains an extraction table, but it is Python-owned. It is
never part of the provider response.

`claim_coverage_links` persists the validated claim-to-obligation edge that
proves `coverage_results.result = 'claims_emitted'`; the stored claim count must
agree with current links for the same obligation and run.

`coverage_obligations` carries the Python-owned applicability audit:
`applicability` is one of `applicable` or `not_applicable`,
`applicability_reason_code` is a deterministic short identifier such as
`universal_sale_process`, `positive_source_support`, `source_support_absent`,
`topic_only_or_ambiguous`, `negated_or_unrelated_source_support`,
`process_scope:<scope>`, or `process_scope_mismatch`, and
`applicability_basis_json` is a JSON list of trigger phrases or scope
values that drove the decision. Validation only requires a current
`coverage_result` for current obligations whose
`applicability = 'applicable'`. Inapplicable obligations are recorded for
audit, never sent to Linkflow, and never become `missed`.

Every claim must have exactly one current disposition:

```text
canonicalized
merged_duplicate
rejected
queued_ambiguity
out_of_scope
```

Every current applicable coverage obligation must have exactly one current result:

```text
claims_emitted
no_supported_claim
ambiguous
missed
```

Python assigns `missed` when the applicable request window contains source
support but Linkflow fails to account for an obligation. Python assigns
`no_supported_claim` when the applicable window is relevant but contains no
source support for the obligation, and `ambiguous` when Python cannot safely
classify support after region and applicability review. `claims_emitted` is
assigned only when a validated claim explicitly names that specific same-type
obligation id. A broad claim-type match is not coverage proof. Python alone
writes coverage results after P8 quote binding and claim-to-obligation
validation.

## Actor Relation Enum And Directions

The final relation enum is exactly:

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

Relation directions:

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

Formal/informal, dropout mode, initiation side, proposal scope, and
strategic/financial labels are Python-owned judgments derived from
source-backed claims. Linkflow must preserve source indicators in ordinary
quote-backed claims instead of emitting scalar provider fields for those
judgments.

## Canonical Graph

The canonical graph stays generic:

```text
deals
filings
process_cycles
actors
actor_relations
events
event_actor_links
participation_counts
judgments
```

Buyer groups, merger subs, financing, support agreements, rollover facts,
advisors, committees, and cohort counts are represented through these generic
tables. No deal-specific tables or fields are allowed.

Canonical rows do not own source proof directly. They must be linked through
`row_evidence`.

## Projection

Bidder rows are deterministic exports from canonical facts. Projection
membership is actor-cycle scoped:

```text
projection_units(projection_name, cycle_id, actor_id)
projection_judgments(projection_unit_id, rule_id, included)
bidder_rows(projection_unit_id, ...)
```

A bidder row means actor X in cycle Y under projection P. Actor-level
eligibility alone is not enough.

## Run Kernel

The run kernel owns:

- explicit run id validation;
- deterministic run clock;
- run lock;
- atomic artifact writes;
- progress ledger;
- stage artifact ledger;
- conservative explicit resume;
- manifest configuration hash.

Pipeline stages must not create implicit proof run ids. Pipeline-generated
timestamps come from the run clock.

## Validation And Verdicts

Validation checks source truth, claim disposition completeness, coverage result
completeness, relational source proof, evidence fingerprints, projection unit
traceability, and stage artifact digest integrity.
Current applicable required or important obligations whose coverage result is
`missed`, `no_supported_claim`, or `ambiguous` are hard validation failures;
they may not be treated as complete merely because a coverage row exists.

Verdicts:

- `SOUND`: live Linkflow semantic extraction ran, coverage is sufficient,
  dispositions are complete, canonical rows are source-backed, and projection
  rows trace to actor-cycle facts.
- `SUSPECT`: structurally valid but thin, incomplete, or rules-only.
- `BLOCKED`: source, provider, schema, or artifact failure blocks meaningful
  extraction.
- `UNSOUND`: output is misleading or unsupported.

Rules-only runs may never produce `SOUND`.
