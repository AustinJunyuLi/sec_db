# Construction Advice For The Canonical Pipeline

**Purpose.** This note is the practical companion to
`docs/architecture/lessons-from-prior-extraction-pipeline.md`. The lesson memo
explains why the new pipeline should be canonical-store first. This note says
how to build that direction without turning Stage 1 into an oversized schema
exercise.

**Position.** The architecture is directionally right. The risk is not that the
design is too ambitious in concept; the risk is implementing too much future
surface before the first real database row exists.

## Bottom Line

Build the canonical pipeline in the smallest slices that prove real data flow.
Do not start by implementing every future table just because the eventual model
names it. Start by proving that filing text can enter DuckDB with stable
identity, stable evidence spans, and reproducible run metadata. Then add
canonical records only as soon as a fixture needs them.

The construction test is simple:

> Can we rerun from the same input bytes and get the same rows, same source-span
> hashes, same IDs, and same run-scoped outputs?

If yes, the foundation is real. If no, adding more tables will only hide the
problem.

## Keep The Architecture, Trim The First Build

The approved architecture separates:

- `fetch`: raw SEC artifacts;
- `ingest`: paragraphs and source spans;
- `extract`: evidence-bound candidates;
- `reconcile`: canonical actors, events, cycles, and judgments;
- `validate`: deterministic integrity checks;
- `project`: estimator-facing views.

Keep that separation. But do not implement the full canonical universe in the
first coding pass. A schema file that can create 25 tables is not useful unless
the first four tables already preserve evidence correctly.

## Lean Stage 1

Stage 1 should prove the database foundation, not the whole research ontology.

Implement first:

- `filings`
- `paragraphs`
- `spans`
- `run_metadata`
- deterministic ID helpers
- quote/hash utilities
- schema/version constants
- a smoke filing fixture
- DuckDB create/insert/fetch tests
- a rerun determinism test over the smoke fixture

This gives later modules a stable surface to build on. It also tests the
hardest invariant early: evidence must point back to exact filing text.

Do not implement extraction, reconciliation, validation, projection, LLM calls,
or rich auxiliary tables in this slice.

## Lean Stage 1B

After the DB foundation works, add only the minimal canonical skeleton needed to
walk one hand-authored example end to end:

- `deals`
- `process_cycles`
- `actors`
- `events`
- `event_actor_links`
- `judgments`
- `participation_counts`

This is enough to test the core idea: estimator rows will eventually be
projected from canonical objects, not extracted directly. It is also enough to
represent the lessons that matter most from the prior pipeline: actors are not
events, counts are not actors, and judgments are not facts.

## Defer Until A Fixture Demands Them

The architecture can name these concepts, but they do not all need immediate
tables and full round-trip tests:

- advisor engagements;
- legal counsel engagements;
- board committees;
- deal terms;
- group memberships beyond one minimal example;
- prior relationships;
- bid normalizations beyond one simple numeric bid;
- cycle phase assignments beyond the first projection test.

Add each when a concrete fixture exercises it. This keeps the build honest. A
table introduced by a fixture has a reason to exist, expected rows, and testable
behavior.

## Non-Negotiables That Are Not Overengineering

Some pieces may look like ceremony, but they are load-bearing:

### Evidence Coordinates

Decide the coordinate system before writing many tables. A span should make
clear whether its offsets refer to raw markdown, cleaned text, or both. If
cleaning can change offsets, store both raw and clean coordinates or store an
explicit `text_version` / `span_basis`.

This is not optional. Without clear coordinates, quote hashes become review
decorations instead of evidence.

### Span Parentage

Ingest should create paragraph-level spans. Later extraction may create
sentence- or clause-level spans inside those paragraphs. A narrower span should
carry parentage, such as `parent_evidence_id`, plus `span_kind` and
`created_by_stage`.

This prevents the system from mixing human-cleaned paragraph evidence and
rule/model-created tight evidence as if they were the same artifact.

### Participation Counts

Counts deserve first-class representation early. A filing may say that 15
potentially interested financial buyers signed confidentiality agreements
without naming all 15. The system must preserve that fact without inventing 15
actors prematurely.

`participation_counts` should be able to represent:

- count type;
- count value;
- count unit;
- process stage;
- bidder subtype split when available;
- evidence span;
- whether actor creation is required, deferred, or projection-only.

The final anonymous-actor policy can be decided later. The schema should not
force the decision too early.

### Run Metadata

Every derived row should be explainable by run metadata: input hashes, parser
version, schema version, and stage versions. A single working DuckDB is fine,
but snapshots and row hashes should make runs comparable.

This is the cheap way to avoid stale-artifact confusion later.

## Avoid These Traps

### Schema Theater

Do not confuse "all tables create successfully" with "the data model works."
Creation tests are necessary, but they are weak. The stronger test is a fixture
that writes rows, reads them back, verifies evidence hashes, and reruns
deterministically.

### Premature Auxiliary Tables

Advisor, counsel, board, term, and prior-relationship tables are valuable, but
they are not the first bottleneck. If they arrive before paragraph/span
evidence is solid, they will distract from the foundation.

### Rebuilding The Old Flat Row Inside DuckDB

Do not create one giant canonical event row that owns actor identity, bidder
lifecycle, bid value, formal-stage admission, dropout, and projection status.
That would recreate the old failure mode with a SQL backend.

Keep these separate:

- event facts;
- actor identity;
- actor-event links;
- participation counts;
- group relationships;
- judgments;
- projection rows.

### Implicit Cross-Module SQL Ownership

A shared DuckDB can become a hidden monolith. Each module should have explicit
read/write ownership. For example:

- `ingest` writes `filings`, `paragraphs`, and seed `spans`;
- `extract` writes `candidates` and derived spans;
- `reconcile` writes canonical tables;
- `validate` reads canonical tables and writes validation artifacts;
- `project` reads canonical tables and writes exported views.

If a module needs another module's internals, change the schema contract rather
than reaching around it.

### Treating Reference Projection Code As Canonical Truth

`docs/references/gptpro_v2/derive_views.py` is useful for projection semantics.
It should not dictate canonical facts. For example, whether a bidder is
`admitted` should not be canonically inferred only from whether a post-boundary
proposal row exists. The canonical store should retain admission decisions,
boundary judgments, dropout judgments, and phase assignments separately.

## Recommended Build Shape

### Slice 1: Evidence Store

Goal: one smoke filing becomes `filings`, `paragraphs`, `spans`, and
`run_metadata` rows.

Acceptance:

- all IDs deterministic;
- paragraph hashes stable;
- span quote hashes verify against stored text;
- rerun produces identical row-content hashes;
- tests pass without network access.

### Slice 2: One Hand-Authored Canonical Walkthrough

Goal: one tiny synthetic deal has a target, two bidders, one count, one cycle,
two bid events, one boundary judgment, and one dropout judgment.

Acceptance:

- every canonical row references a valid span;
- every foreign key resolves;
- the count can exist without forcing extra actors;
- a simple bidder-cycle projection can identify which records would feed a row.

### Slice 3: First Real Ingest

Goal: ingest the four example filings into paragraph/span rows.

Acceptance:

- page markers preserved;
- known aliases survive cleaning;
- section labels are useful but unmatched text is not lost;
- rerun row hashes are stable.

Only after these slices should the project broaden into richer canonical
objects, extraction rules, reconciliation, and projection.

## Advice To Future Agents

When a plan asks for a broad schema, shrink the implementation to the smallest
testable data path unless Austin explicitly asks for the full surface now.

When adding a table, ask:

1. What filing fact or construction fact does this table preserve?
2. Which fixture will create at least one row?
3. Which later module consumes it?
4. What invariant would fail if this table were wrong?

If those answers are vague, defer the table.

When adding a field, ask:

1. Is it factual, interpretive, or runtime metadata?
2. Does it need evidence?
3. Is null ambiguous? If yes, where is the null reason stored?
4. Does it belong in a judgment instead?

If the answer is "maybe," prefer a judgment or a later fixture-driven addition.

## What I Would Change Before Executing The Current Stage 1 Plan

The existing Stage 1 plan is useful, but it should be revised before execution:

- Remove the stale baseline-commit task if the repo already has a baseline
  commit.
- Split Stage 1 into `1A evidence store` and `1B minimal canonical skeleton`.
- Move rich auxiliary tables out of the first implementation slice.
- Add explicit span coordinate and span parentage requirements.
- Add explicit module table-ownership rules.
- Keep `participation_counts` in the early skeleton.
- Do not require a hand-authored fixture that exercises every future table.
  Require one that exercises the core canonical path.

This keeps the system serious without making it heavy.

## Final Guidance

The right goal is not a complete ontology on day one. The right goal is a small
database that cannot lie about where its evidence came from. Once that exists,
the rest of the pipeline can grow without repeating the old flat-row mistakes.
