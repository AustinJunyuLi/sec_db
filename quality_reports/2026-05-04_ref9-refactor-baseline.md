# Reference-9 Schema Refactor — Baseline Synthesis (2026-05-04)

**Status:** BASELINE — orientation document, not a design spec.
**Audience:** Future sessions, Ralph-loop iterations, contributors picking up the refactor.
**Purpose:** Consolidate four parallel baselines so subsequent design and implementation work shares one shared understanding. The four sections are independent — read in any order, or read top-down for the full picture.

The four sections answer:
1. **Where does this codebase currently stand?** A clean snapshot of the repo, the in-flight branch, and the existing implementation.
2. **What did Alex say, and what did the previous pipeline do?** Two parallel histories — Alex's methodology from `bids_try`, and the trajectory of `sec_graph` up to the current canonical-narrative hard reset.
3. **What are we trying to do?** The product goal, the architectural shape, what's in and out of scope.
4. **What is the success gate?** Concrete, testable criteria for "done."

This document is the orientation reference. Architectural decisions live in the design spec (forthcoming under `docs/superpowers/specs/`). Execution lives in the implementation plan (forthcoming under `quality_reports/plans/`). Read this first.

---

## Section 1 — Where Does This Codebase Currently Stand?

A snapshot of the `sec_graph` repository at `/Users/austinli/Projects/sec_graph` as of 2026-05-04.

### 1.1 Branch and In-Flight State

**Current branch:** `schema-robustness-readfirst-20260503` (not main).

**Working tree (`git status --short`):**

| Status | Path | Surface |
|--------|------|---------|
| M | `docs/llm-interface.md` | LLM interface contract (binding) |
| M | `docs/spec.md` | Pipeline / schema spec (binding) |
| D | `quality_reports/plans/2026-05-03_taxonomy-refactor-handoff.md` | Deleted from working tree |
| D | `quality_reports/plans/2026-05-03_taxonomy-refactor-supplement.md` | Deleted from working tree |
| M | `quality_reports/session_logs/2026-05-03_taxonomy-classification-design.md` | Active session log |
| M | `src/sec_graph/extract/llm/convert.py` | Linkflow payload -> claims insert |
| M | `src/sec_graph/extract/llm/linkflow.py` | Linkflow streaming adapter |
| M | `src/sec_graph/extract/llm/models.py` | Pydantic request/response models |
| M | `src/sec_graph/extract/llm/prompt.py` | System and window prompts |
| M | `src/sec_graph/validate/integrity.py` | Hard validation checks |
| M | `tests/test_coverage_semantics.py`, `test_hard_reset_schema.py`, `test_llm_p7_contract.py`, `test_validation_semantics.py` | Tracking the LLM/validate edits |
| ?? | `quality_reports/plans/2026-05-03_combined-taxonomy-region-design.md` | New plan, untracked |
| ?? | `quality_reports/plans/2026-05-03_ref9_schema_refactor_goal_spec.md` | New goal spec, untracked |
| ?? | `quality_reports/plans/2026-05-03_ref9_schema_refactor_implementation_plan.md` | New plan, untracked |
| ?? | `quality_reports/plans/2026-05-03_taxonomy-refactor-plan.md` | New plan, untracked |
| ?? | `quality_reports/schema_read/` | New directory (`2026-05-03_background-shape-scan.md` inside) |

The two `taxonomy-refactor-*` files (handoff, supplement) are deleted in the working tree but exist at HEAD. Replacement plans (taxonomy-refactor-plan, combined-taxonomy-region-design, two ref9_schema_refactor docs) are untracked. Uncommitted code changes are concentrated in the LLM extraction layer (`extract/llm/*.py`) and the validation layer (`validate/integrity.py`). `git diff --stat HEAD` shows ~483 insertions / ~1287 deletions across the working tree (large deletions are the two retired taxonomy plans).

### 1.2 Recent Commit Trajectory

Last 20 commits run from `a1e3e47` through HEAD `4f10ac3`. Three arcs:

- **LLM contract foundation (`e9e1612` -> `e37ee1a`):** provider-neutral LLM contract, Linkflow adapter, prompt-only contract hardened, Stage 8 live proof.
- **Hard cleanse merge (PR #1, `f8f4ac1`):** stale scaffold removal, deployable pipeline contract hardening, fail-loud tender resolver and `--fresh` top-level dispatch, evidence source-truth chain, no-fabrication reconcile semantics.
- **Hard reset (`7cc2fc6` -> `4f10ac3`):** pipeline hard reset designed, run kernel + cost envelope added, subagent execution model required, P7 high-reasoning background extraction adopted, "complete canonical narrative hard reset" landed at HEAD.

### 1.3 Module Map

7,538 lines of Python under `src/sec_graph/`, grouped by package:

| Package | Module | LOC | Purpose |
|---------|--------|-----|---------|
| extract/llm | `linkflow.py` | 516 | Linkflow streaming adapter (Responses API), retries, schema constraint, sanitized artifacts |
| extract/llm | `convert.py` | 309 | Insert validated typed claims; resolve quote -> spans; assign coverage results |
| extract/llm | `models.py` | 202 | Pydantic models for requests, claims, payloads, provider config |
| extract/llm | `prompt.py` | 109 | System + window prompt + obligation acceptance rules |
| extract/llm | `requests.py` | 102 | Build `LLMWindowRequest` from `evidence_regions` + obligations |
| extract | `evidence_map.py` | 125 | Build `Background of the Merger` evidence region + obligations |
| extract/rules | `actors.py` `relations.py` `counts.py` `events.py` | 64-188 | Rules-only stage (offline / dev) |
| schema/models | `extraction.py` | 367 | Claims, evidence regions, coverage tables; closed enums; DDL |
| schema/models | `canonical.py` | 365 | Generic canonical graph (deals, actors, events, etc.); DDL |
| schema/models | `runtime.py` `filings.py` `judgments.py` | 65-166 | Runtime tables, filings/paragraphs/spans, judgment ledger |
| reconcile | `pipeline.py` | 532 | Claims -> canonical graph; disposition assignment |
| reconcile | `boundaries.py` `aliases.py` `cycles.py` | 66-108 | Cycle/event boundary, label aliasing |
| validate | `integrity.py` | 408 | Hard checks (claim disposition, coverage, row evidence, semantic claim evidence, source truth, projection unit) |
| project | `summaries.py` | 438 | `proof_summary`, verdict assignment, cost summary, projection outputs |
| project | `bidder_rows.py` | 133 | Deterministic bidder rows from canonical graph |
| cli | `run_cmd.py` | 276 | Full-pipeline `run` subcommand |
| cli | `__init__.py` | 90 | Top-level dispatcher (`python -m sec_graph`) |
| cli | other `*_cmd.py` | <70 each | Stage subcommands |
| run | `kernel.py` `io.py` `ids.py` `progress.py` `lock.py` | 60-126 | RunKernel, atomic IO, RunClock, progress ledger, lock |
| ingest | `pipeline.py` | 129 | Filing markdown -> filings + paragraphs + spans |
| ingest | `paragraphs.py` `cleaning.py` `sections.py` `spans.py` | <100 each | Paragraph splitting, cleaning, sections |
| top-level | `corpus.py` | 278 | Corpus skeleton (manifest, shard plan, attempt/failure ledgers) |
| top-level | `costs.py` | 229 | Cost/runtime envelope projections |
| fetch | `edgar.py` | 385 | EDGAR downloader, sec2md conversion |

### 1.4 CLI Surface

Entry point: `python -m sec_graph` -> `src/sec_graph/__main__.py` -> `src/sec_graph/cli/__init__.py`. Subcommands registered at `cli/__init__.py:13-21`: `ingest`, `extract`, `reconcile`, `validate`, `project`, `run`, `snapshot`. The `--fresh` flag is forwarded by the dispatcher (`cli/__init__.py:87-88`).

`run` subcommand required flags (per `cli/run_cmd.py:34-48`):
- mutually exclusive group: `--all` OR `--slugs ...` (line 35-36)
- `--run-dir PATH` (line 41)
- `--run-id STRING` (line 42)

Defaults at `run_cmd.py:37-47`: `--source examples`, `--projection bidder_cycle_baseline_v1`, `--llm-reasoning-effort high`, `--request-mode semantic_claims_v1`, `--llm-model gpt-5.5`. Live LLM is gated by `--llm-provider linkflow` (only allowed value).

### 1.5 Tests

Test files under `tests/` (12 modules):

| File | Purpose |
|------|---------|
| `test_cli_dispatch.py` | CLI dispatcher contract per `docs/spec.md` |
| `test_corpus_cost_envelope.py` | Corpus skeleton + cost/runtime envelope contract |
| `test_coverage_semantics.py` | Coverage obligation linking + `claims_emitted` — **MODIFIED** |
| `test_edgar.py` | EDGAR fetcher / tender exhibit selection |
| `test_hard_reset_schema.py` | End-to-end schema replacement — **MODIFIED** |
| `test_ingest_examples.py` | Ingest fixtures contract |
| `test_llm_p7_contract.py` | P7 prompt + Linkflow JSON-schema contract — **MODIFIED** |
| `test_package.py` | `__version__` smoke |
| `test_repo_freshness_contract.py` | Stale-file freshness gate |
| `test_run_kernel.py` | Run kernel atomic writes, lock, resume |
| `test_stale_rules_and_reconcile.py` | Stale-rule import / no-fabrication gates |
| `test_validation_semantics.py` | Bid + actor-relation quote-support — **MODIFIED** |

`tests/fixtures/` holds extract fixtures (`real_candidate_golden.json`). The four modified tests track LLM extract + validate edits.

### 1.6 Data on Disk

`data/filings/` holds **40 directories** (per `ls data/filings/ | wc -l`). Each filing directory has four files: `manifest.json`, `pages.json`, `raw.htm`, `raw.md`.

**All 9 reference deals are present** with the four-file layout: `providence-worcester`, `medivation`, `imprivata`, `zep`, `petsmart-inc`, `penford`, `mac-gray`, `saks`, `stec`. The other 31 deals are part of the broader corpus (e.g., `acacia-communications-inc`, `cephalon-inc`, `vectren-corp`).

`data/examples/` is the default ingest source for development runs (`cli/run_cmd.py:37`).

### 1.7 Probe History

`quality_reports/llm_calibration/` contains: `REVIEWER_GUIDE.md`, `2026-05-03_linkflow-probe-log.md` (narrative session log), four probe scripts (`probe_lf_macgray.py`, `probe_lf_macgray_background.py`, `probe_lf_matrix.py` (603 lines), `probe_lf_scale.py`), `macgray_agentic_scan_result.txt` (697 KB raw scan output), and the `2026-05-03T175805Z_linkflow-p7-matrix_<sha>/` artifact directory.

The 2026-05-03T175805Z probe ran a **3 deals × 2 region scopes × 2 reasoning efforts** matrix:
- Deals: `mac-gray`, `petsmart-inc`, `zep`
- Scopes: `background` (Background of the Merger only) and `raw` (whole filing)
- Efforts: `medium`, `high`
- 12 records: 11 ok, 1 failed (`mac-gray_raw_medium_provider_incomplete_salvaged.json`)

Per `report.md`: all six background cells produced 10/10 coverage with zero quote ambiguity; raw-filing cells had quote misses in every valid cell. High reasoning closed the only background quote miss (mac-gray) and roughly tripled wall time vs medium.

### 1.8 Authority Chain (Current)

Per `CLAUDE.md:11-19`:
1. `docs/superpowers/specs/2026-05-03-pipeline-hard-reset-design.md` — full-pipeline authority for the hard reset (832 lines, committed).
2. `docs/spec.md` — binding design and schema contract — **MODIFIED in working tree**.
3. `docs/llm-interface.md` — Linkflow typed-claim interface contract — **MODIFIED in working tree**.

Failure-mode context only (not execution authority): `docs/prior-pipeline-lessons.md`.

The committed `docs/spec.md` declares the active architecture as: SEC filing -> run kernel -> ingest -> evidence map -> Linkflow GPT-5.5 typed semantic claims -> Python quote validation -> claim disposition ledger -> canonical graph -> semantic validation -> actor-cycle projection -> proof / cost-runtime artifacts.

### 1.9 Concrete Known Issues (Verified by Reading)

**Verdict logic location.** `src/sec_graph/validate/integrity.py` does **not** contain the strings `SOUND` / `SUSPECT` / `BLOCKED` / `UNSOUND`. Only `RULES_ONLY_SOUND` appears, as an enum member at `validate/integrity.py:29`. Actual verdict assignment lives in `src/sec_graph/project/summaries.py:115-125`: `proof_summary()` initializes `verdict = "SOUND"` then downgrades based on live claim count, undisposed claims, missing evidence, validation failures, and thinness.

**Static obligation list still in evidence_map.** `extract/evidence_map.py:14-25` defines `_BACKGROUND_OBLIGATIONS` as a hardcoded 10-tuple covering only the `Background of the Merger` section: 3 events (sales process initiation, final round bid receipt, exclusivity grant), 2 participation counts (IOI stage, first round), 3 actors (target board, target financial advisor, target legal advisor), 1 bid (final bid price), 1 actor relation (buyer group composition). `build_evidence_map()` at line 60 selects only paragraphs in section `"Background of the Merger"`; filings without that section fail with `ValueError` at line 62. Lines 56-58 delete prior coverage results, obligations, and regions before recreating them.

**`actor_class` enum is three values, not four.** `schema/models/extraction.py:82` defines `ActorClass = Literal["financial", "strategic", "mixed"]`. The DuckDB DDL repeats the same closed set at line 323: `CHECK (actor_class IN ('financial', 'strategic', 'mixed'))`. `extract/llm/models.py:130` re-uses the same import. There is no `null` / `s` / `f` / four-value variant.

**Single-region production.** `extract/llm/requests.py:13-52` builds one `LLMWindowRequest` per row in `evidence_regions` (ordered by priority). Combined with `_BACKGROUND_OBLIGATIONS` and single-region creation in `evidence_map.py`, production today produces exactly one Linkflow window per filing.

**Coverage-result ownership.** `extract/llm/convert.py:127-152` is where Python assigns `claims_emitted` (line 134) when at least one validated claim links to an obligation, `missed` (line 140) when neither claims nor a provider coverage_result exist, else the provider's `no_supported_claim` / `ambiguous` result. Provider can never assign `claims_emitted` or `missed`.

**Quote resolution.** `extract/llm/convert.py:190-207` (`_resolve_quote`) uses `paragraph_text.find(quote_text)` and enforces uniqueness across the whole window: multiple matches raise `LLMContractError("quote_text is ambiguous within window")`; zero matches raise `LLMContractError("quote_text is not an exact window substring")`.

**Thin-live threshold.** `project/summaries.py:114` defines `thin_live = live_claims < max(1, row_counts["coverage_obligations"] // 3)`. Live count is filtered by `provider_source_stage = 'linkflow'` (line 113); `'rules'` claims do not count toward liveness.

---

## Section 2 — Two Parallel Baselines

This section places Alex Gorbenko's M&A research methodology and the previous `sec_graph` pipeline side-by-side, as historical/current artifacts. Neither side is the target. Both are inputs to the calibration we now do against.

### Part A — Alex's methodology

#### A.1 Goal of the data collection

Alex's research target is **informal bidding in corporate takeover auctions** (`/Users/austinli/bids_try/reference/CollectionInstructions_Alex_2026.pdf`, §1). The collection is the bidding history extracted from the "Background of the Merger" narrative inside four primary SEC form types: **DEFM14A**, **PREM14A**, **SC TO-T**, and **S-4**. The raw material lives in the prose chronology of the merger background, not on the EDGAR cover page.

The instruction document is bilingual in two senses: black text are the original Chicago RA instructions; **bold red** text are Alex's additions and corrections (PDF p. 1, §1.a). Alex framed the entire workbook to Austin as a **calibration target for an AI handoff**: *"This will allow us to fine-tune collection instructions in order to eventually feed them to an AI"* (PDF p. 3, §2). The 9 corrected reference deals are explicitly chosen *"from the middle of the database … because earlier deals are collected poorly"* (PDF p. 1).

#### A.2 Unit of analysis: events, not deals or bidders

The atom of Alex's workbook is the **event row**, not the deal and not the bidder. Each row in the 35-column workbook is one dated occurrence in the takeover process: an NDA signing, a bid submission, a drop, a final-round announcement, an investment-bank retention, an executed merger.

The `BidderID` column carries the famously misleading name. Alex disclaims it on PDF p. 2: *"this is an unfortunate name that really just enumerates events in their historical order. It can be about a bidder making a formal or informal bid, signing an NDA, dropping out (or getting dropped out by the target), the IB signing an agreement, and so on."* The Chicago version used integers `1..N`. Alex's version uses **non-integer wedge values**: *"if an IB signed a confidentiality agreement between event 1 and 2 in the original dataset, I would give 1.5 to the event of IB retention."* So `BidderID` is an event-sequence index with insertion semantics, not a stable bidder identity.

The 35 columns of `deal_details_Alex_2026.xlsx`:
`(unnamed index)`, `TargetName`, `gvkeyT`, `DealNumber`, `Acquirer`, `gvkeyA`, `DateAnnounced`, `DateEffective`, `DateFiled`, `FormType`, `URL`, `Auction`, `BidderID`, `BidderName`, `bidder_type_financial`, `bidder_type_strategic`, `bidder_type_mixed`, `bidder_type_nonUS`, `bidder_type_note`, `bid_value`, `bid_value_pershare`, `bid_value_lower`, `bid_value_upper`, `bid_value_unit`, `multiplier`, `bid_type`, `bid_date_precise`, `bid_date_rough`, `bid_note`, `all_cash`, `additional_note`, `cshoc`, `comments_1`, `comments_2`, `comments_3`. Several of these (`gvkeyT`, `gvkeyA`, `cshoc`, `DealNumber`, `DateFiled`, `FormType`, `URL`) are external-database / EDGAR metadata, not filing-narrative facts.

#### A.3 Auction classification — the single gating rule

Alex's auction-vs-not classifier is one rule (PDF p. 4, §2.1):

> "Multiple bidders have signed/executed confidentiality agreements … Financial and legal advisors to a deal also sign confidentiality agreements. Those instances are to be ignored for the classification purpose."

Auction status is **deal-level boolean**, derived from a count of NDAs that exclude advisor NDAs and exclude any NDAs from a stale prior process. There is no formal-bid count, no exclusivity test, and no merger-signed test in the auction definition. It is purely the count of **non-advisor bidder NDAs** in the current sale process.

#### A.4 The `bid_note` vocabulary

Alex's `bid_note` column carries a closed enumerated vocabulary. The actual workbook (sampled directly from `deal_details_Alex_2026.xlsx`) shows **29 distinct values**:

`Activist Sale`, `Bid Press Release`, `Bidder Interest`, `Bidder Sale`, `Drop`, `DropAtInf`, `DropBelowInf`, `DropM`, `DropTarget`, `Exclusivity 30 days`, `Executed`, `Final Round`, `Final Round Ann`, `Final Round Ext`, `Final Round Ext Ann`, `Final Round Inf`, `Final Round Inf Ann`, `Final Round Inf Ext`, `Final Round Inf Ext Ann`, `IB`, `IB Terminated`, `NA`, `NDA`, `Restarted`, `Sale Press Release`, `Target Interest`, `Target Sale`, `Target Sale Public`, `Terminated`.

The PDF identifies which are Alex-additions versus Chicago-original. Per the instruction document the **Chicago-original** items are: `NDA`, `Drop`, `DropBelowM` (renamed `DropM` in the workbook), `Bid` (per `bid_type`, `bid_value`, blank `bid_note`), `Press Release`. **Alex's additions** are: all sale-process initiation codes (`Target Sale`, `Target Sale Public`, `Bidder Sale`, `Bidder Interest`, `Activist Sale`), `IB` and `IB Terminated`, `Executed`, `Terminated`, `Restarted`, the additional drop subtypes (`DropBelowInf`, `DropAtInf`, `DropTarget`), and the entire `Final Round*` family with the four-axis matrix (Ann/Ext/Inf combinations). The exclusivity row `Exclusivity 30 days` is encoded as a row, not as a field. Press releases bifurcate into `Sale Press Release` vs `Bid Press Release` (PDF p. 5, §3.2).

#### A.5 Bidder-type vocabulary

Per the PDF (p. 7, Table 1) `bidder_type_note` is a free-text-derived scalar: **`S`** for strategic (CEO involvement, corporate-operating buyer), **`F`** for financial (private-equity, buyout fund, sovereign wealth, family office, SPAC), with optional prefixes `non-US`, `public`, `private`, combinable as `"non-US public S"`. The workbook also has separate boolean-style columns `bidder_type_financial`, `bidder_type_strategic`, `bidder_type_mixed`, `bidder_type_nonUS` that pre-date the consolidated `bidder_type_note` text. Alex notes these can mark a *consortium* as `mixed` when constituents span S and F types.

#### A.6 Bid-formality decision rule

Per PDF p. 7, §3.5 (Table 2), informal vs formal is decided by three filing-text triggers, evaluated in this order:

1. **Range bid → informal.** *"any bid expressed as a range is also to be classified as informal bid."* True structural signal; range always wins.
2. **Subset invitation to a final round → formal.** *"Record a formal bid if the company announced a final round of bidding that only a subset of bidders is invited to."*
3. **Markup of merger agreement returned → formal.** *"Record a formal bid if the bidder also submits/returns a draft or the marked-up copy of a merger agreement."*

Alex's example PDF p. 9 uses the OTPP final-round process letter from the Bidder A / Bidder B / OTPP narrative — *"requested bidders to submit a final binding offer to acquire 100% of the equity of the Company, together with a markup of the agreement and plan of amalgamation"* — as the canonical formal-trigger pattern.

#### A.7 Multi-cycle handling

Alex's instructions (PDF p. 9, §3.9) explicitly admit multi-cycle deals as a first-class structural pattern:

> "Sometimes, a company that wants to sell itself has several attempts at it. Often, earlier attempts are also recorded in the deal background. It can be useful to record these attempts, as well as when these earlier sale processes have been terminated. Record `Terminated` if the deal was terminated by the target due to the lack of interest [as an example, see Zep Inc in the database]. Record `Restarted` if the sale process (by the same target) was restarted later on (it is possible that it will have an entirely different set of bidders)."

The cycle markers are events in the row stream — not a separate cycle structure. Zep is the exemplar; an abandoned 2014 process precedes a new 2015 process under the same target. Restarts may have completely fresh sets of bidders.

#### A.8 Atomization rule — instructions vs encoding

There is a real **internal divergence** in Alex's own corpus between what the instructions say and what the workbook actually encodes.

**Instruction text** (PDF p. 6, §3.4): *"First time a bidder with a signed confidentiality agreement is mentioned record the following columns …"* The plain reading is one row per bidder NDA, with bidders that re-appear later re-using the same `BidderID` family.

**Actual workbook encoding** disagrees in significant cases. Concrete examples from `alex_flagged_rows.json`:

- **Medivation row 6065**: a single NDA row with `BidderName="Several parties, including Sanofi"` collapses Sanofi plus ≥2 unnamed parties into one event. Alex annotates this himself with `expand_per_q5`.
- **Zep row 6390**: *"Five bidders collapsed into a single row. Alex's own comment: 'This field needs to be expanded to 5 bidders; one of them bid 20, another 22, another three [20,22]?'"* — Alex's own self-annotated request to expand.
- The PetSmart row uses `bidder_type_note: "11S, 14F"` for a 25-NDA passage ("25 parties, including X, Y, Z").

So the rule under which Alex actually populated the workbook was a **filing-granularity-following** rule, not the strict atomization the prose implies: where the filing aggregates, Alex aggregates.

#### A.9 Self-flagged errors

Alex flagged several of his own rows as wrong or to-be-reworked. The full list lives in `/Users/austinli/bids_try/reference/alex/alex_flagged_rows.json`:

- **Saks row 7013** — *"Unsolicited letter from Company H; no NDA, no price, no further contact. Alex's own comment: 'Should be deleted.'"* Verdict: `delete`.
- **Saks row 7015** — Sponsor A/E row. *"Not a separate bid, should be deleted."* Verdict: `delete`.
- **Zep row 6390** — five bidders collapsed; needs expansion (see A.8).
- **Mac-Gray row 6960** — `BidderID=21` duplicates row 6957. Structural duplicate, not flagged by Alex but caught structurally.
- **Medivation rows 6066/6070** — `BidderID=5` duplicated, plus an out-of-order date sequence.
- **Medivation rows 6065/6075** — aggregated multi-party NDA + Drop rows needing atomization (see A.8).

#### A.10 Stated framing for AI handoff

Alex frames the workbook directly to Austin (PDF p. 3, §2):

> "Once you have read data collection instructions, I think it would be useful for you to read the 9 deal backgrounds that I read. First, it is useful for you to understand how M&A deals are conducted in practice, and how lawyers record various pieces of information (and how inconsistent they are across deals). Second, it would be useful for you to understand why I collected / corrected Chicago guys' information the way I did. **This will allow us to fine-tune collection instructions in order to eventually feed them to an AI.**"

The workbook is *calibration data*, not the target dataset. The AI extraction goal supersedes literal workbook reproduction. The `bids_try/reference/alex/README.md` makes the same point explicitly: *"Alex's workbook is a reference guideline for the pipeline — not ground truth. The SEC filing is ground truth."*

### Part B — Previous `sec_graph` pipeline

The trajectory of the `sec_graph` repo, reconstructed from `git log --oneline` and the docs, has gone through roughly four distinct shapes before the current canonical-narrative hard reset.

#### B.1 Original intent — schema-first, rules-then-LLM

The earliest commits (`6a95578` → `607c4fd` "stage 1a evidence store" → `04a97c3` "stage 1b canonical skeleton" → `cefbc3c` "validate project track" → `7d56d2a` "extract smoke track") built the pipeline as a layered system: ingest filings, store paragraphs and source spans in DuckDB, populate canonical tables (deals, actors, events, event_actor_links, participation_counts, judgments), validate, and project. The original extractor was **rules-only** (regex-based), running before any LLM was wired in. The schema came first; the extractor was supposed to slot in later as either deterministic rules, an LLM, or both.

#### B.2 The static-obligations + paragraph-local approach

The intermediate design embedded a fixed list of "every deal must answer N questions" obligations and ran the LLM over **paragraph-local windows**. The current `src/sec_graph/extract/evidence_map.py` still carries the residue of that approach: a hardcoded `_BACKGROUND_OBLIGATIONS` tuple of exactly 10 items at lines 14–25, hardcoding *Sales process initiation, Bidder count at IOI stage, Bidder count at first round, Final round bid receipt, Exclusivity grant, Target board, Financial advisor for target, Legal advisor for target, Final bid price, Buyer group composition*.

The Linkflow P7-Background plan (`/Users/austinli/Projects/sec_graph/quality_reports/plans/2026-05-03_linkflow-p7-background-high-implementation-plan.md`) describes the most recent shift: replace tiny three-paragraph chunks with **one full Background-of-the-Merger region per filing**, switch the default reasoning effort to `high`, and stop the prompt suppressing extraction by saying *"appearing exactly once."* Commit `b227248` ("replace paragraph extraction with within-deal narrative windows") marks the move away from paragraph-local.

#### B.3 Rules-only extractors

`src/sec_graph/extract/rules/` still exists and is `__init__.py`-gated to fail loudly on import (lines 1–25):

> *"obsolete deterministic extraction rules: candidate-row rules were removed by the hard-reset typed-claim pipeline; use sec_graph.extract.pipeline"*

The actual rule files (`actors.py`, `bids.py`, `counts.py`, `events.py`, `relations.py`) are still on disk. They contain regex-based generic-actor matchers (e.g., `_GENERIC_ACTOR_RE` matching `Party A`, `Bidder \d+`, `Buyer Group`, `Sponsor [A-Z]`, `Company [A-Z]`, `Merger Sub`, `Parent`), named-actor matchers, dollar-per-share regexes (`_BID_RE`, `_RANGE_RE`), and dated-event regexes (`_DATED_START_RE = re.compile(r"\bOn ([A-Z][a-z]+ \d{1,2}, \d{4}),")`). These produced flat candidate rows with raw value, normalized value, character span, confidence, and span_kind. Commit `bd07072` ("remove deal-specific scaffolds from production extractors") explicitly stripped deal-by-deal allowlists out of the rules path.

#### B.4 Linkflow integration

Linkflow first appeared with `c04d016` ("add linkflow llm adapter"), following `e9e1612` ("add provider neutral llm extraction contract") and `a1e3e47` ("add opt-in llm extraction flags"). The `docs/llm-interface.md` contract emerged with `364223e`. Then `69db6ca` ("harden linkflow prompt-only contract") and `e37ee1a` ("record stage 8 live linkflow proof") locked the strict-contract behavior: strict `json_schema` with `response_format`, prompt-only first pass (no tools), Responses API streaming, no `previous_response_id` (Linkflow returns 400). The recent move to Background-region windows + high reasoning effort (`2457182`, "use high-reasoning P7 background extraction") is the latest production change before the canonical-narrative hard reset.

#### B.5 Hard reset rationale

The hard reset (`docs/superpowers/specs/2026-05-03-pipeline-hard-reset-design.md`, `§3 Current Pipeline Failures This Replaces`) names the failures explicitly:

> "LLM windows are fixed three-paragraph chunks. The default core plan can return only `Background of the Merger` rows and miss financing, support, rollover, or transaction-structure evidence. The LLM schema permits only flat actor/date/bid/count candidates and excludes direct relation claims. Candidate evidence is stored as arrays, making evidence links harder to enforce relationally. Candidate rejection and ambiguity are not consistently represented as a first-class disposition ledger. Projection eligibility is actor-global instead of actor-cycle scoped. Proof can look valid while live extraction is thin, incomplete, or zero-candidate. Pipeline-generated judgments have used hardcoded `created_at` values."

The new shape collapses to a single sentence (§1): *"Python scans for coverage. GPT proposes meaning. Python proves or rejects. DuckDB stores the auditable graph. The run kernel makes the long run deterministic and resumable."* The new authority is a hard reset: **no fallbacks, no backward compatibility, no provider-owned source offsets, no canonical rows written by the model**.

#### B.6 What was salvaged

Reading `src/sec_graph/`, several conceptual primitives persist:

- **Typed claim arrays** (`SemanticClaimsPayload` in `extract/llm/models.py`): one `claim_type` per Pydantic class — `actor_claims`, `event_claims`, `bid_claims`, `participation_count_claims`, `actor_relation_claims`. Five separate payloads, one strict `json_schema`.
- **Source quote binding**: the model returns `quote_text` only; Python re-resolves `(filing_id, char_start, char_end)` and rejects absent/non-unique/ambiguous quotes (`extract/llm/convert.py`).
- **Deterministic projections**: `project/summaries.py` and `project/bidder_rows.py` build bidder rows from canonical tables only; no projection step writes a fact.
- **Evidence fingerprints**: `quote_hash = sha256(quote_text)` plus `evidence_fingerprint = sha256(filing_id + char_start + char_end + quote_text_hash)` — collision-defended across filings.
- **Closed enums**: every `Literal[...]` in `schema/models/extraction.py` (`EventType`, `EventSubtype`, `RelationType`, `ActorKind`, `ActorObservability`, `ProcessStage`, `ActorClass`, `CountQualifier`, etc.) — no `unknown`/`other`/fallback value anywhere.
- **Canonical graph shape**: `deals → filings → process_cycles → actors → actor_relations → events → event_actor_links → participation_counts → judgments` — generic, not deal-specific.

#### B.7 What was abandoned

- **Static obligation lists** as the truth contract — the `_BACKGROUND_OBLIGATIONS` tuple is residue, slated for replacement.
- **Paragraph-local windows** — replaced by full Background-section regions (commit `2457182`).
- **Provider judgment claims** — the LLM no longer writes canonical judgments; reconciliation is fully Python-side.
- **Deal-specific scaffolds** — commit `bd07072` removed PetSmart-only, Saks-only allowlists from rules.
- **Generic bidder labels** in canonical rows — `reconcile/pipeline.py` defines `_GENERIC_BIDDER_LABELS` and `_GENERIC_BIDDER_NOUNS` as a reject-list (lines 44–101) so labels like `"potential bidder"`, `"financial buyer"`, `"strategic buyer"`, `"interested party"` cannot become canonical actor names. Commit `b2d545b` was the `no-fabrication semantics` enforcement.
- **Free-form JSON fallback / `response_format: text` provider branches** — explicitly forbidden in `AGENTS.md` and the spec.
- **`previous_response_id` chain reuse** — Linkflow returns 400; full body is sent every call.
- **Working `data/pipeline.duckdb`** — the redesign plan demoted DuckDB to a query engine over per-deal Parquet partitions; the working store is retired (`quality_reports/plans/2026-05-03_full-redesign-plan.md` §4).

#### B.8 What's still in flight

Concepts present in the current branch but slated for replacement by the in-flight refactor:

- **`process_phase` and cycle status**: the canonical schema's `cycle_label` (`schema/models/canonical.py:77, 255`) and the Alex-mirroring `process_phase` enum integer (`0`/`1`/`2+`) carry the monotone-cycle assumption; the refactor moves to richer multi-cycle representation.
- **`_BACKGROUND_OBLIGATIONS` static list** (10 items at `extract/evidence_map.py:14–25`).
- **The fail-loud `_OBSOLETE_RULES_MESSAGE`** stub in `extract/rules/__init__.py` — still present, not yet deleted.
- **Per-deal applicability fixtures** — the test inventory (`tests/test_hard_reset_schema.py`, `tests/test_coverage_semantics.py`, `tests/test_validation_semantics.py`) still pins specific deal expectations.
- **`provider_incomplete_salvaged` finish status** — referenced in old calibration artifacts, retained as an artifact-only concept.

#### B.9 Lessons logged in `prior-pipeline-lessons.md`

The eight named failure modes:

1. **Output rows tried to be both extraction and data model** — anonymous handles, group constituents, lifecycle rows all had to be solved before the row could validate.
2. **Prompt-only semantics weren't durable** — bidder atomization, DropSilent, formal-round status, rough date anchoring all rode on prompt text and regressed across model effort changes.
3. **Repair could make output smaller, valid, and wrong** — the "PetSmart collapse class" caused commit `8e7e956` (obligation-gated repair).
4. **Count obligations were discovered too late** — exact NDA-signer counts, IOI counts, final-round counts, buyer-group constituent counts were retrofit as post-extraction obligations.
5. **Buyer groups exposed the weakness of flat rows** — one row could not represent a group as a single party, as constituents, as an expanded set, and as a signatory set simultaneously.
6. **Anonymous parties needed stable lifecycle identity** — `a1`, `a2` handles drifted across NDA → bid → drop → execute, and validators couldn't infer cohort membership reliably.
7. **Provider constraints leaked into system design** — `oneOf` was hostile, dynamic schemas were rejected, large tool-output replays were expensive, missing `response.completed` events forced salvage.
8. **Audit consistency became a product feature** — immutable run directories, manifest contract versions, latest pointers, cache eligibility, reconciliation, stability proof — all needed because without them stale archives passed for current.

### Part C — Where they overlap / diverge

**Overlaps.**

- Both use **S/F bidder typing** with the same scalar values (Alex's `bidder_type_note` and the previous pipeline's `bidder_type` field both map to `"s"` / `"f"` / `null`).
- Both treat **NDA count** as the auction-classification primitive and both exclude advisor NDAs from that count.
- Both treat **tender-offer (`SC TO-T`) filings as special cases** — Alex's PDF lists them as accepted, the previous pipeline fails loud if no `EX-99.(A)(1)(A)` Offer to Purchase exhibit is selected (per `CLAUDE.md` working rules).
- Both encode the **range-bid → informal** structural rule. Alex states it explicitly in PDF p. 7; the bids_try `rules/bids.md` §G1 carries it as the deciding structural signal.
- Both record **investment bank retention** as an event/row, not a deal-level field.

**Divergences.**

- Alex has a **flat event stream**; the previous pipeline has **typed claim families** (`actor`, `event`, `bid`, `participation_count`, `actor_relation`) with closed enums and a monotone process-cycle model.
- Alex has **no committee, special-committee, or conflict-of-interest slot**; the previous pipeline models committees explicitly via `ActorKind = "committee"` and `EventActorRole = "advisor_for_target"`.
- Alex **deletes asset-only / partial-company bids** (PDF p. 9 *"Don't record bid because only bid for part of the company"*); the previous pipeline preserves them via `proposal_scope`/scope flags so the partial-bid event is still represented even if filtered downstream.
- Alex's `BidderID` is an **event-sequence wedge index** with non-integer values; the previous pipeline's `BidderID` analogue is a strict event-sequence integer plus a separate canonical actor id (`bidder_NN`).
- Alex's `Final Round*` matrix is a **four-axis closed vocabulary** (`Ann`/`Ext`/`Inf` combinations as separate `bid_note` strings); the previous pipeline collapses this to one event with three structured boolean columns (`final_round_announcement`, `final_round_extension`, `final_round_informal`).
- Alex stores anonymous parties as **`a1`, `a2`, …** strings with no formal cohort structure; the previous pipeline tracks anonymous cohorts and exact-count placeholders as first-class entities with `observability ∈ {"named", "anonymous_handle", "count_only"}`.

---

## Section 3 — What Are We Trying To Do?

### 3.1 Product goal

We are building an extraction and canonicalization pipeline that turns SEC merger filings (DEFM14A, PREM14A, SC TO-T, S4) into a canonical event-stream graph plus deterministic analytical projections for empirical M&A research at corpus scale. The user is the empirical researcher who needs trajectory-level fidelity (non-monotone bids, concurrent cycles, go-shops, committee facts) without hand-encoding each deal. The contribution is structural: prior databases collapse the process into a single bid + status; we preserve the actual sequence of cycles, actors, bids, and dispositions with quote-bound provenance.

### 3.2 Architectural shape — five layers

**Layer 1: Source claims.** What the LLM emits with quote support — the Linkflow GPT-5.5 contract under `docs/llm-interface.md`. Six typed claim arrays: `actor_claims`, `actor_relation_claims`, `event_claims`, `bid_claims`, `participation_count_claims`, `coverage_results`. Carries only what filing text says, with exact substring evidence. NOT here: source offsets (Python owns coordinates), provider judgment claims (no `process_mode`, no `bidder_type` adjudication), applicability decisions, deduplication. Owner: LLM provider. Output: validated JSON per region.

**Layer 2: Applicability.** Per-trigger Python rules that fire from region signals to mark each obligation `applicable | not_applicable | indeterminate` with an audit trail. Example: signal "≥2 actors collaborating to acquire" → `buyer_group: applicable`. NOT here: per-deal hardcoded fixtures, guesses without source signal. Owner: Python `applicability` module. Output: `applicability_audit.json`.

**Layer 3: Coverage.** Answers whether claims satisfy each applicable obligation. Outputs `claims_emitted | no_supported_claim | missed`. NOT here: silent defaults, fabricated claims to fill gaps — we do not fall back; we record `no_supported_claim` and fail loud. Owner: Python coverage engine. Output: `coverage_ledger.json` and `claim_dispositions.jsonl`.

**Layer 4: Canonical graph.** The deduplicated, source-meaning representation. Event-stream-shaped per actor-cycle (chronological event lists, terminal status derived). Process cycles are first-class with closed `cycle_kind` enum (`prior_exploratory | primary_target_run | post_signing_go_shop | hostile_interloper_cycle | tender_offer_cycle | restarted_cycle`); cycles can be concurrent or have parents. Actor relations are a graph with ~9 closed types (`member_of | controls | acquisition_vehicle_of | advises | finances | voting_support_for | rollover_holder_for | committee_member_of | recused_from`). NOT here: analytical roll-ups, derived breadth/timing labels. Owner: Python canonicalization. Output: `canonical_graph.json`.

**Layer 5: Projections.** Deterministic analytical views computed from canonical. Three facets replace the struck `process_mode`: `outreach_breadth`, `competition_timing`, `pressure_origin`. Other in-scope projections: `bidder_rows`, `process_summary`, `applicability_panel`. NOT here: any LLM judgment or non-deterministic logic. Owner: Python projection module. Output: `projection_exports/`.

### 3.3 Scope of this refactor

**In scope.** The schema rewrite (Taxonomy C event-stream canonical), the LLM contract (six typed arrays, no provider judgment), per-trigger applicability rules, the three replacement projection facets, region-selection two-phase logic for tender filings (bidder-side EX-99.(A)(1)(A) AND target-side SC 14D9), quote binding with unicode normalization.

**Out of scope.** Adding new filing types beyond the four named. Scaling to 1000+ deals (corpus generalization is a design property, not a Phase-1 deliverable). Building a UI or query layer over canonical output. Cross-deal analytical work. New LLM providers beyond Linkflow GPT-5.5.

### 3.4 Why we're doing this now — failure modes of prior attempts

Five concrete failures motivate the reset:

1. **Static obligation lists.** Hardcoded per-deal fixtures masked extraction misses behind deal-specific scaffolding and overfit Reference-9. Per-trigger rules fix the root cause.
2. **Paragraph-local extraction.** Emitting one event per paragraph fragmented multi-paragraph cycles. Region-scoped extraction with the full Background of the Merger in context fixes this.
3. **Provider judgment claims.** Letting the LLM emit `process_mode` and `bidder_type` coupled extraction to interpretation. Stripping judgment from the contract decouples them.
4. **Monotone status enum.** A single-status field cannot represent STec WDC's $9.15 → withdrew → $6.60 informal → $6.85 best-and-final → signed trajectory. Event-stream canonical with derived terminal status is the fix.
5. **Single-document tender ingestion.** Medivation-shape filings need both bidder-side EX-99.(A)(1)(A) and target-side SC 14D9. Two-phase region selection requires both.

These are not patches we apply on top; we do not patch — we rewrite from first principles.

### 3.5 The role of Alex Gorbenko's workbook

Alex's workbook is **calibration anchor and ground-truth source** for the curated Reference-9 fixtures, after agent-applied corrections. It is **not the schema blueprint**. We adopt: (a) the event-stream insight that bid trajectories must be sequence-preserving; (b) the bid-formality decision rule (range → informal; subset invited to final round → formal; markup of merger agreement returned → formal; otherwise null); (c) the `DropBelowInf`/`DropAtInf` nuance. We reject: (a) deletion of asset-only bids (we keep them with explicit flag); (b) free-text leakage in `bidder_type_note` (we use closed enums with quote evidence); (c) lack of committee/conflict modeling (we add `committee_member_of` and `recused_from`). Alex's taxonomy is one expert's best attempt — input, not gospel.

### 3.6 The role of Reference-9

`providence-worcester`, `medivation`, `imprivata`, `zep`, `petsmart-inc`, `penford`, `mac-gray`, `saks`, `stec` form the **acceptance test set**, not the training set. Each stresses a different shape (formal target-run, tender-offer, sponsor-led, multi-cycle, consortium, bilateral, vehicle chain, go-shop, asset-only). Generalization to non-Reference-9 deals is design spirit — out-of-sample validation under `data/filings/` is a Phase-0 stop condition. If the schema requires Reference-9-specific code paths, we have overfit and must redesign.

### 3.7 Ralph loop execution shape

The plan runs inside a Ralph loop — recurring autonomous iterations of the same prompt against the latest repo state. The shape is hybrid: **ordered backbone of must-do steps + a small opportunistic shelf** the loop pulls from when the backbone is paused (e.g., waiting on a Linkflow call).

**Iteration 0 — Calibration Phase 0.** Before any backbone code change ships, the loop runs the probe matrix (P1 reasoning effort, P3 region segmentation, P4 quote-binding stress on medivation, P5 out-of-sample held-out probes) and writes a single decisions file at `quality_reports/llm_calibration/2026-05-04_phase0_decisions.md` locking reasoning effort, schema shape, prompt style, segmentation strategy, and quote-binding rules. Probe scripts persist under `quality_reports/llm_calibration/probes/` (per user memory).

**Iterations 1..N — Backbone execution.** Each iteration: read latest plan + git status, identify next unblocked backbone step, implement, run pytest, run a Linkflow probe on one Reference-9 deal, record disposition deltas, update the session log incrementally (1-3 lines per decision). When the backbone is blocked, the loop pulls one shelf item: applicability tests, quote-normalizer edges, held-out fixture stubs.

**Genuinely uncertain calls (acknowledged, not papered over).** Four calls remain unresolved: (1) `actor_class` width — 4 vs 6 values; (2) `drop_reason` enum — compact ~6 vs expanded ~11; (3) non-US / public-vs-private bidder flags — drop vs optional metadata; (4) `mutual_or_process` initiation_side — strike vs keep. Phase-0 probes inform (1), (3), (4); (2) needs Alex-corpus review. The loop must not auto-commit on these without fresh probe evidence.

---

## Section 4 — What Is The Success Gate?

The user picked A AND B together with C as design spirit. Each of the three tracks has hard, testable criteria below, plus stop conditions and non-negotiable quality gates.

### 4.A Structural acceptance gates (binary)

Pass/fail. Any red kills the refactor.

- **A1 — Pytest green.** `PYTHONDONTWRITEBYTECODE=1 uv run pytest -q -p no:cacheprovider`. Exit 0, no skipped or xfailed Reference-9 contract tests.
- **A2 — Two clean live Reference-9 runs.** Two consecutive end-to-end Linkflow runs across all 9 deals complete without manual intervention. Each per-deal directory contains: `region_audit.json`, `applicability_audit.json`, `coverage_ledger.json`, `claim_dispositions.jsonl`, `canonical_graph.json`, `projection_exports/`, `validation_verdict.json`, `provider_metadata.json`, `cost_summary.json`, `proof_summary.md`. Missing artifacts fail.
- **A3 — Loud LLM contract failures.** Schema-invalid responses raise and halt — we do not fall back, we fail loud. Test: `tests/test_llm_p7_contract.py` covers malformed JSON, missing arrays, type violations, quote-evidence absence.
- **A4 — Disposition coverage total.** Every applicable blocking obligation across all 9 deals carries a disposition in `{claims_emitted, no_supported_claim, missed}`. Validator: `tests/test_coverage_semantics.py`.
- **A5 — Quote binding survives unicode.** Medivation NBSP / en-dash / smart-quote text passes with normalized matching. Test: `tests/test_validation_semantics.py::test_quote_binding_unicode_normalization`. Silent rejection of a real span fails.
- **A6 — No fallback or backward-compatibility code.** `rg -n "fallback|backward.compat" src/sec_graph/` returns no active patterns. We do not patch behind defaults; we fix root causes.

### 4.B Substantive acceptance gates (per-deal correctness vs curated fixtures)

Curated ground-truth fixtures are re-encoded under Taxonomy C from filing text, with Alex's workbook as ONE cross-check + agent-identified corrections. Fixtures live at `tests/fixtures/reference_nine/<slug>/canonical_truth.json` and `projection_truth.json`. Fixture creation is part of the backbone.

For each of the 9 deals:

- **B1 — Actor set matches.** Every fixture actor with its `actor_class` appears in canonical; no fabricated actors.
- **B2 — Cycle list matches.** Cycle count, `cycle_kind`, parent links, and concurrency relations match fixture exactly. STec must show non-monotonic trajectory; Saks must show post-signing go-shop as child of primary.
- **B3 — Signed buyer matches.** Field-by-field equality on signed-buyer entity and signed terms.
- **B4 — Bid trajectory matches event-by-event.** Ordered list comparison; STec's $9.15 → withdrew → $6.60 informal → $6.85 best-and-final → signed must reproduce exactly. Out-of-order or merged events fail.
- **B5 — Committee facts match.** Committee membership, recusals, and voting/rollover relations match fixture.
- **B6 — Projection rows match (in-scope only).** `bidder_rows`, `process_summary`, `applicability_panel` rows match for `outreach_breadth`, `competition_timing`, `pressure_origin`. Other projections deferred.
- **B7 — Quote-binding ≥ 95%.** On the fixture quote pool, the binder must succeed on ≥ 95%. Test: `tests/test_quote_binding_fixture_rate.py`.
- **B8 — Match semantics.** Field-by-field equality with explicit `null` allowed where source is silent (`null` at canonical, `unknown` at projection). Fabricated values fail.

### 4.C Generalization gates (design spirit, relaxed)

Held-out test set: `cephalon-inc`, `polypore-international-inc`, `mead-johnson-nutrition-co`, `bioclinica-inc`, plus one of `blackboard-inc` or `presstek-inc` (selected at Phase-0 close based on shape coverage). These are not in the curated fixture set; we do not have hand-encoded ground truth.

- **C1 — Structurally valid artifacts.** Each held-out deal produces all artifacts listed in A2 with no schema-invalid responses, no unrepresentable concepts surfacing as exceptions or NULLs at required fields.
- **C2 — Defensible non-degenerate output.** Domain reviewer (Austin) reads the canonical graph and projection exports for each held-out deal and confirms output is defensible (not random, not blank, not obviously wrong). This is judgment, not numeric — but it must be recorded as a yes/no verdict in `quality_reports/llm_calibration/holdout_review_<date>.md`.
- **C3 — Schema gaps are stop conditions, not deferrals.** If a held-out deal exposes a real-world pattern the schema cannot represent (e.g., an unusual cycle concurrency, a cross-conditional joint buyer arrangement, a bidder-demanded-bilateral structure), the loop halts and the schema is amended before continuing. We do not defer schema gaps to a future refactor.

### 4.S Stop conditions (any triggers backbone halt + human review)

- **S1 — LLM contract unviable.** Phase-0 probes show GPT-5.5 cannot reliably emit atomic claims under high reasoning (e.g., petsmart 30% atomic-event loss persists across reasoning levels). Halt and revisit prompt or claim granularity.
- **S2 — Quote binding fails > 5%.** Binder success drops below 95% on fixture quotes. Halt and revisit normalization before further extraction.
- **S3 — Schema cannot represent a real deal pattern.** Held-out validation surfaces a structurally unrepresentable concept. Halt and amend schema; we do not work around it.
- **S4 — Cost / wall-clock exceeds Phase-0 budget without surfacing.** Live runs exceed the envelope (recorded in the Phase-0 decisions file) without user notification. Halt and re-budget; we do not silently overspend.
- **S5 — Fixture creation reveals systematic source gaps.** Target-side narrative absent from tender exhibit alone (medivation-shape) or other systematic gaps. Halt and revisit region selection before generating B-gate fixtures from incomplete sources.

### 4.Q Non-negotiable quality gates

These are doctrines, not score thresholds. Violation kills the merge regardless of A/B/C status:

- **Q1** The six binding doctrines: NO FALLBACK, NO BACKWARD COMPATIBILITY, NO OVERENGINEERING, NO OVERFIT, NO PATCH-LIKE BEHAVIOR (we fix root causes, never papering symptoms), FIRST PRINCIPLES.
- **Q2** Calibration Phase 0 decisions document is committed at `quality_reports/llm_calibration/2026-05-04_phase0_decisions.md` BEFORE any backbone code change lands. No exceptions.
- **Q3** Stale cleanup phase carves out probe scripts under `quality_reports/llm_calibration/probes/` (probe scripts are kept, per user memory).
- **Q4** Session logging happens incrementally (1-3 lines per design decision) per `~/.claude/rules/session-logging.md`, not batched at end of day.
- **Q5** The four uncertain calls listed in 3.7 are not silently resolved by the loop — each requires explicit probe evidence or expert review committed under `quality_reports/llm_calibration/` before adoption.

The gate is met when A1-A6, B1-B8 across all 9 Reference-9 deals, and C1-C3 across all held-out deals are green simultaneously, no S-condition is firing, and Q1-Q5 are satisfied. Anything less is not done.
