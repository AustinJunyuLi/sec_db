# Parallel Execution Plan: sec_graph

**Status:** DRAFT (2026-05-02)
**Author:** Claude Code (Opus 4.7) on behalf of Austin Li
**Scope:** A parallel-execution overlay on the approved modular architecture.
**Reads with:** `docs/spec.md` (the binding spec, including §17 Stage 1 slicing and §18 construction principles), `docs/prior-pipeline-lessons.md` (failure modes informing the spec).
**Supersedes:** the prior `docs/superpowers/plans/2026-05-02-stage-1-schema-scaffolding.md` (deleted in the 2026-05-02 doc cleanse). Refines Stage 1's internal sequencing and Stages 2-7's inter-stage choreography.

---

## 0. Why This Plan Exists

The spec declares three parallel tracks (§13: A=ingest, B=schema validation path, C=extract rules) that fan out after Stage 1 lands, plus the Stage 1A/1B slicing (§17). What it does not declare:

1. **How Stage 1 itself parallelizes internally.** The schema-scaffolding work has a wide parallel cluster (independent model files, no cross-imports) — most calendar time lives in that cluster.
2. **The exact handoff artifacts** between Track A / B / C — the contract that prevents two tracks from rewriting the same DuckDB column or the same file region.
3. **Worktree mechanics** — branch names, merge order, conflict isolation rules.
4. **Sync gates** — the verifiable conditions each track must clear before merge.

This plan answers all four.

---

## 1. Critical Path & DAG

```
PHASE 0 ─────────────────────────► PHASE 1 ──┬─► TRACK A (ingest)        ──┐
  Stage 1A                           Stage 1B │   Stage 2                    │
  evidence store                     canonical│                              │
  + advice corrections               skeleton ├─► TRACK B (schema-walk) ─────┼─► PHASE 4
  + smoke filing fixture             + smoke  │   Stages 3 → 4 → 5           │   Stage 7
  (sequential, single agent)         canonical│                              │   reconcile real
                                     fixture  └─► TRACK C₁ (smoke)      ─┐   │   (single agent)
                                              │   Stage 6 smoke         │   │
                                              │                          │   │
                                              │   TRACK C₂ (real)       ─┴───┘
                                              │   Stage 6 four examples
                                              │   (depends on Track A)
                                              │
                                              ↓
                                        PHASE 5 (gated)
                                        Stage 8 brainstorm → LLM interface
```

**Critical path:** Stage 1A → Stage 1B → Track A → Track C₂ → Stage 7. Tracks B and C₁ run inside the shadow of Track A. A solo developer reverses Track B and Track C₁ as scheduling allows; they do not extend total duration.

---

## 2. Phase Map (What Runs When)

| Phase | Stage(s) | Concurrency | Blocks | Blocked by |
|-------|---------|-------------|--------|-----------|
| **0** | 1A (evidence store + corrections + smoke MD) | sequential, 1 agent | Phase 1 | nothing (Stage 0 done) |
| **1** | 1B (canonical skeleton + smoke canonical fixture) | sequential, 1 agent | Phase 2 | Phase 0 |
| **2** | Track A (Stage 2) ‖ Track B (Stages 3→4→5) ‖ Track C₁ (Stage 6 smoke) | 3 worktrees, 3 agents | Phase 3, Phase 4 | Phase 1 |
| **3** | Track C₂ (Stage 6 four examples) | 1 agent (worktree, possibly the same as C₁) | Phase 4 | Phase 2 (Track A only) |
| **4** | Stage 7 (reconcile real) | sequential, 1 agent | Phase 5 | Phases 2 + 3 all green |
| **5** | Stage 8 (brainstorm → LLM interface) | gated; brainstorm first | — | Phase 4 |

---

## 3. Phase 0 — Stage 1A: Evidence Store + Advice Corrections

**Goal:** A DuckDB foundation that cannot lie about where evidence came from. Single agent. Must land cleanly before Phase 1 begins.

### 3.1 Tasks (in order)

1. **Move `edgar.py` → `fetch/edgar.py`.** Update `tests/test_edgar.py` import, leave `scripts/fetch_filings.py` as a 5-line shim into `sec_graph.fetch.edgar.main`. Tests that pass today must still pass.
2. **Add `duckdb`, `pydantic>=2` to `pyproject.toml`.** Create `src/sec_graph/schema/{__init__,versions,ids,evidence,db}.py` skeletons.
3. **Stage version constants** (`schema/versions.py`): `PARSER_VERSION`, `INGEST_VERSION`, `EXTRACT_VERSION`, `RECONCILE_VERSION`, `VALIDATE_VERSION`, `PROJECT_VERSION`, `SCHEMA_VERSION`. Each starts at 1. Tests assert presence and integer type.
4. **Deterministic ID helpers** (`schema/ids.py`): `make_id(slug, type_, sequence) -> str` returning `{slug}_{type}_{sequence}`; sequence allocator helper for stable per-(slug, type) numbering. Tests cover stability across reruns.
5. **Evidence helpers** (`schema/evidence.py`): `quote_hash(text: str) -> str` (sha256 hex), `validate_quote(filing_text, char_start, char_end, expected_hash) -> bool`. Tests cover unicode, multi-byte, empty.
6. **DB primitives** (`schema/db.py`): `connect(path: str | Path | None = None)`, `apply_ddl(conn, ddl_text)`. Tests use `:memory:`.
7. **Filings models + DDL** (`schema/models/filings.py`): Pydantic `CleanFiling`, `Section`, `Paragraph`, `SourceSpan`. **The four `SourceSpan` non-negotiables from spec §17.2 land here:**
   - `SourceSpan.span_basis: Literal["raw_md", "clean_text"]` — declares which coordinate system `char_start`/`char_end` refer to.
   - `SourceSpan.span_kind: Literal["paragraph_seed", "sentence", "clause", "phrase"]` — distinguishes ingest seeds from extract-time tighter spans.
   - `SourceSpan.parent_evidence_id: str | None` — narrower spans reference their paragraph parent.
   - `SourceSpan.created_by_stage: Literal["ingest", "extract"]` — provenance of the span.
   The DDL co-locates as a Python string constant inside `models/filings.py`.
8. **Runtime model + DDL** (`schema/models/runtime.py`): `RunMetadata` with `run_id`, all stage version fields, input hashes, timestamp.
9. **Schema initialization** (`schema/schema_init.py`): `init_schema(conn) -> None` that applies every DDL constant in dependency order. Re-export everything from `schema/__init__.py`.
10. **Smoke filing markdown fixture** (`tests/fixtures/smoke_filing.md`): a ~40-60 line synthetic merger filing exercising every section heading we plan to detect, two `<!-- PAGE n -->` markers, a `Party A` / `Party B` alias, a `15 financial buyers` count, a numeric bid value, a no-boundary cycle marker. Static — handcrafted, not generated.
11. **Stage 1A acceptance test** (`tests/test_stage1a_evidence_store.py`):
    - `init_schema(:memory:)` creates the four evidence-layer tables.
    - Insert one `CleanFiling`, three `Paragraph`s, one paragraph-`SourceSpan` per paragraph, one `RunMetadata`. Round-trip Pydantic ↔ row.
    - `quote_hash(paragraph.text) == span.quote_hash` for every span.
    - **Determinism gate:** run the entire smoke ingestion twice; row content hashes must match across the two runs.

### 3.2 Acceptance for Phase 0 (gates Phase 1)

- `pytest tests/` green (existing 5 tests still pass + new evidence-layer tests).
- `init_schema(connect(':memory:'))` creates exactly: `filings`, `paragraphs`, `spans`, `run_metadata`. Nothing else.
- `make_id('petsmart', 'actor', 3) == 'petsmart_actor_3'`.
- `tests/fixtures/smoke_filing.md` exists, has ≥2 page markers, parses as valid markdown.
- Determinism gate passes.

### 3.3 Tasks Deliberately Cut From Phase 0

(All to land in Phase 1 or later, per spec §17.4 "Defer Until A Fixture Demands Them".)

- `ExtractionCandidate` (Stage 1 plan Task 8) — extract-stage concern. **Out of Stage 1 entirely.**
- All canonical models (Deal, ProcessCycle, Actor, Event, EventActorLink, Judgment, ParticipationCount) — moved to Phase 1.
- All 8 auxiliary tables (advisor_engagements, legal_counsel_engagements, board_committees, deal_terms, group_memberships, prior_relationships, bid_normalizations, cycle_phase_assignments) — deferred until a fixture demands them per spec §17.4.

---

## 4. Phase 1 — Stage 1B: Canonical Skeleton + Hand-Authored Smoke Canonical

**Goal:** A canonical-table walkthrough on the smoke filing that exercises the *core* lessons (actors ≠ events, counts ≠ actors, judgments ≠ facts) without trying to be the whole research ontology. Single agent.

### 4.1 Tasks

1. **Canonical core models + DDL** (`schema/models/canonical.py`): `Deal`, `ProcessCycle`, `Actor`, `Event`, `EventActorLink`. Per-model unit tests for round-trip. Each row carries `run_id`.
2. **Judgment model + DDL** (`schema/models/judgments.py`): `Judgment` with `supersedes_judgment_id` for the append-only chain. Unit test asserts a 3-link supersession chain resolves to the latest non-superseded row.
3. **Participation count model + DDL** (`schema/models/participation_counts.py`): `ParticipationCount` with the spec §17.2 actor-creation discriminator — `actor_creation_required: Literal["required", "deferred", "projection_only"]`. Plus `count_type`, `count_value`, `count_unit`, `process_stage`, `bidder_subtype_split` (optional dict), `evidence_ids` (list[str]).
4. **Schema-init extension:** `init_schema` now creates 13 tables total (4 evidence + 9 canonical). Update top-level `schema/__init__.py` exports.
5. **Module-ownership policy** (incorporated into `docs/spec.md` §3 + plan §9): explicit table-by-table read/write matrix per module:
   ```
   ingest  : writes filings, paragraphs, spans (paragraph_seed only)
   extract : writes spans (sentence/clause/phrase only), candidates
   reconcile: writes deals, process_cycles, actors, events, event_actor_links, judgments, participation_counts
   validate : reads canonical; writes runs/{run_id}/validation_report.json
   project  : reads canonical; writes runs/{run_id}/*.jsonl + .csv + .md
   ```
   Encoded as a Markdown table; enforced socially in Phase 2 (no module reaches around it).
6. **Smoke canonical fixture** (`tests/fixtures/smoke_canonical.json`): the smoke filing's hand-authored canonical record set. Must include: one target, two bidders, one process cycle, two bid events, one boundary judgment, one dropout judgment, one participation count covering an unnamed cohort. **Every row references at least one valid `evidence_id` resolving to a span in the smoke filing's `paragraphs`/`spans` tables.**
7. **Stage 1B acceptance test** (`tests/test_stage1b_canonical_walkthrough.py`):
   - Load smoke canonical fixture via Pydantic.
   - Insert into a fresh `:memory:` DuckDB.
   - Verify every FK resolves (every `actor_id` reference exists in `actors`; every `evidence_id` exists in `spans`; every `cycle_id` exists in `process_cycles`).
   - Verify every quote_hash on referenced spans matches the smoke filing bytes.
   - Verify the supersedes-chain resolution helper.
   - Verify `ParticipationCount` survives without forcing extra `Actor` rows when `actor_creation_required = "deferred"`.

### 4.2 Acceptance for Phase 1 (gates Phase 2 fan-out)

- 13 tables creatable, all round-trip green.
- Smoke canonical fixture FK-clean.
- Module-ownership doc committed and referenced from `CLAUDE.md`.
- The smoke canonical fixture is **the contract** Tracks B and C consume.

---

## 5. Phase 2 — Three-Track Fan-Out

After Phase 1 lands on `main`, three tracks run in parallel in separate worktrees. Each track owns a disjoint file set; merges into `main` are independent.

### 5.1 Worktree mechanics

Per the `superpowers:using-git-worktrees` skill, three worktrees:

```
~/Projects/sec_graph                    main           (integrator)
~/Projects/sec_graph-track-a            track-a/ingest
~/Projects/sec_graph-track-b            track-b/validate-project
~/Projects/sec_graph-track-c            track-c/extract-smoke
```

Branch naming: `track-{a,b,c}/{module-cluster}`. Each worktree starts from the `main` commit at the close of Phase 1.

**Merge order:** B → C₁ → A. Track A merges last because it touches the most files (ingest/cleaning rules will likely accrete) and because Track C₂ depends on its merge.

### 5.2 Track A — Ingest (Stage 2)

**Worktree:** `sec_graph-track-a` on `track-a/ingest`.
**Owns (writes):** `src/sec_graph/ingest/{__init__,cleaning,paragraphs,sections,spans}.py`, `tests/test_ingest_*.py`, `tests/fixtures/canonical/{slug}.json` ingest assertions.
**Reads but does not write:** schema models, smoke canonical fixture, `data/examples/{slug}.md`, `data/filings/{slug}/raw.md`.
**DuckDB tables it writes:** `filings`, `paragraphs`, `spans` (paragraph_seed only).
**Does NOT touch:** Any extract/reconcile/validate/project file. No canonical-table writes.

**Tasks:**
1. **Cleaning module** (`ingest/cleaning.py`): explicit pattern set for printer-command lines (`COMMAND=...`), ZEQ banners (`ZEQ.=N,SEQ=...`), repeated `Table of Contents` lines, isolated folio numbers. Every removal logged with original `(char_start, char_end)` and the rule_id that matched. Conservative: when in doubt, keep.
2. **Section detection** (`ingest/sections.py`): heading vocabulary in `ingest/section_vocabulary.py`. Fuzzy match (tolerant of leading `**COMMAND=...**` style noise). Unmatched ranges → `unknown_section`.
3. **Paragraph splitting** (`ingest/paragraphs.py`): paragraph boundary rule (blank-line-delimited, page-marker-respecting, deterministic). Each paragraph gets a stable ID `{slug}_para_{NNN}` and a `paragraph_hash`.
4. **Span seeding** (`ingest/spans.py`): one paragraph-level `SourceSpan` per paragraph at `span_kind="paragraph_seed"`, `span_basis="raw_md"`, `created_by_stage="ingest"`, `parent_evidence_id=None`. **Both** raw and clean coordinates are stored (raw is authoritative; clean is a derived view) — see corrections in Phase 0.
5. **CLI subcommand** (`cli.py` `ingest` subcommand): `python -m sec_graph ingest --slug X | --all`. Writes to `data/pipeline.duckdb`.
6. **Acceptance tests:**
   - All four examples ingest without error.
   - Page markers preserved: PetSmart 29-33, Providence 35-43, Zep 35-42, Saks 31-36 are all in the `paragraphs` rows.
   - In-text aliases survive cleaning verbatim: `Industry Participant`, `Party A`, `G&W`, `Party X`, `Sponsor A`, `Company H`.
   - Determinism: rerun produces identical paragraph IDs and hashes.
   - Counts smoke-test: a paragraph containing `fifty potential buyers (comprising twenty-eight strategic buyers and twenty-two financial buyers...)` (Zep) survives ingest verbatim.

**Acceptance for Track A merge to main:** all of the above pass; no candidate, canonical, validation, or projection code introduced.

### 5.3 Track B — Schema-Walk (Stages 3 → 4 → 5)

**Worktree:** `sec_graph-track-b` on `track-b/validate-project`.
**Owns (writes):** `src/sec_graph/{validate,project}/*.py`, `tests/test_validate_*.py`, `tests/test_project_*.py`, `tests/fixtures/canonical/{slug}.json` for one example filing (Stage 3 hand-authored).
**Reads but does not write:** schema models, smoke canonical fixture, ingest tables (mock-loaded for tests; does not invoke Track A).
**DuckDB tables it writes:** none in `pipeline.duckdb`. Writes `runs/{run_id}/*` artifacts only.
**Does NOT touch:** ingest, extract, or reconcile code paths.

This track is sequential within itself. Three sub-stages:

#### 5.3.1 Stage 3 — Reconcile skeleton (one hand-authored example)

Hand-author `tests/fixtures/canonical/petsmart.json` (PetSmart is the largest example; biggest test surface). The fixture must:
- Use only canonical tables that exist in Phase 1 (no auxiliaries; if PetSmart needs them, capture as a deferred TODO and use the closest primitive that the Phase-1 schema allows — e.g., a buyer-group represented via grouped `Actor`s + `EventActorLink`s rather than a `group_memberships` table).
- Reference real PetSmart paragraphs/spans **only after Track A merges**. During parallel work, use placeholder `evidence_id` strings and a fake spans table seeded into a `:memory:` DB for tests.

**Acceptance:** `pytest tests/test_reconcile_skeleton.py` green; FK-clean; every canonical row references at least one (placeholder) evidence_id.

#### 5.3.2 Stage 4 — Validate

Implement `validate/integrity.py` (hard checks: FK, evidence binding, date sanity, bid bounds, required-judgments-per-cycle, ID format) and `validate/flags.py` (soft flags: low-confidence judgments, alternative_value populated, no-boundary cycles, hidden individual bids, alias ambiguity, unknown bidder subtypes).

**Acceptance:**
- Hand-authored PetSmart fixture (Stage 3) passes all hard checks.
- An intentionally broken fixture (`tests/fixtures/canonical/_broken.json`: missing FK, broken quote_hash, negative duration, etc.) fails with the *correct* error class for each break.
- Soft-flag CSV emits to `runs/{run_id}/ambiguity_queue.csv`.

#### 5.3.3 Stage 5 — Project

Implement `project/bidder_rows.py` and `project/summaries.py` per spec §3.7. Output `runs/{run_id}/bidder_rows.jsonl` + companion files.

**Projection contract** is fully defined in spec §3.7 (output field list and projection-construction rules including `bI`, `bF`, `admitted`, `w_logwidth`, `T`, `confidence_min` derivation). Per spec §18.1, projection must NOT canonically infer `admitted` only from "post-boundary proposal exists." Read it from an explicit `judgments` row when present.

**Acceptance:**
- PetSmart hand-authored canonical produces an expected `bidder_rows.jsonl` matching a manually curated golden set.
- `run_memo.md` generated.

**Acceptance for Track B merge to main:** all three sub-stages green; no extract or reconcile (real) code introduced.

### 5.4 Track C₁ — Extract Rules (smoke milestone)

**Worktree:** `sec_graph-track-c` on `track-c/extract-smoke`.
**Owns (writes):** `src/sec_graph/extract/{__init__,rules/__init__,rules/actors,rules/events,rules/bids}.py`, `tests/test_extract_rules_*.py`, `tests/fixtures/extract/smoke_candidates.json` (golden candidate set on smoke filing).
**Reads but does not write:** schema models, smoke filing markdown, smoke canonical fixture (for sanity).
**Does NOT touch:** ingest, reconcile, validate, project.

**Tasks:**
1. **`extract/rules/actors.py`**: regex passes for actor mentions and aliases. Deterministic. Each candidate carries `evidence_ids` (list, points to spans), `confidence`, `dependencies` (list).
2. **`extract/rules/events.py`**: dated event patterns (signing, NDA execution, indication of interest, withdrawal, rejection, board meeting).
3. **`extract/rules/bids.py`**: bid-value extraction (`$X.XX per share`, `$NNN million in cash`, lower/upper ranges).
4. **Span emission:** every candidate creates one or more `SourceSpan` rows at `span_kind="sentence"` or `"clause"`, `parent_evidence_id` pointing to the paragraph seed. **Per Phase 0 corrections**, this is now structurally enforceable.
5. **CLI subcommand:** `python -m sec_graph extract --slug X | --all` (real-filing path stubbed; smoke-only path real).
6. **Acceptance test:**
   - Run extract against the smoke filing.
   - Compare candidates to `tests/fixtures/extract/smoke_candidates.json` (golden, hand-curated).
   - Every candidate has at least one `evidence_id`.
   - Determinism: rerun produces identical candidates.

**Acceptance for Track C₁ merge to main:** smoke-only milestone green; the four-example milestone is Phase 3.

### 5.5 Track-internal verification protocol

Each track's solo agent must, before requesting merge:

1. Run `pytest tests/` from the worktree root; all green.
2. Run `pytest tests/ -x --ff` twice in a row to confirm determinism on tests that include reruns.
3. Confirm no file outside the track's owned set is modified (`git diff main --name-only` against the ownership list above).
4. Confirm no other track's tables are written.
5. Self-review acceptance criteria.

---

## 6. Phase 3 — Track C₂: Extract Rules on Real Filings

After Track A merges, the same Track C agent (or a fresh one) extends the extraction rules to all four real example filings.

**Worktree:** reuse `sec_graph-track-c` on `track-c/extract-real` (rebased onto post-Track-A `main`).

**Tasks:**
1. Run `python -m sec_graph ingest --all` to populate `data/pipeline.duckdb` with real paragraphs/spans.
2. Run `python -m sec_graph extract --all` against the four examples.
3. Hand-curate golden candidate sets for **PetSmart and Saks** (the two with the richest narratives). Acceptance compares extract output to golden.
4. Identify regex patterns that produce false positives on Providence/Zep but did not appear in smoke; refine `extract/rules/*` accordingly. **Constraint:** keep rules conservative — favor recall + evidence over silencing edge cases. Per spec §18: keep early rules conservative and make unknowns visible.

**Acceptance:** PetSmart + Saks candidates match golden; no actor extracted without span; no candidate without evidence_id; rerun deterministic.

---

## 7. Phase 4 — Stage 7: Reconcile Real

**Single agent on `main` (no worktree).** Replaces Track B's hand-authored canonical fixtures with rule-extracted candidates → canonical records.

**Tasks:**
1. **`reconcile/aliases.py`** — alias merging (`Party A` continuity across the document; `Industry Participant` deduplication; named-then-anonymized handling).
2. **`reconcile/cycles.py`** — cycle assignment (one cycle per economically distinct sale process; restart heuristic; go-shop boundary policy decision and encoding).
3. **`reconcile/boundaries.py`** — formal-boundary judgment construction (including null boundaries with marker events; boundary quality grades).
4. **`reconcile/judgments.py`** — judgment emission for every cycle (formal_boundary, cycle_regime, cycle_visibility, cycle_relation, dropout_mechanism). Append-only.
5. **`reconcile/grouped_bidders.py`** — grouped-bidder representation (Actor + EventActorLink rather than auxiliary tables, until a fixture demands more).
6. **`reconcile/anonymous_actors.py`** — anonymous-actor creation policy: only create when projection requires row-level completeness; otherwise leave as ParticipationCount.
7. **CLI subcommand:** `python -m sec_graph reconcile`.
8. **Acceptance:**
   - All four example filings produce complete canonical record sets.
   - Bidder-cycle rows match hand-curated expected set per filing.
   - All FKs resolve; all evidence_ids point to valid spans; required judgments exist for every cycle.
   - The pipeline-end-to-end command `python -m sec_graph run --all` runs cleanly: ingest → extract → reconcile → validate → project. Snapshot at end.

**Sync gate:** Phase 4 must close before Phase 5 begins.

---

## 8. Phase 5 — Stage 8: LLM Brainstorm + Provider Interface

**Gated. No code until brainstorm produces an approved interface spec.**

**Step 1:** Run `superpowers:brainstorming` with seed prompt:
> "Design a provider-neutral LLM extraction interface for sec_graph that emits evidence-bound candidates (not canonical rows), is deterministic-output-respecting, feature-flagged, and isolates provider behavior. Constraints from `docs/prior-pipeline-lessons.md` §7 ('Provider constraints leaked into system design') and §'Do not make the LLM the canonical writer.'"

**Step 2:** Write an LLM-interface addendum to `docs/spec.md` or a separate `docs/llm-interface.md` (decided at brainstorm time).

**Step 3:** Produce a Stage-8 plan via `superpowers:writing-plans`.

**Step 4:** Implement under `extract/llm/`. Behind a feature flag. Determinism test: with flag off, extract output is bit-identical to Stage 7's rules-only output.

---

## 9. Cross-Track Contracts (the disjoint-write matrix)

| Table | Created by | Written by (only) | Read by |
|-------|-----------|-------------------|---------|
| `filings` | Phase 0 | Track A | All later |
| `paragraphs` | Phase 0 | Track A | All later |
| `spans` (`paragraph_seed`) | Phase 0 | Track A | All later |
| `spans` (sentence/clause/phrase) | Phase 0 | Track C / Stage 7 | Validate, Project |
| `run_metadata` | Phase 0 | Every CLI subcommand | Validate, Project |
| `deals` | Phase 1 | Stage 7 reconcile | Validate, Project |
| `process_cycles` | Phase 1 | Stage 7 reconcile | Validate, Project |
| `actors` | Phase 1 | Stage 7 reconcile | Validate, Project |
| `events` | Phase 1 | Stage 7 reconcile | Validate, Project |
| `event_actor_links` | Phase 1 | Stage 7 reconcile | Validate, Project |
| `judgments` | Phase 1 | Stage 7 reconcile (+ Stage 9 reviewer chain, future) | Validate, Project |
| `participation_counts` | Phase 1 | Stage 7 reconcile | Validate, Project |
| `candidates` | Phase 2 (Track C₁) | Track C / Stage 7-prep | Stage 7 |
| `runs/{run_id}/*` | Phase 2 (Track B) | Validate, Project | Reviewer (future) |

If two tracks need to write the same table, the merge order resolves it; otherwise the write must move into Stage 7 (single agent).

---

## 10. Sync Gates

| Gate | Triggered when | Verifiable by |
|------|----------------|---------------|
| **G0** | Phase 0 acceptance criteria pass | `pytest tests/test_stage1a_evidence_store.py` green; determinism gate green |
| **G1** | Phase 1 acceptance criteria pass | `pytest tests/test_stage1b_canonical_walkthrough.py` green; smoke canonical FK-clean |
| **G2** | All three tracks ready to merge | Each track's verification protocol §5.5 passes; `git merge --no-ff` clean for B → C₁ → A |
| **G3** | Track A merged + Track C₂ green | `python -m sec_graph extract --all` candidates match golden |
| **G4** | Stage 7 acceptance | `python -m sec_graph run --all` end-to-end green; bidder rows match hand-curated expected |
| **G5** | LLM interface spec approved | Spec doc reviewed; brainstorm log captured |

Each gate gets one row in `quality_reports/session_logs/` with the date and the verifying command(s).

---

## 11. Risks & Mitigations

| Risk | Likelihood | Mitigation |
|------|-----------|-----------|
| Schema gap discovered mid-Phase-2 | Medium | Phase 0/1 corrections explicitly encode span coordinates, parentage, count discriminator. Smoke canonical fixture exercises the contract end-to-end before fan-out. If a gap still appears, **bump SCHEMA_VERSION, drop pipeline.duckdb, restart Phase 2** (cheap because raw filings are immutable). |
| Track A's cleaning rules eat a real evidence span | Medium | Cleaning is conservative + every removal logs `(char_start, char_end, rule_id)`. Test fixtures cover Zep printer-command line + Saks folio + Providence ToC line. New patterns require explicit review before commit. |
| Track B uses placeholder evidence_ids that don't survive merge | Low | Phase-1 smoke canonical uses *real* spans from the smoke filing. PetSmart hand-authored canonical (Stage 3) uses placeholders during parallel work, then is rebased after Track A merges and the placeholders are replaced via a deterministic helper. |
| Worktree merge conflict on `cli.py` | High | Each track's CLI subcommand lands on a different file: Track A adds `cli/ingest_cmd.py`, Track B adds `cli/validate_cmd.py` + `cli/project_cmd.py`, Track C adds `cli/extract_cmd.py`. `cli.py` itself is a thin dispatcher updated only at merge time, by the integrator. |
| Track C₂ regex changes silently regress smoke acceptance | Medium | CI runs both smoke and four-example golden checks together; rerun-determinism test catches non-determinism. |
| Solo-contributor reality (one human) | Medium | Tracks B and C₁ are sequential within Track-A's shadow; the human runs them serially when calendar requires. Worktrees still let each track's branch state stay isolated. |
| Reviewer-override persistence (Stage 9 problem) leaks into our schema | Low | Phase 1 doesn't declare `judgments` exclusively rewritten by reconcile; the table tolerates rows added outside the pipeline run via a future `reviewer_overrides.jsonl` re-application step. |
| Provider/LLM design leaks into Stage 7 | Low | Phase 5 is gated; brainstorm-first; no provider SDK in `pyproject.toml` until then. |
| Auto Mode runs Phase 0 → Phase 1 without a checkpoint | Medium | Insert an explicit user-approval gate at G0 and G1. Auto Mode within a phase is fine; cross-phase requires human OK on the merge commit's diff. |

---

## 12. Agent Assignments (suggested)

| Phase / Track | Agent | Role |
|---------------|-------|------|
| Phase 0 | main session (you, the orchestrator) or 1 sub-agent in main worktree | Schema foundation + corrections |
| Phase 1 | Same agent, continues sequentially | Canonical skeleton + smoke fixture |
| Phase 2 Track A | Sub-agent in `sec_graph-track-a` worktree | Implement ingest end-to-end |
| Phase 2 Track B | Sub-agent in `sec_graph-track-b` worktree | Hand-author canonical → validate → project |
| Phase 2 Track C₁ | Sub-agent in `sec_graph-track-c` worktree | Extract rules on smoke |
| Phase 3 Track C₂ | Same Track C agent (or fresh) | Extend rules to four examples |
| Phase 4 | Main session | Reconcile real (needs holistic view) |
| Phase 5 | Brainstorm via `superpowers:brainstorming`, then sub-agent | LLM interface |

Per the user's `superpowers:dispatching-parallel-agents` skill, Phase 2 is the natural place to launch three independent agents in one Agent message.

---

## 13. Documentation & Memory Touchpoints

- **CLAUDE.md update at G1:** add the module-table-ownership policy reference and the smoke canonical fixture path.
- **MEMORY.md (root) `[LEARN:workflow]` entries** at each gate: what worked, what didn't.
- **Session logs** at G0, G1, G2, G3, G4 in `quality_reports/session_logs/YYYY-MM-DD_phase-N.md`.
- **Quality reports at merges only** in `quality_reports/merges/YYYY-MM-DD_track-X.md`.

---

## 14. What This Plan Does Not Cover

- **Per-module implementation details inside any track.** Each track owner runs its own brainstorm → spec → plan if needed.
- **Whole-corpus runs across all 401 seeds.** Out of scope until G4.
- **External-metadata enrichment** (bidder domicile, advisor rankings). Out of scope per architecture spec §14.
- **CVR / non-cash consideration normalization.** Out of scope per spec §14.
- **Reviewer-workflow UI.** Out of scope (Stage 9).

---

## 15. First Action After Approval

When this plan is approved:

1. Save approval timestamp to this file's frontmatter (Status → APPROVED).
2. Open Phase 0 in the main worktree (no worktrees yet — Phase 0 lands on `main`).
3. Begin with Task §3.1.1 (move `edgar.py` → `fetch/edgar.py`).
4. Maintain a session log throughout.
5. Hit G0 before opening Phase 1.

The first command after approval is:

```bash
git checkout -b stage-1a-evidence-store
```

then run Task §3.1.1.

---

**End of plan.**
