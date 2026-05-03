# sec_graph Specification

**Status:** Approved hard-reset contract, 2026-05-03.
**Execution authority:** `docs/superpowers/specs/2026-05-03-pipeline-hard-reset-design.md`.

This repository implements a source-backed SEC merger-filing extraction
pipeline. The active architecture is:

```text
SEC filing
-> run kernel
-> ingest exact text and paragraph spans
-> evidence map
-> Linkflow GPT-5.5 typed semantic claims
-> Python quote validation
-> claim disposition ledger
-> canonical graph
-> semantic validation
-> actor-cycle projection
-> proof and cost/runtime artifacts
```

The May 3 design is a breaking reset. There are no fallbacks, no backward
compatibility paths, and no legacy payload readers.

## Evidence Map And Live LLM Scope

The evidence map routes production Linkflow extraction to one coherent
`Background of the Merger` / sale-process section region per filing. That
region preserves source paragraph order and carries calibrated coverage
obligations for supported sale-process claims.

Single-paragraph request surfaces and bounded snippets are not production LLM
extraction scope. Whole filing extraction is also not production mode and
must not be used as a fallback. Python owns source coordinates: Linkflow returns
typed claims with exact quote text and explicit `coverage_obligation_ids`; Python
rejects absent, mismatched, ambiguous, or wrongly attributed quote binding before
any claim can become canonical source proof. The V0 binder accepts contiguous
quote text copied from one ordered paragraph.

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
actor_claims
event_claims
bid_claims
participation_count_claims
actor_relation_claims
claim_evidence
claim_dispositions
```

Every claim must have exactly one current disposition:

```text
canonicalized
merged_duplicate
rejected
queued_ambiguity
out_of_scope
```

Every current coverage obligation must have exactly one current result:

```text
claims_emitted
no_supported_claim
ambiguous
missed
```

Python assigns `missed` when Linkflow fails to account for an obligation.
`claims_emitted` is assigned only when a validated claim explicitly names that
specific obligation id. A broad claim-type match is not coverage proof.

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

Verdicts:

- `SOUND`: live Linkflow semantic extraction ran, coverage is sufficient,
  dispositions are complete, canonical rows are source-backed, and projection
  rows trace to actor-cycle facts.
- `SUSPECT`: structurally valid but thin, incomplete, or rules-only.
- `BLOCKED`: source, provider, schema, or artifact failure blocks meaningful
  extraction.
- `UNSOUND`: output is misleading or unsupported.

Rules-only runs may never produce `SOUND`.
