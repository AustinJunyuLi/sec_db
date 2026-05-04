# Reference-9 Schema Refactor Goal Spec

**Date:** 2026-05-03
**Status:** Goal-ready execution spec.
**Audience:** Clean-slate `/goal` agent working in `/Users/austinli/Projects/sec_graph`.
**Scope:** Next refactor of region selection, applicability-aware extraction, canonical graph, deterministic projections, and live Reference-9 Linkflow acceptance.

## Goal

Refactor the pipeline so it can run the nine reference deals through Linkflow
without relying on static global obligations, overfit bidder-group fields, or
model-generated research judgments.

The target shape is:

```text
validated SEC filing source sections
-> audited sale-process evidence regions and segments
-> applicability-aware coverage obligations
-> Linkflow atomic typed claims only
-> Python quote binding and claim dispositions
-> generic canonical graph with process cycles
-> deterministic analyst projections
-> Reference-9 live proof artifacts
```

The design should make underextraction visible before projection. It should not
make the output look clean by filling unsupported fields.

## Binding Principles

1. No fallbacks.
2. No backward compatibility layers.
3. No provider-owned source offsets.
4. No model-generated projection rows.
5. No static "every deal must answer every taxonomy question" obligation set.
6. No silent acceptance when section selection, applicability, quote binding, or
   canonicalization is ambiguous.
7. Linkflow GPT-5.5 is the live provider. Default reasoning effort is `high`.
8. Secrets stay in environment variables or ignored `.env` files. Do not write
   keys into tracked files or command logs.

## Active Inputs

Read these before implementation:

- `AGENTS.md`
- `docs/spec.md`
- `docs/llm-interface.md`
- `quality_reports/plans/2026-05-03_combined-taxonomy-region-design.md`
- `quality_reports/schema_read/2026-05-03_background-shape-scan.md`
- `quality_reports/plans/2026-05-03_taxonomy-refactor-plan.md`

Use the taxonomy plan as a draft source of field names, not as the execution
authority. The combined taxonomy/region design supersedes it where they differ.

## Reference-9 Acceptance Set

The live acceptance run must include exactly these slugs:

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

Each deal stresses a different shape:

| Deal | Acceptance stress |
|---|---|
| `providence-worcester` | Formal target-run process after earlier informal contacts; mixed strategic and financial outreach; explicit stage counts; final narrowed finalists; committee/conflict facts. |
| `medivation` | Tender-offer source perspective; selected filing is the Offer to Purchase exhibit, not a proxy; target-side process must be represented with source limitations. |
| `imprivata` | Sponsor-led process with committee and conflict signals; needs source-backed actors, relations, and initiation/finality projection. |
| `zep` | Earlier strategic cycle and later financial-sponsor signing cycle; must not invent buyer group composition where none exists. |
| `petsmart-inc` | Sponsor consortium and rollover/support features; needs actor relations rather than a single flat buyer label. |
| `penford` | Bilateral or limited market-check shape; final-round obligations should be conditional, not universal. |
| `mac-gray` | Buyer group and acquisition vehicles; member/affiliate/vehicle relations matter more than a flat bidder string. |
| `saks` | Go-shop and alternative-target process signals; needs process-cycle separation. |
| `stec` | Asset-only or business-line proposal plus signed transaction; proposal scope and finality must be explicit. |

## Layered Value Policy

### Source Claims

Source claims should carry only values supported by quote text. They may be
nullable. They must not use analyst placeholders.

```text
actor_class: s | f | mixed | null
bid_formality: formal | informal | null
initiation_side: target | bidder | activist | mutual_or_process | null
proposal_scope: whole_company | asset_or_business_line | minority_or_investment | other | null
```

`mixed` means the source describes a mixed strategic/financial group or mixed
population. It does not mean uncertainty.

### Applicability

Applicability is separate from extraction coverage.

```text
applicability_class: universal | conditional | calibration
applicability_status: applicable | not_applicable | ambiguous_applicability
```

Examples:

- buyer group is `not_applicable` for a single strategic buyer unless source
  signals a consortium, club, sponsor group, rollover group, or vehicle chain;
- final round is `not_applicable` for a pure bilateral negotiation unless source
  signals best-and-final, final round, final bidders, finalist invitation, or
  final bid submission;
- go-shop is conditional and should exist only when the source has go-shop or
  post-signing solicitation signals.

### Coverage Results

Coverage answers whether an applicable obligation was satisfied.

```text
claims_emitted | no_supported_claim | ambiguous | missed
```

Linkflow may emit `no_supported_claim` or `ambiguous` for applicable obligations
that produced no claims. Python assigns `claims_emitted` and `missed`.

`not_applicable` is not a coverage result. It belongs only in the applicability
layer and analyst-facing projections.

### Canonical Facts

Canonical graph rows should keep nullable source-backed fields. Do not coerce
unsupported values to `unknown`.

### Projections

Projection views may use analyst-facing values because the projection question is
well formed even when the source is incomplete:

```text
projected_actor_class: s | f | mixed | unknown
final_round_status:
  advanced
  submitted_final_bid
  invited_not_submitted
  not_advanced
  one_bidder_final_negotiation
  not_applicable
  unknown
process_mode:
  formal_auction
  limited_market_check
  targeted_process
  bilateral_negotiation
  single_bidder_negotiation
  post_signing_go_shop
  hostile_or_activist_pressure
  unknown
```

## Region And Window Contract

The pipeline must prove it found the actual chronological sale-process narrative
before creating a Linkflow request.

Required surfaces:

- `source_sections`: all detected source sections with heading, normalized
  heading, section path, line range, paragraph range, char range, heading
  variant, false-hit flags, narrative score, and end-boundary reason.
- `evidence_region_candidates`: candidate sale-process regions with detection
  signals, anti-signals, validation status, and rejection or ambiguity reason.
- `evidence_regions`: selected logical sale-process region with kind, source
  perspective, document perspective, completeness status, boundary confidence,
  and source range.
- `region_segments`: ordered physical spans for one logical region, because
  tender offers and split narratives may require multiple adjacent spans.
- `region_signals`: source-backed feature triggers, including final round,
  buyer group, go-shop, committee, rollover, support/voting agreement, hostile
  pressure, tender perspective, and asset-only proposal.
- `coverage_obligation_signals`: links each generated obligation to the signals
  that made it applicable.
- `semantic_windows`: ordered paragraph refs, region ids, segment ids, source
  hash, obligation-set hash, and fixed request mode.

Selection must reject table-of-contents entries, cross-references, reasons
sections, interests sections, projections, litigation summaries, covenant
summaries, and merger-agreement descriptions. A wrapper section such as `THE
MERGER` may be accepted only when its body validates as the sale-process
chronology.

Tender-offer filings must still fail loudly when no selected
`EX-99.(A)(1)(A)` Offer to Purchase exhibit exists. Do not fallback to the cover
form.

## Obligation Contract

Delete the static global obligation list. Generate obligations from selected
region facts and source-backed signals.

Universal obligations after a valid sale-process region exists:

- process initiation and chronology;
- signed buyer or offeror;
- material proposals or bid revisions described by the narrative;
- cycle boundaries;
- signing, agreement, or offer-launch event;
- participation counts only when count signals exist.

Conditional obligations:

- final round;
- go-shop/no-shop;
- buyer group or consortium;
- committee or conflict;
- rollover, support, or voting agreement;
- financing;
- hostile or interloper pressure;
- asset-only or business-line proposal;
- prior cycle, restarted cycle, or separated post-signing cycle;
- tender source-perspective limitation.

Calibration obligations:

- useful for QA and corpus tuning;
- non-blocking for `SOUND`;
- not canonical truth by themselves.

Rules-only extraction may create mechanical claims and coverage diagnostics, but
it cannot produce a `SOUND` verdict for a live acceptance run.

## Linkflow Contract

The provider response should stay small and typed:

```text
actor_claims
actor_relation_claims
event_claims
bid_claims
participation_count_claims
coverage_results
```

Do not add provider-side `judgment_claims` in this refactor. Python derives
judgments and projections after quote binding and canonicalization.

Every positive claim must include:

- `coverage_obligation_id`;
- `quote_text`;
- source-supported scalar values;
- no source offsets;
- no projection states such as `unknown` or `not_applicable`.

Every Linkflow request must include:

- selected region summary;
- source perspective and document perspective;
- exact semantic window paragraphs;
- generated obligation list;
- instruction to emit only atomic claims;
- instruction to prefer multiple small claims over one global narrative answer.

## Canonical Graph Contract

The canonical graph must represent source meaning before analyst projection.

Required concepts:

- filings;
- source spans;
- evidence regions and segments;
- actors;
- actor aliases;
- actor relations;
- process cycles;
- events;
- event-actor links;
- bids/proposals/revisions;
- participation counts;
- claim dispositions;
- judgments;
- projection units and projection views.

Process cycles are first-class. A deal may have a prior exploratory cycle, a
formal target-run cycle, a post-signing go-shop cycle, a hostile/interloper
cycle, or a tender-offer cycle. Zep and Saks should not be collapsed into one
flat chronology if the source describes distinct cycles.

Actor relations should carry group structure instead of forcing every buyer into
one string. Required relation types:

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
```

Event and bid facts should preserve:

- event type;
- process cycle;
- event date or date text;
- proposal scope;
- bid amount or non-price consideration where supported;
- formality where supported;
- initiation side where supported;
- finality where supported;
- actor links and roles.

## Projection Contract

Projection views are deterministic views over the canonical graph. They are not
provider outputs.

Required projections for the Reference-9 acceptance proof:

- bidder-cycle panel;
- deal-cycle process summary;
- bid/proposal event panel;
- participation funnel panel;
- relationship/conflict panel;
- deal-protection and go-shop panel;
- applicability/coverage panel.

The bidder-cycle panel must be actor-cycle scoped. It must not mark a participant
as a bidder merely because the actor appears somewhere in the narrative. It must
distinguish:

- contacted;
- entered confidentiality agreement;
- submitted IOI;
- submitted LOI;
- submitted revised proposal;
- advanced to final process;
- submitted final bid;
- signed buyer;
- withdrawn, rejected, or declined.

## Verdict Contract

A run may be `SOUND` only when:

- a sale-process region was selected and validated;
- ambiguous region selection is absent;
- all applicable blocking obligations are either `claims_emitted` or explicitly
  `no_supported_claim` with sufficient evidence-window coverage;
- positive claims have quote binding;
- rejected claims are dispositioned visibly;
- canonical rows pass integrity checks;
- projections are derived from canonical facts;
- the Reference-9 live run writes proof artifacts.

A run must fail or produce a non-sound review verdict when:

- region selection is ambiguous;
- a tender filing lacks a selected Offer to Purchase exhibit;
- source quotes cannot be resolved;
- Linkflow returns schema-invalid data;
- applicability cannot be decided for a blocking obligation;
- projections require facts that have no canonical support.

## Required Proof Artifacts

The Reference-9 live run must write a run directory under `runs/` containing:

- raw request manifests without secrets;
- provider response metadata;
- per-deal evidence-region audit;
- per-deal applicability audit;
- per-deal coverage ledger;
- claim disposition ledger;
- canonical graph exports;
- projection exports;
- validation verdicts;
- token and cost summary;
- proof summary over all nine deals.

The proof summary must list each reference slug, the selected region status, live
provider status, claim counts by family, rejected-claim counts, canonical row
counts, projection row counts, blocking verdict, and operator review notes.

## Stale Cleanup Contract

The implementing agent must remove or rewrite stale artifacts that still encode:

- static universal obligations;
- paragraph-local Linkflow extraction;
- provider judgment claims;
- `financial` / `strategic` naming where the accepted taxonomy is `f` / `s`;
- old three-deal-only acceptance gates;
- old plans that claim execution authority after this spec supersedes them;
- docs that mention a clean run without the Reference-9 proof.

Cleanup is part of the refactor, not a polish pass.

## Stop Conditions

Stop and report rather than patching around the issue if:

- Linkflow rejects the strict schema after shrinking it to the accepted typed
  arrays;
- the source selector cannot distinguish a real narrative from false heading
  hits on the reference set;
- medivation cannot be represented with tender source perspective;
- zep requires inventing buyer-group facts to pass;
- projections can pass while the coverage ledger is incomplete;
- any test writes secrets or generated outputs into tracked source paths.
