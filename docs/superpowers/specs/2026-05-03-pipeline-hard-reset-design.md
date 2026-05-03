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
-> run kernel initializes a locked, resumable run
-> exact text ingest and paragraph spans
-> Python evidence map
-> Linkflow GPT-5.5 typed semantic claims
-> Python quote validation
-> claim disposition ledger
-> canonical graph
-> semantic validation
-> bidder-cycle projection
-> proof artifacts
-> cost/runtime envelope
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
The run kernel makes the long run deterministic and resumable.
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
- No proof run may invent an implicit run id inside a stage.
- There is exactly one run id factory and one run clock per run.
- Pipeline-generated timestamps come from the run clock, not hardcoded literals
  or scattered wall-clock calls.
- Ordering and sequence allocation come from source coordinates, explicit
  sequence tables, or append-only ledgers; missing text positions are hard
  failures, not sortable values.
- Evidence identity includes filing id, coordinates, and quote text hash.
  A text-only quote hash is not sufficient evidence identity.
- Durable artifacts are written atomically.
- Long corpus runs have per-deal progress, explicit resume semantics, and a
  lock that prevents accidental concurrent writers.

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
- Pipeline-generated judgments have used hardcoded `created_at` values.
- Multiple stage-local run-id helpers can drift and produce inconsistent run
  identity.
- Some ordering paths depend on string search results that can be `-1`.
- Quote hashes are text-only, so common phrases collide across filings and
  locations.
- Artifact writes are not specified as atomic.
- Long runs lack a lock, per-deal progress ledger, and `--resume` contract;
  a killed process late in a corpus run can lose too much work.

This design replaces those surfaces rather than patching around them.

## 4. Target Architecture

The pipeline has nine conceptual stages.

### 4.1 Run Kernel

The run kernel is the operational spine of the hard reset. It is part of the
pipeline, not optional wrapper code.

The run kernel owns:

- run id creation and validation;
- a single run clock;
- run manifest creation;
- run directory locking;
- atomic artifact writes;
- stage and per-deal progress ledgers;
- sequence allocation policy;
- resume validation;
- finalization of proof artifacts.

Proof runs require an explicit run id created by the top-level run command or
corpus runner. Stage-level helpers must not silently create proof run ids.
Developer-only commands may create clearly marked non-proof run ids, but those
runs cannot produce a `SOUND` verdict.

Pipeline-generated `created_at` fields use the run clock, such as
`run_manifest.started_at`, or another deterministic timestamp assigned by the
run kernel. Hardcoded timestamps and scattered `now()` calls are forbidden for
pipeline-generated rows. Human/reviewer actions may use real wall-clock time
when a reviewer workflow is later designed.

Sequence numbers and ordering derive from explicit sequences or validated
source coordinates:

```text
filing_id
paragraph_sequence
char_start
char_end
claim_sequence
stage_sequence
```

No ordering path may sort on a missing string-search position. If a text search
needed for ordering returns "not found", the stage must fail or create an
ambiguity disposition.

Durable artifacts are written by atomic write:

```text
write temporary file
fsync temporary file
rename into place
fsync parent directory when supported
```

The run directory has a lock file. A second process attempting to write the
same run fails loudly unless it is an explicit validated resume.

Per-deal progress is append-only and stage-scoped:

```text
queued
ingested
evidence_mapped
llm_artifacts_written
claims_imported
reconciled
validated
projected
blocked
```

`--resume` is explicit and conservative. It reads the progress ledger, verifies
artifact hashes, refuses changed schema/provider/run configuration unless a new
run is created, and reruns only incomplete or invalid stages. It never
overwrites completed immutable artifacts.

### 4.2 Ingest

Ingest preserves exact filing text, paragraph order, filing metadata, and
source spans. Python remains the only owner of source coordinates.

Ingest writes:

- filings;
- paragraphs;
- paragraph-level source spans;
- run metadata.

### 4.3 Evidence Map

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

### 4.4 Semantic Windows

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

### 4.5 Linkflow GPT-5.5 Typed Claims

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

### 4.6 Quote Validation and Claim Insertion

Python validates every claim before insertion:

1. The provider response completed under the strict Linkflow contract.
2. The claim payload validates against the local Pydantic model.
3. `quote_text` appears exactly once in the assembled window.
4. The quote resolves back to one or more source spans.
5. The claim uses only closed enums.
6. The claim's source quote is sufficient for local review.

Absent or ambiguous quotes are rejected. They are not salvaged into canonical
rows.

### 4.7 Claim Disposition

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

### 4.8 Canonical Graph

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

### 4.9 Projection and Proof

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

Evidence spans keep both a text hash and a location-aware fingerprint:

```text
quote_text_hash = sha256(quote_text)
evidence_fingerprint = sha256(filing_id + char_start + char_end + quote_text_hash)
```

The text hash helps validate the bytes. The fingerprint identifies a specific
piece of evidence in a specific filing at specific coordinates. Canonical proof
uses the fingerprint, not a text-only hash.

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

### 5.6 Run Kernel and Operational Tables

The schema and artifact layout must include run-kernel state. The exact split
between DuckDB tables and JSONL artifacts is an implementation choice, but the
following surfaces are required and must be queryable in proof:

```text
run_manifest
run_lock
progress_ledger
stage_artifacts
resume_report
cost_runtime_records
```

The manifest records:

- run id;
- run type;
- source manifest hash;
- schema version;
- extract/reconcile/validate/project versions;
- provider;
- model;
- reasoning effort;
- request modes;
- started_at from the run clock;
- code identity when available;
- input hashes.

The progress ledger is append-only and keyed by deal, stage, attempt, and run
id. It records state transitions, artifact digests, and failure reasons.

The stage artifact ledger records every durable artifact with:

- artifact path;
- artifact kind;
- owning stage;
- deal slug when applicable;
- digest;
- created_by stage;
- finalized status.

The resume report records what was reused, what was recomputed, and what was
refused.

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
- every source span has a location-aware evidence fingerprint;
- actor relation evidence supports subject, object, and relation type;
- bid evidence contains bidder/date/context, not only a dollar number;
- participation count evidence contains stage, actor class, count, and context;
- event-actor links are supported by the event and actor evidence;
- projection rows trace to actor-cycle facts and projection judgments;
- pipeline-generated timestamps match the run clock policy;
- proof runs use the single top-level run id;
- sequence and ordering fields do not depend on missing text-search positions;
- durable artifacts listed in the stage artifact ledger exist and match their
  recorded digest;
- progress ledger transitions are complete for every deal;
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

## 9. Cost and Runtime Envelope

Cost and runtime are part of proof, not an external spreadsheet.

Every live proof, pilot, and corpus run must report:

- deals planned;
- deals completed;
- deals blocked;
- windows per deal;
- input tokens per window;
- output tokens per window;
- claims per window;
- coverage obligations per deal;
- p50, p95, and max latency per Linkflow call;
- retry counts;
- provider failures;
- quote-validation rejection rate;
- disposition mix;
- estimated cost;
- actual token usage if Linkflow exposes it;
- whether cost numbers are actual, estimated, or mixed.

Pricing is not hardcoded in source. A run may use a versioned pricing config or
write token usage only. If Linkflow does not expose token usage, the run records
estimated tokens and marks cost as estimated.

Required envelope artifacts:

```text
cost_runtime_summary.json
cost_runtime_summary.csv
provider_usage_ledger.jsonl
latency_ledger.jsonl
```

The implementation plan must require envelopes for:

- the three-deal live proof;
- a 9-deal reference-batch estimate;
- a 30-deal pilot estimate;
- a 400-deal projected run;
- an 800-deal projected run.

The 9-deal, 30-deal, 400-deal, and 800-deal envelopes may be projections during
the first acceptance gate. They must be computed from observed three-deal
metrics plus explicit assumptions, not hand-waved prose.

## 10. Acceptance Gate

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
6. The cost/runtime envelope exists for the three-deal proof and projected
   9/30/400/800-deal scales.
7. The run kernel proves atomic artifacts, per-deal progress, and explicit
   resume behavior.
8. The corpus skeleton exists, but a full 30-deal or 400-deal run is not
   required for this gate.

## 11. Corpus Skeleton

The hard reset must include a corpus runner skeleton for future 400-800 deal
extraction. It does not need to run the full corpus during this acceptance
gate.

Required artifacts:

```text
corpus_manifest.jsonl
shard_plan.jsonl
attempt_ledger.jsonl
failure_ledger.jsonl
progress_ledger.jsonl
stage_artifacts.jsonl
cost_runtime_summary.csv
cost_runtime_summary.json
aggregate_proof_summary.json
resume_report.json
```

The safe scale shape is:

```text
parallel Linkflow calls write sanitized artifacts
single writer imports claims into DuckDB
single reconcile/validate/project pass writes canonical snapshot
```

No many-process writer pattern is allowed for the same DuckDB file.

## 12. Linkflow Artifacts and Secret Hygiene

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
- estimated token usage when actual usage is unavailable;
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

## 13. Subagent Development Model

The `/goal` execution must use subagents as a core development method. The
coordinator owns integration, final decisions, and proof, but must not attempt
to hold the entire hard reset in one context.

Subagents should be deployed with explicit ownership boundaries. At minimum,
the execution should create focused lanes for:

- schema reset and relational evidence links;
- run kernel, atomic artifacts, locking, progress, and resume;
- evidence map and semantic window planning;
- Linkflow typed-claim schema and provider contract;
- quote validation, claim insertion, and disposition ledger;
- reconcile/canonical graph construction;
- semantic validation and proof verdicts;
- projection units and bidder-cycle rows;
- corpus skeleton, sharding, and cost/runtime envelope;
- stale-code/stale-doc cleanup and final review.

Subagents may inspect overlapping context, but implementation ownership must
avoid conflicting write scopes. When code changes are delegated, each subagent
must receive:

- owned files or owned subsystem;
- explicit no-fallback/no-compatibility constraints;
- expected tests or proof artifacts;
- instruction not to revert unrelated user or peer edits;
- requirement to report changed paths and remaining risks.

The coordinator must integrate subagent work through the design authority in
this document. If subagent recommendations conflict, the coordinator resolves
the conflict by preserving the hard-reset invariants: source proof,
disposition completeness, deterministic operations, Linkflow strictness, and
corpus-scale survivability.

Subagents are also required for review. Before final handoff, at least one
read-only review lane must inspect:

- schema/provenance correctness;
- live-provider contract and secret hygiene;
- run-kernel resumability and atomicity;
- validation/proof soundness;
- stale surfaces left behind by the hard reset.

The `/goal` prompt should make this subagent model mandatory. A single-agent
implementation attempt is not acceptable for this reset.

## 14. Stop Conditions

The execution agent must stop and report if:

- a required source filing is missing or corrupt;
- Linkflow repeatedly fails the strict provider contract;
- Linkflow cannot support the declared claim schema or request modes;
- a required acceptance fact cannot be represented by the generic graph;
- semantic validation proves the output is misleading;
- run-kernel invariants fail, including lock violations, non-atomic artifact
  writes, inconsistent run ids, invalid resume state, or progress-ledger
  corruption;
- cost/runtime artifacts cannot distinguish actual metrics from estimates;
- secret material appears in any tracked or generated artifact.

The agent must not stop merely because tests fail during the implementation.
Those are ordinary repair work.

## 15. Out of Scope

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

## 16. Handoff Summary for `/goal`

The implementation objective is to replace the current `sec_graph` extraction
pipeline with the hard-reset architecture in this document. The execution
agent should treat this as the new full-pipeline authority: no fallbacks, no
backward compatibility, no preservation of old LLM payloads, no array-backed
evidence authority, no actor-global projection eligibility, no scattered
run-id or timestamp helpers, no text-only evidence identity, no non-atomic
artifacts, no non-resumable corpus run, and no green-but-thin proof.

The first successful proof is a meaningful live Linkflow GPT-5.5 run over the
three acceptance deals plus a deterministic run kernel, cost/runtime envelope,
and corpus skeleton ready for future 400-800 deal sharding.

The `/goal` execution must deploy subagents with explicit subsystem ownership
and review lanes. The coordinator remains responsible for integration and final
proof, but a single-agent implementation attempt does not satisfy this design.
