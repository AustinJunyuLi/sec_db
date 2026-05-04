# Reference-9 Acceptance Context And Success Gate

**Date:** 2026-05-04
**Status:** Descriptive synthesis for the next `/goal` handoff. This file is not
the binding implementation authority by itself. The active authority chain
remains `docs/superpowers/specs/2026-05-03-pipeline-hard-reset-design.md`,
`docs/spec.md`, and `docs/llm-interface.md`.
**Purpose:** Reduce information overload before the Reference-9 refactor by
stating what the repo has achieved, what it has not achieved, what Alex and the
previous pipeline contribute, what we are trying to build, and what "done" must
mean in production.

## Core Calibration

Reference-9 is the acceptance gate.

The old three deals are still the priority inspection subset inside the gate:

```text
petsmart-inc
mac-gray
providence-worcester
```

Those three should be used as the first fail-fast proof because they already
stress buyer groups, acquisition vehicles, support/rollover facts, mixed
financial and strategic outreach, and formal process boundaries. Passing those
three does not satisfy acceptance. The refactor is accepted only when all nine
Reference-9 deals pass the live source-backed gate.

The Reference-9 set is:

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

The filing is the source of truth. Alex's workbook is expert guidance. The
previous pipeline is failure-mode evidence. The new pipeline must be built from
the filing text, source spans, explicit claims, explicit judgments, and
deterministic projections.

No fallback, no backward compatibility, no quiet patch around a failure, no
slug-specific code branch, and no schema copied just because the old pipeline or
the workbook happened to use it.

## 1. Where The Current Repo Stands

This section describes the current working tree, not necessarily a committed
release state.

### Achieved

The repo has a clear hard-reset design. The intended flow is:

```text
SEC filing
-> run kernel
-> ingest exact text and paragraph spans
-> evidence map
-> Linkflow typed semantic claims
-> Python quote validation
-> claim disposition ledger
-> canonical graph
-> semantic validation
-> actor-cycle projection
-> proof and cost/runtime artifacts
```

This is the right first-principles shape. It separates source preservation,
model proposal, Python proof, canonical storage, validation, and projection.

The core contracts are already written:

- `docs/spec.md` states that extraction truth is claims, not final rows.
- `docs/spec.md` requires relational source proof through `claim_evidence` and
  `row_evidence`.
- `docs/spec.md` defines the generic canonical graph: deals, filings, process
  cycles, actors, actor relations, events, event-actor links, participation
  counts, and judgments.
- `docs/llm-interface.md` says Linkflow returns typed claims with exact quote
  text and one obligation id, while Python owns source coordinates, canonical
  ids, projection rows, coverage proof, and final acceptance.
- `docs/llm-interface.md` bans loose parsing, legacy shapes, whole-filing
  extraction as fallback, provider-owned offsets, and silent provider switches.

The repo also has real implementation surface:

- ingestion from examples and downloaded filings;
- paragraph and span storage;
- static evidence-map construction;
- typed Linkflow request and response models;
- Python quote binding;
- claim insertion and claim dispositions;
- generic canonical tables;
- projection outputs;
- validation outputs;
- run-id validation, run manifests, run locks, atomic writes, progress logs,
  and cost/runtime summary scaffolding.

All nine Reference-9 local filing directories are present under
`data/filings/`.

The current test suite is green:

```bash
PYTHONDONTWRITEBYTECODE=1 uv run pytest -q -p no:cacheprovider
# 54 passed
```

That matters. It means the existing skeleton is internally coherent enough to
refactor from. It does not mean the Reference-9 acceptance gate has been met.

### Objectively Not Achieved

The live Reference-9 proof does not exist yet. The expected proof files are
missing:

```text
runs/2026-05-03_ref9_schema_refactor_live_01/proof_summary.md
runs/2026-05-03_ref9_schema_refactor_live_02/proof_summary.md
quality_reports/session_logs/2026-05-03_ref9_schema_refactor_proof.md
```

The current accepted hard-reset authority still contains older three-deal
acceptance language. That must be cleaned up or explicitly marked historical so
that future agents do not stop at the old gate.

The current evidence map is still too narrow for production Reference-9. It
selects only one exact `Background of the Merger` section and creates a static
obligation list. That is not enough for:

- tender-offer source perspective in `medivation`;
- go-shop and post-signing solicitation facts in `saks`;
- earlier and later process-cycle separation in `zep`;
- buyer-group, support, rollover, and vehicle relations in `petsmart-inc` and
  `mac-gray`;
- bilateral or limited-market-check shapes in `penford`;
- committee/conflict and advisor facts in `imprivata` and
  `providence-worcester`.

Applicability is planned but not implemented. There is no implemented
`src/sec_graph/extract/applicability.py`, no
`tests/test_applicability_obligations.py`, and no Reference-9 applicability
fixture. This is a major gap because the system must distinguish:

- "the filing supports this claim";
- "this obligation applies but no supported claim was found";
- "this obligation does not apply to this deal shape";
- "the filing is ambiguous, so the run must not pretend success."

The schema still contains stale vocabulary and narrow shapes that conflict with
the Reference-9 target. Examples include `financial` / `strategic` actor-class
values where the accepted source-claim policy is `f` / `s` / `mixed` / `null`,
and relation/request logic that is still centered on buyer-group composition
rather than the broader support, rollover, committee, financing, vehicle,
advisor, member, affiliate, and voting/support relations needed by the nine
deals.

The current reconcile layer creates one process cycle per filing. That cannot
be the final shape for Reference-9 because some deals need cycle separation:
for example an earlier strategic cycle and later sponsor signing cycle, or a
go-shop/post-signing cycle distinct from the signing process.

The run kernel exists, but the current run path is not yet the production proof
shape. Current CLI help requires `--run-dir` and an explicit source, while the
draft live command in the implementation plan does not yet include every
currently required argument. Current resume behavior still recomputes the
working database rather than proving a truly conservative reuse path. Linkflow
artifacts are still rooted under `artifacts/linkflow` instead of being fully
tied to the run directory and stage artifact ledger.

The current artifact writer emits useful summaries such as JSON proof,
bidder-row exports, coverage/disposition CSVs, cost summaries, provider usage
ledgers, and a run memo. It does not yet emit the full Reference-9 artifact set:

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

The old Reference-9 offline note is useful operational evidence, but it is not
live proof and cannot produce `SOUND`. Rules-only output may be structurally
valid, but it cannot prove that Linkflow found and supported the source meaning.

## 2. What Alex Said And What The Previous Pipeline Did

### What Alex Contributes

Alex's materials should be treated as expert guidance, not ground truth.

The useful parts are:

- the nine middle-of-database reference deals;
- the field vocabulary that an experienced reader cared about;
- the fact that takeover auction data is event-like and sequence-like;
- the warning that `BidderID` is an unfortunate name because it often behaves
  more like an event sequence number than a durable bidder identity;
- corrections and comments that reveal hard cases in the workbook;
- examples of where Chicago-style rows, workbook rows, and filing meaning do
  not line up cleanly.

The workbook is Alex's best attempt. It is not a golden standard. It contains
self-corrections, row deletions, row expansions, duplicate or aggregated rows,
and human choices that were later normalized by code. It also lacks durable
filing proof such as exact source quotes and source coordinates for each row.

The right way to use Alex is:

- use his materials to choose the stress cases;
- use his rows to identify likely facts to inspect;
- use his comments to understand why a deal is hard;
- use the SEC filing to decide what is true;
- allow the new pipeline to disagree with Alex when the filing supports the
  disagreement;
- require any disagreement to be reviewable through source spans and proof
  artifacts.

The wrong way to use Alex is:

- treat workbook rows as source truth;
- make schema fields only because the workbook has columns;
- hardcode corrections for the nine deals;
- force the filing into a flat event-row taxonomy when the source meaning is
  relational, count-based, conditional, or judgment-based;
- call the pipeline successful just because a projection resembles Alex.

### What The Previous Pipeline Did Well

The previous pipeline learned several important lessons that should be carried
forward as principles, not as backward-compatible code.

It required model output to carry source quote and source page fields. It then
checked quote support against filing pages. That is the ancestor of the current
source-span proof requirement.

It learned that filing-derived obligations are necessary. The model could miss
counts, unnamed bidder cohorts, final-round participation, buyer-group members,
or late support/rollover facts while still producing clean-looking rows. The
old obligation checker made some missing evidence visible.

It learned that repair can make output smaller, valid, and wrong. A repair pass
could delete valid chronology and leave behind a cleaner JSON file. Conservation
checks were added to block that failure mode.

It learned that release proof needs run manifests, immutable run directories,
latest pointers, reconciliation checks, hard-flag rules, stability checks, row
fingerprints, and contract hashes. This is why the new repo treats run identity,
artifact ledgers, and cost/runtime proof as first-class, not paperwork.

It also learned that comparison to Alex is a human-review aid, not an automatic
grade. Alex-vs-AI differences must be adjudicated against the filing.

### What The Previous Pipeline Got Wrong For The New Goal

The old pipeline emitted flat row-per-event JSON. That shape compressed too
many different things into one object:

- evidence;
- actor identity;
- event chronology;
- bidder lifecycle;
- bid amounts;
- buyer-group membership;
- process phase;
- participation counts;
- projection completeness;
- research judgments.

That compression is the main thing the new repo must avoid. A row can be a
projection, but it should not be the canonical truth.

The old pipeline also accumulated repairs and normalizations around specific
workbook problems. Those repairs were useful for the old release task, but they
are exactly the kind of overfit behavior this repo should reject. Reference-9
must be an acceptance set, not a whitelist of special cases.

The previous pipeline's best insight was not its schema. The best insight was:
make missing source meaning visible, bind every durable fact to evidence, and
do not let a clean export hide uncertainty.

## 3. What We Are Trying To Do

We are trying to build a source-backed SEC merger-filing graph.

In plain terms, the pipeline should read a merger filing and preserve what the
filing actually says:

- who the actors are;
- how actors relate to one another;
- what process cycle is being discussed;
- what happened;
- who participated in each event;
- what counts were stated;
- what bids or proposals were made;
- what support, rollover, committee, advisor, financing, vehicle, and buyer
  group facts are source-backed;
- what judgment the system made when the filing was ambiguous;
- which projection rows can be exported for analysis.

The model should not be asked to produce final research rows. The model should
only propose atomic claims with exact quote text. Python should then prove or
reject those claims.

The desired responsibility split is:

```text
Python finds and names the source region.
Python decides which obligations apply to that source/deal shape.
Linkflow proposes typed claims over validated windows.
Python validates quote binding and source coordinates.
Python records every accepted, rejected, duplicate, ambiguous, or out-of-scope claim.
Python builds generic canonical graph rows from supported claims.
Python validates graph integrity and source proof.
Python exports deterministic projection rows.
Python writes proof, provider, cost, and runtime artifacts.
```

This avoids the old trap where the model had to solve extraction, proof,
canonicalization, projection, and research judgment all at once.

The design should be general enough to explain all nine deals without special
branches:

- a buyer group is represented through actors and actor relations;
- an acquisition vehicle is an actor with a relation to its parent or buyer
  group;
- a support agreement or rollover fact is a relation or event, not a bidder
  name suffix;
- an unnamed cohort count is a participation count, not invented bidder rows;
- a final-round obligation is applicable only when the source signals a final
  round or equivalent process;
- a go-shop is a separate source-backed process signal, not a universal field;
- a tender-offer deal must use the selected Offer to Purchase exhibit when that
  is the source of the sale-process narrative.

The project is not trying to preserve the previous pipeline. It is trying to
keep the lessons and replace the shape.

## 4. What The Success Gate Is

### Acceptance Set

Reference-9 is the acceptance gate:

| Deal | Why It Matters |
|---|---|
| `providence-worcester` | Formal target-run process after earlier informal contacts; mixed strategic and financial outreach; explicit stage counts; final narrowed finalists; committee/conflict facts. |
| `medivation` | Tender-offer source perspective; the selected source must be the Offer to Purchase exhibit, not a cover-form fallback. |
| `imprivata` | Sponsor-led process with committee and conflict signals; needs actors, relations, and initiation/finality judgments. |
| `zep` | Earlier strategic cycle and later sponsor signing cycle; must not invent buyer-group composition where the filing does not support it. |
| `petsmart-inc` | Sponsor consortium, rollover, support, and acquisition vehicles; needs relations rather than one flat buyer label. |
| `penford` | Bilateral or limited market-check shape; final-round obligations should be conditional, not universal. |
| `mac-gray` | Buyer group and acquisition vehicles; member, affiliate, and vehicle relations matter. |
| `saks` | Go-shop and alternative-target process signals; needs process-cycle separation. |
| `stec` | Asset-only or business-line proposal plus signed transaction; proposal scope and finality must be explicit. |

The old three are the first priority check:

```text
petsmart-inc
mac-gray
providence-worcester
```

They should fail fast if the architecture is wrong. They are not a substitute
for the remaining six.

### Required Gate Conditions

Acceptance means all of the following are true.

1. Authority is clean.

   Active docs and plans must state that Reference-9 is the acceptance gate.
   Three-deal language can remain only if it is clearly labeled as historical or
   as the priority subset inside Reference-9.

2. Offline tests pass.

   The cache-free test command must pass:

   ```bash
   PYTHONDONTWRITEBYTECODE=1 uv run pytest -q -p no:cacheprovider
   ```

3. The run uses the local Reference-9 filings.

   The run must use the nine local source folders under `data/filings/`. It
   must not switch to examples, stale artifacts, or external shared state.

4. Source-region selection is proven before extraction.

   Each deal needs a region audit showing the selected sale-process source
   region, the reason it was selected, rejected false hits, and any blocking
   ambiguity. For tender-offer deals, missing the selected Offer to Purchase
   exhibit is a hard failure.

5. Applicability is separate from coverage.

   The system must decide which obligations apply before judging coverage.
   `not_applicable` is not a coverage result. It is an applicability decision.
   Applicable obligations must end in `claims_emitted`, `no_supported_claim`,
   `ambiguous`, or `missed`, with source-backed reasons.

6. Linkflow is live and bounded.

   Linkflow GPT-5.5 with reasoning effort `high` is the live provider. The
   provider returns strict typed claim arrays and coverage results only in the
   allowed shape. It does not return source offsets, canonical ids, projection
   rows, claim ids, or final research judgments.

7. Python proves every accepted claim.

   A positive claim must have exact quote text, unique quote binding in the
   source window, Python-owned source spans, a valid same-type obligation id,
   and a claim disposition. Missing, ambiguous, unsupported, or wrongly typed
   claims are rejected or blocked. They are not salvaged.

8. The canonical graph is generic and source-backed.

   The run must produce source-backed filings, deals, process cycles, actors,
   actor relations, events, event-actor links, participation counts, judgments,
   and row-evidence links where those facts are present. It must not create
   deal-specific tables or special branches for Reference-9.

9. Projection is deterministic.

   Bidder rows are exported from canonical graph facts. Projection cannot add
   new facts, hide missing coverage, or turn a rules-only run into `SOUND`.

10. Proof artifacts are complete.

   Each live run must write:

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

   The proof summary must have one row per Reference-9 slug and enough detail
   for a reviewer to see region status, applicability status, provider status,
   claim counts, rejected claims, canonical rows, projection rows, verdict, and
   review notes.

11. Runtime proof is production-shaped.

   Runs must have explicit run ids, run directories, run locks, atomic writes,
   progress ledgers, stage artifact digests, sanitized provider metadata,
   secret-safe logs, cost/runtime summaries, and conservative resume behavior.

12. Live proof is repeated.

   Acceptance requires two live Reference-9 runs, not one lucky run and not an
   offline rules-only run. If the second run differs, the differences must be
   explained through deterministic artifacts and source evidence.

13. Stale code and docs are cleaned.

   Any active source, tests, docs, plans, or generated artifacts that preserve
   the old three-deal gate, static global obligations, legacy payload readers,
   old actor-class vocabulary, or flat-row authority must be deleted, rewritten,
   or clearly labeled historical.

### What Counts As Done

Done means the repo can run the nine Reference-9 filings through the live
Linkflow path and produce a reviewable proof package where every accepted
claim, canonical row, and projection row traces back to source text.

Done does not mean:

- the tests pass only;
- the old three deals pass only;
- the offline rules path passes;
- a projection looks plausible;
- the output resembles Alex;
- every deal emits a clean bidder table;
- missing claims are filled with placeholders;
- ambiguity is hidden in `null`;
- unsupported facts are carried forward because the old pipeline had them.

Done means the system can say, for each of the nine deals:

```text
This is the source region.
These obligations apply.
These obligations do not apply, and why.
These claims were emitted.
These quotes prove those claims.
These claims were rejected, and why.
These canonical rows were created.
These projection rows were derived.
This is the verdict.
This is the cost/runtime footprint.
```

If the source is ambiguous, the provider fails, the strict schema is rejected,
the tender-offer exhibit cannot be selected, quote binding fails, or projection
can pass while coverage is incomplete, the correct outcome is a loud stop, not
a fallback.

## Immediate Design Implication For The `/goal` Call

The next `/goal` should not ask for "make the current plan pass" in a narrow
sense. It should ask for the Reference-9 acceptance architecture to be made
real from first principles:

- region selection before extraction;
- applicability before coverage;
- typed claims before canonical rows;
- Python proof before acceptance;
- canonical graph before projection;
- live Reference-9 proof before handoff;
- stale cleanup before completion.

The agent team should have explicit ownership lanes for:

- source-region and applicability design;
- Linkflow request/response contract;
- canonical graph and reconciliation;
- deterministic projections;
- validation and proof artifacts;
- Reference-9 QA, with the old three as priority inspection;
- stale cleanup and authority-chain consistency.

The success standard is not "more complete taxonomy." The success standard is
source-backed meaning that survives all nine reference deals without fallback,
without overfit, and without making uncertainty look clean.

## Verification Snapshot

Commands run while preparing this synthesis:

```bash
PYTHONDONTWRITEBYTECODE=1 uv run pytest -q -p no:cacheprovider
# 54 passed in 4.20s

for slug in providence-worcester medivation imprivata zep petsmart-inc penford mac-gray saks stec; do
  test -d "data/filings/$slug" && printf 'present %s\n' "$slug" || printf 'missing %s\n' "$slug"
done
# all nine were present

for path in \
  runs/2026-05-03_ref9_schema_refactor_live_01/proof_summary.md \
  runs/2026-05-03_ref9_schema_refactor_live_02/proof_summary.md \
  quality_reports/session_logs/2026-05-03_ref9_schema_refactor_proof.md \
  src/sec_graph/extract/applicability.py \
  tests/test_applicability_obligations.py; do
  test -f "$path" && printf 'present %s\n' "$path" || printf 'missing %s\n' "$path"
done
# all five checked paths were missing

PYTHONDONTWRITEBYTECODE=1 uv run python -m sec_graph run --help
# current CLI requires --run-dir and --run-id
```
