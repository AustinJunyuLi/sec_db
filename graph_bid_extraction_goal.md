# Graph-Backed Bid Extraction Pipeline Long-Running Goal

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` for implementation and review. This is a long-running `/goal` handoff, not a one-shot patch. Deploy subagents with explicit ownership, keep a session log, and stop at the phase gates below for review before expanding scope.

**Goal:** Build, test, and iteratively improve a source-grounded SEC merger bid-extraction pipeline that can process the 392 current deals and later scale to 800+ deals, while producing Alex-style workbook rows with exact evidence provenance and an auditable verdict for every deal.

**Architecture:** Use a graph-backed pipeline, but make it filing-first and event-centered. The core flow is `SEC filing text -> evidence map -> deterministic receipts -> LLM source-backed claims -> Python proof/disposition -> canonical event graph -> Alex-style workbook projection -> quality/stability gate`. The graph is the auditable middle layer; the workbook rows are a deterministic export, not the canonical truth.

**Tech Stack:** Python, DuckDB, Pydantic, pytest, sec2md, pandas/openpyxl for workbook comparison, Linkflow-compatible OpenAI Responses API with strict JSON schema, local run manifests, atomic writes, and per-deal audit artifacts.

---

## Copy-Paste `/goal` Objective

Use this as the long-running objective:

```text
Build and iteratively calibrate a graph-backed SEC merger bid-extraction pipeline.

Primary working repo:
- /Users/austinli/Projects/sec_graph

Reference repos and files to read, not blindly copy:
- /Users/austinli/bids_try
- /Users/austinli/Projects/bids_pipeline
- /Users/austinli/bids_try/reference/CollectionInstructions_Alex_2026.pdf
- /Users/austinli/bids_try/reference/deal_details_Alex_2026.xlsx

Mission:
Extract the Background of the Merger or equivalent sale-process narrative from SEC merger filings into a source-backed canonical graph, then project that graph into Alex-style 35-column workbook rows. The pipeline must support iterative live testing with Linkflow, rigorous evidence proof, Reference-9 acceptance, and later 400/800-deal corpus runs.

Important operating rule:
You have freedom to change architecture when live extraction evidence proves the current design is weak. You do not have freedom to weaken source proof, silently drop facts, hide failed experiments, commit secrets, rely on loose JSON fallback, or declare quality based only on row-count similarity to Alex's workbook.

Credential boundary:
The user will provide the Linkflow API key at runtime. Do not write the key into files, prompts, logs, artifacts, docs, git commits, or shell history. Use environment injection only, for example:
export LINKFLOW_API_KEY='<provided-at-runtime>'

Ground truth:
SEC filing text is ground truth. Alex's workbook is a high-value research example and comparison target, but not an absolute scoring oracle. When Alex and source text disagree, preserve the source-backed fact and flag the divergence.
```

## Base Decision

Use `sec_graph` as the base repo and architectural spine.

Keep from `sec_graph`:
- Evidence regions.
- Claim-only LLM contract.
- Python quote binding.
- Claim dispositions.
- Canonical graph.
- Run manifests, run locks, atomic writes, source hashes.
- Proof verdicts: `SOUND`, `REVIEW_REQUIRED`, `UNSOUND`.

Do not preserve `sec_graph` as-is:
- Current graph projection is too thin because actor-cycle `bidder_rows` cannot reproduce NDA, bid, drop, final-round, executed, advisor, rollover, voting, and buyer-group rows.
- Current taxonomy is too abstract and does not look sufficiently grounded in the filings.
- Current Reference-9 state must be treated as failing until live proof shows otherwise.

Use `bids_try` as the domain-rule donor.

Keep from `bids_try`:
- Filing-grounded rules for event types, bidder identity, atomization, buyer groups, NDAs, bids, drops, silent drops, phases, final rounds, rough dates, and auction logic.
- Strict-schema provider lessons.
- Audit layout, reconcile logic, stability thinking, one-round repair discipline, and target-gate mindset.

Do not preserve from `bids_try`:
- Flat row-per-event JSON as canonical truth.
- Per-deal hardcoded names.
- Global progress state as the corpus-run authority.

Use `bids_pipeline` only as a mechanical-helper donor.

Keep from `bids_pipeline`:
- Background-section detection and ending-heading patterns.
- Price and date checklists.
- Suspicious-tail detection.
- Deterministic cue mining.
- No-peeking tests.
- Compile/export ideas.

Do not preserve from `bids_pipeline`:
- Loose JSON extraction.
- Workbook-first canonical design.
- Monolithic orchestration.
- Old event labels and synthetic generic gap-fill rows.

## Target Data Layers

### 1. Evidence and Audit Layer

Purpose: keep exact source text and every proof trail.

Required tables or equivalent Pydantic models:

```text
filings
paragraphs
spans
evidence_regions
receipts
claims
actor_claims
event_claims
bid_claims
participation_count_claims
actor_relation_claims
claim_evidence
claim_dispositions
coverage_results
```

Plain meaning:
- `filings`: one SEC filing, accession number, filing URL, raw/html/markdown hashes.
- `paragraphs`: normalized text chunks with page index and character offsets.
- `spans`: exact quote ranges inside the normalized filing text.
- `evidence_regions`: Background of the Merger or sale-process windows.
- `receipts`: deterministic checklists found by Python before the LLM runs, such as prices, dates, counts, buyer-group member lists, advisor names, and final-round cues.
- `claims`: LLM-emitted factual statements.
- `claim_evidence`: links claims to exact spans.
- `claim_dispositions`: records whether each claim was supported, merged, rejected, superseded, or queued for review.
- `coverage_results`: records whether required receipts were explained by claims, unresolved, or review-needed.

Hard rule:
No canonical graph row may exist without source-backed evidence or an explicit source-backed derivation record.

### 2. Canonical Event Graph

Purpose: store the real sale-process story in a form that can support workbook export, QA, and later research extensions.

Required tables or equivalent models:

```text
deals
actors
actor_aliases
process_cycles
events
event_actor_links
actor_relations
participation_counts
judgments
row_evidence
```

Plain meaning:
- `deals`: target, final acquirer, announcement/effective dates, final consideration summary.
- `actors`: every company, group, advisor, board, committee, activist, rollover holder, financing source, or other relevant party.
- `actor_aliases`: verbatim filing labels, such as "Party A", "Bidder 2", "the Buyer Group", or "Longview".
- `process_cycles`: sale-process phases, including stale prior processes, restarts, terminated processes, and formal/final rounds.
- `events`: dated or ordered things that happened.
- `event_actor_links`: which actor participated in each event and in what role.
- `actor_relations`: durable relationships, such as member of buyer group, advisor to target, rollover holder, voting-support party, financing source.
- `participation_counts`: stated counts such as "15 financial sponsors signed NDAs" without inventing unnamed parties beyond what the rules allow.
- `judgments`: Python or reviewer decisions for labels like auction status, all-cash status, bid formality, drop reason, final-round flag, and projected fate.
- `row_evidence`: evidence links for graph rows and projected workbook rows.

### 3. Workbook Projection Layer

Purpose: regenerate Alex-style workbook rows.

The projection must generate a table such as:

```text
workbook_event_rows
```

This projection produces the 35-column research shape. It is not canonical truth.

Mapping rules:
- `TargetName`, `Acquirer`, announcement dates, effective dates: from `deals`.
- `BidderID`: deterministic export sequence, not actor identity.
- `BidderName`: from `actors.canonical_label`.
- Verbatim bidder label: from `actor_aliases`.
- Bidder type flags: from source-backed actor attributes and `judgments`.
- Bid value fields: from `bid_claims` and canonical bid events.
- `bid_type`: from Python-owned formality judgment.
- `bid_note`: from canonical event subtype plus rule mapping.
- Drop/final-round flags: from events plus judgments.
- `all_cash`: from consideration components and deal-level judgment.
- Comments: only source-backed notes or explicit review notes.
- `source_quote` and page: from `row_evidence -> spans -> paragraphs`.

## Event Vocabulary

Use a closed canonical event vocabulary. The exact names may be revised during implementation, but every revision must be documented in the rulebook and migration notes.

Minimum required event kinds:

```text
process_start
advisor_engaged
nda
consortium_agreement
ioi
bid
drop
drop_silent
restart
final_round_invitation
final_round_deadline
final_round_extension
auction_closed
buyer_group_composition
rollover_agreement
voting_agreement
financing_commitment
exclusivity
committee_or_recusal
press_release
terminated
executed
```

Minimum required process-start subtypes:

```text
target_sale
target_public_sale
bidder_interest
bidder_sale
activist_sale
```

Minimum required bid subtypes:

```text
priced_ioi
unpriced_ioi
informal_bid
formal_bid
unknown_bid
same_price_reaffirmation
revised_bid
final_bid
```

Minimum required drop subtypes:

```text
below_market
below_minimum
target_other
no_response
never_advanced
scope_mismatch
inferred_from_silence
```

Minimum required relation types:

```text
member_of
advisor_to
financing_source_for
rollover_holder_for
voting_support_for
affiliate_of
acquisition_vehicle_of
committee_member_of
recused_from
```

## LLM Contract

The LLM emits only source-backed claims.

Allowed claim families:

```text
actor_claims
event_claims
bid_claims
participation_count_claims
actor_relation_claims
```

Every LLM claim must include:
- claim type.
- factual payload.
- exact quote text.
- receipt or obligation id when applicable.
- confidence or support strength.

The LLM must not emit:
- canonical ids.
- source offsets.
- source pages.
- `BidderID`.
- workbook rows.
- final auction flag.
- final all-cash flag.
- formal/informal bid label when Python can classify it.
- drop-reason classification when Python can classify it.
- coverage results.
- claim dispositions.

Python owns:
- region selection.
- receipt extraction.
- quote binding.
- character offsets.
- evidence fingerprints.
- claim dispositions.
- actor identity reconciliation.
- alias stability.
- process-cycle segmentation.
- event ordering.
- bidder atomization.
- bid formality classification.
- drop reason and initiator classification.
- auction and all-cash judgment.
- workbook row projection.
- validation verdicts.

Provider rules:
- Use Linkflow-compatible Responses API with strict JSON schema.
- No loose JSON fallback.
- No `previous_response_id` chains.
- Runtime failures are runtime failures, not extraction facts.
- Repair calls may add claims or mark unresolved obligations; they may not silently rewrite accepted claims.

## Rule Adoption Map

Adopt these rules from `bids_try`:

```text
rules/schema.md      -> deal-level fields, auction logic, source-backed row discipline
rules/events.md      -> event vocabulary, process starts, NDA/CA distinction, drops, final rounds, terminated/restarted process
rules/bidders.md     -> actor identity, aliases, atomization, buyer groups, anonymous count handling
rules/bids.md        -> bid values, ranges, same-price reaffirmations, bid revisions, formal/informal cues
rules/dates.md       -> precise/rough dates, date ordering, stale-process timing
rules/invariants.md  -> validator-facing hard checks, adapted to graph rows instead of flat JSON rows
pipeline/obligations.py -> count-receipt idea, after removing per-deal hardcoding
pipeline/llm/client.py and audit/run_pool patterns -> provider reliability, usage capture, audit layout
pipeline/stability.py -> cross-run stability concept
```

Adopt these pieces from `bids_pipeline`:

```text
pipeline/preprocess.py -> section start/end detection and suspicious-tail checks
pipeline/cues.py       -> deterministic cue mining
pipeline/validate.py   -> formality/drop classification ideas, rewritten into the new vocabulary
pipeline/compile.py    -> export shape reference only
tests/test_no_peeking.py -> no-peeking principle
```

Adopt these pieces from `sec_graph`:

```text
docs/spec.md and docs/llm-interface.md -> architecture spine, after domain-rule rewrite
src/sec_graph/extract/evidence_map.py  -> evidence-region idea
src/sec_graph/extract/llm/convert.py   -> Python quote-binding/disposition pattern
src/sec_graph/schema/models            -> starting point for claim and graph models
src/sec_graph/validate/integrity.py    -> proof/integrity validation concept
src/sec_graph/run                      -> run id, lock, atomic write, manifest, progress ledger
```

## Freedom to Try Different Architectures

The long-running agent is expected to iterate. It may change architecture when live extraction evidence shows a better design.

Allowed experiments:
- Different sale-process windowing strategies.
- Different claim families or event vocabularies.
- More granular vs less granular actor-relation modeling.
- One-pass extraction vs claim-additive repair.
- Per-region extraction vs whole-background extraction.
- Medium vs high reasoning for primary extraction.
- Different prompt rule pack layouts.
- Different graph projection rules.
- Different review gates for Reference-9 vs corpus pilot.

Non-negotiable constraints:
- SEC filing text remains ground truth.
- Every accepted claim must bind to source evidence.
- Every canonical row must trace to evidence or a documented derivation.
- Every rejected or replaced LLM claim must appear in the disposition ledger.
- No secret leakage.
- No loose JSON fallback.
- No silent claim or row drops.
- No per-deal hardcoded names in production code.
- No success claim without test output and run artifacts.

Every architecture experiment must write an experiment note:

```text
quality_reports/experiments/YYYY-MM-DD-<short-name>.md
```

Each experiment note must include:
- hypothesis.
- deals tested.
- exact command used.
- model, reasoning effort, prompt hash, schema hash.
- source-backed quality result.
- failure modes observed.
- decision: keep, revise, or discard.
- migration impact if kept.

## Mandatory Subagent Lanes

The coordinator must not do this as one monolithic context. Use subagents with disjoint ownership.

Lane 1: Raw-filing fact ledger agents.
- Assign at least one agent each to PetSmart, Providence & Worcester, Zep, Medivation, and Mac Gray first.
- Output: source-backed fact ledger with exact quotes for process start, actors, aliases, NDAs, bids, drops, final rounds, execution, buyer groups, advisors, rollover, voting, financing, and ambiguous facts.
- These agents do not edit code.

Lane 2: Schema and graph agent.
- Owns Pydantic/DuckDB models for evidence, claims, graph, judgments, and projection rows.
- Must prove that workbook rows can be regenerated from events, actors, relations, counts, judgments, and evidence.

Lane 3: Ingest and region agent.
- Owns SEC/sec2md ingestion, page/paragraph spans, section detection, suspicious-tail rules, and evidence regions.

Lane 4: LLM contract and provider agent.
- Owns strict JSON schema, Linkflow Responses call, retries, watchdogs, usage capture, raw response artifacts, and provider-failure classification.

Lane 5: Quote proof and disposition agent.
- Owns exact quote binding, evidence fingerprints, claim dispositions, conservation checks, and unsupported-claim rejection.

Lane 6: Reconcile and judgment agent.
- Owns actor identity, aliases, cycles, event ordering, bidder atomization, formality/drop/auction/all-cash judgments.

Lane 7: Projection and workbook comparison agent.
- Owns Alex-style export and source-aware comparison reports.
- Must treat Alex as comparison, not absolute truth.

Lane 8: Evaluation and stability agent.
- Owns cached replay, Reference-9 gate, live run matrix, 30-deal pilot, stability proof, and quality reports.

Lane 9: Skeptical review agent.
- Runs read-only review before each phase gate.
- Looks specifically for unsupported rows, quote-binding errors, taxonomy drift, hidden fallbacks, and stale docs.

## Phase Gates

### Phase 0: Repo Intake and Baseline

Actions:
- Inspect `/Users/austinli/Projects/sec_graph`, `/Users/austinli/bids_try`, and `/Users/austinli/Projects/bids_pipeline`.
- Record current git status in the session log.
- Run current tests before changing architecture.

Commands:

```bash
cd /Users/austinli/Projects/sec_graph
git status --short
PYTHONDONTWRITEBYTECODE=1 uv run pytest -q -p no:cacheprovider

cd /Users/austinli/bids_try
git status --short
python -m pytest -q

cd /Users/austinli/Projects/bids_pipeline
git status --short
python -m pytest -q
```

Stop criteria:
- Baseline test results recorded.
- Current docs/code drift recorded.
- No unrelated user changes reverted.

### Phase 1: Raw-Filing Rule Ledger

Actions:
- Build source-backed ledgers for the Reference-9 deals:

```text
providence-worcester
medivation
imprivata
zep
petsmart-inc
penford
mac-gray
saks
stec
```

- Each ledger must cite filing quotes, pages, and paragraphs.
- Each ledger must list facts Alex's workbook captures and facts it misses or represents awkwardly.

Artifacts:

```text
quality_reports/fact_ledgers/<slug>.md
quality_reports/fact_ledgers/reference9_summary.md
```

Stop criteria:
- At least PetSmart, Providence, Zep, Medivation, and Mac Gray fact ledgers are complete before schema freeze.
- The event vocabulary is revised based on real filing evidence, not abstract modeling preference.

### Phase 2: Minimal Evidence and Graph Skeleton

Actions:
- Implement or refactor evidence tables/models.
- Add `actor_aliases`.
- Replace thin actor-cycle projection with event-row projection design.
- Add closed `judgments` keys for workbook-critical labels.

Required proof:
- Unit tests for deterministic ids.
- Unit tests for quote fingerprints.
- Unit tests proving that a canonical event row cannot exist without evidence or a documented derivation.
- A fixture proving that one small filing window creates actors, aliases, one NDA, one bid, one relation, and one projected workbook row.

Stop criteria:
- Evidence and graph skeleton tests pass.
- Skeptical review agent confirms no unsupported graph rows are possible in the fixture.

### Phase 3: LLM Claim Contract

Actions:
- Define strict JSON schema for five claim families.
- Build prompt rule pack from filing-grounded rules.
- Run cached replay tests first.
- Then run one live Linkflow smoke on a small region.

Credential handling:

```bash
export LINKFLOW_API_KEY='<provided-at-runtime>'
```

The key must not be echoed, committed, or written to artifacts.

Stop criteria:
- Strict schema works against Linkflow.
- Raw response and parsed claims are saved inside the run directory.
- Quote binding succeeds on the live smoke or the failure is classified with exact provider/schema evidence.

### Phase 4: Reconcile, Validate, and Project

Actions:
- Convert supported claims into graph rows.
- Build judgments.
- Generate workbook rows.
- Generate source-backed comparison reports against Alex's workbook.

Required reports:

```text
output/proof/<run_id>/<slug>/claim_dispositions.csv
output/proof/<run_id>/<slug>/coverage_results.csv
output/proof/<run_id>/<slug>/canonical_graph_summary.json
output/proof/<run_id>/<slug>/workbook_projection.csv
output/proof/<run_id>/<slug>/alex_comparison.md
```

Stop criteria:
- Projection rows all trace to evidence.
- Alex comparison separates true pipeline errors from workbook/source disagreements.
- No unsupported claim survives into the graph.

### Phase 5: Reference-9 Live Iteration

Actions:
- Run each Reference-9 deal as an independent live job.
- Do not run Reference-9 as one bundled opaque process.
- Keep per-deal artifacts and a matrix summary.

Minimum output:

```text
quality_reports/session_logs/reference9_latest_matrix.json
quality_reports/session_logs/reference9_latest_summary.md
```

Acceptance for continuing to 30-deal pilot:
- `UNSOUND` count is zero.
- Every `REVIEW_REQUIRED` flag has exact source evidence and a concrete review question.
- All claims are disposed.
- All projected rows have evidence.
- Runtime failures are separated from proof verdicts.

### Phase 6: Architecture Experiment Loop

Actions:
- Review Reference-9 failures.
- Propose experiments one at a time.
- Run experiments on a small deal set first.
- Keep or discard based on evidence.

Iteration rule:
- The agent may revise schema, prompts, windowing, claim types, repair strategy, or projection rules.
- The agent must preserve migration notes and explain why the new architecture is better.
- Failed experiments must remain documented.

Stop criteria:
- Reference-9 reaches stable quality good enough for a 30-deal pilot.
- Stability means repeated runs produce stable graph/projection fingerprints, not just successful process exit.

### Phase 7: 30-Deal Pilot

Actions:
- Build a stratified pilot: Reference-9 plus 21 non-reference deals covering tender offers, buyer groups, special committees, recusals, voting support, rollover, financing, go-shop/amendment, high-bidder-count cases, and sparse-process cases.
- Run live jobs with bounded provider concurrency.
- Produce cost/runtime projections for 400 and 800 deals.

Acceptance:
- `UNSOUND` equals zero.
- `SOUND` is at least 24 of 30.
- `REVIEW_REQUIRED` is at most 6 of 30.
- No canonical rows lack evidence.
- No undisposed claims remain.
- Cost/runtime report includes observed and projected costs.

### Phase 8: 400-Deal Run Readiness

Actions:
- Implement deterministic sharding.
- Implement conservative resume.
- Ensure run authority lives inside the run directory, not in one global mutable progress file.
- Add corpus-level summaries.

Required run layout:

```text
runs/{run_id}/
  run_manifest.json
  shard_manifest.jsonl
  progress_ledger.jsonl
  stage_artifacts.jsonl
  deals/{slug}/attempts/{attempt_id}/
    request.json
    prompt_or_messages.json
    raw_response.json
    parsed_claims.json
    quote_binding.json
    disposition.json
    validation.json
    repair_turns.jsonl
    manifest.json
  canonical.duckdb
  proof_summary.json
  corpus_summary.json
```

Stop criteria:
- Dry-run over the full deal list creates the expected shard plan.
- Resume reuses completed valid deal artifacts only when hashes match.
- Resume refuses loudly when code, prompt, schema, input, or artifact hashes do not match.

### Phase 9: Documentation, Cleanup, and Handoff

Actions:
- Update active docs only.
- Archive or delete stale plans and obsolete architecture docs.
- Write operator guide for Linkflow runs, replay runs, review queues, and corpus runs.
- Write final architecture decision record summarizing kept and rejected experiments.

Required docs:

```text
docs/spec.md
docs/llm-interface.md
docs/operator-guide.md
docs/architecture-decisions.md
quality_reports/experiments/
quality_reports/session_logs/
```

Stop criteria:
- Tests pass.
- Docs match code.
- No stale source-of-truth documents contradict the active design.
- Secrets are absent from git diff and artifacts.

## Verdict Semantics

Runtime status and proof verdict are separate.

Runtime statuses:

```text
queued
running
completed
retry_exhausted
failed_io
failed_provider
```

Proof verdicts:

```text
SOUND
REVIEW_REQUIRED
UNSOUND
```

`SOUND` means source-backed claims, complete dispositions, valid graph rows, valid projection rows, and no unresolved required obligations.

`REVIEW_REQUIRED` means structurally valid but ambiguous, incomplete, or needing human adjudication.

`UNSOUND` means schema failure, quote not found, invalid evidence link, unsupported canonical row, or a hard contradiction the validator can prove.

Do not collapse runtime failures into `UNSOUND`. Runtime failures block corpus completion separately.

## Quality Measurement

Do not use raw row count as the main metric.

Measure quality at four levels:
- claim support precision.
- required receipt recall.
- canonical graph correctness.
- workbook projection correctness.

Reference-9 target before pilot:
- claim support precision: 100 percent on accepted claims.
- required receipt recall: 100 percent or source-backed `REVIEW_REQUIRED`.
- projected row evidence traceability: 100 percent.
- `UNSOUND`: zero.

Pilot target before 400-deal run:
- `UNSOUND`: zero.
- stable run fingerprints on repeated Reference-9 runs.
- average review burden low enough for human adjudication.
- observed runtime and cost support 400-deal execution.

## Final Instruction to the Long-Running Agent

Be aggressive about improving the design, but conservative about truth. The pipeline may change shape if live filings prove the design wrong. The evidence contract may not change: source text first, exact quote proof second, graph third, workbook projection last.

The desired end state is not a pretty taxonomy. The desired end state is a pipeline that can read messy SEC sale-process narratives, preserve what the filing actually says, explain every row it exports, and make uncertainty visible instead of hiding it.
