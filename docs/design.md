# sec_graph Design

## Positioning

`sec_graph` is a clean, independent side project for testing a canonical
graph-style approach to SEC merger-filing extraction. It should define its own
code, state, artifact, prompt, and output contracts.

The starting point is the GPT-Pro v2 greenfield plan in
`docs/references/gptpro_v2/plan/`. That plan is reference material, not a
binding implementation contract. This document is the live local design.

## Research Target

The project should turn SEC merger filing narratives into a structured
representation of takeover sale processes. The current estimator-facing view is
one row per bidder-cycle, but that row should be a deterministic projection from
canonical records rather than the primary extraction format.

The canonical store should support future views over advisors, counsel, board
committees, go-shops, deal terms, process restarts, prior relationships,
consortia, and ambiguity judgments without re-extracting the filing text.

## Initial Inputs

The initial implementation target is local filing ingestion. The repo has four
example markdown files in `data/examples/`:

- `petsmart-inc.md`
- `providence-worcester.md`
- `saks.md`
- `zep.md`

These files are examples, not gold labels. The project can also download SEC
HTML from EDGAR URLs in `seeds.csv` through `scripts/fetch_filings.py`; those
downloads are stored under `data/filings/{deal_slug}/` as raw HTML, sec2md
markdown, per-page JSON, and a manifest.

## Canonical Objects

The first schema should include these object families:

- `CleanFiling`: normalized filing text, document hashes, section index, page
  marker index, paragraph index.
- `SourceSpan`: evidence primitive with filing id, paragraph id, optional page
  marker, character offsets, quote, and hash.
- `Actor`: target, bidder, acquirer, advisor, counsel, committee, shareholder,
  regulator, financing source, or other participant.
- `ProcessCycle`: one economically distinct sale process, restart, or optional
  go-shop segment.
- `Event`: dated narrative fact such as outreach, NDA, proposal, withdrawal,
  rejection, boundary candidate, signing, advisor engagement, or deal-term
  disclosure.
- `EventActorLink`: typed relation between an event and an actor.
- `Judgment`: scoped interpretation such as formal boundary, cycle regime,
  dropout mechanism, valuation comparability, scope validity, alias resolution,
  or no-boundary reason.
- `ParticipationCount`: aggregate count statements that should not be confused
  with individually observed actors.

## Data Flow

1. **Fetch** EDGAR source documents from `seeds.csv` when local raw artifacts do
   not exist.
2. **Convert** SEC HTML to page-aware markdown/JSON with sec2md.
3. **Ingest** markdown filing text into `CleanFiling`, page markers,
   paragraphs, and source-span seeds.
4. **Extract Candidates** from clean text. Early versions may use deterministic
   patterns and hand-authored fixtures before any LLM provider is introduced.
5. **Reconcile** candidates into canonical records with deterministic IDs,
   alias resolution, cycle assignment, and explicit judgments.
6. **Validate** referential integrity, evidence binding, date consistency, bid
   consistency, required judgments, and projection eligibility.
7. **Project Views** such as bidder-cycle rows, cycle summaries, ambiguity
   queues, and review tables.

## Evidence Policy

Canonical objects that assert filing facts must be evidence-backed. The model
for evidence is stricter than a free-text note: an object references one or more
`SourceSpan` ids, and those spans resolve to exact text in a filing.

Python code should own offsets and quote hashing. If an LLM is added later, it
should emit quote text and location hints; the pipeline should resolve and
validate exact spans.

## First Milestone

The first useful milestone is ingestion only:

- Fetch selected filings from EDGAR into `data/filings/`.
- Read all four example filings.
- Preserve raw hashes.
- Parse page markers such as `<!-- PAGE n -->`.
- Build deterministic paragraph ids.
- Emit a source-span seed for each paragraph.
- Write a stable JSON artifact per filing.
- Add tests proving reruns are deterministic.

No bidder extraction is required for the first milestone.

## Design Risks To Resolve

- Exact value sets for judgment fields such as `cycle_visibility`,
  `scope_validity`, `valuation_comparability`, and `cycle_relation`.
- Whether go-shops are represented as cycles, cycle tails, or both.
- How grouped bidders and constituent actors project into bidder-cycle rows
  without double-counting.
- How no-boundary cycles avoid false formal-bid or admission classification.
- How stochastic LLM extraction, if introduced, is isolated from deterministic
  reconciliation and projection.

## Next Agent Task

Start with a small ingestion package under `src/sec_graph/` and tests under
`tests/`. Do not implement extraction, reconciliation, or LLM calls until the
ingestion artifact format is tested and documented.
