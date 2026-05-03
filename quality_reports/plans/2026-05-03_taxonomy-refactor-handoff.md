# 2026-05-03 Taxonomy Refactor Handoff

## Purpose

This note is a self-contained handoff for the next agent that will repair the
research taxonomy in `sec_graph`.

The current extraction granularity is directionally good: the graph design can
record actors, groups, vehicles, relations, events, counts, evidence, and
projection rows more cleanly than the prior flat-row pipeline. The remaining
problem is taxonomy: the current schema does not yet preserve the research
classifications that matter for sale-process analysis.

The next agent should work from first principles. Do not preserve stale row
labels, compatibility shims, or fallback behavior from the old pipeline.

## Austin's Current Decisions

- Bidder economic type only needs `s`, `f`, `mixed`, and `null`.
- Ignore US/non-US, public/private, and similar bidder-descriptor clutter.
- Formal vs informal bids are one of the most important research variables.
- Target/bidder/activist initiation is also important.
- Final-round structure is important.
- Alex's workbook taxonomy is useful evidence of research intent, but it is
  fragmented and should not be copied literally.
- The canonical graph should store decomposed facts; any Alex-style table
  should be a projection.

## Read-Only Reference Material

Use the old project only as read-only reference material:

- `/Users/austinli/bids_try/rules/bidders.md`
- `/Users/austinli/bids_try/rules/bids.md`
- `/Users/austinli/bids_try/rules/events.md`
- `/Users/austinli/bids_try/rules/invariants.md`
- `/Users/austinli/bids_try/rules/schema.md`
- `/Users/austinli/bids_try/pipeline/core.py`
- `/Users/austinli/bids_try/pipeline/llm/response_format.py`
- `/Users/austinli/bids_try/scripts/build_reference.py`
- `/Users/austinli/bids_try/reference/deal_details_Alex_2026.xlsx`
- `/Users/austinli/bids_try/reference/CollectionInstructions_Alex_2026.pdf`
- `/Users/austinli/bids_try/reference/alex/*.json`

Do not modify the old project.

## Current `sec_graph` Surfaces To Inspect

Read the active authority chain first:

- `docs/spec.md`
- `docs/llm-interface.md`
- `quality_reports/plans/2026-05-03_full-redesign-plan.md`

Then inspect the actual implementation surfaces:

- `src/sec_graph/schema/models/extraction.py`
- `src/sec_graph/schema/models/canonical.py`
- `src/sec_graph/schema/models/judgments.py`
- `src/sec_graph/schema/models/participation_counts.py`
- `src/sec_graph/extract/llm/models.py`
- `src/sec_graph/extract/llm/convert.py`
- `src/sec_graph/reconcile/pipeline.py`
- `src/sec_graph/project/bidder_rows.py`
- `src/sec_graph/validate/`
- `tests/`

## High-Level Finding

The old pipeline tracked many research variables, but forced them into one
flat event-row schema. The graph design should retain the useful variables
while avoiding the old shape.

Current `sec_graph` already has good substrate:

- actors
- actor kinds
- group/vehicle/cohort concepts
- actor relations
- event chronology
- event actor roles
- bid values and ranges
- participation counts
- evidence spans
- projection rows

But current `sec_graph` is missing or only partially represents these key
research axes:

- bidder `s/f/mixed`
- formal vs informal bid classification
- initiation side
- final-round structure
- formal-stage advancement/submission
- drop/outcome agency and reason
- target-bidder NDA vs bidder-bidder consortium CA
- deterministic auction projection
- bid/deal consideration structure

## Target Taxonomy

### 1. Bidder Economic Class

Values:

- `s`: strategic operating buyer.
- `f`: financial sponsor/fund/financial buyer/sponsor-controlled vehicle.
- `mixed`: group, consortium, or cohort with both `s` and `f` participants.
- `null`: source does not support classification.

Rules:

- A single ordinary named actor should be `s`, `f`, or `null`.
- `mixed` should normally be reserved for group/cohort/projection units, not
  for an ordinary single actor.
- `mixed` means known mixture, not ambiguity.
- "Could be strategic or financial" is `null`, not `mixed`.
- "11 strategic and 14 financial parties" is mixed at the cohort/count level.
- "Buyer Group includes Sponsor A and Strategic Co." is mixed at the group
  level.

Canonical homes:

- actor economic class for named actors
- group/cohort economic class for aggregate/group actors
- participation-count class for count claims
- bidder-row projection class for exported analysis rows

Current gap:

- `ActorClass = financial/strategic/mixed` exists for participation counts,
  but named actors and bidder rows do not currently carry the economic class.

### 2. Bid Formality

Values:

- `informal`
- `formal`
- `null`

Rules:

- Formal/informal belongs on bid events, not actors.
- The same bidder can submit an informal bid and later a formal bid.
- True range bids are informal unless the project deliberately changes that
  rule with source-backed justification.
- If classification is not supportable, use `null` and surface review, not a
  guessed value.

Old-pipeline lessons:

- The prior rulebook treated formal/informal as the highest-risk research
  variable.
- The old code enforced enum shape and evidence-shape, but did not truly parse
  the reasoning in the inference note.

New design target:

- Store formal/informal as a typed bid-event classification with evidence.
- If an LLM supplies the classification, the evidence should be source-span
  backed and auditable.
- Avoid free-text-only `bid_type_inference_note` as the sole authority.

### 3. Initiation Side

Values:

- `target`
- `bidder`
- `activist`
- `mutual_or_process`
- `unknown` or `null`

Rules:

- Initiation is separate from bidder identity and bid formality.
- It answers: who caused this process/contact/proposal to begin?
- Target-initiated private contact should not be buried in a note.
- Bidder unsolicited approach should be explicit.
- Activist pressure should be explicit when it initiates or catalyzes a sale
  process.

Canonical homes:

- process/contact events
- event actor links
- possibly `initiator_actor_id` / role fields if the schema chooses that route

Old-pipeline lesson:

- `Target Interest` was normalized into `Bidder Interest` plus
  `"target-initiated"` in `additional_note`. Do not copy that awkward shape.

### 4. Round And Process Stage

Core stages:

- contacted / initial contact
- NDA signed
- IOI / preliminary indication
- first round
- final round
- exclusivity
- signing
- post-signing / go-shop if needed

Rules:

- Keep round/stage separate from bid formality.
- A final-round bid is not automatically formal unless the source or round
  structure supports that classification.
- Process cycles should replace old `process_phase` integers.

Canonical homes:

- process cycle
- event subtype
- round/phase events
- projection judgments

Current gap:

- `process_cycles` exists, but current reconciliation has historically been
  thin around real multi-cycle/restart boundaries.

### 5. Final-Round Structure

Facts to preserve:

- final round announced
- final-round submission/deadline occurred
- final round extended
- final round was informal or formal if the source supports it
- bidder was invited/admitted to the final round
- bidder submitted a formal final-round bid
- bidder was not advanced / excluded / withdrew before formal submission

Rules:

- These are not one row label.
- Store them as events and projection judgments.
- Bidder-specific advancement and bidder-specific submission are separate
  facts.

Old-pipeline lesson:

- The old fields were:
  - `final_round_announcement`
  - `final_round_extension`
  - `final_round_informal`
  - `invited_to_formal_round`
  - `submitted_formal_bid`
- Alex's converted JSONs often leave the last two blank, but the concepts are
  still analytically important.

### 6. Outcome / Fate / Drop

Core outcome values:

- advanced
- excluded by target
- withdrawn by bidder
- nonresponsive
- signed / winner
- auction closed / process terminated
- inferred silent after NDA, as a derived fate rather than a source event

Drop agency:

- `target`
- `bidder`
- `unknown`

Drop reason classes worth carrying:

- `below_market`
- `below_minimum`
- `never_advanced`
- `no_response`
- `scope_mismatch`
- `target_other`
- `null`

Rules:

- Keep agency and reason separate.
- Do not force a reason when the filing does not support one.
- `DropSilent` from the old pipeline should become a derived graph/projection
  result when an NDA signer has no later observed fate.

Canonical homes:

- event subtype for observed outcome
- judgment or projection field for inferred silent fate
- evidence-linked reason detail when source-backed

### 7. NDA / Consortium CA / Rollover Side Agreement

Carry this strongly, because it affects auction counts and buyer-group logic.

Types:

- target-bidder NDA: auction-funnel NDA; counts toward auction threshold.
- bidder-bidder consortium CA: relationship among bidders; does not count as
  target-bidder NDA.
- rollover/support side agreement: not an auction-funnel NDA.

Rules:

- A bidder-bidder consortium CA does not substitute for a same-bidder
  target-bidder NDA.
- A late member joining an already-NDA-bound buyer group may need both:
  - a consortium/member relation or CA event
  - inherited auction-funnel NDA status if source-backed
- Represent buyer groups with graph structure: group actor, members, vehicles,
  financing/support relations, and source-backed membership dates.

Canonical homes:

- event for agreement execution
- actor relations for group membership and support/financing/rollover
- deterministic projection for auction counts

### 8. Auction

Rule:

- `auction` should be deterministic, not an LLM-owned field.
- Old rule: auction is true when there are at least two bidder-side
  target-bidder NDA rows in the current sale process.
- In `sec_graph`, derive this from canonical events/relations and process
  cycle boundaries.

Canonical home:

- deterministic deal/cycle projection summary, not canonical extracted fact.

### 9. Consideration

Carry as secondary but useful.

Fields/concepts:

- bid value
- per-share value
- range lower/upper
- aggregate value if filing states only aggregate
- consideration components: cash, stock, CVR, earnout, other
- signed-deal all-cash classification

Rules:

- Bid consideration belongs on bid/transaction events.
- Deal-level `all_cash` describes the signed transaction, not every competing
  bid.
- Do not use a final signed all-cash deal to overwrite a competing bid that
  had stock/CVR/earnout terms.

### 10. Advisors / Counsel

This is not core taxonomy, but the graph can handle it cleanly.

Rules:

- Do not keep null deal fields such as `target_legal_counsel` or
  `acquirer_legal_counsel` just because the old schema had them.
- If source-backed, record counsel and bankers as actors with `advises`
  relations.
- Advisor roles should not contaminate bidder counts or bidder economic class.

## Do Not Carry

Do not carry these from the old project:

- US/non-US
- public/private
- Alex's decimal or wedge `BidderID` convention
- old `bid_note` labels as canonical truth
- old flat row schema as canonical data
- comments as canonical facts unless re-grounded to filing source spans
- null counsel fields
- `auction` as model output
- `DropSilent` as a directly extracted filing event
- mixed-to-null collapse from the old reference converter

## Implementation Principles For The Next Agent

1. Update `docs/spec.md` first with the taxonomy decisions.
2. Keep the canonical graph decomposed: actors, events, relations, counts,
   judgments, projections.
3. Do not add fallbacks or backward compatibility layers.
4. Add closed enums where values are known.
5. Fail loudly on impossible schema shapes.
6. Do not let Python infer source-meaning beyond deterministic graph
   projections such as auction and silent fate.
7. Use evidence spans for every source-backed classification.
8. Prefer deterministic projections for derived analysis fields.
9. Remove stale fields/docs/tests that conflict with the new taxonomy.
10. Keep generated artifacts out of source directories.

## Suggested Work Plan

### Phase 1: Spec The Taxonomy

In `docs/spec.md`, define the final taxonomy axes:

- bidder economic class
- bid formality
- initiation side
- process stage / round
- final-round state
- outcome / drop agency / drop reason
- CA/NDA type
- auction derivation
- consideration structure

Make explicit which axes are source-backed canonical facts and which are
deterministic projections.

### Phase 2: Schema Design

Decide where each axis lives:

- actor/group/count/projection for `s/f/mixed`
- bid event for formal/informal
- process/contact event for initiation
- event/process cycle for final-round structure
- outcome events and judgments for drop/fate
- agreement event and actor relations for NDA/ConsortiumCA
- projection summary for auction

Then update Pydantic models and DDL accordingly.

### Phase 3: Extraction Contract

Update the LLM schema and prompt to request only source-backed claims. Avoid
asking the model to emit final projection rows.

The model may classify:

- actor economic class when the filing supports it
- bid formality when evidence supports it
- initiation side when the passage supports it
- final-round facts when narrated
- drop agency/reason when narrated
- CA/NDA type when the parties and agreement scope are clear

The model should not emit:

- auction
- silent-drop derived fates
- unsupported formal-stage status
- guessed economic class

### Phase 4: Reconcile And Project

Reconcile claims into canonical graph rows, then build deterministic projections:

- bidder rows with `s/f/mixed/null`
- formal/informal bid summaries
- advancement/submission summaries
- drop/fate summaries
- auction flag by cycle/deal

Projection should remain inspectable and evidence-linked.

### Phase 5: Tests

Add focused tests for:

- actor/group `s/f/mixed`
- mixed group derived from member composition
- range bid is informal
- formal bid evidence is preserved
- target-initiated private contact is explicit
- bidder unsolicited approach is explicit
- final-round announcement/deadline/extension
- invited vs submitted formal bid separation
- target-excluded vs bidder-withdrew vs nonresponsive
- target-bidder NDA vs consortium CA
- auction derived from target-bidder NDA count only
- `DropSilent`/silent fate derived, not extracted

### Phase 6: Stale Cleanup

After implementation, remove stale schema fields, stale docs, stale fixtures,
and stale tests that encode the old taxonomy. Do not leave compatibility
language around the retired shape.

## Expected End State

The new pipeline should be able to answer these research questions directly:

- Was each bidder strategic, financial, mixed, or unknown?
- Which bids were informal and which were formal?
- Who initiated the process or contact?
- Which bidders reached the final round?
- Which bidders submitted formal bids?
- Who dropped out, who was excluded, and why?
- Which agreements were auction-funnel NDAs versus bidder-bidder consortium
  agreements?
- Was the deal/cycle an auction under the deterministic NDA-count rule?
- What was the bid value/range and consideration structure?

The canonical graph should store the underlying facts. Any row/table resembling
Alex's workbook should be a projection, not the source of truth.
