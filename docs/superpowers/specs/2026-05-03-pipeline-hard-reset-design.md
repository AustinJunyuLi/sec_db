# sec_graph Pipeline Hard Reset Design

**Date:** 2026-05-03
**Status:** Approved design for implementation-plan handoff.
**Scope:** Full replacement authority for the live extraction pipeline.
**Repository:** `/Users/austinli/Projects/sec_graph`

## 1. Objective

Replace the current small-window, flat-candidate pipeline with a single
coordinated evidence machine:

```text
SEC filing
-> exact text ingest and paragraph spans
-> Python evidence map
-> Linkflow GPT-5.5 typed semantic claims
-> Python quote validation
-> claim disposition ledger
-> canonical graph
-> semantic validation
-> bidder-cycle projection
-> proof artifacts
-> corpus manifest/shard skeleton
```

The new authority is a hard reset. It does not preserve old LLM payload shapes,
old candidate semantics, array-backed evidence links, actor-global projection
eligibility, or green-but-thin proof behavior.

The core split is:

```text
Python scans for coverage.
GPT proposes meaning.
Python proves or rejects.
DuckDB stores the auditable graph.
```

## 2. Non-Negotiables

- No fallbacks.
- No backward compatibility.
- No hidden legacy payload readers.
- No provider-owned source offsets.
- No canonical rows written by the model.
- No cross-deal context in a model request.
- No secrets in code, docs, artifacts, logs, or command output.
- No rules-only run can produce a `SOUND` proof verdict.
- No canonical or projection row may exist without explainable source evidence.
- No claim may disappear silently; every claim gets a current disposition.
- No many-process concurrent writes to the same DuckDB file.

## 3. Current Pipeline Failures This Replaces

The current live path is disciplined about provider isolation and local quote
resolution, but it is still built around the wrong extraction shape:

- LLM windows are fixed three-paragraph chunks.
- The default core plan can return only `Background of the Merger` rows and
  miss financing, support, rollover, or transaction-structure evidence.
- The LLM schema permits only flat actor/date/bid/count candidates and excludes
  direct relation claims.
- Candidate evidence is stored as arrays, making evidence links harder to
  enforce relationally.
- Candidate rejection and ambiguity are not consistently represented as a
  first-class disposition ledger.
- Projection eligibility is actor-global instead of actor-cycle scoped.
- Proof can look valid while live extraction is thin, incomplete, or
  zero-candidate.

This design replaces those surfaces rather than patching around them.

## 4. Target Architecture

The pipeline has eight conceptual stages.

### 4.1 Ingest

Ingest preserves exact filing text, paragraph order, filing metadata, and
source spans. Python remains the only owner of source coordinates.

Ingest writes:

- filings;
- paragraphs;
- paragraph-level source spans;
- run metadata.

### 4.2 Evidence Map

Python performs a high-recall scan over the filing. This scan is not canonical
truth. It identifies regions that should be inspected by the model.

The evidence map records:

- region id;
- paragraph range;
- region kind;
- trigger phrases or mechanical signals;
- expected claim types;
- priority;
- source paragraph references.

Region kinds include:

- sale process narrative;
- bid/proposal sequence;
- contacted/NDA/IOI/final-round counts;
- buyer group and transaction structure;
- parent, merger sub, and acquisition vehicle structure;
- financing;
- support agreement;
- rollover;
- advisor or committee;
- go-shop or amendment;
- ambiguous or unclassified sale-process material.

Python may produce simple mechanical claims for exact dates, dollar amounts,
and counts, but only as structured claims that go through the same disposition
ledger as model claims. Python does not use these scans to silently fill
semantic gaps around GPT.

### 4.3 Semantic Windows

Semantic windows are built from the evidence map, not from a fixed stride.

Windows are large enough to preserve deal narrative context and small enough
for Linkflow to complete under the strict provider contract. Each window is
inside one filing and one deal only.

Typical windows:

- sale process arc;
- bid sequence;
- transaction structure;
- financing/support/rollover;
- go-shop/amendment material when present.

If Linkflow cannot support one large mixed-claim schema, the pipeline may use
explicit request modes by claim family. Those modes are fixed at launch and
documented in the run manifest. They are not fallback behavior.

### 4.4 Linkflow GPT-5.5 Typed Claims

Linkflow remains the primary live provider. Official OpenAI GPT-5.5 capacity
and Responses API features inform the design, but the implementation target is
Linkflow's actual strict-contract behavior.

Each model request includes:

- window text;
- paragraph ids;
- evidence-map obligations;
- allowed claim schema;
- coverage requirements;
- schema version;
- extract version.

The model returns:

- typed claims;
- coverage results;
- provider metadata needed for sanitized proof artifacts.

Typed claim families:

- actor claim;
- event claim;
- bid claim;
- participation count claim;
- actor relation claim.

Every claim includes exact `quote_text`. The model never returns
`char_start`, `char_end`, canonical ids, projection rows, or provider-specific
canonical fields.

Actor relation claims are first-class. They cover:

- member of;
- affiliate of;
- controls;
- acquisition vehicle of;
- advises;
- finances;
- supports;
- rollover holder of.

### 4.5 Quote Validation and Claim Insertion

Python validates every claim before insertion:

1. The provider response completed under the strict Linkflow contract.
2. The claim payload validates against the local Pydantic model.
3. `quote_text` appears exactly once in the assembled window.
4. The quote resolves back to one or more source spans.
5. The claim uses only closed enums.
6. The claim's source quote is sufficient for local review.

Absent or ambiguous quotes are rejected. They are not salvaged into canonical
rows.

### 4.6 Claim Disposition

Every claim must have exactly one current disposition:

- `canonicalized`;
- `merged_duplicate`;
- `rejected`;
- `queued_ambiguity`;
- `out_of_scope`.

Disposition rows record:

- claim id;
- disposition;
- reason code;
- human-readable reason;
- canonical table and canonical id when applicable;
- surviving claim or canonical id for merges;
- created stage;
- run id.

This ledger is the core anti-underextraction and anti-silent-loss mechanism.
It must be possible to answer: "What happened to every source-backed claim?"

### 4.7 Canonical Graph

Canonical rows are written only after disposition. The canonical graph remains
compact and generic:

- deals;
- filings;
- process cycles;
- actors;
- actor relations;
- events;
- event-actor links;
- participation counts;
- judgments.

No PetSmart-only or deal-specific tables are allowed. Buyer groups, merger
subs, financing, support agreements, rollover facts, advisors, and committees
must be represented through the generic graph.

### 4.8 Projection and Proof

Projection is generated from canonical graph rows and actor-cycle projection
units. A bidder row means:

```text
actor X in cycle Y under projection P
```

Projection eligibility is not actor-global. It is actor-cycle scoped.

Proof artifacts summarize:

- evidence-map regions;
- Linkflow windows;
- coverage obligations;
- coverage results;
- claim counts by type;
- claim dispositions;
- canonical row counts;
- validation failures;
- projection rows;
- live provider status;
- zero-claim or thin-claim warnings;
- final verdict.

## 5. Schema Reset

The schema reset is full and breaking.

### 5.1 Evidence Links

Replace array-backed evidence ownership with relational link tables.

Required link surfaces:

```text
claim_evidence(claim_id, evidence_id, ordinal)
row_evidence(row_table, row_id, evidence_id, ordinal)
```

Where specialized link tables make queries clearer, they are allowed, but the
design must avoid parallel duplicate truth. Evidence links must be enforceable
and queryable as rows.

### 5.2 Claims

Claims are the extraction-stage truth surface before reconciliation. They are
not canonical rows.

Required tables:

```text
claims
actor_claims
event_claims
bid_claims
participation_count_claims
actor_relation_claims
claim_evidence
claim_dispositions
```

`claims` stores common fields:

- claim id;
- run id;
- filing id;
- deal slug;
- provider/source stage;
- claim type;
- confidence;
- raw value;
- normalized value when applicable;
- status.

Type-specific tables store closed typed fields.

### 5.3 Evidence Map and Coverage

Required tables:

```text
evidence_regions
coverage_obligations
coverage_results
```

Each obligation must have one current coverage result:

- `claims_emitted`;
- `no_supported_claim`;
- `ambiguous`;
- `missed`.

The `missed` result is assigned by Python when GPT fails to account for an
obligation. A run with important missed obligations cannot be `SOUND`.

### 5.4 Canonical Graph

Canonical graph tables keep the generic shape:

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

Canonical tables do not store `evidence_ids` arrays as the authoritative
evidence link. They use `row_evidence`.

### 5.5 Projection

Required projection surfaces:

```text
projection_units
projection_judgments
bidder_rows
```

`projection_units` keys actor-cycle-projection membership.

`projection_judgments` applies named projection rules to a projection unit.

`bidder_rows` are deterministic exports, not source truth.

## 6. Rules and Offline Mode

Rules-only/offline mode remains for local development and unit tests.

It may:

- ingest filings;
- build evidence maps;
- produce mechanical date/dollar/count claims;
- run schema and validation tests;
- exercise reconcile code on fixtures.

It may not:

- claim live semantic extraction success;
- produce a `SOUND` proof verdict;
- silently stand in for Linkflow semantic claims.

If no live Linkflow semantic claims ran, proof must be `SUSPECT` or `BLOCKED`.

## 7. Validation

Validation must prove source meaning, not only source presence.

Validation checks:

- every claim has a current disposition;
- every coverage obligation has a current coverage result;
- every canonical row has relational source evidence;
- every source span resolves to exact filing text;
- actor relation evidence supports subject, object, and relation type;
- bid evidence contains bidder/date/context, not only a dollar number;
- participation count evidence contains stage, actor class, count, and context;
- event-actor links are supported by the event and actor evidence;
- projection rows trace to actor-cycle facts and projection judgments;
- rules-only runs cannot be marked `SOUND`;
- zero-claim or thin-claim live windows downgrade proof.

## 8. Proof Verdicts

Verdicts:

- `SOUND`: live Linkflow semantic extraction ran, coverage is sufficient,
  dispositions are complete, canonical rows are source-backed, and projection
  rows trace to canonical facts.
- `SUSPECT`: output is structurally valid but thin, incomplete, rules-only, or
  has important missed obligations.
- `BLOCKED`: source, provider, schema, or required artifact failure prevents
  meaningful extraction.
- `UNSOUND`: output is wrong or misleading, such as unsupported relations,
  par-value-as-bid rows, projection rows without canonical support, or quote
  evidence that does not prove the row meaning.

Green validation alone is not success.

## 9. Acceptance Gate

The implementation acceptance gate is:

1. Three live acceptance deals run through the new pipeline:
   - `petsmart-inc`;
   - `mac-gray`;
   - `providence-worcester`.
2. Each deal produces meaningful source-backed:
   - actors;
   - actor relations;
   - events;
   - event-actor links;
   - participation counts where present;
   - bidder-cycle projection rows;
   - claim dispositions;
   - coverage results.
3. Proof artifacts explain remaining limitations.
4. Rules-only proof is not accepted as `SOUND`.
5. Offline tests pass with the repository's cache-free pytest command.
6. The corpus skeleton exists, but a full 30-deal or 400-deal run is not
   required for this gate.

## 10. Corpus Skeleton

The hard reset must include a corpus runner skeleton for future 400-800 deal
extraction. It does not need to run the full corpus during this acceptance
gate.

Required artifacts:

```text
corpus_manifest.jsonl
shard_plan.jsonl
attempt_ledger.jsonl
failure_ledger.jsonl
cost_runtime_summary.csv
aggregate_proof_summary.json
```

The safe scale shape is:

```text
parallel Linkflow calls write sanitized artifacts
single writer imports claims into DuckDB
single reconcile/validate/project pass writes canonical snapshot
```

No many-process writer pattern is allowed for the same DuckDB file.

## 11. Linkflow Artifacts and Secret Hygiene

Sanitized Linkflow artifacts may contain:

- run id;
- request id;
- deal slug;
- window id;
- provider name;
- model;
- reasoning effort;
- finish status;
- attempt count;
- latency;
- token usage if available;
- response digest;
- claim count;
- inserted claim count;
- sanitized error type and HTTP status.

Artifacts must not contain:

- API keys;
- authorization headers;
- raw provider bodies;
- raw full window text;
- paragraph text;
- quote text;
- secrets from environment variables.

## 12. Stop Conditions

The execution agent must stop and report if:

- a required source filing is missing or corrupt;
- Linkflow repeatedly fails the strict provider contract;
- Linkflow cannot support the declared claim schema or request modes;
- a required acceptance fact cannot be represented by the generic graph;
- semantic validation proves the output is misleading;
- secret material appears in any tracked or generated artifact.

The agent must not stop merely because tests fail during the implementation.
Those are ordinary repair work.

## 13. Out of Scope

The hard reset does not require:

- a reviewer UI;
- a full 30-deal pilot;
- a full 400-800 deal corpus run;
- Postgres migration;
- SQLite migration;
- direct OpenAI provider implementation;
- cross-deal model context;
- external enrichment datasets.

Provider-explicit direct OpenAI support can be designed later if Linkflow
blocks required GPT-5.5 behavior.

## 14. Handoff Summary for `/goal`

The implementation objective is to replace the current `sec_graph` extraction
pipeline with the hard-reset architecture in this document. The execution
agent should treat this as the new full-pipeline authority: no fallbacks, no
backward compatibility, no preservation of old LLM payloads, no array-backed
evidence authority, no actor-global projection eligibility, and no green-but-
thin proof.

The first successful proof is a meaningful live Linkflow GPT-5.5 run over the
three acceptance deals plus a corpus skeleton ready for future 400-800 deal
sharding.
