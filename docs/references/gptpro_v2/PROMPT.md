# Data Pipeline Design Request

## Role

You are designing a data-construction pipeline for an empirical economics research project. Your job is to architect the system that takes SEC merger filings as input and produces structured estimation rows as output.

## Goal

Produce **one zip file** containing 12 modular markdown files that constitute a detailed implementation plan for this pipeline. The plan must be specific enough that a competent implementer can build the system from it without further design decisions on the architectural questions you address.

## What you have in this packet

The attachments arrive as a single zip. Extract it before reading. Contents:

- `BRIEF.md` — the research target: what the pipeline produces and why
- `derive_views.py` — the canonical output schema (the contract you must hit)
- `filing_petsmart-inc.md`, `filing_providence-worcester.md`, `filing_zep.md`, `filing_saks.md` — four SEC merger proxy filings, trimmed to the merger-narrative sections (Background of the Merger through Interests-of-Directors, before the Merger Agreement boilerplate). Original page markers (`<!-- PAGE n -->`) are preserved in-text. They are *examples of input*. There is no key.

## Scope

### In scope (your design owns these)
- Filing-to-structured-deal-representation pipeline
- A canonical structured representation rich enough that **bidder-cycle estimation rows are one deterministic projection of it**, and adjacent research queries (see `BRIEF.md` §2.2) can be answered by writing new projections without re-extracting filings
- All schemas of intermediates and the canonical representation
- Validation, evidence binding, audit, and provenance design
- Test plan against the four reference filings
- MVP build sequence with acceptance criteria

### Out of scope (do not design or amend)
- The structural estimator itself. It exists. It is the consumer of your output. You do not redesign it.
- The structural model class. Treat the model described in `BRIEF.md` as fixed context. Do not propose model amendments. Do not argue alternative model specifications.
- LLM provider binding (specific APIs, rate limits, cost optimization, streaming, tool-call protocols). Your design is conceptual. Provider binding is a separate task in a future packet.
- Comparisons to or critiques of any prior pipeline. There is no prior pipeline visible to you, by construction.

## Anti-anchor instructions

These are constraints on how you reason, not on what you produce:

1. **Do not assume any prior pipeline exists.** Design from first principles within this packet's evidence. If you find yourself thinking "the standard way to do this is X," ask whether X is justified by *this packet*. If not, design what *is* justified.
2. **There is no curated stress-test casebook.** The four filings are examples of input, period. You decide what's hard about them.
3. **There is no example output.** No worked example of "good schema" or "good pipeline" is provided, deliberately. Do not pattern-match to similar pipelines you may have seen.
4. **`derive_views.py` defines one canonical view, not the only output.** It specifies the bidder-cycle projection used by the current structural estimator. Your data model produces a richer structured representation from which this view is a deterministic projection. The representation must also support adjacent research queries listed in `BRIEF.md` §2.2 — without re-extraction. Event-shaped intermediate is one option, not the only one.

## Output: 12 markdown files, in one zip

Manifest. Do not deviate.

| # | Filename | Role | Word range |
|---|---|---|---|
| 00 | `00_README.md` | Exec summary, navigation, scope/out-of-scope restated | 400–700 |
| 01 | `01_RESEARCH_TARGET.md` | Your restatement of the data contract with the estimator | 600–1000 |
| 02 | `02_DATA_MODEL.md` | Schemas of intermediates and final output; JSON sketches; types | 1000–1500 |
| 03 | `03_ARCHITECTURE.md` | System shape, component graph, data flow | 800–1200 |
| 04 | `04_INGESTION.md` | Filing → cleaned text + provenance/source map | 600–1000 |
| 05 | `05_EXTRACTION.md` | Text → structured intermediate | 1000–1500 |
| 06 | `06_AGGREGATION.md` | Intermediate → bidder-cycle estimation rows + cycle metadata | 800–1200 |
| 07 | `07_VALIDATION_AND_AUDIT.md` | Invariants, evidence binding, hard/soft flags, provenance, reproducibility | 1000–1500 |
| 08 | `08_TEST_PLAN.md` | Reference-deal acceptance criteria, stability checks | 600–1000 |
| 09 | `09_BUILD_SEQUENCE.md` | MVP staging, milestones, rollout order | 600–1000 |
| 10 | `10_DECISIONS.md` | Architecture decisions: alternatives + chosen + rationale | 800–1200 |
| 11 | `11_OPEN_QUESTIONS.md` | Unknowns; items requiring more input; design questions deferred | 400–700 |

## Success criteria

A reviewer will check these. Each criterion is binary.

1. **Bidder-cycle view producible.** Your data model includes a deterministic projection that produces every field of `estimation_bidder_rows` as defined in `derive_views.py`. Any field you cannot extract from filings is explicitly flagged in `11_OPEN_QUESTIONS.md` with the reason.
2. **Auxiliary data preserved.** The data model retains deal-, process-, participant-, and event-level fields beyond what the bidder-cycle view consumes (illustrative list in `BRIEF.md` §2.3). The data is organized such that an analyst can write a new projection — for the example queries in `BRIEF.md` §2.2 or others — without re-extracting filings.
3. **Boundary absence handled.** The data model explicitly accommodates cycles that lack a formal/informal boundary (see `BRIEF.md` §3, §4). A cycle without a formal phase is a valid representation, not an error.
4. **Provenance.** Every object specified in your data model has a defined provenance back to specific filing text. No floating data without source.
5. **Dropout-vs-screening.** The identification problem described in `BRIEF.md` §3 is addressed in `06_AGGREGATION.md` with a specific extraction strategy and an explicit acknowledgment of where ambiguity is fundamental rather than resolvable.
6. **Concrete acceptance criteria.** `08_TEST_PLAN.md` defines acceptance criteria evaluable against the four attached filings: counts, expected fields, expected values. Not aspirational language.
7. **Staged build.** `09_BUILD_SEQUENCE.md` orders implementation in stages where each stage produces a runnable system handling a defined subset of cases. Not a flat task list.
8. **Decisions with alternatives.** `10_DECISIONS.md` lists at least six substantive architecture decisions, each with at least one alternative considered and the reason for choosing. Not a victory lap.
9. **Word ranges respected.** No file shorter than its lower bound. No file exceeds upper bound by more than 20%.
10. **Internal completeness.** No file references a feature or design choice you did not justify in the same or another file.

## Stop rules

- When all 12 files exist, are within word ranges, and meet the success criteria — emit the zip and stop.
- If you cannot satisfy a success criterion within the word budget, log the gap in `11_OPEN_QUESTIONS.md` rather than expanding scope.
- If a design question genuinely cannot be answered without additional input from the requester, list it in `11_OPEN_QUESTIONS.md` with a specific question rather than guessing.

## What I am not asking for

- Source code (no Python, no SQL, no JSON Schema beyond illustrative sketches inside `02_DATA_MODEL.md`)
- Justification of why this research is interesting (assume it is)
- Literature review or related-work survey
- A discussion of whether the structural model in `BRIEF.md` is the right model
- Cost or operational tradeoffs (those belong in the future Linkflow-binding packet)

## Recommended order of work

1. Read `BRIEF.md` and `derive_views.py`. Understand the output contract before reading filings.
2. Read all four filings. Note what's hard about going from these texts to bidder-cycle rows. Note what's hard *for you*, not what's hard "in principle."
3. Sketch the architecture before drafting any of the 12 files.
4. Draft `02_DATA_MODEL.md` and `03_ARCHITECTURE.md` first — they are the spine the rest hangs on.
5. Draft pipeline-stage files (`04`, `05`, `06`) as detail on the architecture.
6. Draft validation/test/build/decisions/open-questions files last; they depend on the rest.
7. Emit one zip containing the 12 files.
