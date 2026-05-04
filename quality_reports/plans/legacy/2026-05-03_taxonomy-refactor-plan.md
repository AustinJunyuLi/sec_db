# 2026-05-03 Taxonomy Refactor Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:subagent-driven-development` or
> `superpowers:executing-plans` to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Status:** Draft implementation plan. This document replaces
`2026-05-03_taxonomy-refactor-handoff.md` and
`2026-05-03_taxonomy-refactor-supplement.md`.

**Goal:** Add the research taxonomy needed for robust M&A sale-process analysis
without breaking the hard-reset guarantees: source-backed facts, typed claims,
closed schemas, no fallbacks, and deterministic projections.

**Architecture:** Linkflow proposes typed source-backed claims from sale-process
windows. Python binds quotes to source spans, validates claim meaning, records
claim dispositions, canonicalizes accepted facts into the generic graph, and
builds bidder-cycle research projections. The LLM never emits canonical row ids,
source offsets, auction flags, silent fates, or final analysis rows.

**Tech Stack:** Python, Pydantic, DuckDB DDL, Linkflow GPT-5.5 Responses-style
structured JSON, pytest.

---

## Authority And Scope

This plan is not above the repository authority chain. Before implementation,
the taxonomy decisions below must be copied into `docs/spec.md` as the
deployable taxonomy/schema contract, and any provider-facing request or
validator changes must be copied into `docs/llm-interface.md`.

Active authority remains:

1. `docs/superpowers/specs/2026-05-03-pipeline-hard-reset-design.md`
2. `docs/spec.md`
3. `docs/llm-interface.md`

`docs/prior-pipeline-lessons.md` is failure-mode context only. Historical
plans, calibration logs, and session logs are not execution authority. This
repo must stay self-contained; implementation must not depend on reading or
modifying any external project.

## Research Variables To Preserve

The taxonomy must answer these research questions from source-backed facts and
deterministic projections:

- Was each bidder strategic, financial, mixed, or not source-classified?
- Which bid events were informal and which were formal?
- Who initiated a contact, proposal, process event, or pressure event?
- Which bidders reached the final round?
- Which bidders submitted final-round bids?
- Who withdrew, who was excluded, who went silent, and why?
- Which agreement events were target-bidder NDAs versus bidder-bidder
  consortium CAs or rollover/support side agreements?
- Was a deal or cycle an auction under the deterministic NDA-count rule?
- What value/range and consideration structure did each bid use?

## Closed Value Policy

Use `null` when the filing does not support a classification. Do not add
`unknown`, `other`, or legacy catch-all enum values. `null` means "not emitted
as a source-backed value." The reason for null or ambiguity belongs in
coverage results, claim dispositions, or semantic-validation judgments.

Bidder economic class values:

```text
s
f
mixed
null
```

Rules:

- `s` means strategic operating buyer.
- `f` means financial sponsor, fund, or sponsor-controlled financial buyer.
- `mixed` means a known mixture of `s` and `f` members, not uncertainty.
- Use `null` for unsupported or ambiguous class.
- Participation counts, actors, groups, and bidder-row projections must use the
  same vocabulary. Do not keep `financial`/`strategic` as a compatibility layer.

Bid formality values:

```text
informal
formal
null
```

Rules:

- Formality belongs on bid claims and bid events, not on actors.
- A bidder can make both informal and formal bids in the same cycle.
- True range bids are informal unless the source clearly shows a formal range
  submission.
- If evidence does not support formality, use `null` and record a disposition
  or review item. Do not guess.

Initiation side values:

```text
target
bidder
activist
mutual_or_process
null
```

Rules:

- Initiation is event-specific.
- Target outreach, bidder unsolicited approaches, activist pressure, and mutual
  process-start facts must be separate from bidder identity and bid formality.
- `mutual_or_process` is only for source-backed process events where the source
  describes joint or process-driven initiation without a clearer actor side.

Outcome/drop fields:

```text
drop_agency: target | bidder | null
drop_reason: below_market | below_minimum | never_advanced | no_response |
             scope_mismatch | target_other | null
```

Rules:

- Agency and reason are separate fields.
- Silent fate is not extracted from the filing as an event. It is a projection
  derived when an actor has auction-funnel NDA status and no later observed
  fate in the same cycle.
- `target_other` is allowed because target-side reasons can be source-backed
  but not analytically decomposed further. It is not a generic fallback for all
  unknowns.

Agreement kind values:

```text
target_bidder_nda
bidder_bidder_consortium_ca
rollover_support
null
```

Rules:

- Only `target_bidder_nda` counts toward auction-funnel NDA counts.
- A bidder-bidder consortium CA does not substitute for a target-bidder NDA.
- A rollover or support agreement is not an auction-funnel NDA.

Final-round facts:

```text
final_round_announced
final_round_deadline_set
final_round_extended
advanced_to_final_round
not_advanced_to_final_round
submitted_final_round_bid
```

Rules:

- Final-round announcement, bidder admission, bidder non-admission, and bidder
  submission are separate facts.
- A final-round bid is not automatically formal. Bid formality must be stored
  separately on the bid event.

Consideration encoding:

Use a closed enum plus optional component detail:

```text
all_cash
all_stock
cash_and_stock
cash_and_assumption_of_debt
cash_and_earnout
complex_other
null
```

For `complex_other`, the evidence quote must describe the structure. Deal-level
`all_cash` is a deterministic signed-transaction projection, not a field that
overwrites every competing bid.

## How Features Enter The Graph

Every source-backed classification starts as a claim. Accepted claims become
generic canonical graph rows. Research tables are projections, not source truth.

| Research feature | Extraction claim home | Canonical graph home | Evidence link | Projection home |
|---|---|---|---|---|
| Named actor `s/f/null` | `actor_claims.actor_class`, `actor_class_confidence` | `actors.actor_class` | `claim_evidence` from claim; `row_evidence` from actor | `bidder_rows.actor_class` |
| Group/cohort `mixed` | `actor_claims.actor_class` for group/cohort or `participation_count_claims.actor_class` | `actors.actor_class`; `participation_counts.actor_class` | Same as above | bidder-row class derives from actor/group/cycle facts |
| Bid formality | `bid_claims.bid_formality`, `bid_formality_confidence` | `events.bid_formality` where `event_type='bid'` | Bid claim evidence and event row evidence | `bidder_rows.initial_bid_formality`, `bidder_rows.final_bid_formality` |
| Initiation side | `event_claims.initiation_side`, `initiator_actor_label`, confidence | `events.initiation_side`; optional `event_actor_links.role='initiator'` | Event claim evidence and link row evidence | cycle/deal summaries; bidder rows when event is actor-specific |
| Final-round admission | `event_claims.event_subtype='advanced_to_final_round'` with actor role | `events` plus `event_actor_links` | Event and link evidence | `bidder_rows.advanced_to_final_round` |
| Final-round submission | `bid_claims.final_round_submission=true` or event subtype | `events` where `event_type='bid'`; event link to bidder | Bid event evidence | `bidder_rows.submitted_final_round_bid` |
| Drop agency/reason | `event_claims.drop_agency`, `drop_reason`, confidence | `events.drop_agency`, `events.drop_reason` | Event evidence | `bidder_rows.observed_fate`, `bidder_rows.drop_reason` |
| Silent fate | No LLM claim | No source event row | Derived rule evidence must point to NDA row and absence-of-later-fate judgment | `bidder_rows.derived_fate='silent_after_nda'` |
| NDA/CA kind | `event_claims.agreement_kind` | `events.agreement_kind`; event links identify parties | Agreement event evidence | auction projection and NDA participation summaries |
| Auction | No LLM claim | No source event row | Derived from target-bidder NDA event rows | `cycle_summaries.auction`, `bidder_rows.auction_cycle` |
| Bid value/range | `bid_claims.bid_value`, lower/upper/unit | `events.bid_value*` | Bid claim evidence | `bidder_rows.b_i`, `b_i_lower`, `b_i_upper`, `b_f` |
| Consideration | `bid_claims.consideration_type`, component detail | `events.consideration_type`, detail | Bid claim evidence | bidder/deal consideration summaries |

The current code does not yet support most of these columns. Implementation
must change Pydantic models, DDL, insert statements, reconcile, validation,
projection, fixtures, and tests together.

## Validator And Multi-Pass Design

The validator is required for high-risk research variables, but it must obey the
same provider boundary as extraction.

Validator rules:

- All provider-specific validator code lives under `src/sec_graph/extract/llm/`.
- `docs/llm-interface.md` must define the validator request and response shape
  before code is added.
- The validator must receive a source window that Python can bind, not only a
  decontextualized quote snippet.
- Validator output is not embedded as an optional nested object inside primary
  provider claim payloads. Store validator results in local validation tables,
  claim dispositions, or `judgments`.
- Validator input is assembled only after local Pydantic validation and quote
  binding. It contains local claim id, claim type, field path, emitted value,
  exact validated quote text, and the minimal paragraph context needed to check
  support. It does not contain provider-owned offsets or canonical ids.
- Validator output contains verdict metadata only: claim id, field path,
  verdict, reason code, and short reason. It does not return quote text,
  source offsets, coverage results, canonical ids, or projection rows.
- A claim that fails validator support is not canonicalized. It is rejected or
  queued for explicit review.

Confidence rules:

- Every non-null high-risk classification has paired confidence:
  `high`, `medium`, or `low`.
- Confidence is a signal, not authority. The quote/window still has to support
  the classification.
- Low-confidence source-backed claims may be stored as claims, but they do not
  become canonical facts until validator or human review accepts them.

Multi-pass routing:

- Use N=3 only for high-risk fields: `bid_formality`, `initiation_side`,
  `drop_reason`, `agreement_kind`, and final-round admission/submission.
- 3/3 agreement can proceed to validator.
- 2/3 agreement can proceed to validator with effective confidence `medium`.
- 1/1/1 disagreement is not canonicalized; queue a semantic-validation
  judgment or ambiguity artifact.
- Multi-pass is a fixed run mode, not a retry or fallback.
- Each pass receives a distinct request id and pass id.
- Individual pass outputs are auditable as pass-scoped claims or pass-output
  records. They must not all write final current coverage rows.
- Aggregation writes one deterministic decision record, assigns dispositions to
  the underlying pass claims, and only then writes final current coverage rows.
- Multi-pass results are local orchestration data, not provider-owned canonical
  fields.

Review queue:

- The current `judgments` table lacks status fields. Add an explicit lifecycle
  before using it as a blocking queue:
  `queued`, `resolved`, `rejected`.
- Add enough fields to know target claim/field, prior value, accepted value,
  reason, reviewer, timestamp, and supersession chain.
- No reviewer UI is required for this phase. A CLI or artifact-driven workflow
  is enough, but the database state must be explicit.

## Registry Design

The known-actor registry is a curation aid, not canonical truth.

Allowed behavior:

- Registry hit agrees with filing-backed claim: corroborate and log.
- Registry hit disagrees with filing-backed claim: do not override silently;
  queue review.
- Registry hit exists but filing has no source-backed class: do not commit
  actor class as a canonical fact unless a human judgment explicitly resolves it.
- Exact alias and declared parent/vehicle matches may normalize names or attach
  registry metadata. They do not satisfy filing coverage obligations by
  themselves.
- Suffix-stripped, substring, and fuzzy matches are candidate matches only and
  must queue review before affecting canonical or projection facts.
- No fuzzy registry match can auto-commit.

Location:

```text
data/registry/known_actors.yaml
src/sec_graph/extract/registry.py
```

Registry results must be represented as local review/curation metadata unless
and until a human judgment accepts them. The registry must never create
provider-owned offsets or source spans.

## Coverage Contract

Provider coverage results only cover obligations where the provider emitted no
claim.

Rules:

- Provider output has two channels: positive typed claims and negative or
  ambiguous obligation notices.
- A positive claim must name every coverage obligation id it supports.
- The provider may emit `no_supported_claim` or `ambiguous` only for obligations
  with no emitted claim.
- The provider must not emit a coverage notice for an obligation that also has a
  claim. Import should fail if this happens.
- Python owns final coverage rows. It writes `claims_emitted` after quote
  binding, claim validation, and multi-pass aggregation prove a linked claim.
- Python alone assigns `missed` when no linked claim and no provider coverage
  result exist.

Update `src/sec_graph/extract/llm/prompt.py`, `docs/llm-interface.md`, and
tests so prompt language matches importer behavior.

## File Map

Specification and contracts:

- Modify: `docs/spec.md`
  - Add §1A taxonomy authority with value sets, source/projection split, and
    relational placement.
- Modify: `docs/llm-interface.md`
  - Add provider coverage semantics, validator request/response shape, and
    multi-pass constraints.
- Modify: `quality_reports/session_logs/2026-05-03_taxonomy-classification-design.md`
  - Mark the old two-doc authority statement as superseded by this merged plan.

Schema models and DDL:

- Modify: `src/sec_graph/schema/models/extraction.py`
  - Add taxonomy fields to `ActorClaim`, `EventClaim`, `BidClaim`,
    `ParticipationCountClaim`, and DDL.
  - Rename `ActorClass` values to `s`, `f`, `mixed`; allow null where the
    source does not support classification.
  - Add durable claim-to-obligation link storage so the system can answer
    which claim satisfied which coverage obligation after import and
    aggregation.
- Modify: `src/sec_graph/schema/models/canonical.py`
  - Add taxonomy fields to `Actor`, `Event`, and `BidderRow`; update DDL.
- Modify: `src/sec_graph/schema/models/participation_counts.py`
  - Use the same actor-class vocabulary as actors.
- Modify: `src/sec_graph/schema/models/judgments.py`
  - Add explicit review lifecycle state for semantic-validation queue.
- Modify: `src/sec_graph/schema/schema_init.py`
  - Only if new DDL constants are added or DDL application order changes.
  - Do not put DDL in `src/sec_graph/schema/__init__.py`; it only re-exports.
- Modify: `src/sec_graph/schema/versions.py`
  - Bump `SCHEMA_VERSION`, `EXTRACT_VERSION`, `RECONCILE_VERSION`,
    `VALIDATE_VERSION`, and `PROJECT_VERSION` when behavior changes.

LLM and extraction:

- Modify: `src/sec_graph/extract/evidence_map.py`
  - Add obligations for taxonomy variables: actor class, bid formality,
    initiation, NDA/CA kind, final-round admission/submission, drop/fate,
    consideration.
- Modify: `src/sec_graph/extract/llm/models.py`
  - Mirror claim fields in provider payloads without nested nullable validator
    verdict objects.
- Modify: `src/sec_graph/extract/llm/linkflow.py`
  - Keep strict schema export compatible with Linkflow; add tests for no
    unsupported `anyOf` object-null shapes.
  - Provider schema must stay inside the tested Linkflow-safe subset: no
    `$defs`, `oneOf`, `allOf`, `anyOf`, defaults, formats, patterns,
    min/max constraints, or schema-valued `additionalProperties`.
  - Optional provider semantics are represented as required nullable scalar
    fields, not optional nested objects.
- Modify: `src/sec_graph/extract/llm/convert.py`
  - Insert taxonomy fields, enforce coverage contract, and keep Python-owned
    source-span binding.
- Modify: `src/sec_graph/extract/llm/prompt.py`
  - Add plain rubrics for source-backed taxonomy claims.
- Create: `src/sec_graph/extract/llm/aggregation.py`
  - Multi-pass agreement rules.
- Create: `src/sec_graph/extract/llm/validator.py`
  - Validator provider calls and result parsing.
- Create: `src/sec_graph/extract/registry.py`
  - Noncanonical registry lookup and review queue handoff.

Reconcile, validate, project:

- Modify: `src/sec_graph/reconcile/pipeline.py`
  - Consume only accepted claims.
  - Canonicalize taxonomy fields without Python guessing source meaning.
  - Stop deriving bid formality from bid stage.
  - Preserve actor kind/class for relation-only actors; do not create every
    relation subject/object as a generic named organization when the source or
    claim says group, vehicle, cohort, advisor, or committee.
  - Build real process-cycle boundaries for multi-cycle/restart filings before
    projecting final-round, auction, or silent-fate facts.
  - Stop linking deal/cycle rows to arbitrary first claim evidence if the row
    meaning is not proved by that evidence.
- Modify: `src/sec_graph/validate/integrity.py`
  - Validate taxonomy evidence meaning: actor class, bid formality, initiation,
    NDA kind, final-round admission/submission, drop agency/reason, and
    consideration.
  - Validate projection rows trace to actor-cycle facts and projection
    judgments, not only that a projection unit exists.
  - Wire stage-artifact and progress-ledger digest checks required by the
    hard-reset spec.
- Modify: `src/sec_graph/project/bidder_rows.py`
  - Export taxonomy columns and deterministic derived fields.
  - Do not reuse `admitted=true` to mean "has any source-backed bid"; final-round
    admission and final-round submission are separate projected fields.
- Create: `src/sec_graph/project/auction.py`
  - Derive cycle auction flag from `target_bidder_nda` count >= 2.
- Create: `src/sec_graph/project/silent_fate.py`
  - Derive silent fate from target-bidder NDA plus no later observed fate.
- Modify: `src/sec_graph/cli/run_cmd.py`
  - Add explicit validator stage before reconcile.
  - Wire conservative resume digest checks instead of deleting
    `working.duckdb` on resume.
- Modify: `src/sec_graph/cli/__init__.py`
  - Ensure new flags are forwarded by the top-level dispatcher.

Tests and fixtures:

- Modify/add tests under `tests/` for each task below.
- Refresh or delete stale golden fixtures that still encode old candidate or
  projection fields.
- Preserve `data/filings/`; it is local research data.

## Implementation Tasks

### Task 1: Make Authority Clean

**Files:**

- Modify: `docs/spec.md`
- Modify: `docs/llm-interface.md`
- Modify: `quality_reports/session_logs/2026-05-03_taxonomy-classification-design.md`
- Delete: old split taxonomy plan files, after this merged plan is committed.

- [ ] Add `docs/spec.md` §1A with the taxonomy value sets, null policy, and
  feature-to-table placement from this plan.
- [ ] Add `docs/llm-interface.md` language for provider coverage results,
  validator windows, multi-pass, and strict JSON restrictions.
- [ ] Update the session log so it says the previous handoff/supplement pair
  was superseded by this merged plan and is not authority.
- [ ] Run:

```bash
rg -n "binding taxonomy authority|handoff wins|2026-05-02_stale-scaffold|validator.verdict|schema/__init__.*DDL" \
  AGENTS.md README.md docs quality_reports src tests \
  --glob '!quality_reports/plans/2026-05-03_taxonomy-refactor-plan.md'
```

Expected: no active-plan or active-doc hits that preserve the old conflicting
guidance.

### Task 2: Add Schema Fields And DDL

**Files:**

- Modify: `src/sec_graph/schema/models/extraction.py`
- Modify: `src/sec_graph/schema/models/canonical.py`
- Modify: `src/sec_graph/schema/models/participation_counts.py`
- Modify: `src/sec_graph/schema/models/judgments.py`
- Modify: `src/sec_graph/schema/versions.py`
- Test: `tests/test_taxonomy_schema.py`

- [ ] Write tests that assert all closed enum values and nullable fields match
  this plan.
- [ ] Add the fields to Pydantic models and DDL.
- [ ] Add review lifecycle fields to `judgments`.
- [ ] Bump schema and stage versions.
- [ ] Run:

```bash
PYTHONDONTWRITEBYTECODE=1 uv run pytest -q -p no:cacheprovider tests/test_taxonomy_schema.py
```

Expected: tests pass.

### Task 3: Fix LLM Claim Contract

**Files:**

- Modify: `src/sec_graph/extract/evidence_map.py`
- Modify: `src/sec_graph/extract/llm/models.py`
- Modify: `src/sec_graph/extract/llm/convert.py`
- Modify: `src/sec_graph/extract/llm/prompt.py`
- Modify: `src/sec_graph/extract/llm/linkflow.py`
- Test: `tests/test_llm_taxonomy_contract.py`
- Test: `tests/test_coverage_semantics.py`

- [ ] Add taxonomy obligations to the evidence map.
- [ ] Add taxonomy fields to provider payload models.
- [ ] Keep validator outcomes out of primary payloads.
- [ ] Fix prompt wording so the model emits coverage results only for
  obligations with no claim.
- [ ] Extend strict schema tests to reject unsupported nullable object shapes.
- [ ] Run:

```bash
PYTHONDONTWRITEBYTECODE=1 uv run pytest -q -p no:cacheprovider \
  tests/test_llm_taxonomy_contract.py tests/test_coverage_semantics.py
```

Expected: tests pass.

### Task 4: Add Validator, Multi-Pass, And Registry Safely

**Files:**

- Create: `src/sec_graph/extract/llm/aggregation.py`
- Create: `src/sec_graph/extract/llm/validator.py`
- Create: `src/sec_graph/extract/registry.py`
- Modify: `src/sec_graph/reconcile/pipeline.py`
- Test: `tests/test_taxonomy_validation_queue.py`
- Test: `tests/test_actor_registry.py`

- [ ] Implement N=3 aggregation for the high-risk fields only.
- [ ] Implement validator provider calls under `src/sec_graph/extract/llm/`.
- [ ] Store validator outcomes in local queue/disposition structures.
- [ ] Implement registry lookup as corroboration/review metadata only.
- [ ] Prove registry disagreement cannot auto-commit canonical actor class.
- [ ] Run:

```bash
PYTHONDONTWRITEBYTECODE=1 uv run pytest -q -p no:cacheprovider \
  tests/test_taxonomy_validation_queue.py tests/test_actor_registry.py
```

Expected: tests pass.

### Task 5: Reconcile Accepted Claims Into Graph Rows

**Files:**

- Modify: `src/sec_graph/reconcile/pipeline.py`
- Modify: `src/sec_graph/validate/integrity.py`
- Test: `tests/test_taxonomy_reconcile.py`
- Test: `tests/test_validation_semantics.py`

- [ ] Reconcile only claims that passed quote binding and semantic validation or
  explicit human review.
- [ ] Store actor class on actors.
- [ ] Store bid formality, agreement kind, initiation side, drop fields, and
  consideration on events.
- [ ] Store actor roles through `event_actor_links`, including initiators,
  bidders, target, advisors, support holders, and group members.
- [ ] Keep deterministic projections separate from source event rows.
- [ ] Run:

```bash
PYTHONDONTWRITEBYTECODE=1 uv run pytest -q -p no:cacheprovider \
  tests/test_taxonomy_reconcile.py tests/test_validation_semantics.py
```

Expected: tests pass.

### Task 6: Project Research Rows Deterministically

**Files:**

- Modify: `src/sec_graph/project/bidder_rows.py`
- Create: `src/sec_graph/project/auction.py`
- Create: `src/sec_graph/project/silent_fate.py`
- Modify: `src/sec_graph/project/summaries.py`
- Test: `tests/test_taxonomy_projection.py`

- [ ] Add bidder-row columns for actor class, formality, final-round admission,
  final-round submission, observed fate, silent fate, drop reason, NDA status,
  auction flag, and consideration summaries.
- [ ] Derive auction from count of distinct actor-cycle target-bidder NDA
  participants.
- [ ] Derive silent fate from NDA participation and absence of later observed
  fate.
- [ ] Validate projection rows have traceable projection units and projection
  judgments.
- [ ] Run:

```bash
PYTHONDONTWRITEBYTECODE=1 uv run pytest -q -p no:cacheprovider tests/test_taxonomy_projection.py
```

Expected: tests pass.

### Task 7: Runtime And End-To-End Proof

**Files:**

- Modify: `src/sec_graph/cli/run_cmd.py`
- Modify: `src/sec_graph/cli/__init__.py`
- Modify: `src/sec_graph/run/`
- Modify: `README.md`
- Test: `tests/test_run_kernel.py`
- Test: `tests/test_cli_dispatch.py`

- [ ] Add validator stage before reconcile in the run command.
- [ ] Wire conservative resume checks so completed artifacts are digest-checked
  and not deleted on resume.
- [ ] Forward any new CLI flags through `python -m sec_graph`.
- [ ] Update README command examples only after the CLI is real.
- [ ] Run:

```bash
PYTHONDONTWRITEBYTECODE=1 uv run pytest -q -p no:cacheprovider \
  tests/test_run_kernel.py tests/test_cli_dispatch.py
```

Expected: tests pass.

### Task 8: Stale Cleanup And Full Verification

**Files:**

- Modify/delete stale tests and fixtures under `tests/fixtures/`.
- Modify: `tests/test_repo_freshness_contract.py` if new freshness constraints
  are needed.
- Preserve: `data/filings/`.

- [ ] Delete or refresh fixtures that encode old candidate rows, old projection
  fields, `financial`/`strategic` actor-class values, or old coverage semantics.
- [ ] Run stale-surface scan:

```bash
rg -n "financial/strategic|unknown\\\"|validator.verdict|Emit one coverage_result per obligation|old project|bids_try|2026-05-02_stale" \
  AGENTS.md README.md docs quality_reports src tests \
  --glob '!quality_reports/plans/2026-05-03_taxonomy-refactor-plan.md'
```

Expected: only historical context or explicitly allowed references remain.

- [ ] Run full offline verification:

```bash
PYTHONDONTWRITEBYTECODE=1 uv run pytest -q -p no:cacheprovider
```

Expected: all tests pass.

- [ ] Run the three live acceptance deals after credentials are present:

```bash
python -m sec_graph run \
  --source filings \
  --slugs petsmart-inc mac-gray providence-worcester \
  --run-id 2026-05-03T010203Z_taxonomy-proof_deadbeef \
  --run-dir runs/2026-05-03T010203Z_taxonomy-proof_deadbeef \
  --llm-provider linkflow \
  --llm-model gpt-5.5 \
  --llm-reasoning-effort high
```

Expected: meaningful source-backed claims, dispositions, canonical rows,
taxonomy projections, validation report, proof summary, and cost/runtime
artifacts. Rules-only runs cannot be `SOUND`.

## Non-Goals

- Do not implement direct OpenAI provider support in this taxonomy refactor.
- Do not use whole raw filing extraction as production fallback.
- Do not add backward-compatible readers for old flat rows.
- Do not preserve old `financial`/`strategic` values as alternate accepted
  actor-class values.
- Do not use registry or manual curation as hidden canonical truth.
- Do not build a reviewer UI in this phase.

## Robustness Definition

The taxonomy is robust only when all of the following are true:

- The taxonomy is binding in `docs/spec.md`.
- Provider-facing behavior is binding in `docs/llm-interface.md`.
- Every source-backed classification has claim evidence.
- Every canonical taxonomy field has row evidence.
- Low-confidence or validator-disputed claims cannot silently become canonical.
- Registry disagreement cannot silently override filing evidence.
- Auction and silent fate are deterministic projections, not LLM outputs.
- Bidder rows trace through projection units and projection judgments.
- Offline tests pass.
- Three live acceptance deals produce meaningful taxonomy-bearing proof
  artifacts.
