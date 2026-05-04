# Combined Taxonomy, Region, And Projection Design

**Date:** 2026-05-03
**Status:** Discussion design, not implementation authority until accepted.
**Combines:**
- `quality_reports/plans/2026-05-03_taxonomy-refactor-plan.md`
- `quality_reports/schema_read/2026-05-03_background-shape-scan.md`

## Executive Decision

Do not implement the taxonomy refactor plan as written. The plan is directionally
right, but the 39-deal scan shows a larger design issue:

```text
wrong or cut-off region
-> static obligations
-> model is asked for global judgments
-> projection looks clean while extraction is structurally underfit
```

The combined design should be:

```text
validated source sections
-> audited evidence regions and region segments
-> applicability-aware obligations
-> Linkflow atomic typed claims
-> Python quote binding and dispositions
-> generic canonical graph with real process cycles
-> deterministic research projections
```

The model proposes source-backed facts. Python owns source coordinates,
applicability, coverage proof, canonicalization, and research projections.

## Layered Value Policy

The taxonomy-only plan tried to use one value policy everywhere. That is too
rigid. Use different policies by layer.

### Source Claims And Canonical Facts

Use `NULL` when the filing does not support a value.

```text
actor_class: s | f | mixed | NULL
bid_formality: formal | informal | NULL
initiation_side: target | bidder | activist | mutual_or_process | NULL
```

`mixed` means source-backed mixture of strategic and financial participants. It
does not mean uncertainty.

Do not add `unknown` or `not_applicable` to provider positive claim fields.

### Applicability Layer

Applicability is separate from coverage result.

```text
applicability_class: universal | conditional | calibration
applicability_status: applicable | not_applicable | ambiguous_applicability
```

Examples:

- buyer group is `not_applicable` in a single strategic-buyer deal unless source
  signals a group, consortium, sponsor club, rollover group, or vehicle chain;
- final round is `not_applicable` in a pure bilateral exclusivity negotiation
  unless source signals final-round admission/submission/best-and-final process;
- go-shop is conditional, never universal.

### Coverage Results

Keep the current coverage result vocabulary:

```text
claims_emitted | no_supported_claim | ambiguous | missed
```

Python assigns `claims_emitted` and `missed`. Linkflow may emit
`no_supported_claim` or `ambiguous` only for applicable obligations with no
claim.

### Research Projections

Projection outputs may use analyst-facing states:

```text
projected_actor_class: s | f | mixed | unknown
final_round_status: advanced | submitted_final_bid | invited_not_submitted |
                    not_advanced | one_bidder_final_negotiation |
                    not_applicable | unknown
process_mode: formal_auction | limited_market_check | targeted_process |
              bilateral_negotiation | single_bidder_negotiation |
              post_signing_go_shop | hostile_or_activist_pressure | unknown
```

`unknown` is allowed only in deterministic projections where the question is
well formed but source-backed facts are insufficient.

## Region Selection Must Come First

The 39-deal scan found only 3 temporary excerpts complete enough to trust. The
production evidence map therefore cannot be a simple heading search.

### Required Region Surfaces

Add or formalize:

- `source_sections`: detected sections from `raw.md`/paragraph spans with raw
  heading, normalized heading, section path, raw line range, paragraph range,
  char range, heading variant, TOC/cross-reference flags, narrative score, and
  end-boundary reason.
- `evidence_region_candidates`: all candidate regions with detection signals,
  anti-signals, validation status, and rejection/ambiguity reason.
- `evidence_regions`: selected logical region with region kind, source
  perspective, document perspective, selection status, completeness status,
  boundary confidence, and source range.
- `region_segments`: ordered physical spans inside one logical region. This is
  needed for tender documents and split narratives.
- `region_signals`: evidence-linked triggers for features such as go-shop,
  buyer group, committee, rollover, hostile pressure, final round, asset-only
  proposal, and tender perspective.
- `coverage_obligation_signals`: links each generated obligation to the signals
  that made it applicable.
- `semantic_windows`: assembled ordered paragraph refs, region/segment ids,
  source-window hash, obligation-set hash, and fixed request mode.

### Region Validation Gates

No Linkflow request should be created unless:

- the selected logical sale-process region validates as chronological narrative;
- TOC, cross-reference, Reasons, Interests, Projections, litigation, covenant,
  and merger-agreement-summary false hits are rejected;
- omitted-heading cases such as Mead Johnson are accepted only when the wrapper
  body validates as the actual process narrative;
- tender-offer documents record buyer/offeror source perspective and target-side
  limits;
- ambiguous region selection blocks `SOUND`.

`SC TO-T` without an `EX-99.(A)(1)(A)` Offer to Purchase remains a hard block,
not a fallback to the cover form.

## Coverage Obligation Design

Delete the static “10 obligations for every deal” shape. Generate obligations
from validated region facts and signals.

### Universal Obligations

Created once a valid sale-process region exists:

- process initiation/main chronology;
- signed buyer or offeror;
- material bid/proposal revisions where present in the narrative;
- cycle boundaries;
- signing or offer-launch event;
- key participation counts when count signals are present.

### Conditional Obligations

Generated only from source triggers:

- final round;
- go-shop/no-shop;
- buyer group/consortium;
- committee/conflict;
- rollover/support/voting agreement;
- financing;
- hostile/interloper pressure;
- asset-only or business-line proposal;
- prior or restarted cycle;
- tender/source-perspective limitation.

### Calibration Obligations

Used for corpus tuning or Alex-facing QA, but non-blocking for `SOUND` and not
canonical truth by themselves.

## Provider Contract

Shrink the provider contract relative to the taxonomy-only plan.

Keep the top-level arrays:

```text
actor_claims
actor_relation_claims
event_claims
bid_claims
participation_count_claims
coverage_results
```

Do not add provider-side `judgment_claims` in the baseline. Do not ask Linkflow
for auction flags, silent fate, global final-round conclusions, bidder rows,
source offsets, `unknown`, or `not_applicable`.

### Claim Families

`actor_claims` should capture source labels, anonymized labels, actor kind, and
source-supported `s/f/mixed/null` actor class only when supported.

`actor_relation_claims` should cover:

```text
member_of
affiliate_of
controls
acquisition_vehicle_of
advises
finances
supports
voting_support_party_of
rollover_holder_of
committee_member_of
committee_of
recused_from
conflicted_with
```

`event_claims` should cover source chronology:

```text
approach/outreach
activist pressure
board or committee action
NDA/CA execution
diligence access
management presentation
bid instruction
final-bid request
final-round admission or non-admission
withdrawal/exclusion/no-response
exclusivity
signing
go-shop start/end
support/voting/rollover/financing event
standstill waiver
hostile/public proposal or consent solicitation
```

`bid_claims` need richer proposal facts:

```text
bidder
date
value/range/unit
consideration type and component detail
proposal scope
oral/written status
revision sequence or prior bid link where supported
best/final statement
certainty or condition facts
regulatory/financing terms
expiration or contingency
```

`participation_count_claims` should capture contacted, NDA/CA, IOI, diligence,
management presentation, preliminary bid, final bid, and go-shop outcome counts
by cycle/stage and actor class.

### Linkflow Schema Constraints

Keep the Linkflow-safe subset:

- no `$defs`, `oneOf`, `allOf`, `anyOf`;
- no defaults, formats, regex patterns, min/max constraints, or dynamic maps;
- no schema-valued `additionalProperties`;
- required fields with nullable scalar semantics;
- one scalar `coverage_obligation_id` per claim;
- strict top-level arrays.

## Generic Graph Expansion

Keep the generic graph. Do not add deal-specific tables.

### Process Cycles

`process_cycles` must become a real unit:

- cycle kind;
- cycle sequence;
- boundary evidence;
- optional parent/restart relation;
- source-backed start/end;
- source-perspective limits.

This is required for `zep`, `immucor`, `young-innovations`, `b-m-c-software`,
`advent-software`, `sanderson-farms`, and similar multi-cycle filings.

### Proposal Scope

Bid/proposal events need `proposal_scope`:

```text
whole_company
asset_only
business_line
target_acquisition
financing_alternative
cross_conditional
NULL
```

Asset-only and business-line proposals should not become baseline whole-company
bidder rows unless a projection explicitly includes them.

### Committees And Conflicts

Do not collapse all committees into `special_committee`. Preserve committee
type and authority:

```text
special committee
transaction committee
strategic transaction committee
executive committee
finance committee
independent/disinterested directors
ad hoc committee
```

Conflicts are relation/event facts: management rollover, no rollover, shareholder
rollover, controller support, voting agreement, founder/family conflict,
recusal, advisor conflict, employment agreement, consulting agreement,
non-compete, TRA/economic allocation, and management-contact restriction.

## Deterministic Research Projections

Analyst variables should be exported through projections, not stored as model
answers.

Recommended projections:

- `bidder_cycle_panel`: actor-cycle row with projected class, group membership,
  NDA status, initial/final bid values, bid formality, final-round admission,
  final-round submission, observed fate, silent fate, drop reason, consideration,
  proposal scope, and auction-cycle flag.
- `cycle_process_summary`: process formality, initiation side, auction flag,
  final-round shape, go-shop/no-shop outcome, signed-buyer summary, source
  perspective, phase boundaries, and applicability judgments.
- `bid_event_panel`: one row per bid/revision with value/range, consideration,
  proposal scope, oral/written status, revision chain, best/final flag,
  certainty/condition fields, and formality.
- `participation_funnel_panel`: contacted, NDA/CA, diligence, management
  presentation, IOI, preliminary bid, final bid, and go-shop outcome counts by
  cycle, phase, and actor class.
- `relationship_conflict_panel`: buyer group, financing, rollover, support,
  voting, advisor, committee, controller, recusal, and conflict relations.
- `deal_protection_panel`: go-shop/no-shop, DADW/standstill waiver, matching
  rights, termination fee, excluded-party status, and post-signing outcome.
- `applicability_panel`: whether buyer group, final round, go-shop, committee,
  rollover/conflict, asset-only proposal, or tender-source-perspective
  obligations were universal, triggered, not applicable, ambiguous, missed, or
  calibration-only.

## Deterministic Rules

Auction:

- cycle-scoped;
- count distinct source-backed `target_bidder_nda` participants;
- exclude bidder-bidder consortium CAs, support/voting agreements, rollover
  agreements, and post-signing go-shop contacts unless projecting a separate
  go-shop market-check outcome.

Silent fate:

- projection-only;
- derive only when actor-cycle has auction-funnel target-bidder NDA status and
  no later observed bid, withdrawal, exclusion, no-response, final submission,
  signing, or other fate in the same cycle.

Final round:

- separate final-bid request, admission, non-admission, submission, best/final
  statement, and one-bidder final negotiation;
- never reuse `admitted=true` to mean "has any bid."

S/F/mixed:

- source facts can be `s/f/mixed/null`;
- projected actor-cycle class can be `s/f/mixed/unknown`;
- `mixed` requires source-backed mixed membership, not uncertainty.

## Scope Reduction

Defer these from the baseline:

- provider-based validator pass;
- N=3 multi-pass model voting;
- known-actor registry;
- reviewer UI.

Keep local deterministic validation and minimal ambiguity/review lifecycle. An
LLM validator and registry may be designed later, but including them now would
make the pipeline more opaque before the region/coverage/graph foundations are
stable.

## Acceptance Gate

The old three-deal gate is not enough for this combined design.

Minimum credible gate:

- offline section-selection regression over the 39-deal raw ranges documented in
  `quality_reports/schema_read/2026-05-03_background-shape-scan.md`;
- offline regression fixtures for:
  - `zep` for multiple cycles;
  - `medivation` for tender/source perspective;
  - `mead-johnson-nutrition-co` for omitted heading and bilateral strategic;
  - `petsmart-inc` for activism/buyer group;
  - `saks` for alternative target-acquisition lane and go-shop;
  - `polypore-international-inc` for business-line/cross-conditional deal;
  - `cephalon-inc` for hostile pressure and asset-only alternative;
  - `habit-restaurants-inc` for formal auction and rich counts.
- live Linkflow proof on at least five deals:
  - `petsmart-inc`;
  - `mac-gray`;
  - `providence-worcester`;
  - `zep`;
  - `medivation`.

Before any 400-deal run, also require a 30-deal pilot with frozen schema/request
modes, cost/runtime envelope, progress/resume proof, and stale-plan cleanup.

## Implementation Order

1. Authority cleanup:
   - copy accepted combined decisions into `docs/spec.md`;
   - copy provider-facing behavior into `docs/llm-interface.md`;
   - mark stale plans/session logs as historical or delete them.

2. Region and applicability foundation:
   - `source_sections`;
   - `evidence_region_candidates`;
   - `region_segments`;
   - `region_signals`;
   - applicability-aware `coverage_obligations`;
   - scan regression tests.

3. LLM contract simplification:
   - atomic typed claims only;
   - no provider judgments;
   - strict Linkflow-safe schema;
   - prompt says "extract facts, not global classifications."

4. Generic graph expansion:
   - real process cycle fields;
   - richer event/relation/proposal subtypes;
   - participation counts by cycle/stage;
   - minimal ambiguity/review state.

5. Deterministic projections:
   - bidder cycle panel;
   - cycle process summary;
   - bid event panel;
   - participation funnel;
   - relationship/conflict;
   - deal protection;
   - applicability panel.

6. Validation and proof:
   - no projection without cycle scope;
   - no final-round collapse;
   - no LLM-derived auction/silent fate;
   - no asset-only proposal in whole-company bidder projection unless explicit;
   - no `SOUND` with ambiguous region/applicability or important missed
     obligations.

7. Five-deal live proof, then 30-deal pilot, then 400-deal corpus.

## Stale/Conflict Cleanup Targets

Known stale or conflicting surfaces to address before implementation:

- `quality_reports/session_logs/README.md` still points to deleted May 2 plans
  as current authority.
- `quality_reports/plans/2026-05-03_full-redesign-plan.md` conflicts with the
  hard-reset authority.
- `quality_reports/plans/2026-05-03_linkflow-p7-background-high-implementation-plan.md`
  preserves static 10-obligation logic and old coverage wording.
- Current implementation still has `financial`/`strategic` actor-class literals
  and static obligations in `src/sec_graph/extract/evidence_map.py`.
- Current `bidder_rows` projection collapses admission into `admitted=true` for
  any actor-cycle with bid evidence and uses min/max bid values as initial/final
  approximations.

Do not shim these. Replace them under the combined design.
