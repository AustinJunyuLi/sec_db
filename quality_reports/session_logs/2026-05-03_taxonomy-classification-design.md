# Session Log — Taxonomy Classification Design

**Date:** 2026-05-03
**Status:** Standalone spec retracted; supplementary material to GPT's
handoff produced instead

## Goal

Determine whether the sec_graph pipeline's classification taxonomy is sound
relative to Alex Gorbenko's hand-coded ground truth, and design any required
schema additions to close gaps that matter analytically.

## Context

- Following Round 7 comparison: Path B (Linkflow gpt-5.5 + P7 + Background-only,
  on mac-gray) found to capture all of Alex's 13 bids (with richer range
  encoding), more events (35 vs 21), and corrected two of Alex's date errors.
- User asked for a systematic taxonomy review to determine whether our schema
  is structurally sound enough to replace Alex's hand-coding for the wider
  corpus.

## Approach

1. Dispatched two parallel Explore agents:
   - Agent A enumerated every column / enum value in Alex's reference workbook
     (`/Users/austinli/bids_try/reference/deal_details_Alex_2026.xlsx`) plus
     codebook (`CollectionInstructions_Alex_2026.pdf`).
   - Agent B enumerated every Literal / closed enum across our schema models
     (`src/sec_graph/schema/models/`, `docs/spec.md`).

2. Synthesized 9 gaps where Alex codes something we don't capture, ranked
   HIGH / MEDIUM / LOW.

3. User narrowed scope: care about s/f/mixed (drop nonUS, drop public/private),
   formal/informal, target/bidder initiation, final round (collapsed). Drop
   Alex's fragmentation.

4. Worked four dimensions systematically: bid_formality, sale_trigger, final
   round facets, actor_class on Actor. Produced concrete enum proposals.

5. Discussed extraction-mechanism split: Python deterministic (region selection,
   quote verification, derivation) vs LLM-emitted (inference). Concluded LLM
   handles classification, Python handles validation and derivation.

6. Worked through three remaining items: deal-level structure (all_cash,
   auction_process, consideration_type enum), validator architecture
   (multi-pass + confidence + validator pass), named-entity registry.

7. Produced binding spec at
   `quality_reports/specs/2026-05-03_classification-taxonomy-spec.md` (later
   retracted — see step 8).

8. User pointed at GPT's prior handoff at
   `quality_reports/plans/2026-05-03_taxonomy-refactor-handoff.md` and
   asked for a comparison. GPT's handoff is more research-complete on
   taxonomy: covers 10 axes (vs my 4), models initiation per-event, treats
   auction as DETERMINISTIC (Python-derived from NDA count, not
   LLM-emitted), distinguishes NDA types (target-bidder vs bidder-bidder
   consortium CA vs rollover/support), decomposes drop into agency × reason,
   treats silent fate as derived projection, permits null where source
   doesn't support a value, separates per-bidder advancement from
   per-bidder submission, lists go-shop stage. My standalone spec had two
   structural mistakes: auction should be derived not extracted, and null
   should be permitted for source gaps.

9. User directed deletion of the standalone spec. Replaced with a
   supplement document at
   `quality_reports/plans/2026-05-03_taxonomy-refactor-supplement.md`
   that adds the implementation-side material GPT's handoff did not
   specify: validator architecture, named-entity registry, cohort
   inheritance contract, Pydantic model location map, file-level migration
   sequence, operational cost envelope, and a closed-enum/components
   tradeoff for `consideration_type`. The supplement explicitly defers to
   the handoff on all taxonomy decisions.

## Authority Chain (Final)

- `quality_reports/plans/2026-05-03_taxonomy-refactor-handoff.md` —
  binding taxonomy authority (GPT's spec). Defines all axes, value sets,
  and architectural rules (auction-as-derived, NDA types, drop matrix,
  silent fate, per-event initiation).
- `quality_reports/plans/2026-05-03_taxonomy-refactor-supplement.md` —
  supplement, layered on top. Adds validator architecture, named-entity
  registry, cohort inheritance, Pydantic model map, file-level migration
  sequence, cost envelope.
- The supplement defers to the handoff on every taxonomy decision; it
  changes none of them.

## Decisions Encoded in Supplement

| Topic | Decision |
|---|---|
| Confidence emission | Closed 3-value {high, medium, low} paired with every non-null classification |
| Multi-pass N | 3 |
| Multi-pass routing | Applied to bid_formality, initiation_side, drop_reason, agreement_kind, final-round advancement |
| Validator pass | Blocking before reconcile; queues judgment on disagreement |
| Registry format | YAML, single file at `data/registry/known_actors.yaml` |
| Registry bootstrap | Corpus-driven seed from proof corpus extraction (Option B) |
| Cohort inheritance | LLM emits both individual and cohort actor_class; Python validates consistency, does not auto-derive |
| consideration_type encoding | Two options offered (composable booleans vs closed enum + complex_other escape); decision deferred |
| Migration | 15-step ordered sequence; spec.md → models → DDL → schema fn → prompt → registry → multi-pass/validator → projections → version bumps → re-extract → tests |

## Deferred / Dropped

- IB engagement events as new event_subtypes — deferred (medium priority)
- Drop reason subtypes (DropM/DropBelowM/etc.) — deferred (derivable)
- Date precision flag — deferred (low priority)
- nonUS bidder flag — DROPPED (user scope)
- public/private flag — DROPPED (user scope)
- Final Round 8-way fragmentation — DROPPED (replaced by orthogonal facets)

## Open Questions

1. Approval pending on the spec before merge into `docs/spec.md` §1A.
2. Should `final_round_extended` carry a separate confidence field? Currently
   not specified — implicitly inherits closed-enum reliability of event_subtype.
3. Validator pass implementation: where in `src/sec_graph/extract/llm/` does
   the validator agent live? Not specified in spec.
4. Multi-pass orchestration: synchronous within a single `python -m sec_graph
   extract` invocation, or queued via a separate orchestration layer?

## Blockers

None — spec is complete and self-consistent. Next action is user review and
approval, then implementation per §15 migration sequence.

## Artifacts Produced

- `quality_reports/plans/2026-05-03_taxonomy-refactor-supplement.md`
  (supplement to GPT's handoff, 10 sections, ~3K words)
- This session log
- (Retracted: standalone spec at `quality_reports/specs/...` — deleted
  per user request after the handoff comparison)

## Cross-References

- Round 7 comparison appears in
  `quality_reports/llm_calibration/2026-05-03_linkflow-probe-log.md`
  (empirical basis for validator architecture).
- The active hard-cleanse repair plan
  (`quality_reports/plans/2026-05-02_stale-scaffold-hard-cleanse-repair-plan.md`)
  must not conflict with the migration sequence in §15. Confirmed compatible:
  the cleanse phases and this spec's migration are sequential, not overlapping.
