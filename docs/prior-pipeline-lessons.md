# Lessons From Prior Extraction Work

**Purpose.** This memo transfers useful engineering lessons from the earlier
M&A extraction pipeline into the new `sec_graph` architecture. It is not a
migration guide. The new pipeline should be built from raw filings, canonical
schema contracts, and deterministic module boundaries. The prior pipeline is
useful evidence about failure modes, not a codebase to preserve.

**Audience.** Future agents and humans implementing the modular architecture in
`docs/spec.md`.

## Executive Summary

The prior pipeline eventually learned that row-per-event JSON is a weak primary
representation for merger-process extraction. It can be a useful export shape,
but it is too compressed to be the canonical state. It forces one object to
carry evidence, actor identity, event chronology, bidder lifecycle, process
phase, bids, group membership, and research-facing row completeness all at
once. Small model errors then become large downstream ambiguities.

The new pipeline should keep the approved direction: canonical store first,
estimator rows as deterministic projections. The most important carry-forward
lesson is to separate layers by responsibility:

- `ingest` preserves text and provenance.
- `extract` emits evidence-bound candidates, not final truth.
- `reconcile` makes canonical judgments explicitly.
- `validate` enforces deterministic integrity.
- `project` exports bidder-cycle rows without adding facts.

The prior pipeline made progress by adding deterministic guardrails around a
model emitter. The new pipeline should make those guardrails native from day
one instead of bolting them onto a monolithic JSON extraction loop.

## What The Prior Pipeline Struggled With

### 1. The output row tried to be both extraction and data model

The old shape asked the model to emit one finalized JSON row per auction event.
That made the row both an evidence claim and a canonical research record. This
created recurring friction:

- Actor identity and event identity were tangled. Anonymous bidder handles,
  buyer-group constituents, bidder aliases, and lifecycle rows all had to be
  solved before the row could be valid.
- Process judgments were encoded indirectly through row fields such as
  `process_phase`, `bid_note`, formal-round booleans, and drop classifications.
- Evidence was attached at row level, which made it hard to express that one
  paragraph supported a count, another paragraph supported identities, and a
  third paragraph supported a later membership change.
- Bidder-cycle row completeness affected extraction decisions too early. The
  model had to decide whether to atomize unnamed parties before the system had a
  canonical actor layer or a participation-count layer.

The new canonical model should avoid this compression. `ExtractionCandidate`,
`Actor`, `Event`, `EventActorLink`, `Judgment`, `ParticipationCount`, and
`GroupMembership` should be separate records because the filing supports them
with different evidence and different uncertainty.

### 2. Prompt-only semantics were not durable enough

Many rule changes began as prompt clarifications: bidder-group atomization,
DropSilent, formal-round status fields, same-day final-round pairing, rough
date anchoring, and bid-value nullness on non-bid rows. The same prompt could
work on one reference run and regress under a different model effort or provider
condition.

The pattern was not that prompts were useless. They were useful as model
instructions. The problem was treating prompt compliance as the durable
contract. Durable semantics had to move into deterministic checks, explicit
rule files, or audit-gated workflows.

For `sec_graph`, prompt text should never be the only place where a research
semantic lives. If the semantic affects canonical data, encode it in one of:

- schema constraints;
- reconciliation logic;
- validation checks;
- projection rules;
- reviewer-visible judgments.

### 3. Repair could make output smaller, valid, and wrong

A central failure class was repair collapse: a large initial extraction with
local hard flags could be repaired into a much smaller extraction that satisfied
row-local validation while deleting valid chronology. The pipeline then added
row-conservation checks and filing-derived obligations to prevent this.

The new architecture should avoid creating this failure class. Repairs should
not operate on the whole canonical truth as a single blob. If a future LLM pass
exists, it should propose candidates or localized revisions. Deterministic
reconciliation and validation should decide what changes become canonical. Any
reviewer or repair action should be append-only or diffable against prior
evidence-bound records.

### 4. Count obligations were discovered too late

The old pipeline eventually added deterministic obligations from filing text:
exact counts of NDA signers, bid submissions, final-round participants, buyer
group constituents, and late-member inherited NDA rows. These were valuable
because filings often state aggregate facts before naming or not naming every
party.

The lesson is that counts are first-class evidence, not merely validator
afterthoughts. In the new schema, a count like "15 potentially interested
financial buyers" should be representable even when the individual actors are
anonymous or only partially resolvable. The system should not need to invent 15
actor rows just to remember that the filing asserted a count. Instead, the
canonical store should support `ParticipationCount` and link it to source spans,
cycles, phases, and later reconciliation decisions.

### 5. Buyer groups exposed the weakness of flat rows

Buyer groups caused repeated fixes because the filing can discuss a group as one
party, as several economic constituents, as a later expanded group, and as a
signatory set in transaction documents. A row-per-event schema had to choose
between aggregation and atomization at extraction time.

The new pipeline should model this as structure:

- `Actor` for individuals, firms, groups, and anonymous placeholders.
- `GroupMembership` for membership intervals and evidence.
- `EventActorLink` for each actor's role in each event.
- `ParticipationCount` for filing-level counts that treat a group as one party.
- `Judgment` for policy choices such as whether a projection needs constituent
  rows or group-level rows.

Projection can then decide how to emit estimator rows. Extraction should not
have to collapse all of this into one bidder alias field.

### 6. Anonymous parties needed stable lifecycle identity

Unnamed bidders were another repeated failure mode. The old pipeline had to
preserve anonymous handles across NDA, bid, drop, and execution events. Repairs
could accidentally rename or delete handles, and validators had to infer whether
an unnamed bid belonged to a prior unnamed NDA cohort.

For `sec_graph`, anonymous identity should be explicit and evidence-bound. An
anonymous actor should carry:

- the source span that created it;
- the cohort or count it belongs to;
- the lifecycle phase where it is valid;
- whether it is projection-required or only count-level evidence;
- links to later events only when reconciliation can justify the linkage.

Do not make anonymous lifecycle continuity depend on label strings alone.

### 7. Provider constraints leaked into system design

The prior runtime had to adapt to real provider behavior:

- strict JSON schema calls accepted only a provider-friendly subset;
- `oneOf` and dynamic schema-valued `additionalProperties` were hostile;
- `previous_response_id` was unavailable;
- large tool-output replays were expensive;
- streaming was necessary for long full-body responses;
- missing final stream events sometimes required salvage of already-streamed
  text;
- provider capacity and model availability changed across runs.

The new architecture should isolate provider behavior behind a small interface.
Provider limitations should not define the canonical schema. If an LLM is added
in Stage 8, its output should be a provider-neutral candidate payload with
evidence references, not the canonical DuckDB schema itself.

### 8. Audit consistency became a product feature

The old pipeline needed immutable run directories, manifest contract versions,
latest pointers, cache eligibility checks, reconciliation, and stability proof.
This was not bureaucracy. Without explicit run identity, stale audit artifacts
could make a repo look current while proof tooling failed.

The new run model already points the right way: working DuckDB plus frozen run
snapshots. Carry forward these lessons:

- Every run should declare code and schema versions by module.
- Derived artifacts should be rebuilt from raw filings, not migrated.
- Snapshot comparison should use row hashes and canonical IDs, not database file
  bytes.
- A "latest" pointer is convenient but should never be the evidence authority.
- Validation and projection outputs should identify the exact run and input
  hashes that produced them.

## Useful Insights To Carry Forward

### Evidence binding is the root invariant

Every meaningful record should be traceable to a source span whose quote hash
matches the underlying filing bytes. This should start in `ingest`, not in
model output. Paragraph spans, sentence spans, and clause spans should be
records with stable IDs. Candidates and canonical rows should reference those
records.

Do not rely only on quote strings copied into output rows. Quote strings are
useful for review, but source-span IDs plus byte offsets plus quote hashes are
the stronger contract.

### Separate facts from judgments

The filing can state facts: a date, a party name, a confidentiality agreement, a
proposal amount, a final-round invitation, or a merger agreement execution. The
pipeline also makes judgments: cycle boundaries, actor merging, formal boundary
quality, dropout mechanism, whether a count requires anonymous actors, and how a
buyer group projects to estimator rows.

The new schema should make judgments explicit records. This is better than
burying them in row fields because judgments can be reviewed, superseded, and
projected differently without rewriting source facts.

### Deterministic validation should block export, not invent repairs

Validation should check referential integrity, evidence binding, date sanity,
required judgments, ID format, and projection preconditions. It should not
silently rewrite data. Rewrites belong in extraction, reconciliation, or
reviewer override flows where the source and reason are auditable.

### Obligations are candidates for canonical tables

Old filing-derived obligations were implemented as post-extraction checks. In
the new architecture, many of them deserve schema support:

- exact count of NDA signers;
- exact count of bid submissions;
- final-round advancement count;
- countable dropout outcome;
- buyer-group definition;
- inherited NDA or consortium agreement event.

Some should become `ExtractionCandidate` rows first, then
`ParticipationCount`, `GroupMembership`, `Event`, or `Judgment` rows during
reconciliation.

### Projections should absorb estimator-specific compromises

The estimator wants bidder-cycle rows. The filing does not naturally provide
bidder-cycle rows. It provides narrative events, counts, actors, group
relationships, and board/process context. The projection layer is the right
place to make row-completeness compromises explicit:

- create anonymous actors only when required by a projection rule;
- explain nulls through scope flags;
- choose latest non-superseded judgments;
- expose ambiguity instead of hiding it in extracted rows.

### No backward compatibility is easier when raw filings are source of truth

The old project correctly converged on fail-loud contracts and deletion of stale
formats. `sec_graph` should keep this doctrine. Since raw filing artifacts are
the source of truth, a schema change should usually mean dropping the derived
DuckDB and rerunning the pipeline, not preserving old readers.

## Warnings For The New Pipeline

### Do not make the LLM the canonical writer

If Stage 8 adds an LLM, it should write candidates with evidence pointers. It
should not directly write canonical actors, cycles, judgments, or projection
rows as final truth. The canonical store should be deterministic after
candidate generation.

### Do not use schema pass as research verification

A strict schema can prove shape. It cannot prove that the filing was understood.
The prior pipeline repeatedly produced outputs with valid JSON and remaining
research disagreements. Validation, ambiguity queues, diffs, and reviewer
judgments are separate signals.

### Do not collapse group and count semantics into labels

Labels like "Buyer Group", "Party A", and "Bidder 3" are not enough. They can
mean a group, a shorthand, a lifecycle handle, or a projection placeholder.
Represent the semantics directly in actor, group, count, and judgment tables.

### Do not let cache or snapshot rules be implicit

If an artifact can be reused, its eligibility should be mechanically checked
against schema and module versions. If it cannot be checked, rebuild it. Stale
artifacts should fail loudly.

### Do not overfit the first four filings

The four example filings are excellent for buildout, but the old reference set
showed that new deals expose new doctrine: stale prior processes, go-shops,
late buyer-group members, press-release executions, final-round milestones,
advisor roles, and ambiguous dropouts. Keep early rules conservative and make
unknowns visible.

## Mapping Lessons To The Approved Modules

### `schema`

Design schema records so the system can represent partial truth without forcing
premature canonical decisions. In particular, make room for:

- source spans with byte-stable quote hashes;
- extraction candidates separate from canonical records;
- participation counts independent from anonymous actors;
- group memberships with evidence and effective dates;
- append-only judgments with supersession;
- run metadata and module versions on structured outputs.

### `ingest`

Keep cleaning conservative and logged. The prior work repeatedly needed exact
phrases for counts, party labels, and dates. Ingest should preserve substantive
text even when it looks noisy. Strip only explicit, reviewed patterns. Every
removed span should be auditable.

### `extract`

The first extraction layer should favor recall with evidence over final
canonical correctness. Rules or LLM passes should produce candidates for actor
mentions, dates, bids, group definitions, and counts. They should not be forced
to solve alias merging, cycle boundaries, or projection completeness.

### `reconcile`

This is where hard domain decisions belong. Reconcile should own alias merging,
cycle assignment, grouped-bidder representation, anonymous actor creation,
dropout mechanism classification, and formal-boundary judgments. Those are not
just extraction facts; they are interpretations over multiple evidence spans.

### `validate`

Validation should be deterministic, strict, and export-blocking for hard
failures. It should produce an ambiguity queue for soft issues. It should check
that every canonical row has evidence, every foreign key resolves, every quote
hash matches, required judgments exist, and projection preconditions are met.

### `project`

Projection should be pure. It should not discover new facts or repair missing
canonical records. It should transform canonical tables into bidder-cycle views,
with scope flags explaining nulls and ambiguity. If projection needs a fact that
does not exist, validation should flag the missing prerequisite upstream.

## Build Principles For Future Agents

1. Start every module from its input and output contract.
2. Preserve source evidence before normalizing it.
3. Make uncertainty a record, not a prose note.
4. Keep provider behavior outside the canonical schema.
5. Prefer rebuilds from raw filings over migrations of derived artifacts.
6. Treat reviewer overrides as append-only judgments.
7. Make every export reproducible from a run snapshot.
8. Keep estimator rows downstream of canonical truth.

## Appendix: Forensic Evidence From The Prior Pipeline

This appendix names the prior project explicitly so future maintainers can audit
where the lessons came from. The main body above is the transfer lesson; this
section is the evidence ledger.

### Prior files that carried the burden

- `/Users/austinli/bids_try/pipeline/core.py`: deterministic preparation,
  validation, bidder-registry rebuilding, finalization, state writes, and many
  schema invariants.
- `/Users/austinli/bids_try/pipeline/llm/extract.py`: prompt construction,
  strict Responses calls, tool replay, repair loop control, and repair context
  assembly.
- `/Users/austinli/bids_try/pipeline/obligations.py`: deterministic
  filing-derived obligations for exact counts, final-round counts, buyer-group
  constituents, and late-member inherited NDA requirements.
- `/Users/austinli/bids_try/pipeline/repair_conservation.py`: protection
  against repair outputs deleting unrelated valid chronology.
- `/Users/austinli/bids_try/pipeline/stability.py`: immutable archive analysis
  and target-gate proof construction.
- `/Users/austinli/bids_try/pipeline/reconcile.py`: read-only consistency check
  across progress, latest output, flags, and audit archives.
- `/Users/austinli/bids_try/scoring/diff.py`: human-review comparison aid
  between AI output and Alex reference rows.

### Commit evidence

- `ce770fd` implemented the robust extraction blueprint: target gate,
  immutable audit archive v2, reconciliation, stability harness, and runtime
  hardening.
- `e3b6b5c`, `52ceaa7`, and `e1f358f` recorded strict-schema Linkflow probes
  and provider-shape hardening. The important lesson was that provider-facing
  JSON schema must be simpler than the canonical contract.
- `d9ad1ba`, `ca0d16a`, and `2cec3ac` added tool use and multi-turn replay,
  then had to force a final strict JSON turn after tool-call limits. This showed
  the cost of tool-heavy full-body extraction.
- `e613e0e`, `48124f7`, and related prompt-first commits moved initial
  extraction away from tools and reserved tools for repair.
- `8e7e956` designed obligation-gated single repair after the PetSmart collapse
  class: repair could otherwise delete valid rows and still pass validation.
- `c90f00f` implemented obligation checks, repair conservation, reference
  verification scripts, and stricter audit metadata.
- `a2c06c0`, `8ae2214`, `f5a2261`, `f7922d1`, `e10aeca`, and `35e28f0` show
  repeated fixes around anonymous handles, process windows, buyer-group count
  units, inherited NDA ambiguity, and constituent NDA rows.
- `d88b884` recorded a high-reasoning reference batch with 7 passed and 2
  validated, including a Providence non-bid value-field regression and a
  PetSmart buyer-group atomization decision point.
- `4593877` recorded a later high run where provider behavior, repair turns,
  and exact hard-flag classes were material operational facts.

### Observed state during this memo

The prior repo's current reference outputs reconciled successfully:

```text
python -m pipeline.reconcile --scope reference
reconcile OK: checked=9 errors=0 warnings=0
```

The stricter stability harness failed on stale archived metadata:

```text
python -m pipeline.stability --scope reference --runs 3 --json
archived run manifest missing required obligation_contract_version: output/audit/providence-worcester/runs/5e9bf34132da4933a2bc2b7cb4400290/manifest.json
```

This is the concrete reason the new pipeline should treat run schema versions,
module versions, and snapshot eligibility as part of the architecture rather
than as optional reporting details.

### What not to copy

Do not copy the old pipeline's row-per-event JSON as the canonical model. Do
not copy its provider-specific orchestration into the new core. Do not copy old
state, flags, audit, or output formats. The useful material is the set of
failure modes and the deterministic principles that emerged from them.
