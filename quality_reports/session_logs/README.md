# Session Logs Index

This directory holds **point-in-time proof logs** from past pipeline gates and
offline-proof runs. The logs are evidence that a specific gate passed at a
specific hour against the then-current command surface. They are NOT current
authority and they are NOT instructions for what to run next.

## Current Authority

- `docs/spec.md` is the binding design and schema authority. §1A is the
  binding deployable schema contract.
- `quality_reports/plans/2026-05-02_stale-scaffold-hard-cleanse-repair-plan.md`
  is the executing cleanup-and-repair plan, in force until every phase inside
  it is complete.
- `quality_reports/plans/2026-05-02_deployable-canonical-pipeline-goal.md`
  is the goal-handoff document for live deployable proof, paired with its
  companion implementation plan
  `quality_reports/plans/2026-05-02_deployable-canonical-pipeline-plan.md`.

## Retained Logs

| Log file | What passed |
|---|---|
| `2026-05-02_g0-stage-1a.md` | Stage 1A evidence-store gate: Pydantic models, DDL, ID helpers, smoke ingestion, rerun determinism. |
| `2026-05-02_g1-stage-1b.md` | Stage 1B canonical-skeleton gate: Deal/Cycle/Actor/Event/Link/Judgment/ParticipationCount tables and hand-authored smoke canonical fixture. |
| `2026-05-02_g2-phase-2-merge.md` | Phase 2 merge gate: Track A (ingest) merged onto main with all four example filings ingesting deterministically. |
| `2026-05-02_g3-track-c2-real-extraction.md` | Track C2 gate: deterministic rule extraction against the four real example filings. |
| `2026-05-02_g4-stage-7-reconcile-real.md` | Stage 7 gate: real reconcile pipeline producing canonical records and bidder-cycle rows for the four examples. |
| `2026-05-02_g5-stage-8-linkflow.md` | Stage 8 gate: opt-in Linkflow GPT-5.5 extraction adapter passing offline tests under the strict streaming + Python-owned-offset contract. |
| `2026-05-02_reference9_offline-proof.md` | Offline reference-nine proof: nine reference filings ingested and rule-extracted without live Linkflow calls. |

## Warning

Stale commands inside retained logs MUST NOT be rerun without first checking
the current command surface. The CLI has changed since several of these logs
were written. Before reusing any command from a retained log, run:

```bash
python -m sec_graph --help
python -m sec_graph <subcommand> --help
```

and reconcile the historical command against the current help output. In
particular, `--run-id`, `--run-dir`, `--projection`, and `--fresh` flags may
have been added or moved since the retained log was written.

If a retained log conflicts with current authority, current authority wins.
