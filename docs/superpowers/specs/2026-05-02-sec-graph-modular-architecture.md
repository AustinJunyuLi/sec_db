# sec_graph: Modular Architecture Spec

**Status:** APPROVED (2026-05-02)
**Scope:** Repository-wide architecture for the SEC merger-filing canonical pipeline.
**Out of scope:** Per-module implementation plans (each module gets its own brainstorm → spec → plan → implementation cycle).
**Supersedes:** Nothing. Lives alongside `docs/design.md` (the local design contract) and refines its module-level structure.

---

## 1. Purpose

`sec_graph` turns SEC merger-proxy narratives into a canonical structured representation of takeover sale processes (`deals`, `process_cycles`, `actors`, `events`, `event_actor_links`, `judgments`, evidence-bound source spans, plus auxiliary tables for advisors, counsel, terms, group memberships, prior relationships, and participation counts). Bidder-cycle estimator rows are produced as **deterministic projections** over the canonical store, not as the primary extraction format.

This document is the architecture-level contract for **how** the pipeline is decomposed, what each module owns, where data lives, how runs are versioned, and in what order modules are built. It does not prescribe implementation details inside any single module — those belong in per-module specs.

## 2. Architectural Approach

The pipeline is a **layered construction system** with seven modules, each with a narrow input/output contract. Layers never destroy evidence from prior layers; data flows one direction; cross-layer access is forbidden except through the shared schema module.

```
fetch ──► ingest ──► extract ──► reconcile ──► validate ──► project
                       ▲             ▲             ▲           ▲
                       └─────────────┴─────────────┴───────────┘
                              all reference shared
                                  schema module
```

**Why layers, not concept-objects:** Concept-oriented decomposition (one module per canonical object) would couple every module to every concept and make extraction's stochastic boundary leak across the system. Layered decomposition draws the boundary at *what kind of work happens here*, which keeps stochastic / deterministic work cleanly separated and lets implementations of one layer be replaced (e.g., rules-only vs LLM-augmented extraction) without touching the others.

## 3. Module Catalog

Each module is a Python subpackage under `src/sec_graph/`. Each owns one stage of the pipeline. Modules communicate only through declared input/output artifacts; no module reaches into another's internals.

### 3.1 `schema` (shared)

**Owns:** Canonical type definitions, deterministic-ID helpers, evidence-binding utilities, DuckDB DDL.

**Outputs:** Pydantic / dataclass models for `CleanFiling`, `Paragraph`, `SourceSpan`, `ExtractionCandidate`, `Deal`, `ProcessCycle`, `Actor`, `Event`, `EventActorLink`, `Judgment`, `AdvisorEngagement`, `LegalCounselEngagement`, `BoardCommittee`, `DealTerm`, `GroupMembership`, `PriorRelationship`, `ParticipationCount`, `BidNormalization`, `CyclePhaseAssignment`, `RunMetadata`. Plus a `ddl.sql` (or generated DDL) and `ids.py` for deterministic ID construction.

**Consumed by:** Every other module.

**Acceptance:** All tables are creatable in DuckDB from the DDL; round-trip Pydantic ↔ DuckDB row works for every model; deterministic ID helpers produce stable strings of form `{slug}_{type}_{sequence}` (e.g., `petsmart_actor_3`, `petsmart_evt_017`).

### 3.2 `fetch`

**Owns:** EDGAR download + sec2md conversion. Already implemented; the contract here documents what we keep when migrating it out of `src/sec_graph/edgar.py` into `src/sec_graph/fetch/`.

**Inputs:** A row from `seeds.csv` (deal slug + EDGAR URL).

**Outputs:** `data/filings/{slug}/`:
- `raw.htm` — verbatim SEC HTML
- `raw.md` — sec2md markdown with `<!-- PAGE n -->` markers
- `pages.json` — per-page payload from sec2md
- `manifest.json` — source URL, accession, form type, fetch timestamp, sec2md version, file SHA-256s

**Consumed by:** `ingest`.

**Determinism:** Fetched bytes depend on SEC's response. The manifest captures the fetch timestamp and content hashes so downstream determinism is anchored on the raw artifacts, not the network round-trip.

**Acceptance:** Already met by the existing implementation and `tests/test_edgar.py`. Migration to `fetch/` keeps all existing tests passing without API changes.

### 3.3 `ingest`

**Owns:** Markdown normalization + provenance map.

**Inputs:** A directory `data/filings/{slug}/` containing `raw.md` and `manifest.json`. Also accepts hand-trimmed examples in `data/examples/{slug}.md` with no manifest (some fields stay null).

**Outputs:** Rows written to DuckDB tables:
- `filings` — one row per filing with hashes, page count, section index, parser version
- `paragraphs` — one row per paragraph: `paragraph_id`, `filing_id`, `section`, `page_hint`, `char_start`, `char_end`, `paragraph_text`, `paragraph_hash`
- `spans` — one source-span seed per paragraph: `evidence_id`, `filing_id`, `paragraph_id`, `char_start`, `char_end`, `quote_text`, `quote_hash`. Tighter spans (sentence/clause level) are added by `extract`, not here.

**Cleaning policy:** Conservative. Preserve substantive text, page markers, dollar signs, dates, party labels, quotation marks. Strip well-defined noise (printer-command lines like `COMMAND=STYLE_ADDED,…`, ZEQ banners, repeated `Table of Contents` lines, isolated folio numbers) **only when the line matches an explicit pattern**; otherwise keep and let extraction filter. Every removal is logged with original char span.

**Section detection:** Anchor on known phrase set (`Background of the Merger`, `Reasons for the Merger`, `Opinion of …`, `Financing`, `Interests of Directors and Executive Officers`, plus a small extension list). Heading-detection is fuzzy (tolerant of leading style noise and bold markup). Unmatched ranges go into `unknown_section`.

**Determinism:** Reruns over identical raw bytes + identical `parser_version` produce identical paragraph IDs, hashes, and section spans.

**Acceptance:** All 4 example filings ingest deterministically. Page markers preserved for PetSmart 29-33, Providence & Worcester 35-43, Zep 35-42, Saks 31-36. In-text aliases (`Industry Participant`, `Party A`, `G&W`, `Party X`, `Sponsor A`, `Company H`) survive cleaning verbatim.

### 3.4 `extract`

**Owns:** Production of `ExtractionCandidate` objects from cleaned text. Multiple passes: actor mentions and aliases, dated process events, proposals and bids, terms and engagements, cycle/boundary/withdrawal/rejection signals.

**Subpackages:**
- `extract/rules/` — deterministic regex / pattern passes. Stage 6 implements these.
- `extract/llm/` — empty until Stage 8. Provider-neutral interface to be designed in its own brainstorm before any code.

**Inputs:** Reads `paragraphs` and `spans` (paragraph-level seeds) from DuckDB.

**Outputs:**
- `candidates` table — one row per candidate with `candidate_id`, `candidate_type`, `raw_value`, `normalized_value`, `confidence`, `evidence_ids` (list), `dependencies` (list), `status`. Candidates may overlap or conflict — they are not yet canonical.
- Additional rows in the `spans` table at sentence/clause granularity (narrower than ingest's paragraph seeds). Every narrower span must lie within an existing paragraph seed (no floating evidence). Each candidate references one or more of these narrower spans via `evidence_ids`.

**Acceptance (rules pass, Stage 6):** Output matches a hand-curated golden candidate set on PetSmart and Saks for actor mentions, dated events, and bid values. No actor extracted without a span; no candidate without at least one evidence_id.

### 3.5 `reconcile`

**Owns:** Conversion of candidates into canonical records. Owns the hard architectural decisions: alias merging, cycle assignment, formal-boundary judgment construction (including null boundaries with marker events), grouped-bidder representation, anonymous-actor creation when projection requires row-level completeness, dropout-mechanism classification.

**Inputs:** Reads `candidates` and `spans` from DuckDB.

**Outputs:** Writes the canonical tables to DuckDB: `deals`, `process_cycles`, `actors`, `events`, `event_actor_links`, `judgments`, plus auxiliaries (`advisor_engagements`, `legal_counsel_engagements`, `board_committees`, `deal_terms`, `group_memberships`, `prior_relationships`, `participation_counts`, `bid_normalizations`, `cycle_phase_assignments`).

**Determinism:** Given a fixed candidate set + fixed reconciliation config, output is bit-stable.

**Acceptance:** All four example filings produce a complete, FK-clean canonical record set. Every canonical row references at least one valid `evidence_id`. Required judgments exist for every cycle (`formal_boundary`, `cycle_regime`, `cycle_visibility`, `cycle_relation`).

### 3.6 `validate`

**Owns:** Pre-export integrity checks. Splits issues into **hard failures** (block export) and **soft flags** (allowed but routed to ambiguity queue).

**Hard checks:** Referential integrity (every FK resolves), evidence binding (every canonical row has a valid `evidence_id`, every span has a valid `paragraph_id`, every quote_hash matches the actual quote bytes), date sanity (no negative durations, no events before `cycle_start_date`), bid bounds (`bid_value_lower ≤ bid_value ≤ bid_value_upper` when all present), required judgments per cycle, deterministic-ID format conformance.

**Soft flags:** Low-confidence judgments, judgments with `alternative_value` populated, no-boundary cycles, hidden individual bid values behind aggregate counts, alias-resolution ambiguity, unknown bidder subtypes.

**Inputs:** Reads canonical tables from DuckDB.

**Outputs:** `runs/{run_id}/validation_report.json` (pass/fail per check), `runs/{run_id}/ambiguity_queue.csv` (soft-flag rows for reviewer triage).

**Acceptance:** All four example filings pass hard checks. Known soft flags (Providence Party D/E reengagement, Zep Party X withdrawal ambiguity, Saks go-shop unnamed parties) appear in the ambiguity queue.

### 3.7 `project`

**Owns:** Pure deterministic projection from canonical tables to estimator-facing views. No new factual judgments. Adapts the reference `derive_views.py` semantics.

**Inputs:** Reads canonical tables from DuckDB.

**Outputs:** Files under `runs/{run_id}/`:
- `bidder_rows.jsonl` — one row per bidder-cycle (matches `derive_views.py` schema)
- `auctions.jsonl` — cycle-level metadata
- `cycle_summary.csv`, `bidder_summary.csv`, `deal_index.csv`, `review_master.csv`
- `run_memo.md` — markdown run summary

**Acceptance:** Every exported `bidder_rows.jsonl` row populates all fields from the reference schema (`deal_slug`, `cycle_id`, `actor_id`, `actor_label`, `bI`, `bI_lo`, `bI_hi`, `w_logwidth`, `bF`, `admitted`, `T`, `bid_value_unit`, `consideration_type`, `boundary_event_id`, `boundary_quality`, `formal_boundary`, `dropout_mechanism`, `dropout_has_alternative`, `cycle_visibility`, `scope_validity`, `valuation_comparability`, `confidence_min`); nulls are present only where a corresponding scope flag explains them.

## 4. Storage Architecture

**Hybrid: files for blobs, DuckDB for everything structured.**

- **Files** under `data/filings/{slug}/`: `raw.htm`, `raw.md`, `pages.json`, `manifest.json`. Bulk filing text stays on disk because it is read whole, not queried.
- **DuckDB** at `data/pipeline.duckdb`: a single embedded database file holding **every** structured table — `filings`, `paragraphs`, `spans`, `candidates`, all canonical tables, all auxiliary tables, `run_metadata`. Paragraph text and quote text are duplicated into rows (cheap; ~1-5 KB per paragraph) so SQL queries can search them.
- **Run snapshots** under `runs/{run_id}/`: a frozen copy of `pipeline.duckdb` plus exported reports/views.

**Why not files-everywhere:** Cross-filing queries ("every paragraph mentioning 'standstill' with no candidate yet") become brittle Python crawls. SQL is the right tool for the job at the structured layer, and DuckDB is single-file, embedded, no-server, columnar.

**Why not DuckDB-everywhere (including raw text):** Raw filings are 0.5-2 MB blobs read whole. The database structure does no work for blobs; storing them in rows adds overhead without payoff.

## 5. Repository Layout

```
src/sec_graph/
  __init__.py
  schema/                 # models, IDs, DDL, evidence helpers
    __init__.py
    models.py
    ddl.sql
    ids.py
  fetch/                  # existing edgar.py moved here
    __init__.py
    edgar.py
  ingest/                 # markdown → DuckDB
    __init__.py
    cleaning.py
    paragraphs.py
    sections.py
    spans.py
  extract/
    __init__.py
    rules/                # deterministic patterns (Stage 6)
      __init__.py
      actors.py
      events.py
      bids.py
    llm/                  # empty until Stage 8 (own brainstorm first)
      __init__.py
  reconcile/
    __init__.py
    aliases.py
    cycles.py
    boundaries.py
    judgments.py
  validate/
    __init__.py
    integrity.py
    flags.py
  project/
    __init__.py
    bidder_rows.py
    summaries.py
  cli.py                  # python -m sec_graph {subcommand} ...

scripts/
  fetch_filings.py        # existing thin shim, kept for back-compat

data/
  examples/{slug}.md      # 4 hand-trimmed reference filings (existing)
  filings/{slug}/         # raw.htm, raw.md, pages.json, manifest.json
  pipeline.duckdb         # single canonical store; replaced on rerun

runs/{run_id}/            # frozen snapshot + exported views + reports
  canonical.duckdb
  validation_report.json
  ambiguity_queue.csv
  bidder_rows.jsonl
  auctions.jsonl
  cycle_summary.csv
  bidder_summary.csv
  deal_index.csv
  review_master.csv
  run_memo.md

tests/
  test_<module>.py        # unit tests per module
  fixtures/
    smoke_filing.md       # synthetic filing for CI smoke test
    canonical/{slug}.json # golden canonical outputs per example
  integration/
    test_pipeline.py      # full-pipeline tests against 4 examples
  test_determinism.py     # rerun-equivalence test
```

## 6. CLI / Orchestration

Single CLI entry point `python -m sec_graph` with subcommands per module:

```
python -m sec_graph fetch --slug X | --reference-only | --all
python -m sec_graph ingest --slug X | --all
python -m sec_graph extract --slug X | --all
python -m sec_graph reconcile
python -m sec_graph validate
python -m sec_graph project
python -m sec_graph run --slug X | --all   # ingest → extract → reconcile → validate → project
python -m sec_graph snapshot [--run-id Y]  # freeze pipeline.duckdb to runs/{Y}/
```

`run` invokes `snapshot` automatically with a generated `run_id` (timestamp + short hash). The standalone `snapshot` command is for cases where you want to override the auto-generated id (e.g., a memorable name like `baseline-2026-05-02`); if `--run-id` is omitted, a fresh id is generated.

`scripts/fetch_filings.py` remains as a thin compatibility shim into `python -m sec_graph fetch`. The existing test invocation continues to work.

## 7. Determinism Contract

The pipeline makes three guarantees:

1. **Stable IDs.** Every record has a deterministic ID of form `{slug}_{type}_{sequence}` (e.g., `petsmart_actor_3`, `petsmart_evt_017`, `petsmart_judgment_005`). The third actor in PetSmart is always `petsmart_actor_3`. IDs do not change between runs over identical input + identical code.
2. **Byte-stable rows.** Reruns over unchanged input + unchanged code produce identical row content hashes. The unit of comparison is the row hash, not the DuckDB file bytes (which can differ even when contents match).
3. **Versioned runs.** Every run gets a `run_id` (timestamp + short hash). Every canonical row carries the `run_id` that produced it. Each stage maintains its own version counter (`ingest_version`, `extract_version`, `reconcile_version`, `validate_version`, `project_version`) recorded in `run_metadata`. Code-version bumps trigger a new `run_id`; the prior run is preserved in its snapshot.

A determinism test runs the pipeline twice on the smoke filing and asserts identical row content hashes across runs.

## 8. Run Model & Snapshots

`pipeline.duckdb` is **the** working canonical store and gets fully rewritten on each rerun. To preserve historical runs:

- `python -m sec_graph snapshot --run-id Y` copies `pipeline.duckdb` → `runs/{Y}/canonical.duckdb` and exports current views/reports into the same folder.
- `python -m sec_graph run --slug X` invokes `snapshot` automatically at the end.

Snapshots are filesystem-frozen artifacts. Comparing run A to run B is a row-by-row content diff between `runs/{A}/canonical.duckdb` and `runs/{B}/canonical.duckdb` (via DuckDB queries), not a file-bytes diff.

## 9. Schema Evolution Policy

**No migrations.** When the schema changes:

1. Bump the relevant `*_version` constant.
2. Drop `data/pipeline.duckdb`.
3. Re-run the pipeline from raw filings: `python -m sec_graph run --all`.

Justification: raw filings are the source of truth and are immutable on disk. The DB is a derived artifact. Rebuild time on 4 filings is seconds; on 400 it remains minutes. We will revisit this policy if and when the corpus grows past 1000 filings or the project moves to a continuously-running service. Neither is in current scope.

## 10. Cross-Cutting Concerns

### 10.1 Evidence binding (every-module concern)

Every canonical row must reference at least one `evidence_id` resolving to a `SourceSpan` whose `quote_hash` matches the bytes at the recorded `(filing_id, char_start, char_end)`. `validate` enforces this. `schema` provides helpers for span construction and quote-hash verification.

### 10.2 Append-only judgments + reviewer-override chain

Stage 9 (reviewer workflow) is **out of build scope** for this roadmap. But the schema must accommodate it on Day 1 to avoid retrofit cost.

Schema rule: `judgments` rows are append-only. A reviewer override is a *new* judgment row whose `supersedes_judgment_id` points to the prior judgment. Projections select the latest non-superseded row in the chain. This is cheap to bake into the schema now and expensive to retrofit later.

**Reviewer-override persistence across reruns (Stage 9 problem, flagged here).** The Run Model (§8) rewrites `pipeline.duckdb` on every rerun. Reviewer-added judgment rows would be lost unless they're persisted outside the pipeline-rewritten tables. Stage 9's design must answer: are reviewer overrides stored in a sidecar table or file (`reviewer_overrides.jsonl`?) that gets re-applied at the end of every pipeline run, or are they kept in a separate non-pipeline-rewritten DuckDB table? We do not solve this here, but Stage 1's schema work must leave room for either approach (e.g., do not declare `judgments` as exclusively rewritten by `reconcile`).

### 10.3 `run_id` discriminator on canonical tables

Every canonical-table row carries `run_id`. Per §8, `pipeline.duckdb` only ever holds the current run's data, so within `pipeline.duckdb` `run_id` is uniform and acts as a label rather than a filter. The `run_id` column earns its keep when:

- Two snapshots are imported into a single DB for comparison (`ATTACH 'runs/A/canonical.duckdb' AS a; ATTACH 'runs/B/canonical.duckdb' AS b;`); rows from each carry distinct `run_id` values and can be joined or anti-joined.
- Stage 9 reviewer-override rows are mixed into the same table as pipeline-produced rows; the `run_id` distinguishes "produced by pipeline run X" from "added by reviewer session Y".
- Snapshot exports (`runs/{run_id}/canonical.duckdb`) self-identify without a separate metadata file.

The cost is one column on every row. Worth it.

## 11. Testing Strategy

Four test tiers:

1. **Unit tests** (`tests/test_<module>.py`): one per module, fast, run on every commit. Target individual functions (regex behavior, ID construction, span hashing, FK resolution helpers).
2. **Smoke test** (`tests/fixtures/smoke_filing.md` + `tests/integration/test_pipeline.py`): a ~50-line synthetic filing exercising every code path (page markers, every section heading, every candidate type, a no-boundary cycle, a go-shop, an ambiguous dropout, an unnamed aggregate count). Full pipeline runs in seconds. CI gate.
3. **Integration tests** (`tests/integration/test_pipeline.py` against `data/examples/{slug}.md`): full pipeline against the 4 examples, golden outputs in `tests/fixtures/canonical/{slug}.json`. Run on demand and in CI; updates require an explicit golden-regenerate step (so unintentional rule changes are caught at review).
4. **Determinism test** (`tests/test_determinism.py`): runs the smoke pipeline twice, asserts identical row content hashes. Catches non-determinism the moment it creeps in.

## 12. Build Order

Each stage produces a runnable, testable artifact. Stages are completed in order. Do **not** start Stage N+1 until Stage N's acceptance criteria pass.

| Stage | Module(s) touched | Goal | Acceptance |
|---|---|---|---|
| **0** (done) | — | `fetch` works; 4 examples on disk; existing tests pass. | ✓ |
| **1** | `schema` | Pydantic models + DuckDB DDL + ID helpers + evidence utilities + `run_metadata` scaffolding. | All tables creatable; round-trip Pydantic ↔ DB; ID helpers stable; smoke filing fixture written. |
| **2** | `ingest` | Markdown → `filings`, `paragraphs`, `spans` rows in DuckDB. | All 4 examples ingest deterministically; reruns produce identical IDs and hashes; section/page-marker preservation matches §3.3. |
| **3** | `reconcile` (skeleton) | Hand-author one filing's canonical records as a fixture. Walk the schema end-to-end. | One filing has complete canonical record set; all FKs resolve; all evidence_ids point to valid spans. |
| **4** | `validate` | Hard-failure + soft-flag separation; ambiguity-queue export. | Stage-3 hand-authored fixture passes all hard checks; an intentionally-broken fixture fails with the right error class. |
| **5** | `project` | Adapt `derive_views.py`; wire to DuckDB; export bidder-cycle rows + companion views. | Stage-3 hand-authored canonical produces an expected `bidder_rows.jsonl` and `run_memo.md`. |
| **6** | `extract/rules` | Deterministic patterns for actor mentions, dated events, bid values on the 4 examples. | Candidate output matches a hand-curated golden set on PetSmart and Saks; every candidate has at least one evidence_id. |
| **7** | `reconcile` (real) | Replace Stage 3 manual fixtures with rule-extracted candidates → canonical. Add judgments. | All 4 examples produce canonical records; bidder-cycle rows match a hand-curated expected set. |
| **8** | `extract/llm` (gated) | Provider-isolated LLM pass for events/aliases that rules miss. **Begins with its own brainstorm.** No provider SDK in dependencies until that brainstorm produces an approved interface spec. | Behind a feature flag; deterministic outputs unchanged when flag off. |
| **9** (out of roadmap) | reviewer workflow | Reviewer triages ambiguity queue; overrides emit new judgments referencing prior. | Out of build scope. Schema accommodates per §10.2. |

## 13. Parallelization and Critical Path

After Stage 1 lands, the remaining build splits into three parallel tracks that converge at Stage 7. Stage 1 is sequential because every other module depends on the schema; once it is stable (with the smoke filing fixture and a hand-authored canonical fixture verifying the contract end-to-end), three streams advance independently.

### 13.1 Tracks

**Track A — Data path:** Stage 2 (`ingest`). Operates on raw markdown; produces `paragraphs` and `spans` rows in DuckDB. No dependency on Tracks B or C.

**Track B — Schema validation path:** Stage 3 (`reconcile` skeleton) → Stage 4 (`validate`) → Stage 5 (`project`). Uses hand-authored canonical fixtures committed to `tests/fixtures/canonical/`, so it does not wait on real extraction. Proves the schema contract end-to-end. Sequential within the track because each stage depends on the prior fixture's existence.

**Track C — Extraction path:** Stage 6 (`extract/rules`). Begins against the smoke filing (built in Stage 1) for early regex / pattern development. Full acceptance against the four real example filings depends on Track A finishing.

### 13.2 Convergence

All three tracks merge at **Stage 7** (`reconcile` real). Stage 7:
- Replaces Stage 3's hand-authored fixtures with rule-extracted candidates from Track C, against Track A's ingested paragraphs/spans.
- Validates the result through Track B's `validate` and `project` modules.

Stage 8 (`extract/llm`) is downstream of Stage 7 and gated on its own brainstorm. Stage 9 (reviewer workflow) is out of build scope.

### 13.3 Critical Path

The expected critical path is **Stage 1 → Stage 2 → Stage 6 → Stage 7**, driven by extraction rules being the largest single piece of work and depending on real ingested data. Track B (Stages 3 → 4 → 5) typically finishes inside the shadow of Track C and does not extend total duration.

```
Stage 1 ──► Stage 2 ──► Stage 6 ──► Stage 7        (critical path)
   │                                   ▲
   └──► Stage 3 ──► Stage 4 ──► Stage 5┘            (Track B, parallel)
```

### 13.4 Risks and Mitigations

- **Schema iteration risk.** A schema gap discovered mid-track invalidates parallel work. Mitigation: Stage 1's deliverable includes both the type definitions *and* a hand-authored canonical example on the smoke filing, so the schema is exercised end-to-end before fan-out.
- **Coordination cost.** Each module has a declared input/output via the DuckDB schema (§3 + §4). As long as schema changes route through Stage 1 with a version bump (§9), parallel tracks do not step on each other.
- **Solo-contributor reality.** Parallelism is most valuable with multiple contributors / agents. A solo developer can still benefit from interleaving Track B with Track C while Track A runs first, because Track B unblocks early end-to-end validation feedback before extraction is complete.
- **Track C partial dependence.** Stage 6's smoke-filing milestone ships independently; its real-filing acceptance waits on Stage 2. Track C is therefore planned as two explicit milestones: (a) smoke-only, (b) all-four-examples.

### 13.5 Recommended Sequencing

1. Stage 1 alone (schema + smoke filing fixture + hand-authored canonical fixture on the smoke filing). Land it.
2. Fan out: Track A (Stage 2), Track B (Stages 3 → 4 → 5), Track C (Stage 6) in parallel.
3. Sync at Stage 7.
4. Optionally Stage 8, beginning with its own brainstorm.

## 14. What's Explicitly Out of Scope (For This Roadmap)

- **LLM extraction implementation.** The interface for how an LLM is called, what it sees, and what it returns is designed in a separate Stage-8 brainstorm before any code is written. The `extract/llm/` directory is empty until then.
- **Reviewer workflow UI.** Stage 9 is acknowledged but not built; the schema accommodates it (§10.2).
- **Whole-corpus runs.** Stages 1-7 target the 4 examples. Running across all ~400 deals in `seeds.csv` happens only after Stage 7 acceptance.
- **External-metadata enrichment.** Bidder domicile, advisor rankings, public/private status, industry codes, etc., require external datasets the trimmed filings don't supply. The schema has fields for them; population is future work.
- **CVR / non-cash consideration normalization.** Stored faithfully (raw text + flag); converting to per-share cash equivalents for `r_23` requires policy outside the filing — deferred.

## 15. Open Questions

These are unresolved and will be revisited at the relevant stage:

- **Section vocabulary.** §3.3 lists a starter set of section headings. The full vocabulary is finalized during Stage 2 implementation; any heading not in the vocabulary lands in `unknown_section` and is fixable later by extending the list.
- **Cleaning patterns.** The exact regex set for printer-command lines, ZEQ banners, and folio-number stripping is enumerated and reviewed in Stage 2 before any stripping happens.
- **`cycle_relation` value set.** Whether go-shops are encoded as same-cycle tails, separate cycles, or both (configurable per projection). Decided in Stage 4 / Stage 7.
- **Dropout-mechanism evidence rules.** The text patterns / linked events that justify `target-rejected` vs `voluntarily-withdrew` vs `ambiguous` are codified in Stage 7.
- **Anonymous aggregate-bidder policy.** When `participation_counts` reports N IOIs without naming each, do we always create N anonymous actors, or only when projection requires row-level completeness? Decided in Stage 7.
- **LLM provider interface.** Designed in Stage 8 brainstorm. Constraints recorded here: provider-neutral, deterministic-output-respecting, evidence-emitting (quote text + location hints), feature-flagged.
- **Reviewer UI shape.** Out of scope for this roadmap. The schema affordance (§10.2) is what we commit to today.

## 16. Related Documents

- [docs/design.md](../../design.md) — local design contract (live).
- [AGENTS.md](../../../AGENTS.md) — repository contract for working agents.
- [docs/references/gptpro_v2/plan/](../../references/gptpro_v2/plan/) — reference architecture from the GPT-Pro v2 packet. Material, not binding.
- [docs/references/gptpro_v2/derive_views.py](../../references/gptpro_v2/derive_views.py) — reference projection from canonical DuckDB to bidder-cycle views.

## 17. Acceptance of This Spec

Approval is the user's; written confirmation in conversation suffices. After approval, the next action is to invoke the `superpowers:writing-plans` skill to produce an implementation plan for **Stage 1 (`schema` scaffolding)**, which is the first buildable stage.
