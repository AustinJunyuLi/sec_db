# Reference-9 Schema Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the next `sec_graph` extraction refactor so the nine reference deals run through Linkflow GPT-5.5 `high` with validated regions, applicability-aware obligations, typed atomic claims, canonical graph rows, deterministic projections, and proof artifacts.

**Architecture:** Python owns source selection, region validation, applicability, quote binding, claim dispositions, canonicalization, projections, and verdicts. Linkflow owns only semantic recall into strict typed claim arrays over a validated sale-process window.

**Tech Stack:** Python, Pydantic, DuckDB or the existing local store abstraction, pytest, Linkflow GPT-5.5 through `src/sec_graph/extract/llm/`, local EDGAR artifacts under `data/filings/`.

---

## Execution Rules

- Start from a clean branch off current `main` unless the user gives a specific branch.
- Preserve `data/filings/`; it is local research data.
- Do not add fallbacks, compatibility shims, or alternate legacy paths.
- Use `LINKFLOW_API_KEY` from the environment only.
- Do not write generated outputs into tracked source directories.
- Every phase must update tests before or with implementation.
- Commit after each green phase.
- Use subagents with disjoint ownership. Workers are not alone in the codebase;
  they must not revert edits from other workers and must adapt to concurrent
  changes.

## Required Subagent Lanes

Coordinator keeps branch state, integration, and final proof. Dispatch these
read/write lanes:

1. **Region/Applicability Lane**
   - Owns `src/sec_graph/extract/evidence_map.py`, source-section modules,
     evidence-region models, applicability generation, and tests.
2. **LLM Contract Lane**
   - Owns `src/sec_graph/extract/llm/models.py`,
     `src/sec_graph/extract/llm/prompt.py`,
     `src/sec_graph/extract/llm/convert.py`,
     `src/sec_graph/extract/llm/linkflow.py`, and LLM contract tests.
3. **Canonical Graph Lane**
   - Owns schema models, store migrations or table creation, reconciliation, and
     claim disposition logic.
4. **Projection Lane**
   - Owns `src/sec_graph/project/` and projection tests.
5. **Validation/Proof Lane**
   - Owns `src/sec_graph/validate/`, run proof summaries, CLI verdict behavior,
     and run-artifact tests.
6. **Reference-9 QA Lane**
   - Owns live run orchestration, reference fixtures, deal notes, and proof
     inspection. This lane may not change model/schema code during QA.
7. **Stale Cleanup Lane**
   - Owns docs, obsolete plans, generated artifact hygiene, and stale grep
     checks.

## File Map

Expected create/modify set:

- Modify: `docs/spec.md`
- Modify: `docs/llm-interface.md`
- Create: `quality_reports/session_logs/2026-05-03_ref9_schema_refactor_execution_log.md`
- Create: `quality_reports/session_logs/2026-05-03_ref9_schema_refactor_proof.md`
- Modify: `src/sec_graph/extract/evidence_map.py`
- Create: `src/sec_graph/extract/sections.py`
- Create: `src/sec_graph/extract/applicability.py`
- Modify: `src/sec_graph/extract/llm/models.py`
- Modify: `src/sec_graph/extract/llm/prompt.py`
- Modify: `src/sec_graph/extract/llm/convert.py`
- Modify: `src/sec_graph/extract/llm/linkflow.py`
- Modify: `src/sec_graph/schema/models/extraction.py`
- Modify: `src/sec_graph/schema/models/canonical.py`
- Modify: `src/sec_graph/reconcile/pipeline.py`
- Modify: `src/sec_graph/project/bidder_rows.py`
- Create: `src/sec_graph/project/process_summary.py`
- Create: `src/sec_graph/project/bid_events.py`
- Create: `src/sec_graph/project/participation_funnel.py`
- Create: `src/sec_graph/project/relationship_conflicts.py`
- Create: `src/sec_graph/project/deal_protections.py`
- Create: `src/sec_graph/project/applicability_panel.py`
- Modify: `src/sec_graph/validate/integrity.py`
- Modify or create: `src/sec_graph/cli/` command modules used by `python -m sec_graph`
- Create: `tests/test_section_selection.py`
- Create: `tests/test_applicability_obligations.py`
- Modify: `tests/test_llm_p7_contract.py`
- Modify: `tests/test_hard_reset_schema.py`
- Modify: `tests/test_coverage_semantics.py`
- Modify: `tests/test_validation_semantics.py`
- Create: `tests/test_reference9_contract.py`
- Create: `tests/test_projection_views.py`
- Create: `tests/fixtures/reference9_expected_sections.json`
- Create: `tests/fixtures/reference9_expected_applicability.json`

## Phase 0: Preflight And Branch

- [ ] **Step 0.1: Confirm checkout**

Run:

```bash
pwd
git branch --show-current
git status --short
```

Expected:

```text
/Users/austinli/Projects/sec_graph
```

Do not proceed if the checkout is not `sec_graph`.

- [ ] **Step 0.2: Create execution branch**

Run:

```bash
git switch main
git pull --ff-only
git switch -c ref9-schema-refactor-20260503
```

Expected: branch `ref9-schema-refactor-20260503` exists.

- [ ] **Step 0.3: Establish baseline**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 uv run pytest -q -p no:cacheprovider
```

Expected: record pass or fail in
`quality_reports/session_logs/2026-05-03_ref9_schema_refactor_execution_log.md`.
If baseline fails, fix only failures caused by stale project state before moving
to schema work.

- [ ] **Step 0.4: Confirm Reference-9 local filings**

Run:

```bash
python scripts/fetch_filings.py --help
python -m sec_graph ingest --help
```

Then verify these slug directories exist or fetch them through the supported
project fetcher:

```text
data/filings/providence-worcester
data/filings/medivation
data/filings/imprivata
data/filings/zep
data/filings/petsmart-inc
data/filings/penford
data/filings/mac-gray
data/filings/saks
data/filings/stec
```

Commit after baseline logging:

```bash
git add quality_reports/session_logs/2026-05-03_ref9_schema_refactor_execution_log.md
git commit -m "chore: log ref9 schema refactor baseline"
```

## Phase 1: Authority Docs

- [ ] **Step 1.1: Update spec authority**

Modify `docs/spec.md` so §1A states:

```text
The deployable schema starts with validated source sections and evidence
regions. Coverage obligations are generated from source-backed region signals
and applicability rules. Linkflow emits only atomic typed claims. Python owns
source coordinates, applicability, coverage proof, canonicalization, judgments,
projection views, and verdicts.
```

Also state the accepted source value policy:

```text
actor_class = s | f | mixed | NULL
bid_formality = formal | informal | NULL
initiation_side = target | bidder | activist | mutual_or_process | NULL
```

- [ ] **Step 1.2: Update LLM interface authority**

Modify `docs/llm-interface.md` so the provider contract lists exactly:

```text
actor_claims
actor_relation_claims
event_claims
bid_claims
participation_count_claims
coverage_results
```

State explicitly:

```text
No provider judgment claims. No provider source offsets. No provider projection
states such as unknown or not_applicable in positive claim fields.
```

- [ ] **Step 1.3: Remove stale authority**

Search:

```bash
rg -n "static obligation|paragraph-local|judgment_claim|three-deal|financial\\|strategic|strategic\\|financial" docs quality_reports src tests
```

Rewrite or delete stale references that conflict with this spec. Keep historical
session logs only when they are clearly labeled historical and not execution
authority.

- [ ] **Step 1.4: Verify docs**

Run:

```bash
rg -n "paragraph-local|judgment_claim|three-deal proof|static 10|static ten" docs quality_reports
```

Expected: no active-authority matches.

Commit:

```bash
git add docs/spec.md docs/llm-interface.md quality_reports
git commit -m "docs: define ref9 region applicability schema authority"
```

## Phase 2: Source Sections And Region Selection

- [ ] **Step 2.1: Write section-selection fixtures**

Create `tests/fixtures/reference9_expected_sections.json` with these expected
accepted heading families:

```json
{
  "providence-worcester": ["Background of the Merger"],
  "medivation": ["Background of the Offer", "Past Contacts, Transactions, Negotiations and Agreements"],
  "imprivata": ["Background of the Merger"],
  "zep": ["Background of the Merger"],
  "petsmart-inc": ["Background of the Merger"],
  "penford": ["Background of the Merger"],
  "mac-gray": ["Background of the Merger"],
  "saks": ["Background of the Merger"],
  "stec": ["Background of the Merger"]
}
```

- [ ] **Step 2.2: Write failing section tests**

Create `tests/test_section_selection.py` with tests that assert:

```text
source_sections are detected with line and paragraph ranges;
TOC/cross-reference false hits are rejected;
evidence_region_candidates record rejection reasons;
selected evidence_regions have chronological narrative status;
medivation can produce a tender/offer source perspective;
ambiguous candidates block SOUND.
```

Test command:

```bash
PYTHONDONTWRITEBYTECODE=1 uv run pytest -q -p no:cacheprovider tests/test_section_selection.py
```

Expected before implementation: failures for missing `sections` module or
missing fields.

- [ ] **Step 2.3: Implement `src/sec_graph/extract/sections.py`**

Create focused models/functions:

```text
SourceSection
EvidenceRegionCandidate
EvidenceRegion
RegionSegment
RegionSignal
detect_source_sections(markdown_text)
score_sale_process_candidate(section)
select_sale_process_region(sections, filing_metadata)
```

Required detection support:

```text
Background of the Merger
Background of the Offer
Background of the Offer and Merger
Past Contacts, Transactions, Negotiations and Agreements
Anchor Background of the Merger
COMMAND=STYLE_ADDED... Background of the Merger
wrappers: THE MERGER, THE MERGER (PROPOSAL 1), PROPOSAL ONE: THE MERGER, SPECIAL FACTORS
```

Required anti-signals:

```text
table of contents
cross-reference-only paragraph
Reasons
Interests
Projections
Litigation
Merger Agreement summary
Covenants
```

- [ ] **Step 2.4: Replace static region creation**

Modify `src/sec_graph/extract/evidence_map.py` so it calls
`select_sale_process_region(...)` and records candidates, selected region,
segments, and signals. Delete static assumptions that every deal has one clean
Background section.

- [ ] **Step 2.5: Verify Phase 2**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 uv run pytest -q -p no:cacheprovider tests/test_section_selection.py
```

Expected: pass.

Commit:

```bash
git add src/sec_graph/extract/sections.py src/sec_graph/extract/evidence_map.py tests/test_section_selection.py tests/fixtures/reference9_expected_sections.json
git commit -m "feat: validate sale process evidence regions"
```

## Phase 3: Applicability-Aware Obligations

- [ ] **Step 3.1: Write applicability fixtures**

Create `tests/fixtures/reference9_expected_applicability.json`:

```json
{
  "providence-worcester": {
    "buyer_group": "not_applicable",
    "final_round": "applicable",
    "committee_or_conflict": "applicable",
    "go_shop": "not_applicable"
  },
  "medivation": {
    "tender_source_perspective": "applicable",
    "buyer_group": "not_applicable",
    "final_round": "applicable"
  },
  "imprivata": {
    "committee_or_conflict": "applicable",
    "buyer_group": "not_applicable"
  },
  "zep": {
    "prior_cycle": "applicable",
    "buyer_group": "not_applicable"
  },
  "petsmart-inc": {
    "buyer_group": "applicable",
    "rollover_or_support": "applicable"
  },
  "penford": {
    "buyer_group": "not_applicable",
    "final_round": "not_applicable"
  },
  "mac-gray": {
    "buyer_group": "applicable"
  },
  "saks": {
    "go_shop": "applicable",
    "prior_cycle": "applicable"
  },
  "stec": {
    "asset_or_business_line": "applicable",
    "buyer_group": "not_applicable"
  }
}
```

These are acceptance priors for tests. If raw source review contradicts one, the
implementing agent must update the fixture and document the quote basis in the
execution log.

- [ ] **Step 3.2: Write failing applicability tests**

Create `tests/test_applicability_obligations.py` asserting:

```text
coverage obligations are generated from region signals;
buyer group is not applicable for zep unless a group signal exists;
final round is conditional;
coverage_results never use not_applicable;
applicability ambiguity blocks SOUND;
calibration obligations are non-blocking.
```

- [ ] **Step 3.3: Implement `src/sec_graph/extract/applicability.py`**

Create:

```text
ApplicabilityClass = universal | conditional | calibration
ApplicabilityStatus = applicable | not_applicable | ambiguous_applicability
CoverageStatus = claims_emitted | no_supported_claim | ambiguous | missed
CoverageObligation
CoverageObligationSignal
derive_region_signals(evidence_region)
generate_coverage_obligations(evidence_region, region_signals)
```

Use these blocking universal obligation families:

```text
process_chronology
signed_buyer_or_offeror
material_proposals_or_revisions
cycle_boundaries
signing_or_offer_launch
participation_counts_when_signaled
```

Use these conditional families:

```text
final_round
go_shop
buyer_group
committee_or_conflict
rollover_or_support
financing
hostile_or_interloper
asset_or_business_line
prior_or_restarted_cycle
tender_source_perspective
```

- [ ] **Step 3.4: Wire evidence map**

Modify `src/sec_graph/extract/evidence_map.py` so each semantic window carries:

```text
evidence_region_id
region_segment_ids
source_window_hash
obligation_set_hash
coverage_obligations
coverage_obligation_signals
fixed_request_mode
```

- [ ] **Step 3.5: Verify Phase 3**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 uv run pytest -q -p no:cacheprovider tests/test_applicability_obligations.py tests/test_coverage_semantics.py
```

Expected: pass.

Commit:

```bash
git add src/sec_graph/extract/applicability.py src/sec_graph/extract/evidence_map.py tests/test_applicability_obligations.py tests/test_coverage_semantics.py tests/fixtures/reference9_expected_applicability.json
git commit -m "feat: generate applicability aware coverage obligations"
```

## Phase 4: Linkflow Typed Claim Contract

- [ ] **Step 4.1: Write LLM schema tests**

Modify `tests/test_llm_p7_contract.py` so it rejects:

```text
judgment_claims
provider source offsets
unknown in positive claim fields
not_applicable in positive claim fields
schema-valued additionalProperties
oneOf
```

It must accept only:

```text
actor_claims
actor_relation_claims
event_claims
bid_claims
participation_count_claims
coverage_results
```

- [ ] **Step 4.2: Update Pydantic extraction models**

Modify `src/sec_graph/extract/llm/models.py` and
`src/sec_graph/schema/models/extraction.py` to use:

```text
actor_class: s | f | mixed | None
bid_formality: formal | informal | None
initiation_side: target | bidder | activist | mutual_or_process | None
proposal_scope: whole_company | asset_or_business_line | minority_or_investment | other | None
```

Every claim family must require:

```text
claim_id
coverage_obligation_id
quote_text
```

No claim family may include provider source offsets.

- [ ] **Step 4.3: Update prompt**

Modify `src/sec_graph/extract/llm/prompt.py` so the system prompt says:

```text
Extract atomic facts from the provided sale-process window. Do not produce
research conclusions, bidder rows, final taxonomy answers, or source offsets.
Use null when the source does not support a claim field. Do not use unknown or
not_applicable in positive claims.
```

The user prompt must include:

```text
selected evidence region summary
source perspective
document perspective
ordered region segments
coverage obligations
paragraph refs and text
```

- [ ] **Step 4.4: Update conversion and provider request**

Modify `src/sec_graph/extract/llm/convert.py` and
`src/sec_graph/extract/llm/linkflow.py` so:

```text
DEFAULT_REASONING_EFFORT = high
response_format uses the strict accepted schema
Linkflow response metadata is recorded without secrets
schema-invalid responses fail loudly
coverage result ids must match generated obligations
```

- [ ] **Step 4.5: Verify Phase 4**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 uv run pytest -q -p no:cacheprovider tests/test_llm_p7_contract.py
```

Expected: pass.

Commit:

```bash
git add src/sec_graph/extract/llm src/sec_graph/schema/models/extraction.py tests/test_llm_p7_contract.py
git commit -m "feat: shrink linkflow contract to typed claims"
```

## Phase 5: Canonical Graph And Dispositions

- [ ] **Step 5.1: Expand canonical schema tests**

Modify `tests/test_hard_reset_schema.py` to require:

```text
evidence_regions
region_segments
region_signals
coverage_obligation_signals
actors with actor_class s/f/mixed/null
actor_aliases
actor_relations with required relation types
process_cycles
events
bids_or_proposals
event_actor_links
participation_counts
claim_dispositions
judgments
```

- [ ] **Step 5.2: Modify canonical models**

Modify `src/sec_graph/schema/models/canonical.py` so canonical rows can express:

```text
process cycle kind and parent cycle id
actor source labels and normalized labels
actor class s/f/mixed/null
actor relation type
event type and cycle id
proposal scope
bid formality
initiation side
finality signals
participation count stage
claim disposition status
judgment type and evidence basis
```

Disposition statuses:

```text
canonicalized
merged_duplicate
rejected
queued_ambiguity
out_of_scope
```

- [ ] **Step 5.3: Modify reconcile pipeline**

Modify `src/sec_graph/reconcile/pipeline.py` so reconciliation:

```text
creates real process cycles from cycle-boundary claims;
keeps zep earlier strategic activity separate from the signed-cycle facts;
creates actor relations for buyer group, vehicle, affiliate, advisor, support,
rollover, financing, committee, and recusal relations;
does not derive target labels from slug fallbacks;
does not mark a claim canonicalized unless quote binding and schema validation pass.
```

- [ ] **Step 5.4: Verify Phase 5**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 uv run pytest -q -p no:cacheprovider tests/test_hard_reset_schema.py tests/test_validation_semantics.py
```

Expected: pass.

Commit:

```bash
git add src/sec_graph/schema/models/canonical.py src/sec_graph/reconcile/pipeline.py tests/test_hard_reset_schema.py tests/test_validation_semantics.py
git commit -m "feat: canonicalize typed claims into process graph"
```

## Phase 6: Deterministic Projections

- [ ] **Step 6.1: Write projection tests**

Create `tests/test_projection_views.py` asserting:

```text
bidder rows are actor-cycle scoped;
zep has no buyer group composition projection unless canonical relations support it;
petsmart and mac-gray can show buyer group structure from actor relations;
final_round_status can be not_applicable;
unknown appears only in projection outputs;
rules-only cannot produce SOUND live verdicts.
```

- [ ] **Step 6.2: Refactor bidder rows**

Modify `src/sec_graph/project/bidder_rows.py` so bidder rows require actor-cycle
participation evidence. Include these projected statuses:

```text
contacted
confidentiality_agreement
ioi_submitted
loi_submitted
revised_proposal_submitted
advanced_to_final_process
submitted_final_bid
signed_buyer
withdrawn_or_declined
rejected
```

- [ ] **Step 6.3: Add projection modules**

Create:

```text
src/sec_graph/project/process_summary.py
src/sec_graph/project/bid_events.py
src/sec_graph/project/participation_funnel.py
src/sec_graph/project/relationship_conflicts.py
src/sec_graph/project/deal_protections.py
src/sec_graph/project/applicability_panel.py
```

Each module should accept canonical graph rows and return deterministic rows
only. No module may call Linkflow or read raw filing text.

- [ ] **Step 6.4: Verify Phase 6**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 uv run pytest -q -p no:cacheprovider tests/test_projection_views.py
```

Expected: pass.

Commit:

```bash
git add src/sec_graph/project tests/test_projection_views.py
git commit -m "feat: derive analyst projections from canonical graph"
```

## Phase 7: Validation, Verdicts, And Proof Artifacts

- [ ] **Step 7.1: Write Reference-9 contract tests**

Create `tests/test_reference9_contract.py` asserting:

```text
all nine slugs are present in the reference acceptance set;
each deal writes region, applicability, coverage, disposition, canonical,
projection, validation, and proof artifacts;
SOUND requires live provider metadata;
ambiguous region blocks SOUND;
schema invalid Linkflow response fails loudly;
proof summary has one row per reference slug.
```

- [ ] **Step 7.2: Extend validation**

Modify `src/sec_graph/validate/integrity.py` so `SOUND` requires:

```text
validated evidence region;
no ambiguous blocking applicability;
applicable blocking obligations resolved;
positive claims quote-bound;
all claims dispositioned;
canonical graph integrity pass;
projection support pass;
live provider metadata for live acceptance.
```

- [ ] **Step 7.3: Extend run artifacts**

Modify the CLI/run modules under `src/sec_graph/cli/` so a live Reference-9 run
writes:

```text
region_audit.json
applicability_audit.json
coverage_ledger.json
claim_dispositions.jsonl
canonical_graph.json
projection_exports/
validation_verdict.json
provider_metadata.json
cost_summary.json
proof_summary.md
```

- [ ] **Step 7.4: Verify Phase 7**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 uv run pytest -q -p no:cacheprovider tests/test_reference9_contract.py tests/test_validation_semantics.py
```

Expected: pass.

Commit:

```bash
git add src/sec_graph/validate src/sec_graph/cli tests/test_reference9_contract.py tests/test_validation_semantics.py
git commit -m "feat: require proof artifacts for ref9 acceptance"
```

## Phase 8: Full Local Test Suite

- [ ] **Step 8.1: Run full tests**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 uv run pytest -q -p no:cacheprovider
```

Expected: pass.

- [ ] **Step 8.2: Run stale grep**

Run:

```bash
rg -n "judgment_claims|paragraph-local|static obligation|three-deal|financial\\|strategic|strategic\\|financial|buyer group composition required" docs quality_reports src tests
```

Expected: no active-contract matches. Historical matches must include prose that
labels them historical and non-authoritative.

- [ ] **Step 8.3: Commit integrated green state**

Run:

```bash
git status --short
git add docs src tests quality_reports
git commit -m "test: pass ref9 schema refactor contract suite"
```

If there are no staged changes because prior phase commits captured everything,
record that in the execution log instead of creating an empty commit.

## Phase 9: Live Reference-9 Linkflow Run

- [ ] **Step 9.1: Configure secret in shell only**

Run in the shell that launches the test:

```bash
test -n "$LINKFLOW_API_KEY"
```

Expected: exit code `0`. If it fails, ask Austin to provide the key through the
shell or ignored `.env`; do not write it into tracked files.

- [ ] **Step 9.2: Launch one live batch**

Run the supported CLI after the Phase 7 command is implemented. The final
command must use:

```text
provider = linkflow
model = gpt-5.5
reasoning_effort = high
slugs = providence-worcester medivation imprivata zep petsmart-inc penford mac-gray saks stec
run_id = 2026-05-03_ref9_schema_refactor_live_01
```

If the implemented CLI is `python -m sec_graph run`, the command should be:

```bash
python -m sec_graph run \
  --slugs providence-worcester medivation imprivata zep petsmart-inc penford mac-gray saks stec \
  --run-id 2026-05-03_ref9_schema_refactor_live_01 \
  --llm-provider linkflow \
  --llm-model gpt-5.5 \
  --llm-reasoning-effort high
```

If the project keeps separate ingest/extract/reconcile/project/validate
subcommands, run the exact supported sequence and record the commands in the
execution log.

- [ ] **Step 9.3: Inspect proof**

Open:

```text
runs/2026-05-03_ref9_schema_refactor_live_01/proof_summary.md
```

It must have one row per reference slug and columns for:

```text
region_status
applicability_status
provider_status
claim_counts
rejected_claims
canonical_rows
projection_rows
verdict
review_notes
```

- [ ] **Step 9.4: Fix only structural failures**

If the run fails because of source selection, schema rejection, quote binding,
canonicalization, or projection support, fix that structural defect with tests.

Do not tune the prompt to force a desired Reference-9 answer. Do not add
deal-specific code branches.

- [ ] **Step 9.5: Run stable second live batch**

After the first live batch reaches the expected structural state, run:

```bash
python -m sec_graph run \
  --slugs providence-worcester medivation imprivata zep petsmart-inc penford mac-gray saks stec \
  --run-id 2026-05-03_ref9_schema_refactor_live_02 \
  --llm-provider linkflow \
  --llm-model gpt-5.5 \
  --llm-reasoning-effort high
```

Compare the two proof summaries. Structural acceptance requires both runs to
finish without schema-invalid responses, missing required artifacts, unresolved
blocking applicability, or unsupported projections.

- [ ] **Step 9.6: Write proof report**

Create `quality_reports/session_logs/2026-05-03_ref9_schema_refactor_proof.md`
with:

```text
branch name
commit hash
test command and result
live run ids
per-deal verdict table
region selection notes
applicability notes
claim-count summary
projection summary
known review-required items
secret-handling statement
```

Commit:

```bash
git add quality_reports/session_logs/2026-05-03_ref9_schema_refactor_proof.md
git commit -m "test: record ref9 live linkflow proof"
```

## Phase 10: Aggressive Stale Cleanup

- [ ] **Step 10.1: Delete obsolete plans that conflict with current authority**

Review `quality_reports/plans/` and remove or rewrite plans that still claim:

```text
the three-deal proof is the active gate;
static obligations are accepted;
paragraph-local extraction is accepted;
provider judgment claims are accepted;
old financial/strategic enum names are accepted.
```

Historical plans may remain only when their header clearly says they are
superseded and names the current authority.

- [ ] **Step 10.2: Clean generated outputs**

Run:

```bash
git status --ignored --short
```

Generated run data belongs under ignored `runs/`, `artifacts/`, or `tmp/`. Do
not commit generated Linkflow responses unless the project already has a tracked
fixture convention for sanitized test fixtures.

- [ ] **Step 10.3: Final stale grep**

Run:

```bash
rg -n "fallback|backward compatibility|paragraph-local|judgment_claims|static obligation|three-deal|buyer group composition required|financial\\|strategic|strategic\\|financial" docs quality_reports src tests
```

Expected: no active-contract matches. If the words appear in prohibitions such
as "no fallback", leave them.

- [ ] **Step 10.4: Commit cleanup**

Run:

```bash
git add -A
git commit -m "chore: remove stale refactor authority"
```

## Phase 11: Final Verification

- [ ] **Step 11.1: Run full suite**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 uv run pytest -q -p no:cacheprovider
```

Expected: pass.

- [ ] **Step 11.2: Verify live proof artifacts**

Run:

```bash
test -f runs/2026-05-03_ref9_schema_refactor_live_01/proof_summary.md
test -f runs/2026-05-03_ref9_schema_refactor_live_02/proof_summary.md
test -f quality_reports/session_logs/2026-05-03_ref9_schema_refactor_proof.md
```

Expected: all exit code `0`.

- [ ] **Step 11.3: Verify branch diff**

Run:

```bash
git status --short
git log --oneline --decorate -8
```

Expected: only intentional ignored generated outputs remain untracked. If source
or docs are uncommitted, commit them before handoff.

- [ ] **Step 11.4: Merge only after green proof**

If Austin requested merge:

```bash
git switch main
git pull --ff-only
git merge --no-ff ref9-schema-refactor-20260503
PYTHONDONTWRITEBYTECODE=1 uv run pytest -q -p no:cacheprovider
```

Do not merge if either live Reference-9 run lacks proof artifacts.

## `/goal` Prompt To Use

```text
/goal Execute the Reference-9 schema refactor in /Users/austinli/Projects/sec_graph.

Read AGENTS.md, docs/spec.md, docs/llm-interface.md,
quality_reports/plans/2026-05-03_ref9_schema_refactor_goal_spec.md, and
quality_reports/plans/2026-05-03_ref9_schema_refactor_implementation_plan.md.

Use subagent-driven development. You must deploy separate lanes for:
region/applicability, LLM contract, canonical graph, projections,
validation/proof, Reference-9 QA, and stale cleanup. Workers are not alone in the
codebase and must not revert each other's edits.

Implement from first principles with no fallbacks, no backward compatibility
layers, no provider-owned source offsets, no provider judgment claims, and no
deal-specific code branches. Linkflow GPT-5.5 with reasoning effort high is the
live provider. Secrets must stay in env vars or ignored .env files.

Acceptance requires:
1. PYTHONDONTWRITEBYTECODE=1 uv run pytest -q -p no:cacheprovider passes.
2. Two live Reference-9 Linkflow runs complete for providence-worcester,
   medivation, imprivata, zep, petsmart-inc, penford, mac-gray, saks, and stec.
3. Each live run writes region, applicability, coverage, disposition, canonical,
   projection, validation, provider metadata, cost, and proof-summary artifacts.
4. quality_reports/session_logs/2026-05-03_ref9_schema_refactor_proof.md records
   the branch, commit, commands, run ids, per-deal verdicts, known review items,
   and secret-handling statement.
5. Aggressively delete or rewrite stale code/docs/plans that conflict with this
   refactor before final handoff.

Stop and report rather than patching around the problem if region selection is
ambiguous, medivation tender perspective cannot be represented, zep requires
invented buyer-group facts, Linkflow rejects the strict typed schema, or
projections can pass while coverage is incomplete.
```
