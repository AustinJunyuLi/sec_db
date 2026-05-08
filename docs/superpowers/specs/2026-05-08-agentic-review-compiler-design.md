---
title: Agentic SEC filing review compiler - clean-slate design
status: DRAFT
date: 2026-05-08
companion_spec: docs/superpowers/specs/2026-05-08-linkflow-api-probe-spec.md
---

# Agentic SEC filing review compiler - clean-slate design

## 1. Authority

This document is the starting authority for a new SEC merger-filing extraction
repository. It is not a patch plan. The implementation must derive code,
schema, table names, prompts, tests, artifact formats, branch conventions, and
pipeline stages from this document and from live evidence gathered during the
build.

The only companion authority is:

- `docs/superpowers/specs/2026-05-08-linkflow-api-probe-spec.md`

The execution handoff is:

- `docs/superpowers/plans/2026-05-08-agentic-review-compiler-ralph-implementation.md`
- `ralph/prd.json`

An implementation agent should treat every other file, if present, as
out-of-scope unless the user explicitly reintroduces it. The implementation
target is a new system whose behavior is derived from this spec, from raw SEC
filings, and from live Linkflow capability probes.

## 2. Objective

Build a rigorous, filing-grounded extraction and review compiler for SEC merger
filings. The system should make hand review easier by producing source-backed
claim dossiers, verifier judgments, conflict reports, coverage gaps, and a
deterministic canonical graph.

The design is intentionally agentic, but agents do not own truth. Agents propose
and challenge claims. Deterministic Python code owns evidence binding, state
transitions, source coordinates, persistence, canonical compilation, and
publication.

## 3. Non-negotiables

- Filing text is the only source of factual truth.
- All LLM calls go through Linkflow direct SDK calls.
- Linkflow capability assumptions must be proven before extraction agents are
implemented.
- No external extraction pipeline is a dependency.
- No answer-key or baseline-comparison tool is visible to extractors or
verifiers.
- No fallback extraction mode, no legacy reader, no silent downgrade, and no
compatibility shim.
- No model-owned source offsets, canonical ids, actor ids, graph ids, or final
review statuses.
- No canonical row can exist without exact source evidence.
- No proposed claim can enter canonical until it has been uniquely quote-bound,
independently verified, and checked for cross-claim consistency.
- No verifier can directly mutate an accepted claim. Corrections create new
claim attempts and go through the same binding and verification process.
- No "latest verdict wins" rule. Conflicting verdicts are resolved by an
explicit aggregation policy or escalated.
- No hidden LLM inside a deterministic tool. If a model is used, it is an
audited agent step.
- No partial deal output is marked trusted when required filing regions failed
to load, index, inspect, or verify.
- Secrets are environment-only and never written to committed files or raw
artifacts.
- The no-fallback, no-backward-compatibility, no-overengineering, no-overfit,
  no-patchlike-behavior, always-first-principle doctrine is binding.

The doctrine means:

- build from the current filing evidence, current specs, and current Linkflow
  probe results, not from historical pipeline shape;
- reject compatibility bridges, legacy aliases, fallback readers, silent
  downgrade paths, and temporary shim layers;
- implement the smallest complete mechanism that satisfies a verified
  requirement, with tests and audit artifacts;
- do not hard-code behavior to one fixture, one deal, one provider accident, or
  one expected answer;
- when a requirement is unclear, fail loudly or surface a review-visible gap
  instead of patching around it.

## 4. Success definition

The system succeeds when a reviewer can inspect a deal dossier and answer:

1. What facts did the system believe?
2. Where exactly did each fact come from in the filing?
3. Which agent proposed it?
4. Which verifier challenged it?
5. What conflicts, corrections, ambiguities, or omissions remain?
6. Which accepted claim cards compiled into each canonical row?
7. Which rows require human attention before research use?

The first goal is not speed. The first goal is reviewable accuracy.

## 5. Conceptual pipeline

```text
SEC filing package
-> deterministic filing package builder
-> filing atlas
-> local retrieval index
-> per-deal orchestrator
-> scout agent
-> specialist extractor agents
-> omission inspector
-> deterministic evidence binder
-> independent verifier
-> verdict aggregation
-> consistency checker
-> human-review dossier
-> deterministic canonical compiler
-> exported graph and review tables
```

The pipeline is per deal. A corpus run dispatches many independent deal runs,
but no deal can contaminate another deal's state.

## 6. Filing package

A filing package is the immutable input unit for one deal. It contains:

- filing metadata;
- raw SEC HTML or text;
- selected exhibits;
- normalized text;
- paragraph records;
- table records when extractable;
- byte or character coordinates for every source span;
- source hashes for raw and normalized material.

Tender-offer filings must include the substantive offer-to-purchase exhibit
when that exhibit exists in the filing package. If the package builder cannot
identify the substantive offer document, the deal is not processable. The system
must fail loudly rather than using a cover document as a substitute.

## 7. Filing atlas

The atlas is a deterministic map of the filing package. It is not truth about
deal facts; it is an indexable map of source material.

Required atlas records:

- `filings`
- `exhibits`
- `sections`
- `paragraphs`
- `tables`
- `source_spans`
- `section_candidates`
- `atlas_warnings`

Atlas construction may mark a section label as ambiguous, but it must not skip
the section silently. Any unavailable, ambiguous, or failed section becomes a
review-visible source-coverage issue.

Minimum span identity:

```text
evidence_id = sha256(filing_id + char_start + char_end + quote_text_hash)
```

Text-only quote hashes are not evidence identity.

## 8. Retrieval index

The retrieval index is local to a filing package. It supports agents and
verifiers, but it does not decide truth.

Required retrieval modes:

- literal text lookup;
- exact quote lookup;
- regex lookup;
- BM25 keyword search;
- paragraph-neighborhood fetch;
- section fetch;
- optional embeddings if the Linkflow probe and local dependencies support
  them reliably.

Every retrieval result must include stable source ids, paragraph ids, character
coordinates where applicable, and enough surrounding context for a verifier to
inspect the source. Retrieval failures are logged and surfaced; they are not
silently treated as absence of evidence.

## 9. Deal-room store

Each run creates a per-deal deal room:

```text
runs/<run_id>/<deal_slug>/
  deal_room.duckdb
  filing_package_manifest.json
  atlas.json
  retrieval_manifest.json
  agent_messages.jsonl
  tool_calls.jsonl
  provider_calls.jsonl
  exports/
    claim_cards.csv
    review_queue.csv
    canonical_rows.csv
    human_decisions_template.csv
```

`deal_room.duckdb` is the queryable authority for that deal's state. JSONL logs
are audit artifacts, not the source of truth for compilation.

The database must be append-oriented. Re-running an agent appends attempts. It
does not overwrite earlier attempts.

## 10. Core data model

### 10.1 Source records

Source tables define what was available to the system:

- `filings`
- `exhibits`
- `sections`
- `paragraphs`
- `tables`
- `source_spans`

All source records are immutable after package creation.

### 10.2 Claim attempts

A claim attempt is one agent's proposed fact.

Required fields:

- `attempt_id`: unique run-local id;
- `claim_fingerprint`: deterministic semantic fingerprint;
- `deal_slug`;
- `claim_type`;
- `payload_json`;
- `origin_agent_role`;
- `origin_agent_run_id`;
- `model`;
- `prompt_hash`;
- `created_sequence`;
- `created_at_run_clock`;
- `status`.

`attempt_id` is not the same as `claim_fingerprint`. Two agents may propose the
same claim, or one agent may re-propose a corrected claim. Those are separate
attempts that can share a fingerprint.

### 10.3 Evidence bindings

An evidence binding connects a claim attempt to exact source text.

Required fields:

- `binding_id`;
- `attempt_id`;
- `evidence_id`;
- `filing_id`;
- `paragraph_id`;
- `char_start`;
- `char_end`;
- `quote_text`;
- `quote_text_hash`;
- `binding_status`;
- `binding_error_code`;
- `tool_version`;

A binding is accepted only when the quote resolves uniquely to source text.
Absent, ambiguous, approximate, or model-supplied coordinates are rejected.

### 10.4 Normalized values

Normalization is deterministic Python output:

- dates;
- money values;
- counts;
- actor labels;
- actor aliases;
- filing-local actor ids.

Normalization can return `unknown`, `ambiguous`, or `unparseable`. Those states
are review-visible. They are not repaired by hidden model guesses.

### 10.5 Verifier verdicts

A verifier verdict is an independent judgment on one bound claim attempt.

Allowed verdicts:

- `confirm`: the cited evidence supports the claim as written.
- `partial`: the evidence supports a nearby fact, but one or more fields are
  wrong or underspecified.
- `reject`: the evidence does not support the claim.
- `ambiguous`: the filing evidence is insufficient or genuinely unclear.
- `malformed`: the verifier response failed schema or citation requirements.

Required fields:

- `verdict_id`;
- `attempt_id`;
- `verifier_agent_run_id`;
- `model`;
- `prompt_hash`;
- `verdict`;
- `reasoning_summary`;
- `supporting_evidence_ids`;
- `proposed_correction_json`;
- `confidence`;
- `created_at_run_clock`.

A `partial` verdict never edits the original attempt in place. If the proposed
correction is parseable, the orchestrator creates a new corrected claim attempt
linked to the original. The corrected attempt must be evidence-bound and
verified before it can be accepted.

### 10.6 Verdict aggregation

Claim status is derived by policy, not by recency.

Default aggregation policy:

- one valid `confirm` and no blocking conflict -> eligible for consistency;
- any valid `reject` against an otherwise confirmed claim -> escalate unless a
  second independent verifier resolves the disagreement;
- any `partial` -> create corrected attempt or escalate;
- any `ambiguous` without a confirming independent verifier -> escalate;
- repeated `malformed` verifier output -> system failure for the verifier stage.

The aggregation policy is versioned and logged in the run manifest.

### 10.7 Coverage ledger

Coverage is a first-class table, not just a review note.

Each expected fact category for a deal has one or more coverage checks:

- `checked_found`: source support exists and at least one claim attempt covers
  it;
- `checked_absent`: the filing appears not to contain that fact;
- `ambiguous`: source text is unclear;
- `not_applicable`: the category does not apply to this deal shape;
- `failed_to_check`: the system did not inspect enough source material to make
  a judgment.

`failed_to_check` blocks trusted canonical publication. `ambiguous` and
`checked_absent` are review-visible and may still allow a trusted graph if all
accepted canonical rows remain source-backed.

### 10.8 Conflicts

Conflicts are explicit records:

- contradictory dates;
- incompatible bid values;
- inconsistent actor identities;
- mutually exclusive process stages;
- duplicate claims with incompatible payloads;
- canonical graph invariant violations.

No blocking conflict can be resolved by hiding a claim. The system must reject,
supersede, or escalate the involved attempts with a logged reason.

### 10.9 Human decisions

Human review is represented as imported data, even if the review UI is external.

The system exports `human_decisions_template.csv`. A reviewer can return a file
with:

- `attempt_id`;
- `decision`: `accept`, `reject`, `correct`, `defer`;
- `correction_json`;
- `reviewer`;
- `reviewed_at`;
- `notes`.

Human corrections create new corrected attempts unless the correction is only a
review note. The original attempt remains immutable.

## 11. Agent roles

### 11.1 Scout

The scout maps where important deal facts are likely to live. It outputs a
region map and search plan. It does not output canonical facts.

### 11.2 Party and relation extractor

Extracts actors and relationships:

- target;
- acquirer;
- merger subsidiaries;
- consortium members;
- advisors;
- financing sources;
- support parties;
- committee members;
- recused persons.

### 11.3 Timeline and bid extractor

Extracts process events and bid facts:

- initial contact;
- NDA;
- indication of interest;
- preliminary proposal;
- revised proposal;
- final bid;
- exclusivity;
- go-shop;
- agreement execution;
- amendment;
- withdrawal or exclusion.

### 11.4 Count and coverage extractor

Extracts participation counts and process breadth:

- contacted parties;
- NDA parties;
- IOI parties;
- first-round parties;
- final-round parties;
- strategic, financial, mixed, or unknown composition where source-backed.

### 11.5 Omission inspector

Checks a deal-shape skeleton against the atlas and claim attempts. It must
produce coverage ledger records, not free-form speculation.

### 11.6 Evidence binder

Deterministic Python only. It validates exact quote existence, source span
identity, parser output, and local actor references.

### 11.7 Verifier

An independent Linkflow agent. It sees:

- one bound claim attempt;
- its cited evidence;
- neighboring source context;
- schema rules;
- verifier instructions.

It does not see extractor reasoning, agent chat history, baseline answers, or
external pipeline output.

### 11.8 Consistency checker

Mostly deterministic Python. If an LLM is needed for a genuinely semantic
cross-claim judgment, it is invoked as a named audited checker agent and its
output is stored as a verdict-like record. It is not hidden inside a helper.

### 11.9 Canonical compiler

Deterministic Python only. It reads accepted attempts, evidence bindings,
coverage records, conflicts, and human decisions. It writes canonical graph
tables and row-evidence links.

## 12. Tool layer

Agents may call only orchestrator-exposed tools. Tools are versioned and logged.

Required read tools:

- `search_filing(query, mode, k)`;
- `get_section(section_id)`;
- `get_paragraph(paragraph_id)`;
- `get_neighborhood(paragraph_id, before, after)`;
- `get_table(table_id)`;
- `verify_quote(filing_id, quote_text)`;
- `parse_date(text, context)`;
- `parse_money(text, context)`;
- `parse_count(text, context)`;
- `normalize_actor_label(label, context)`;
- `list_claim_attempts(filter)`;
- `list_coverage_checks(filter)`;
- `list_conflicts(filter)`.

Agents do not get direct write tools. They return structured proposals to the
orchestrator. The orchestrator validates and commits.

Forbidden tools:

- comparison to another extraction system;
- answer-key lookup;
- internet search during extraction unless the user explicitly expands scope;
- source text mutation;
- direct DuckDB writes from agents;
- direct filesystem writes from agents.

## 13. Orchestrator

The orchestrator owns:

- run id creation;
- run clock;
- deal-room creation;
- Linkflow call dispatch;
- tool execution;
- tool-call caps;
- timeout handling;
- retries;
- database writes;
- state transitions;
- canonical compilation;
- export publication.

Default concurrency:

- multiple deals may run in parallel only when each deal has an isolated deal
  room;
- within a deal, specialist extractors may run in parallel;
- DuckDB writes for one deal are sequential through the orchestrator;
- publication is atomic.

## 14. Linkflow boundary

The system uses Linkflow direct SDK calls for every model call. The implementation
must not assume tool calling, structured outputs, streaming, stateful response
ids, model names, or concurrency behavior until the companion Linkflow probe has
produced evidence.

The agentic compiler cannot start beyond deterministic scaffolding until these
Linkflow capabilities are proven or the architecture is revised:

- strict structured output for claim attempts and verdicts;
- single tool call;
- multi-turn tool loop;
- final structured output after tool use;
- provider-safe schema subset;
- bounded concurrency behavior;
- retryable failure taxonomy.

## 15. Failure semantics

System failures block trusted output:

- missing filing package;
- substantive exhibit selection failure;
- atlas construction failure for required source regions;
- retrieval index build failure;
- Linkflow provider contract failure;
- repeated malformed verifier output;
- failed evidence binding for claims that would otherwise enter canonical;
- `failed_to_check` coverage on required source regions;
- canonical graph invariant failure;
- non-atomic or incomplete publication.

Review burden does not block trusted source-backed rows:

- filing is genuinely ambiguous;
- a fact category appears absent after successful inspection;
- a claim is rejected and quarantined;
- a non-blocking conflict is surfaced;
- optional coverage is incomplete but marked.

The run status vocabulary should be derived during implementation from these
semantics. Do not import status names from prior systems without rejustifying
them.

## 16. Canonical graph principles

The canonical graph is a deterministic projection, not a model output.

Required principles:

- canonical rows are typed and validated;
- closed enums are preferred, but enum values are chosen from raw filing needs;
- row ids are deterministic where possible;
- every canonical row has row-evidence links;
- canonical rows never own source proof directly;
- projection rows are downstream views, not authority;
- incomplete review state is visible in exports.

The exact canonical schema is not fixed by this spec. It must be designed from
the claim attempts and review needs discovered in the vertical slice.

Expected entity families:

- deals;
- filings;
- source spans;
- actors;
- actor relations;
- process cycles;
- events;
- bids;
- participation counts;
- judgments;
- canonical row evidence.

## 17. Build order

### Phase 0 - Linkflow capability probe

Implement and run the companion probe spec. Stop if Tier 1 capabilities fail.

### Phase 1 - Repository skeleton

Create a minimal Python package, test harness, run directory policy, and
deal-room database migration system. No extraction agents yet.

### Phase 2 - Filing package and atlas

Build deterministic filing ingestion, exhibit selection, source spans,
paragraphs, sections, and atlas records. Test against a small set of real
filings.

### Phase 3 - Retrieval and deterministic tools

Build local retrieval, quote verification, parsers, and actor-label
normalization. Unit-test every tool with adversarial examples.

### Phase 4 - Claim attempts and evidence binding

Implement claim-attempt tables, evidence bindings, lifecycle transitions, and
append-only invariants. Prove recompile reproducibility.

### Phase 5 - First vertical slice

Run one deal through:

```text
atlas -> scout -> one specialist -> evidence binder -> verifier -> review export
```

Do not add the full agent team until the dossier is reviewable.

### Phase 6 - Verifier calibration

Build a calibration set from raw filing facts and adversarial planted errors.
The initial calibration set must not be generated only from the system's own
outputs.

### Phase 7 - Full agent team

Add remaining specialists, omission inspector, verdict aggregation, consistency
checker, human-decision import, and canonical compiler.

### Phase 8 - Corpus scaling

Run a representative multi-deal batch. Measure accuracy, omissions, runtime,
cost, and stability.

## 18. Acceptance criteria

The implementation is not acceptable until it can demonstrate:

- exact source trace for every accepted canonical row;
- no canonical row from an unbound or rejected claim;
- verifier independence from extractor reasoning;
- partial verifier corrections re-enter as new attempts;
- coverage ledger distinguishes absence, ambiguity, not-applicable, and failure
  to check;
- reproducible canonical compilation from deal-room state;
- human-review CSV export and import path;
- Linkflow probe artifacts attached to the run documentation;
- no dependency on external extraction outputs;
- no stale files from an older pipeline in the active repository.

## 19. Execution governance

Before writing code, an implementation agent must read this spec, the Linkflow
probe spec, the Ralph implementation plan, and `ralph/prd.json`.

Execution is not administered through `/goal`. The intended execution mode is a
Claude-administered Ralph loop:

- Claude is the administrator and review gate.
- Ralph executes one `ralph/prd.json` user story at a time.
- Claude verifies each story against this design, the Ralph plan, tests, secret
  scans, and git status before marking a story complete.
- Claude updates Ralph story notes only after verification evidence exists.
- A story that violates the doctrine in Section 3 is not complete even if tests
  pass.

The implementation remains clean-slate: derive the repo structure, schema,
tests, and runtime behavior from the active specs, the Ralph handoff, and live
evidence gathered during implementation.
