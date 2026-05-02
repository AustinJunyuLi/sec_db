# sec_graph: Specification

**Status:** APPROVED (2026-05-02). Sole source of truth for design and contracts.
**Scope:** Repository-wide architecture, schema-shape commitments, build order, slicing rules, and non-negotiable invariants.
**Companion documents:** `quality_reports/plans/2026-05-02_stale-scaffold-hard-cleanse-repair-plan.md` is the executing cleanup-and-repair plan and is in force until every phase inside it is complete. `quality_reports/plans/2026-05-02_deployable-canonical-pipeline-goal.md` is the goal-handoff document for live deployable proof, paired with `quality_reports/plans/2026-05-02_deployable-canonical-pipeline-plan.md`. Historical failure context lives in `docs/prior-pipeline-lessons.md`.
**Out of scope:** Per-module implementation prose (each module gets its own brainstorm -> spec -> plan -> implementation cycle when its track activates).

---

## 1. Purpose

`sec_graph` turns SEC merger-proxy narratives into a canonical structured representation of takeover sale processes (`deals`, `process_cycles`, `actors`, `actor_relations`, `events`, `event_actor_links`, `participation_counts`, `judgments`, evidence-bound source spans). Bidder-cycle estimator rows are produced as **deterministic projections** over the canonical store, not as the primary extraction format.

The canonical store must support future views over advisors, counsel, board committees, go-shops, deal terms, process restarts, prior relationships, consortia, and ambiguity judgments without re-extracting the filing text. The first representation for these should be generic actor/event/relation/count/judgment facts; specialized auxiliary tables are deferred until a fixture makes them unavoidable.

This document is the architecture-level contract for **how** the pipeline is decomposed, what each module owns, where data lives, how runs are versioned, and in what order modules are built. It does not prescribe implementation details inside any single module — those belong in per-module specs.

## 1A. Deployable Canonical Schema Contract

This section is the current binding schema contract for the deployable
canonical-pipeline goal. It supersedes any older examples in this repository
that contain row-first actor identity, free-form judgment categories,
downstream-estimator naming, or fallback enum values such as `unknown` and
`other`.

### Closed-Enum Discipline

Every enum below is closed. Do not add `unknown`, `other`, miscellaneous
catch-all values, provider-owned categories, or backward-compatible aliases. If
the pipeline cannot classify a source fact into a closed value, it must not
write that row; it should preserve the evidence as a candidate, validation
failure, or reviewer-facing ambiguity instead.

### Actors

`actors` represent source-backed entities, not bidder rows:

```python
actor_kind: Literal[
    "organization",
    "person",
    "group",
    "vehicle",
    "cohort",
    "committee",
]
observability: Literal[
    "named",
    "anonymous_handle",
    "count_only",
]
lead_arranger_label: str | None
member_count_known: int | None
has_strategic_member: bool | None
has_sovereign_wealth_member: bool | None
```

`actor_type`, `bidder_subtype`, and `is_anonymous` are not part of the
deployable schema. Group-only fields are `NULL` unless `actor_kind == "group"`.

### Actor Relations

`actor_relations` is the generic structure for group membership, affiliate and
control structure, acquisition vehicles, advisors, financing, support holders,
and rollover holders:

```python
relation_type: Literal[
    "member_of",
    "affiliate_of",
    "controls",
    "acquisition_vehicle_of",
    "advises",
    "finances",
    "supports",
    "rollover_holder_of",
]
cycle_id_first_observed: str | None
cycle_id_last_observed: str | None
effective_date_first: date | None
effective_date_last: date | None
confidence: Literal["low", "medium", "high"] | None
```

Validation must enforce:

```sql
cycle_id_first_observed IS NOT NULL OR effective_date_first IS NOT NULL
```

Do not add separate `guarantees` or `voting_support_for` relation values unless
a filing-grounded review first changes this spec. Use `supports` plus
`role_detail` for support/voting-support facts and `finances` plus
`role_detail` for guaranty/financing structure when the evidence supports it.

### Events

`events.event_type` remains a coarse grouping. `events.event_subtype` carries
the closed source verb:

```python
event_subtype: Literal[
    "contact_initial",
    "nda_signed",
    "ioi_submitted",
    "first_round_bid",
    "final_round_bid",
    "exclusivity_grant",
    "merger_agreement_executed",
    "withdrawn_by_bidder",
    "excluded_by_target",
    "non_responsive",
    "cohort_closure",
    "advancement_admitted",
    "advancement_declined",
    "rollover_executed",
    "financing_committed",
]
```

Withdrawal, exclusion, cohort closure, and advancement are event subtypes, not
event-actor roles or judgment categories.

### Event Actor Links

`event_actor_links.role` is the actor's role in one event:

```python
role: Literal[
    "target",
    "bid_submitter",
    "potential_buyer",
    "group_vehicle",
    "group_member",
    "advisor_for_target",
    "advisor_for_bidder",
    "equity_financing_source",
    "debt_financing_source",
    "support_shareholder",
    "rollover_holder",
    "offeror",
    "acquisition_sub",
    "sender",
    "recipient",
]
```

Rare legal details belong in `role_detail`; they do not justify an open enum.

### Participation Counts

`participation_counts` preserves aggregate cohort observations without
creating actors:

```python
process_stage: Literal[
    "contacted",
    "nda_signed",
    "ioi_submitted",
    "first_round",
    "final_round",
    "exclusivity",
]
actor_class: Literal["financial", "strategic", "mixed"]
count_min: int
count_max: int | None
count_qualifier: Literal[
    "exact",
    "approximate",
    "lower_bound",
    "upper_bound",
    "range",
]
named_subset_actor_ids: list[str]
anonymous_remainder_count: int
```

`actor_creation_required`, `potential_buyer`, `shareholder`, and `unknown` are
not participation-count fields or enum values in the deployable schema.

### Filings

`filings.process_scope` is required:

```python
process_scope: Literal[
    "target_full_proxy",
    "bidder_partial_schedule_to",
    "amendment_only",
    "go_shop_only",
]
```

Target-side projections must refuse or hard-flag source scopes that are not
`target_full_proxy`.

### Judgments

Judgments are a two-axis append-only surface:

```python
judgment_kind: Literal["fact_correction", "projection_eligibility"]

# fact_correction only
target_table: str | None
target_id: str | None
target_column: str | None
prior_value: str | None
new_value: str | None

# projection_eligibility only
projection_name: str | None
actor_id: str | None
included: bool | None
rule_id: str | None

# both
evidence_ids: list[str]
supersedes_judgment_id: str | None
created_at: datetime
created_by: str
```

The deployable schema does not use `judgment_type`, `judgment_value`,
`alternative_value`, or free-form categories such as `formal_boundary`,
`cycle_visibility`, `admission`, `dropout_mechanism`, `scope_validity`, or
`valuation_comparability`. Those become typed canonical facts or named
`rule_id` values under `projection_eligibility`.

Initial `bidder_cycle_baseline_v1` rule IDs:

```text
bidder_cycle_baseline_v1.formal_boundary
bidder_cycle_baseline_v1.cycle_visibility
bidder_cycle_baseline_v1.admission
bidder_cycle_baseline_v1.valuation_comparability
bidder_cycle_baseline_v1.scope_validity
bidder_cycle_baseline_v1.consortium_collapse
```

### Run-State Safety

No pipeline stage may delete `data/pipeline.duckdb` or `runs/{run_id}/` except
under an explicit fresh-run flag whose exact behavior is documented here and in
the CLI help. No stage may delete or wipe `judgments`, since judgments are
append-only and may carry reviewer overrides that pre-date the current pipeline
run. No command may overwrite an existing `runs/{run_id}/` directory unless
the caller passes the explicit fresh-run flag and the docs name the exact
behavior. Reviewer overrides and proof snapshots must fail loudly rather than
disappear.

### Stale-Doc Policy

Active docs and active code must reference exactly one current authority chain.

- Active docs may not reference superseded plans as execution authority. If a
  plan has been retired, active docs must not point to it as the executing
  plan; the document is either deleted or rewritten as a one-page historical
  note whose status banner explicitly disclaims authority.
- Proof logs are point-in-time evidence only. They record what passed at a
  given hour against a then-current command surface. They are not current
  authority and must not be treated as instructions.
- Historical notes may not contain executable next steps unless the header
  says they are rejected historical instructions. A historical note with
  active-looking commands is a contract violation.
- The current authority chain is `docs/spec.md` plus the executing
  cleanup-and-repair plan named in the §16 references; no other document
  speaks for the spec.

### Within-Deal Narrative Memory

LLM extraction operates on within-deal narrative windows, not on isolated
paragraphs.

- A window is built from ordered paragraphs inside one filing. Earlier
  paragraphs in the window inform interpretation of later paragraphs in the
  same window.
- No cross-deal memory is allowed. A window must never include content from
  another deal, and prior-deal memory summaries must be derived from the same
  filing only.
- Every quote emitted from a window must still map back to exact source
  coordinates against the underlying paragraph source span. Python owns
  source coordinate derivation; the provider never produces or echoes
  `char_start` / `char_end`.
- Window construction policy and prior-deal memory shape are defined in
  `docs/llm-interface.md`.

### Fetch Fail-Loud Contract

Tender-offer filings (`SC TO-T`, including amendments) MUST fail loudly if no
`EX-99.(A)(1)(A)` "Offer to Purchase" exhibit is selected. No fallback to the
cover form is allowed. The fetcher raises a hard error rather than recording
the cover form as the substantive document.

This contract is in addition to the form-type whitelist
(`PRIMARY_FORM_TYPES = {DEFM14A, PREM14A, SC TO-T, S-4}` plus amendments) and
the `EXCLUDED_FORM_TYPES` rejection of 425.

### CLI Dispatch Contract

`python -m sec_graph` is the single top-level entry point. Subcommands include
at least `ingest`, `extract`, `reconcile`, `validate`, `project`, `run`, and
`snapshot`.

- The top-level dispatcher MUST forward `--fresh` to the `ingest` subcommand.
  The form
  `python -m sec_graph ingest --input data/examples --db data/pipeline.duckdb --fresh`
  is supported and forwarded by top-level dispatch.
- `python -m sec_graph run` accepts `--run-id` and `--run-dir`; the run
  directory is immutable per the Run-State Safety rule above.
- `python -m sec_graph project` accepts `--projection` and selects rows under
  the named projection rule (e.g., `bidder_cycle_baseline_v1`).
- `scripts/fetch_filings.py`, if retained, is a deliberate root convenience
  command for EDGAR downloads. It is not retained for backward compatibility;
  if a full `python -m sec_graph fetch` command supersedes it, the script is
  deleted rather than maintained as a duplicate command surface.

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

**Outputs:** Pydantic / dataclass models for `CleanFiling`, `Paragraph`, `SourceSpan`, `ExtractionCandidate`, `Deal`, `ProcessCycle`, `Actor`, `ActorRelation`, `Event`, `EventActorLink`, `ParticipationCount`, `Judgment`, `RunMetadata`. Plus a `ddl.sql` (or generated DDL) and `ids.py` for deterministic ID construction. Deferred auxiliary models are listed in §17.4 and do not become implementation obligations until fixture-demanded.

**Consumed by:** Every other module.

**Acceptance:** All tables are creatable in DuckDB from the DDL; round-trip Pydantic ↔ DuckDB row works for every model; deterministic ID helpers produce stable strings of form `{slug}_{type}_{sequence}` (e.g., `petsmart_actor_3`, `petsmart_evt_017`).

### 3.2 `fetch`

**Owns:** EDGAR download + sec2md conversion. Implemented in `src/sec_graph/fetch/edgar.py`.

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

**Inputs:** A directory `data/filings/{slug}/` containing `raw.md` and `manifest.json`. Also accepts hand-trimmed examples in `data/examples/{slug}.md` with no manifest (some fields stay null). Current `data/examples/` set: `petsmart-inc.md`, `providence-worcester.md`, `saks.md`, `zep.md`.

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
- `extract/llm/` — opt-in provider-neutral LLM candidate producer. Stage 8 is implemented behind explicit flags and bound by `docs/llm-interface.md`.

**Inputs:** Reads `paragraphs` and `spans` (paragraph-level seeds) from DuckDB.

**Outputs:**
- `candidates` table — one row per candidate with `candidate_id`, `candidate_type`, `raw_value`, `normalized_value`, `confidence`, `evidence_ids` (list), `dependencies` (list), `status`. Candidates may overlap or conflict — they are not yet canonical.
- Additional rows in the `spans` table at sentence/clause granularity (narrower than ingest's paragraph seeds). Every narrower span must lie within an existing paragraph seed (no floating evidence). Each candidate references one or more of these narrower spans via `evidence_ids`.

**Acceptance (rules pass, Stage 6):** Output matches a hand-curated golden candidate set on PetSmart and Saks for actor mentions, dated events, and bid values. No actor extracted without a span; no candidate without at least one evidence_id.

### 3.5 `reconcile`

**Owns:** Conversion of candidates into canonical records. Owns the hard architectural decisions: alias merging, cycle assignment, formal-boundary judgment construction (including null boundaries with marker events), grouped-bidder representation, cohort-count representation, relation construction, and dropout-mechanism classification.

**Inputs:** Reads `candidates` and `spans` from DuckDB.

**Outputs:** Writes the canonical tables to DuckDB: `deals`, `process_cycles`, `actors`, `actor_relations`, `events`, `event_actor_links`, `participation_counts`, `judgments`. Rich auxiliary tables remain deferred under §17.4.

**Determinism:** Given a fixed candidate set + fixed reconciliation config, output is bit-stable.

**Acceptance:** All four example filings produce a complete, FK-clean canonical record set. Every canonical row references at least one valid `evidence_id`. Required judgments exist for every cycle (`formal_boundary`, `cycle_regime`, `cycle_visibility`, `cycle_relation`).

### 3.6 `validate`

**Owns:** Pre-export integrity checks. Splits issues into **hard failures** (block export) and **soft flags** (allowed but routed to ambiguity queue).

**Hard checks:** Referential integrity (every FK resolves), evidence binding (every canonical row has a valid `evidence_id`, every span has a valid `paragraph_id`, every quote_hash matches the actual quote bytes), date sanity (no negative durations, no events before `cycle_start_date`), bid bounds (`bid_value_lower ≤ bid_value ≤ bid_value_upper` when all present), required judgments per cycle, deterministic-ID format conformance.

**Soft flags:** Low-confidence projection-eligibility judgments, fact corrections with disputed values, no-boundary cycles, count-only cohorts that cannot enter baseline bidder rows, alias-resolution ambiguity, and candidate facts that could not be classified into closed enum values.

**Inputs:** Reads canonical tables from DuckDB.

**Outputs:** `runs/{run_id}/validation_report.json` (pass/fail per check), `runs/{run_id}/ambiguity_queue.csv` (soft-flag rows for reviewer triage).

**Acceptance:** All four example filings pass hard checks. Known soft flags (Providence Party D/E reengagement, Zep Party X withdrawal ambiguity, Saks go-shop unnamed parties) appear in the ambiguity queue.

### 3.7 `project`

**Owns:** Pure deterministic projection from canonical tables to estimator-facing views. No new factual judgments.

**Inputs:** Reads canonical tables from DuckDB.

**Outputs:** Files under `runs/{run_id}/`:
- `bidder_rows.jsonl` — one row per bidder-cycle
- `auctions.jsonl` — cycle-level metadata
- `cycle_summary.csv`, `bidder_summary.csv`, `deal_index.csv`, `review_master.csv`
- `run_memo.md` — markdown run summary

**Acceptance:** Every exported `bidder_rows.jsonl` row populates all fields from the projection schema (`deal_slug`, `cycle_id`, `actor_id`, `actor_label`, `bI`, `bI_lo`, `bI_hi`, `w_logwidth`, `bF`, `admitted`, `T`, `bid_value_unit`, `consideration_type`, `boundary_event_id`, `boundary_quality`, `formal_boundary`, `dropout_mechanism`, `dropout_has_alternative`, `cycle_visibility`, `scope_validity`, `valuation_comparability`, `confidence_min`); nulls are present only where a corresponding scope flag explains them.

**Projection-construction rules:**
- Projection first selects the latest non-superseded
  `judgment_kind='projection_eligibility'` row for the requested projection.
  No actor-cycle row is emitted without an included current judgment.
- `bI` = the actor's most recent source-backed proposal **before** the cycle's
  projection boundary event date.
- `bF` = the actor's highest source-backed proposal **at or after** the cycle's
  projection boundary event date.
- `admitted` must be justified by canonical event facts plus the current
  projection rule; do not infer admission only from a post-boundary proposal.
- `w_logwidth` = `log(bI_hi / bI_lo)` when both bounds are positive; null otherwise.
- `T` is populated only when source-backed actor classification supports the
  strategic/financial distinction for the projection; otherwise it is null with
  an explicit scope/ambiguity flag.
- `confidence_min` = the lowest confidence across the current projection
  eligibility rule and any source-backed canonical facts used to populate the
  row.

### 3.8 Module Table Ownership

Shared DuckDB tables are not shared write surfaces. Each module owns the tables below; if a module needs a table outside its write set, change this schema contract before writing around it.

| Module | Writes | Reads |
|---|---|---|
| `ingest` | `filings`, `paragraphs`, `spans` (`paragraph_seed` only) | raw filing artifacts |
| `extract` | `spans` (`sentence`, `clause`, `phrase` only), `candidates` | `filings`, `paragraphs`, `spans` |
| `reconcile` | `deals`, `process_cycles`, `actors`, `actor_relations`, `events`, `event_actor_links`, `participation_counts`, `judgments` | `candidates`, `spans`, evidence tables |
| `validate` | `runs/{run_id}/validation_report.json`, `runs/{run_id}/ambiguity_queue.csv` | all canonical and evidence tables |
| `project` | `runs/{run_id}/*.jsonl`, `runs/{run_id}/*.csv`, `runs/{run_id}/run_memo.md` | all canonical and evidence tables |

## 4. Storage Architecture

**Hybrid: files for blobs, DuckDB for everything structured.**

- **Files** under `data/filings/{slug}/`: `raw.htm`, `raw.md`, `pages.json`, `manifest.json`. Bulk filing text stays on disk because it is read whole, not queried.
- **DuckDB** at `data/pipeline.duckdb`: a single embedded database file holding **every** structured table — `filings`, `paragraphs`, `spans`, `candidates`, all implemented canonical tables, any fixture-demanded auxiliary tables, `run_metadata`. Paragraph text and quote text are duplicated into rows (cheap; ~1-5 KB per paragraph) so SQL queries can search them.
- **Run snapshots** under `runs/{run_id}/`: a frozen copy of `pipeline.duckdb` plus exported reports/views.

**Why not files-everywhere:** Cross-filing queries ("every paragraph mentioning 'standstill' with no candidate yet") become brittle Python crawls. SQL is the right tool for the job at the structured layer, and DuckDB is single-file, embedded, no-server, columnar.

**Why not DuckDB-everywhere (including raw text):** Raw filings are 0.5-2 MB blobs read whole. The database structure does no work for blobs; storing them in rows adds overhead without payoff.

## 5. Repository Layout

```
src/sec_graph/
  __init__.py
  schema/                 # models, IDs, DDL, evidence helpers
    __init__.py
    models/
      __init__.py
      filings.py          # CleanFiling, Section, Paragraph, SourceSpan
      canonical.py        # Deal, ProcessCycle, Actor, ActorRelation, Event, EventActorLink
      judgments.py        # Judgment (with supersedes chain)
      participation_counts.py
      auxiliary.py        # advisor / counsel / board / terms / prior / bid-norm / cycle-phase (deferred until fixture-demanded)
      runtime.py          # RunMetadata
      extraction.py       # ExtractionCandidate (Stage 6+)
    ids.py
    evidence.py
    db.py
    versions.py
    schema_init.py
  fetch/                  # existing edgar.py moved here
    __init__.py
    edgar.py
  ingest/                 # markdown → DuckDB
    __init__.py
    cleaning.py
    paragraphs.py
    sections.py
    section_vocabulary.py
    spans.py
  extract/
    __init__.py
    rules/                # deterministic patterns (Stage 6)
      __init__.py
      actors.py
      events.py
      bids.py
    llm/                  # opt-in provider-neutral LLM candidate producer
      __init__.py
  reconcile/
    __init__.py
    aliases.py
    cycles.py
    boundaries.py
    judgments.py
    grouped_bidders.py
    anonymous_actors.py
  validate/
    __init__.py
    integrity.py
    flags.py
  project/
    __init__.py
    bidder_rows.py
    summaries.py
  cli/                    # per-track subcommand files (avoids merge conflicts)
    __init__.py
    ingest_cmd.py
    extract_cmd.py
    reconcile_cmd.py
    validate_cmd.py
    project_cmd.py
  cli.py                  # thin dispatcher: python -m sec_graph {subcommand} ...

scripts/
  fetch_filings.py        # thin fetch CLI shim

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
    smoke_canonical.json  # hand-authored canonical walkthrough
    canonical/{slug}.json # golden canonical outputs per example
    extract/smoke_candidates.json
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

`scripts/fetch_filings.py` is a deliberate root convenience command for EDGAR
downloads. It is not retained for backward compatibility; if a full
`python -m sec_graph fetch` command supersedes it, the script is deleted
rather than maintained as a duplicate command surface.

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

**`SourceSpan` shape — non-negotiables (see §17.2):**

- `span_basis: Literal["raw_md", "clean_text"]` declares which coordinate system `char_start`/`char_end` reference.
- `span_kind: Literal["paragraph_seed", "sentence", "clause", "phrase"]` distinguishes ingest seeds from extract-time tighter spans.
- `parent_evidence_id: str | None` — narrower spans reference their paragraph parent.
- `created_by_stage: Literal["ingest", "extract"]` — stage provenance.

Without these, narrower extract-time evidence cannot be distinguished from ingest seeds, and quote-hash mismatches across raw vs cleaned coordinates become unreviewable.

### 10.2 Append-only judgments + reviewer-override chain

Stage 9 (reviewer workflow) is **out of build scope** for this roadmap. But the schema must accommodate it on Day 1 to avoid retrofit cost.

Schema rule: `judgments` rows are append-only. A reviewer override is a *new* judgment row whose `supersedes_judgment_id` points to the prior judgment. Projections select the latest non-superseded row in the chain. This is cheap to bake into the schema now and expensive to retrofit later.

**Reviewer-override persistence across reruns (Stage 9 problem, flagged here).** The Run Model (§8) rewrites `pipeline.duckdb` on every rerun. Reviewer-added judgment rows would be lost unless they're persisted outside the pipeline-rewritten tables. Stage 9's design must answer: are reviewer overrides stored in a sidecar table or file (`reviewer_overrides.jsonl`?) that gets re-applied at the end of every pipeline run, or are they kept in a separate non-pipeline-rewritten DuckDB table? We do not solve this here, but Phase 1 schema work must leave room for either approach (e.g., do not declare `judgments` as exclusively rewritten by `reconcile`).

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
| **1A** | `schema` (evidence) | Pydantic models + DuckDB DDL for `filings`/`paragraphs`/`spans`/`run_metadata` + ID helpers + evidence utilities + smoke filing fixture. | All four evidence tables creatable; round-trip Pydantic ↔ DB; ID helpers stable; smoke filing fixture written; rerun-determinism test green. |
| **1B** | `schema` (canonical skeleton) | `Deal`, `ProcessCycle`, `Actor`, `Event`, `EventActorLink`, `Judgment`, `ParticipationCount` + hand-authored smoke canonical fixture. Auxiliaries deferred. | 11 tables creatable; smoke canonical FK-clean; module-table-ownership doc committed. |
| **2** | `ingest` | Markdown → `filings`, `paragraphs`, `spans` rows in DuckDB. | All 4 examples ingest deterministically; reruns produce identical IDs and hashes; section/page-marker preservation matches §3.3. |
| **3** | `reconcile` (skeleton) | Hand-author one filing's canonical records as a fixture. Walk the schema end-to-end. | One filing has complete canonical record set; all FKs resolve; all evidence_ids point to valid spans. |
| **4** | `validate` | Hard-failure + soft-flag separation; ambiguity-queue export. | Stage-3 hand-authored fixture passes all hard checks; an intentionally-broken fixture fails with the right error class. |
| **5** | `project` | Wire to DuckDB; export bidder-cycle rows + companion views per §3.7. | Stage-3 hand-authored canonical produces an expected `bidder_rows.jsonl` and `run_memo.md`. |
| **6** | `extract/rules` | Deterministic patterns for actor mentions, dated events, bid values on the 4 examples. | Candidate output matches a hand-curated golden set on PetSmart and Saks; every candidate has at least one evidence_id. |
| **7** | `reconcile` (real) | Replace Stage 3 manual fixtures with rule-extracted candidates → canonical. Add judgments. | All 4 examples produce canonical records; bidder-cycle rows match a hand-curated expected set. |
| **8** | `extract/llm` | Provider-isolated LLM candidate producer for events/aliases that rules miss. Bound by `docs/llm-interface.md`: streaming Linkflow transport, strict provider JSON schema, Python-owned quote offsets, no fallback, no backward compatibility. | Behind explicit flags; deterministic outputs unchanged when flag off. |
| **9** (out of roadmap) | reviewer workflow | Reviewer triages ambiguity queue; overrides emit new judgments referencing prior. | Out of build scope. Schema accommodates per §10.2. |

## 13. Parallelization and Critical Path

After Stages 1A and 1B land, the remaining build splits into three parallel tracks that converge at Stage 7. Stage 1 is sequential because every other module depends on the schema; once it is stable (with the smoke filing fixture and a hand-authored canonical fixture verifying the contract end-to-end), three streams advance independently.

### 13.1 Tracks

**Track A — Data path:** Stage 2 (`ingest`). Operates on raw markdown; produces `paragraphs` and `spans` rows in DuckDB. No dependency on Tracks B or C.

**Track B — Schema validation path:** Stage 3 (`reconcile` skeleton) → Stage 4 (`validate`) → Stage 5 (`project`). Uses hand-authored canonical fixtures committed to `tests/fixtures/canonical/`, so it does not wait on real extraction. Proves the schema contract end-to-end. Sequential within the track because each stage depends on the prior fixture's existence.

**Track C — Extraction path:** Stage 6 (`extract/rules`). Begins against the smoke filing (built in Stage 1) for early regex / pattern development. Full acceptance against the four real example filings depends on Track A finishing.

### 13.2 Convergence

All three tracks merge at **Stage 7** (`reconcile` real). Stage 7:
- Replaces Stage 3's hand-authored fixtures with rule-extracted candidates from Track C, against Track A's ingested paragraphs/spans.
- Validates the result through Track B's `validate` and `project` modules.

Stage 8 (`extract/llm`) is downstream of Stage 7 and now implemented as an opt-in candidate producer. Stage 9 (reviewer workflow) is out of build scope.

### 13.3 Critical Path

The expected critical path is **Stage 1A → Stage 1B → Stage 2 → Stage 6 → Stage 7**, driven by extraction rules being the largest single piece of work and depending on real ingested data. Track B (Stages 3 → 4 → 5) typically finishes inside the shadow of Track C and does not extend total duration.

```
Stage 1A ─► Stage 1B ─► Stage 2 ──► Stage 6 ──► Stage 7        (critical path)
                │                                   ▲
                └─► Stage 3 ──► Stage 4 ──► Stage 5┘            (Track B, parallel)
```

### 13.4 Risks and Mitigations

- **Schema iteration risk.** A schema gap discovered mid-track invalidates parallel work. Mitigation: Phase 0/1 deliverables include both the type definitions *and* a hand-authored canonical example on the smoke filing, so the schema is exercised end-to-end before fan-out. The non-negotiables in §10.1 and §17.2 land in Phase 0.
- **Coordination cost.** Each module has a declared input/output via the DuckDB schema (§3 + §4). As long as schema changes route through Phase 0/1 with a version bump (§9), parallel tracks do not step on each other.
- **Solo-contributor reality.** Parallelism is most valuable with multiple contributors / agents. A solo developer can still benefit from interleaving Track B with Track C while Track A runs first, because Track B unblocks early end-to-end validation feedback before extraction is complete.
- **Track C partial dependence.** Stage 6's smoke-filing milestone ships independently; its real-filing acceptance waits on Stage 2. Track C is therefore planned as two explicit milestones: (a) smoke-only, (b) all-four-examples.

### 13.5 Recommended Sequencing

1. Stage 1A alone (evidence-store schema + corrections + smoke filing fixture). Land it.
2. Stage 1B alone (canonical skeleton + hand-authored smoke canonical fixture). Land it.
3. Fan out: Track A (Stage 2), Track B (Stages 3 → 4 → 5), Track C (Stage 6) in parallel.
4. Sync at Stage 7.
5. Optionally run Stage 8 through explicit LLM flags.

The current deployable canonical-pipeline `/goal` is described in
`quality_reports/plans/2026-05-02_deployable-canonical-pipeline-goal.md` and
implemented through
`quality_reports/plans/2026-05-02_deployable-canonical-pipeline-plan.md`. The
hard-cleanse-and-repair work that bridges to this goal is the executing plan
`quality_reports/plans/2026-05-02_stale-scaffold-hard-cleanse-repair-plan.md`.
Older parallelization or stage-overlay plans are no longer execution authority.

## 14. What's Explicitly Out of Scope (For This Roadmap)

- **LLM canonical writing.** Stage 8 is a candidate producer only. LLM output never writes canonical rows, projection rows, reviewer judgments, or provider-specific schema fields.
- **Reviewer workflow UI.** Stage 9 is acknowledged but not built; the schema accommodates it (§10.2).
- **Whole-corpus runs.** Stages 1A-7 target the 4 examples. Running across all ~400 deals in `seeds.csv` happens only after Stage 7 acceptance.
- **External-metadata enrichment.** Bidder domicile, advisor rankings, public/private status, industry codes, etc., require external datasets the trimmed filings don't supply. The schema has fields for them; population is future work.
- **CVR / non-cash consideration normalization.** Stored faithfully (raw text + flag); converting to per-share cash equivalents for `r_23` requires policy outside the filing — deferred.

## 15. Open Questions

These are unresolved and will be revisited at the relevant stage:

- **Section vocabulary.** §3.3 lists a starter set of section headings. The full vocabulary is finalized during Stage 2 implementation; any heading not in the vocabulary lands in `unknown_section` and is fixable later by extending the list.
- **Cleaning patterns.** The exact regex set for printer-command lines, ZEQ banners, and folio-number stripping is enumerated and reviewed in Stage 2 before any stripping happens.
- **`cycle_relation` value set.** Whether go-shops are encoded as same-cycle tails, separate cycles, or both (configurable per projection). Decided in Stage 4 / Stage 7.
- **Dropout-mechanism evidence rules.** The text patterns / linked events that justify `target-rejected` vs `voluntarily-withdrew` vs `ambiguous` are codified in Stage 7.
- **Anonymous aggregate-bidder policy.** Count-only `participation_counts` do not create baseline bidder rows. Open projection work may later decide whether a named sensitivity view includes synthetic count-derived rows, but that must be explicit and judgment-backed, not a canonical default.
- **LLM provider interface.** Stage 8 is bound by [`docs/llm-interface.md`](./llm-interface.md): provider-neutral, deterministic-output-respecting, evidence-emitting by exact quote text only, feature-flagged, candidate-only, and locally span-resolved.
- **Reviewer UI shape.** Out of scope for this roadmap. The schema affordance (§10.2) is what we commit to today.

## 16. Related Documents

- [`quality_reports/plans/2026-05-02_stale-scaffold-hard-cleanse-repair-plan.md`](../quality_reports/plans/2026-05-02_stale-scaffold-hard-cleanse-repair-plan.md) — executing cleanup-and-repair plan, in force until every phase inside it is complete.
- [`quality_reports/plans/2026-05-02_deployable-canonical-pipeline-goal.md`](../quality_reports/plans/2026-05-02_deployable-canonical-pipeline-goal.md) — goal handoff for the live deployable proof.
- [`quality_reports/plans/2026-05-02_deployable-canonical-pipeline-plan.md`](../quality_reports/plans/2026-05-02_deployable-canonical-pipeline-plan.md) — implementation plan paired with the goal handoff.
- [`docs/llm-interface.md`](./llm-interface.md) — provider-neutral LLM extraction interface.
- [`docs/prior-pipeline-lessons.md`](./prior-pipeline-lessons.md) — failure-mode postmortem from the previous extraction attempt; informs §17 invariants.
- [`AGENTS.md`](../AGENTS.md) — repository contract for agents.
- [`CLAUDE.md`](../CLAUDE.md) — Claude Code orientation.
- [`quality_reports/session_logs/README.md`](../quality_reports/session_logs/README.md) — point-in-time proof-log index.

## 17. Stage 1 Slicing (Approved Addendum)

The original Stage 1 plan was overbroad. It implemented the entire 21-table canonical universe up front. Per the construction-advice review (now folded into this section), Stage 1 splits into two sub-stages with clear acceptance gates.

### 17.1 Stage 1A — Evidence Store

**Goal.** Prove the database foundation (DuckDB + Pydantic + ID helpers + evidence utilities) on the smallest table set that exercises the hardest invariant: evidence must point back to exact filing text.

**Implements only:** `filings`, `paragraphs`, `spans`, `run_metadata`. Deterministic ID helpers. Quote/hash utilities. Schema/version constants. Smoke filing fixture. DuckDB create/insert/fetch tests. Rerun-determinism test over the smoke fixture.

**Does NOT implement in 1A:** Any canonical table. `ExtractionCandidate`. Auxiliary tables. Reconciliation, validation, projection, LLM. Rich auxiliary tables.

**Acceptance:** see Stage 1A row in §12 + the parallel plan §3.

### 17.2 Stage 1A Non-Negotiables (the corrections that prevent retrofit)

These three schema details are not optional. Without them, downstream modules will silently corrupt evidence:

1. **Span coordinate basis.** `SourceSpan.span_basis: Literal["raw_md", "clean_text"]`. If cleaning changes offsets, both raw and clean coordinates can be stored, but every span must declare which system it uses. Without this, quote hashes become decorations.
2. **Span parentage.** `SourceSpan.parent_evidence_id: str | None` plus `span_kind: Literal["paragraph_seed", "sentence", "clause", "phrase"]`. Ingest creates paragraph seeds; extract creates tighter spans inside them. Mixing them as if equivalent is the failure mode.
3. **Span stage provenance.** `SourceSpan.created_by_stage: Literal["ingest", "extract"]`. Distinguishes ingest evidence from rule/model-created evidence at audit time.

### 17.3 Stage 1B — Minimal Canonical Skeleton

**Goal.** A canonical-table walkthrough on the smoke filing that exercises the *core* lessons (actors ≠ events, counts ≠ actors, judgments ≠ facts) without trying to be the whole research ontology.

**Implements:** `Deal`, `ProcessCycle`, `Actor`, `ActorRelation`, `Event`, `EventActorLink`, `Judgment` (with `supersedes_judgment_id`), `ParticipationCount`. Module-table-ownership doc. Hand-authored smoke canonical fixture covering: one target, two bidders, one process cycle, two bid events, one boundary judgment, one dropout judgment, one unnamed cohort participation count, and one relation row when a fixture supplies relationship evidence.

**Does NOT implement in 1B:** Auxiliary tables (advisor, counsel, board, terms, group, prior, bid-norm, cycle-phase). `ExtractionCandidate`.

**Acceptance:** see Stage 1B row in §12 + the parallel plan §4.

### 17.4 Defer Until A Fixture Demands Them

These tables are named in the schema but have no immediate implementation, no DDL, no round-trip test, until a concrete fixture exercises them:

- `advisor_engagements`
- `legal_counsel_engagements`
- `board_committees`
- `deal_terms`
- rich group-specific membership tables beyond generic `actor_relations`
- `prior_relationships`
- `bid_normalizations` (beyond one minimal numeric bid)
- `cycle_phase_assignments` (beyond the first projection test)

When an extraction or reconciliation fixture cannot avoid one of these, the table lands at that moment with: a fixture row, a model, DDL, a round-trip test, and a documented `created_by_stage` provenance for any new spans it requires. Until then the schema names the concept but does not allocate storage.

## 18. Construction Principles (Approved Patterns)

These principles bind the implementation regardless of which module a contributor or agent is in.

### 18.1 Avoid these traps

- **Schema theater.** "All tables create successfully" is necessary but weak. The strong test is a fixture that writes rows, reads them back, verifies evidence hashes, and reruns deterministically.
- **Premature auxiliary tables.** See §17.4. Adding tables before paragraph/span evidence is solid distracts from the foundation.
- **Rebuilding the old flat row inside DuckDB.** Do not create one giant canonical event row that owns actor identity, bidder lifecycle, bid value, formal-stage admission, dropout, and projection status. Keep these separate: event facts; actor identity; actor-event links; participation counts; group relationships; judgments; projection rows.
- **Implicit cross-module SQL ownership.** A shared DuckDB can become a hidden monolith. Each module has explicit read/write ownership (see plan §9). If a module needs another module's internals, change the schema contract rather than reaching around it.
- **Treating projection code as canonical truth.** Whether a bidder is `admitted` is a canonical decision that lives in `judgments`, not a SELECT-side inference from "post-boundary proposal exists."

### 18.2 When adding a table, ask:

1. What filing fact or construction fact does this table preserve?
2. Which fixture will create at least one row?
3. Which later module consumes it?
4. What invariant would fail if this table were wrong?

If the answers are vague, defer the table.

### 18.3 When adding a field, ask:

1. Is it factual, interpretive, or runtime metadata?
2. Does it need evidence?
3. Is null ambiguous? If yes, where is the null reason stored?
4. Does it belong in a judgment instead?

If the answer is "maybe," prefer a judgment or a later fixture-driven addition.

### 18.4 Build principles for future agents

1. Start every module from its input and output contract.
2. Preserve source evidence before normalizing it.
3. Make uncertainty a record, not a prose note.
4. Keep provider behavior outside the canonical schema.
5. Prefer rebuilds from raw filings over migrations of derived artifacts.
6. Treat reviewer overrides as append-only judgments.
7. Make every export reproducible from a run snapshot.
8. Keep estimator rows downstream of canonical truth.

The right goal is not a complete ontology on day one. The right goal is a small database that cannot lie about where its evidence came from. Once that exists, the rest of the pipeline can grow without repeating the old flat-row mistakes.

### 18.5 Atomization and Relation Doctrine

The governing schema rule is:

> Store source facts at the level the filing supports. Atomize only in a named projection, with a judgment explaining why that actor is eligible for that projection.

Extraction must not decide buyer-group atomization by row shape. PetSmart-style buyer groups should be decomposed canonically when the filing supplies member, vehicle, financing, rollover, or support-holder evidence, but the baseline bidder-cycle projection should treat a group bid vehicle as one bidder row when the bid is source-described as group-level. Member-split projections are sensitivity views unless a current `projection_eligibility` judgment supports each member as a distinct projection decision unit.

Generic `actor_relations` is the first-class relation surface for buyer-group membership, affiliate structures, financing participation, rollover participation, support agreements, acquisition vehicles, and advisor-client relationships. It is not optional and not deferred. Do not add a narrow relation table until a fixture proves that `actor_relations` plus `events`, `event_actor_links`, `participation_counts`, and `judgments` cannot represent the source fact without loss.

`ParticipationCount` rows are cohort observations, not actor-creation instructions. Count-only anonymous cohorts may support process summaries, ambiguity queues, or future first-stage/covariate analyses. They do not enter the baseline bidder-row projection unless named actor evidence and projection eligibility judgments justify the row.

No fallback enum values are permitted anywhere in the canonical schema. `unknown`, `other`, miscellaneous catch-all values, provider-owned categories, and backward-compatible aliases are forbidden. Closed enums are listed in §1A; if a source fact cannot be classified into a closed value, the pipeline must not write the row, and must instead preserve the evidence as a candidate, a validation failure, or a reviewer-facing ambiguity.

No row-shaped downstream bidder identity is permitted in canonical tables. `Actor` is the source-backed identity surface; bidder-cycle decision units are produced only as deterministic projection rows justified by current `projection_eligibility` judgments. Old-pipeline names that fused identity, bidder lifecycle, bid value, formal-stage admission, dropout, and projection status into one row are explicitly rejected.

No deal-specific or PetSmart-only schema surface is permitted. Schema fields, table shapes, and enum values must generalize across all reference deals listed in `quality_reports/plans/2026-05-02_deployable-canonical-pipeline-goal.md`. PetSmart-style buyer-group facts (BC Partners, CDPQ, GIC, StepStone, Longview, late-Longview rollover/support, acquisition vehicles, financing) must be representable through generic `actor_relations`, `events`, `event_actor_links`, `participation_counts`, and `judgments`. They must not require a PetSmart-only table or PetSmart-only field.

---

**End of spec.**
