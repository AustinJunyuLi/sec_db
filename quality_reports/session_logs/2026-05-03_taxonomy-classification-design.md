# Session Log — Taxonomy Classification Design

**Date:** 2026-05-03
**Status:** Historical design log. The split handoff/supplement pair was later
merged and corrected in
`quality_reports/plans/2026-05-03_taxonomy-refactor-plan.md`.

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
   - Agent A enumerated the external hand-coded reference taxonomy and codebook
     used for research comparison.
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

8. User pointed at GPT's prior handoff, since superseded by
   `quality_reports/plans/2026-05-03_taxonomy-refactor-plan.md`, and
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

9. User directed deletion of the standalone spec. A temporary supplement was
   produced, then later merged with the handoff and corrected in
   `quality_reports/plans/2026-05-03_taxonomy-refactor-plan.md`.

## Authority Chain Correction

This log originally overstated the authority of the handoff/supplement pair.
That was wrong. The active repository authority remains:

- `docs/superpowers/specs/2026-05-03-pipeline-hard-reset-design.md`
- `docs/spec.md`
- `docs/llm-interface.md`

The merged taxonomy plan is an implementation plan. It is not binding schema
authority until the accepted taxonomy is copied into `docs/spec.md`, and it is
not binding provider-interface authority until validator/multi-pass behavior is
copied into `docs/llm-interface.md`.

## Decisions Preserved In The Merged Plan

| Topic | Decision |
|---|---|
| Actor class | Closed values `s`, `f`, `mixed`, and null; do not preserve `financial`/`strategic` aliases |
| Null policy | Use null for unsupported classifications; do not add `unknown` enum values |
| Multi-pass N | 3 |
| Multi-pass routing | Applied to bid_formality, initiation_side, drop_reason, agreement_kind, final-round advancement |
| Validator pass | Provider code lives under `src/sec_graph/extract/llm/`; validator output is stored locally, not inside primary provider claim payloads |
| Registry | Curation aid only; registry hit cannot silently override filing-backed evidence |
| Cohort inheritance | LLM emits both individual and cohort actor_class; Python validates consistency, does not auto-derive |
| consideration_type encoding | Closed enum plus optional detail; `complex_other` requires evidence |
| Migration | spec.md → llm-interface.md → models/DDL → evidence map/schema/prompt/convert → validator/registry → reconcile/validate/project → versions → tests → live proof |

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

- The merged plan must be reviewed and accepted.
- The accepted taxonomy must be copied into `docs/spec.md`.
- The validator/multi-pass provider contract must be copied into
  `docs/llm-interface.md`.
- Implementation must not start from the retired split handoff/supplement pair.

## Artifacts Produced

- `quality_reports/plans/2026-05-03_taxonomy-refactor-plan.md`
  (merged and corrected taxonomy refactor plan)
- This session log
- (Retracted: standalone spec at `quality_reports/specs/...` — deleted
  per user request after the handoff comparison)

## Cross-References

- Round 7 comparison appears in
  `quality_reports/llm_calibration/2026-05-03_linkflow-probe-log.md`
  (empirical basis for validator architecture).
- The hard-reset execution authority is
  `docs/superpowers/specs/2026-05-03-pipeline-hard-reset-design.md`.
