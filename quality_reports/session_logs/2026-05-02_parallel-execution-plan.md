# Session Log: Parallel Execution Plan

**Date:** 2026-05-02
**Author:** Claude Code (Opus 4.7) for Austin Li
**Branch:** `main`
**Triggering prompt:** "scan through the codebase, especially `/Users/austinli/Projects/sec_graph/docs`. understand the current design and the advice from previous attempts. then /ultraplan for a parallelized development execution workflow"

## Goal

Produce an executable plan that turns the approved modular architecture (now `docs/spec.md`) into a parallel build sequence, respecting the construction advice (now folded into spec §17/§18) and prior-attempt lessons (now `docs/prior-pipeline-lessons.md`).

## Approach

1. Mapped the repo: only Stage 0 done (edgar.py + 4 examples). No DuckDB, no schema, no canonical store yet.
2. Read the architecture spec, construction advice, and lessons doc directly.
3. Dispatched two parallel sub-agents:
   - One to summarize the existing 3700-line Stage 1 plan as parallelizable build units.
   - One to synthesize the gptpro_v2 reference plan (adopt vs reject vs adapt) — including `derive_views.py` projection contract.
4. Drafted a parallel-execution overlay that respects the architecture spec but adds:
   - Stage 1A vs 1B slicing (per construction advice — splits the plan's 16 tasks)
   - Three explicit construction-advice corrections to land in Phase 0 (span coordinate basis, span parentage, count discriminator)
   - Worktree mechanics (one per track)
   - Disjoint-write table-ownership matrix
   - Sync gates G0-G5 with verifiable conditions
   - Risks & mitigations

## Output

`quality_reports/plans/2026-05-02_parallel-execution-plan.md` (~420 lines).

Status: DRAFT. Awaiting user approval before Phase 0 execution.

## Doc Cleanse (same session, follow-on)

After plan delivered, user asked for a doc-staleness cleanse: "single source of truth for spec and executing plan". Executed:

- **Created** `docs/spec.md` — consolidates the approved modular-architecture spec + construction-advice slicing addendum (§17) + construction principles (§18). One source of truth for design.
- **Moved** lessons doc to `docs/prior-pipeline-lessons.md` (was `docs/architecture/lessons-from-prior-extraction-pipeline.md`).
- **Deleted** `docs/references/` (whole tree, including gptpro_v2 packet), `docs/architecture/` (construction-advice folded into spec), `docs/superpowers/` (old Stage 1 plan superseded; spec moved out), `docs/design.md` (superseded by `spec.md`).
- **Updated cross-refs** in CLAUDE.md, AGENTS.md, README.md, data/examples/README.md, this plan, this session log.
- **Final docs/ shape:** just `spec.md` and `prior-pipeline-lessons.md`.

## Key Decisions

- **Reordered Stage 1 internal task list** to land construction-advice corrections (`span_basis`, `span_kind`, `parent_evidence_id`, `created_by_stage` on `SourceSpan`; `actor_creation_required` on `ParticipationCount`) **before** any other model — these are non-negotiable invariants that must be designed in, not retrofitted.
- **Cut 8 auxiliary tables** from Phase 1 (advisor_engagements, legal_counsel_engagements, board_committees, deal_terms, group_memberships, prior_relationships, bid_normalizations, cycle_phase_assignments). They land when a fixture demands them, per construction advice.
- **Cut `ExtractionCandidate` from Stage 1 entirely** — it's an extract-stage concern, not schema scaffolding.
- **Three worktrees, three tracks, merge order B → C₁ → A.** A merges last because it touches the most files and Track C₂ depends on its merge.
- **CLI dispatcher pattern** (per-track files: `cli/{ingest,validate,project,extract}_cmd.py`) to avoid `cli.py` merge conflicts.

## Open Questions

- User to confirm whether to execute Phase 0 immediately on approval, or pause for review of plan first.
- Phase 5 (Stage 8 LLM interface) is correctly gated; no decisions needed yet.
- Reviewer-override persistence (Stage 9) flagged in spec §10.2 — Phase 1 schema accommodates either resolution; concrete decision deferred.

## Next

- gptpro_v2 sub-agent was cancelled (parallel Bash errored mid-fan-out); no follow-up needed since the gptpro_v2 packet was deleted in the doc cleanse.
- Plan presented; doc cleanse complete; awaiting approval.
- On approval, begin Phase 0 Task 1 (move `edgar.py` → `fetch/edgar.py`) on a `stage-1a-evidence-store` branch.
