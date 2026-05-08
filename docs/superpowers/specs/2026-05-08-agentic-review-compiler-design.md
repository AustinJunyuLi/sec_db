---
title: sec_graph agentic review compiler — clean-slate design
status: DRAFT
date: 2026-05-08
supersedes_partially: docs/superpowers/specs/2026-05-03-pipeline-hard-reset-design.md
preserves: docs/spec.md (schema-encoded canonical layer)
authors: Junyu Li, Claude (Opus 4.7)
---

# sec_graph agentic review compiler — clean-slate design

## 1. Status

DRAFT. Awaiting user approval before implementation plan is written.

This document supersedes the **extraction and disposition** layers of the existing pipeline-hard-reset design. It **preserves** the schema-encoded canonical layer (Pydantic + closed enums + graph integrity) which remains the binding contract for the canonical graph.

## 2. Context and motivation

The current sec_graph pipeline rejects 33% of LLM-extracted claims on the Reference 9 calibration set (47 of 142 typed claims). All 9 reference deals fail to land in `passed_clean` status; 5 land `needs_review` and 4 land `high_burden`. The bids_try pipeline, by contrast, lands all 9 deals in `passed_clean` with no validation flags.

Diagnosis: the rejection volume is concentrated in `extract/disposition.py`'s **quote-keyword-substring re-validation gate**. After the LLM emits a typed claim, Python re-reads the LLM's evidence quote and demands that hand-curated taxonomy tokens (event-subtype synonyms, count class/scope words, both-peer labels for relations, date/value substrings) appear literally inside the quote. The synonym lists were sampled from a finite set of seen filings; SEC merger proxies have no shared vocabulary; every law firm writes differently. The system is overfitting to the writing styles in the training sample and rejecting valid extractions on filings that phrase facts differently.

The user has decided **not** to incrementally tune the existing system for marginal improvement. The decision is to clean-slate redesign sec_graph as an agentic extraction-and-review system that makes the LLM (constrained by deterministic tools and challenged by an independent reviewer team) the trust anchor, replacing the brittle keyword-regex disposition layer.

bids_try remains the stable production system. sec_graph becomes the rigorous research-grade alternative path. The two systems are independently developed and compared only on exported artifacts, never wired to each other.

## 3. Goals

In priority order:

1. **Higher fidelity than bids_try.** Fewer mistakes in the canonical graph. Every claim that enters canonical has been independently challenged by a verifier with citations. Research-grade quality that holds up across 392 → 800 deals.
2. **Scale and reliability.** The system runs on 800 deals with no babysitting. Each deal independently passes its own rigor bar. Per-deal failure does not contaminate other deals.
3. **Structured research-grade graph.** A canonical graph queryable for cross-deal patterns ("how often do strategic bidders drop out at first round when target's financial advisor is X?"). Strict schema, closed enums, full provenance.

## 4. Non-goals

- Outperforming bids_try on every metric. Some categories (speed, simplicity) bids_try will continue to win on. We are not optimizing for those.
- Replacing bids_try as the production fast path.
- Building human-review UX inside sec_graph. CSV export is the only human-review interface. Hand review uses external tooling.
- Cross-pipeline comparison features. sec_graph has zero knowledge of bids_try.
- Cost optimization during Phase 1 (per existing memory; quality and stability come first).
- Tweaking the current `disposition.py` keyword regex layer. It is being replaced wholesale.

## 5. Architecture overview

```
                        ┌─────────────────────────┐
SEC filing + exhibits → │  Atlas builder          │ → atlas.json
                        └─────────────────────────┘
                                    │
                                    ▼
                        ┌─────────────────────────┐
                        │  Retrieval index        │ ← contextual chunks + BM25 + embeddings
                        └─────────────────────────┘
                                    │
                                    ▼
                        ┌─────────────────────────┐
                        │  Scout                  │ → region map
                        └─────────────────────────┘
                                    │
                ┌───────────────────┼───────────────────┐
                ▼                   ▼                   ▼
        ┌──────────────┐    ┌──────────────┐    ┌──────────────┐
        │ Party/       │    │ Timeline/    │    │ Count/       │
        │ relation     │    │ bid          │    │ coverage     │
        │ extractor    │    │ extractor    │    │ extractor    │
        └──────────────┘    └──────────────┘    └──────────────┘
                │                   │                   │
                └───────────────────┼───────────────────┘
                                    ▼
                        ┌─────────────────────────┐
                        │  Omission inspector     │ ← structural skeleton checklist
                        └─────────────────────────┘
                                    │
                                    ▼ proposed claim cards
                        ┌─────────────────────────┐
                        │  Evidence binder        │ ← deterministic tools, no LLM
                        └─────────────────────────┘
                                    │
                                    ▼ bound claim cards
                        ┌─────────────────────────┐
                        │  Verifier               │ ← independent, calibration-anchored
                        └─────────────────────────┘
                                    │
                                    ▼ verdicts attached
                        ┌─────────────────────────┐
                        │  Consistency checker    │ ← cross-claim invariants
                        └─────────────────────────┘
                                    │
                                    ▼ accepted cards
                        ┌─────────────────────────┐
                        │  Canonical compiler     │ ← schema-encoded rulebook (preserved)
                        └─────────────────────────┘
                                    │
                                    ▼
                              canonical.duckdb
                                    │
                                    ▼
                              CSV export
```

Two important properties:

- **Same role set for every deal.** The agents are fixed; what varies is which cards each deal accumulates. There is no "team scaling with corpus."
- **Append-only state.** Every claim card, verdict, conflict, and tool call is logged. Re-running an agent appends a new attempt; nothing overwrites prior work. The canonical graph is a deterministic projection of the immutable claim history — delete `canonical/`, recompile, get the same result.

## 6. Data model

### 6.1 Claim card (the unit of truth)

The claim card replaces the current `claim` + `claim_disposition` + `claim_evidence` triple as the system's central object. It is append-only, with a state machine and a complete provenance chain.

```python
ClaimCard:
  card_id: str              # deterministic hash of (deal_slug, claim_type, key_fields, source_quote)
  deal_slug: str
  run_id: str
  claim_type: enum          # actor | event | bid | participation_count | actor_relation | coverage_gap
  status: enum              # proposed → bound → verified → consistent → accepted | rejected | escalated

  # Typed payload (claim_type-specific)
  payload: TypedDict        # validated against schema (closed enums)

  # Origin — which agent proposed this
  origin:
    agent_role: enum        # scout | party_relation | timeline_bid | count_coverage | omission
    agent_run_id: str
    model_version: str
    prompt_hash: str
    extracted_at: timestamp

  # Evidence — bound by deterministic tools, never by LLM
  evidence:
    source_filing_id: str
    paragraph_ids: list[str]
    quote_text: str         # verbatim from filing
    quote_position: tuple[int, int]   # (char_start, char_end) in raw filing bytes
    binding_tool_versions: dict[str, str]   # which version of verify_quote, parse_date, etc.

  # Normalization — deterministic Python, never LLM
  normalized:
    dates: dict[field_name, ISO_date_or_null]
    money: dict[field_name, MoneyStruct]
    actor_refs: dict[field_name, canonical_actor_id]

  # Verdicts — accumulated over lifecycle (a card may have many)
  verdicts: list[Verdict]

  # Cross-claim
  conflict_links: list[card_id]         # inconsistent with these other cards
  superseded_by: optional[card_id]      # if a later, better-bound version replaced this
```

**State machine.** Cards transit forward only:

```
proposed   →  bound      (evidence binder verified the quote, normalized fields)
           ↓
bound      →  verified   (verifier emitted at least one verdict)
           ↓
verified   →  consistent (consistency checker found no blocking conflict)
           ↓
consistent →  accepted   (eligible for canonical compilation)
                rejected (verdict was reject, or unresolvable conflict)
                escalated (ambiguous + needs human, surfaces in CSV)
```

**Append-only invariants.**
- A card's `payload`, `origin`, and `evidence` fields are immutable after `bound`.
- New attempts produce new cards (with `superseded_by` set on the prior card if applicable).
- Verdicts are appended; never deleted or modified.

### 6.2 Verdict

```python
Verdict:
  verdict_id: str
  card_id: str
  verdict: enum             # confirm | partial | reject | ambiguous
  reasoning: str            # required, must reference specific evidence
  supporting_paragraph_ids: list[str]   # required, non-empty
  proposed_correction: optional[TypedDict]   # if partial or reject
  confidence: float         # 0.0–1.0
  verifier_run_id: str
  model_version: str
  prompt_hash: str
  emitted_at: timestamp
```

**Verdict semantics for canonical eligibility:**

- **confirm** → card transits to `consistent`/`accepted` (unless consistency check blocks).
- **partial** → card transits to `accepted` with the proposed correction applied. The correction is a deterministic edit on a specific field (e.g. date 2014-03-12 → 2014-03-13). If the verifier emits a partial without a parseable correction, treat as ambiguous.
- **reject** → card transits to `rejected`. Does not enter canonical. Surfaces in CSV with status=rejected for human review.
- **ambiguous** → card transits to `escalated`. Does not enter canonical. Surfaces in CSV with status=needs_review.

### 6.3 Atlas

The atlas is the structured map of a filing, built once per deal, used by every agent.

```python
Atlas:
  filing_id: str
  raw_sha256: str           # source-truth hash
  total_chars: int
  sections: list[Section]   # heading-anchored regions
  paragraphs: list[Paragraph]   # ordered, with char positions, table flags
  tables: list[Table]       # extracted tabular data with structure
  exhibits: list[Exhibit]   # SC TO-T attachments etc.
  page_anchors: list[PageAnchor]
```

Built deterministically from sec2md output where possible; minimal LLM calls only for ambiguous section labels (e.g. distinguishing "Background of the Merger" from neighboring narrative sections).

### 6.4 Deal room store

Per-deal persisted state at `runs/<run_id>/<deal_slug>/`:

```
runs/<run_id>/<deal_slug>/
  atlas.json                    # filing structure, deterministic
  retrieval_index.parquet       # contextual chunks + embeddings + BM25 terms
  retrieval_meta.json           # index version, chunking config, embedding model
  claim_cards.duckdb            # all cards across all states (append-only)
  verdicts.duckdb               # all verdicts (each card may have many)
  conflicts.duckdb              # cross-card conflict links
  tool_call_log.jsonl           # every tool call with inputs/outputs/version
  agent_messages.jsonl          # raw LLM I/O per agent turn (for debug; not authoritative)
  canonical/                    # compiled graph, derived from accepted cards only
    canonical.duckdb
  exports/
    canonical_rows.csv          # the human review handoff
    review_queue.csv            # rejected + escalated cards for human attention
  run_manifest.json             # run config, model versions, prompt hashes
```

**Recompile invariant:** Delete `canonical/` and `exports/`, re-run the canonical compiler from `claim_cards.duckdb` + `verdicts.duckdb`, get byte-identical output (modulo timestamps in metadata).

## 7. Agent role set

| Role | Input | Output | Tools | LLM? |
|---|---|---|---|---|
| **Atlas builder** | Raw filing + exhibits | `atlas.json` | sec2md, structural parsers | Minimal — only for ambiguous section labels |
| **Scout** | Atlas | Region map (which sections likely contain what) | search_filing, get_section, get_neighborhood | Yes |
| **Party/relation extractor** | Atlas + region map | Claim cards: `actor`, `actor_relation` | full retrieval + parse_*, normalize_actor | Yes |
| **Timeline/bid extractor** | Atlas + region map | Claim cards: `event`, `bid` | full retrieval + parse_date, parse_money | Yes |
| **Count/coverage extractor** | Atlas + region map | Claim cards: `participation_count` | full retrieval + parse_count | Yes |
| **Omission inspector** | All proposed cards + atlas + structural deal-shape skeleton | New cards or `coverage_gap` cards | full retrieval | Yes, but constrained by checklist |
| **Evidence binder** | Each proposed card | Card with verified quote position + normalized fields, OR `binding_failed` status | verify_quote, parse_*, normalize_actor | **No — deterministic Python only** |
| **Verifier** | Bound card + cited evidence + neighboring context + schema rules | Verdict | retrieval (read-only) | Yes; **does not see extractor reasoning** |
| **Consistency checker** | All cards for a deal | Conflict links + violation flags | rule-based Python + LLM fallback | Mixed |
| **Canonical compiler** | Accepted cards | canonical.duckdb rows | schema-encoded Pydantic models, integrity validators | **No — deterministic Python only** |

### 7.1 Omission inspector — bounded, not free-form

Free-form "what's missing?" is a hallucination engine. The omission inspector is constrained by a **structural deal-shape skeleton**: a fixed list of ~25 expected fact categories (target board approval, target financial advisor, financing source, hostile/friendly, exclusivity periods, fiduciary out, NDA timing, IOI count, final-round count, etc.). For each category, the inspector checks: has any extractor filed a card? If not, does retrieval surface evidence? Outcome is either a new claim card (filed) or a `coverage_gap` card with reason (filed for visibility, not canonical compilation).

This is where the deterministic obligation grid you have today gets reborn — not as a binary gate that flips run status, but as the omission inspector's checklist. Coverage gaps become a category of card surfaced in the CSV review queue.

### 7.2 Verifier — independence is load-bearing

The verifier:
- Receives only `card + cited evidence + neighboring context + schema rules`. **Never** sees extractor reasoning, agent messages, or other cards.
- Must cite at least one paragraph in `supporting_paragraph_ids`. Empty citation = malformed verdict = rejected at the schema layer.
- Verdict + reasoning + citations are appended to `verdicts.duckdb`. Re-runs append new verdicts; never overwrite.

### 7.3 Orchestrator

A plain Python orchestrator coordinates per-deal execution. No agent framework dependency in V1.

The orchestrator:
- Owns write access to `claim_cards.duckdb`, `verdicts.duckdb`, `conflicts.duckdb`. Agents emit proposals; the orchestrator commits.
- Enforces per-agent step caps and timeouts.
- Implements the state machine transitions for each card.
- Handles parallel dispatch of the three specialist extractors.
- Manages retries with backoff on Linkflow transient failures.

Designed with framework-shape awareness: state machine for cards, message-based agent invocation, explicit checkpoints. Future migration to LangGraph or DSPy should be mechanical, not a rewrite.

## 8. Tool layer

Deterministic Python tools. Versioned. Logged with every call.

### 8.1 Retrieval

- `search_filing(deal, query, mode, k=10)` — `mode` ∈ {`semantic`, `bm25`, `hybrid`, `literal_regex`}. Returns ranked passages with surrounding context. Index pre-built using contextual chunking (Anthropic's pattern: each chunk gets a 1-sentence context prepend before embedding).
- `get_section(deal, section_name)` — fetch by heading.
- `get_paragraph(filing_id, paragraph_id)` — exact fetch.
- `get_neighborhood(paragraph_id, n_before=2, n_after=2)` — surrounding context.
- `get_table(deal, table_id)` — structured tabular data from exhibits.

### 8.2 Verification (deterministic)

- `verify_quote(filing_id, quote)` → `{verbatim_present: bool, positions: list[(start, end)]}`. The anti-hallucination tool. Used by the evidence binder.

### 8.3 Parsers (deterministic, versioned)

- `parse_date(string, context_hint=None)` → `ISODate | None`. Handles "March 12, 2014", "early March 2014", "the week of March 12", etc. Returns null when phrase is too vague.
- `parse_money(string)` → `{value, currency, unit, confidence}`. Handles "$14.00 per share", "approximately $1.2 billion", "$14 in cash and 0.5 shares".
- `parse_count(string)` → `{min, max, qualifier}`. Handles "approximately 30", "between 20 and 25", "more than 50".

### 8.4 Knowledge layer

- `normalize_actor(name)` → `{canonical_id, aliases, confidence}`. Fuzzy match against a growing canonical actor table (PE firms, law firms, banks). New actors enter as deal-local until human-approved.
- `classify_advisor_type(name)` → `{legal | financial | strategic_advisor | unknown}`. Curated list + LLM fallback for unknowns.

### 8.5 State (read for extractors, write for orchestrator)

- `list_claim_cards(deal, filter=None)` — read-only for extractors.
- `show_conflicting_claims(card_id)` — read-only.
- `get_coverage_skeleton_status(deal)` → `{category: filled | unfilled | partial}` — for the omission inspector.

### 8.6 Forbidden tools

- **No `compare_to_other_extraction(...)`.** The system has zero access to bids_try output, ever.
- **No tool that reveals an "answer key."** Reference 9 ground truth (when it exists) is reserved for calibration set construction, never exposed at extraction time.
- **No agent has direct write access to truth.** Agents emit proposals; only the orchestrator commits.

### 8.7 Tool call logging

Every tool call appends to `tool_call_log.jsonl`:

```
{
  "timestamp": ...,
  "agent_role": "party_relation",
  "agent_run_id": ...,
  "tool": "search_filing",
  "tool_version": "1.2.0",
  "inputs": {...},
  "outputs": {...},
  "duration_ms": ...
}
```

This log is the fine-grained audit trail. It makes "which paragraph did agent X look at, in what order, before proposing this card?" answerable.

## 9. Verifier harness

The verifier is the system's load-bearing oracle. Without rigorous calibration, an agentic verifier becomes a fancier rubber stamp.

### 9.1 Calibration set

~80 hand-graded claim cards spanning all claim types, with adversarially planted errors. Composition (default; user reviews on spec):

| Category | Count | Description |
|---|---|---|
| Confirmed-correct | 20 | Cards both Junyu and Alex agree are correct. |
| Single-field errors | 20 | Cards with one wrong field (right bidder, wrong round). |
| Multi-field errors | 20 | Cards with two or more wrong fields. |
| Plausible hallucinations | 10 | Cards with plausible payload but quote doesn't actually support it. |
| Genuinely ambiguous | 10 | Cards where the filing genuinely doesn't decide. |
| Coverage gaps | 10 | Categories where the deal lacks the expected fact. |

**Constructed organically.** The calibration set is not a separate side project. It is built from Junyu's and Alex's review work as deals are processed. Cards both reviewers confirm with no edits become positive examples; cards either reviewer rejected become negative examples; cards reviewers disagreed on become disagreement examples.

**Append-only.** Calibration entries are versioned. Corrections are new versions; old gradings stay as historical fact.

### 9.2 Calibration protocol

Before every batch run:

1. Verifier processes the calibration set on cold context.
2. Compute per-category metrics: confirm-rate on confirmed-correct, reject-rate on planted errors, ambiguous-rate on ambiguous-by-design.
3. Compare against required bands. **Required bands (default; user reviews):**
   - Confirmed-correct: confirm-rate ≥ 90%
   - Single-field errors: partial-or-reject rate ≥ 85%
   - Multi-field errors: reject rate ≥ 90%
   - Plausible hallucinations: reject rate ≥ 95%
   - Coverage gaps: detection rate ≥ 80%
4. If any band is violated, batch blocks. Investigate (model drift? prompt regression? new filing style?) before unblocking.

Calibration runs are logged with model version, prompt version, tool version. Drift over time is data, not failure.

### 9.3 Verdict-rate sanity bounds

Per deal, expected ranges:
- Confirm rate: 70–90%
- Partial rate: 5–15%
- Reject rate: 5–15%
- Ambiguous rate: 1–5%

If a deal's confirm rate is > 99% (rubber-stamping) or reject rate is > 50% (hostile reviewer), alarm. Surface for investigation; do not silently emit canonical.

### 9.4 Inter-rater reliability

5–10% of cards (sampled per deal) are verified twice with slightly different prompt phrasings (paraphrased instructions, different few-shot examples). Disagreement above threshold (e.g. < 85% agreement) escalates the card to `ambiguous` regardless of either individual verdict.

## 10. Schema-encoded canonical layer (preserved)

This is sec_graph's genuine asset. **It is not being changed by this redesign.**

- All canonical tables in `canonical.duckdb` are still validated by Pydantic models with `extra="forbid"`.
- All enums (`event_subtype`, `relation_type`, `actor_kind`, etc.) remain closed.
- All graph integrity invariants (every canonical row has row_evidence, source-truth hash equality, span-coordinate-in-bounds, fingerprint matches) remain enforced.
- The schema-vs-LLM divide stays: the LLM proposes typed claims; Python compiles canonical rows. Closed enums prevent the LLM from inventing event types or relation types.

What changes:
- The `claim_disposition` table is replaced by the verdict + claim card lifecycle.
- `extract/disposition.py` (the keyword regex layer) is **deleted**.
- `quote_support.py` synonym tables are **deleted**.
- `reconcile/pipeline.py:_canonicalize_bid` generic-label rejection is **deleted**.
- The fixed obligation grid as a binary status gate is **replaced** by the omission inspector's structural skeleton (advisory, surfaces in CSV, does not flip status).

What canonical compilation looks like:
1. Read all cards with `status=accepted` from `claim_cards.duckdb`.
2. Group by canonical row type (deals, actors, events, etc.).
3. Apply existing Pydantic models. Anything that fails Pydantic validation is a system bug — log loudly, stop the compile.
4. Apply existing graph integrity validators. Anything that fails is a system bug.
5. Write `canonical.duckdb`.

The canonical compile step has no LLM, no fuzzy matching, no judgment. It is a deterministic projection of the accepted-card set through the schema.

## 11. Linkflow integration

All LLM calls go through Linkflow (existing constraint, existing memory).

- **Extractors, scout, omission inspector, verifier, atlas builder ambiguity:** Linkflow Responses API with function calling.
- **Tool calling:** Standard pattern — Linkflow returns a tool call request, our Python orchestrator executes the tool, returns the result, model continues. Each turn is logged.
- **Model selection:** Default `gpt-5.5` with `medium` reasoning effort per the existing P8 contract. Verifier may use a different model variant (e.g. `gpt-5.5-thinking` or higher reasoning effort) — this is the closest we get to "different reviewer" given the Linkflow-only constraint.
- **Schema-strict outputs:** All extractor and verifier outputs use Linkflow's strict JSON schema mode. Non-conforming responses fail fast.

**Pre-implementation smoke test:** Before building the agent layer, validate that Linkflow tool calling round-trips correctly with the OpenAI Responses API contract. Estimate: 30 min. Blocking.

## 12. Failure modes and defaults

| Failure | Default behavior |
|---|---|
| Atlas builder fails on a section | Log, skip section, continue. Section-aware tools return `section_unavailable`. |
| Retrieval index build fails | Hard fail; deal cannot be processed. |
| Specialist extractor times out | Log; cards already proposed are kept; missing categories surface as coverage_gaps. |
| Specialist extractor exceeds tool-call cap (default: 50) | Hard cap; cards already proposed kept; agent terminated. |
| Evidence binder cannot find quote in filing | Card status → `binding_failed`. Does not enter canonical. Surfaces in CSV as rejected. |
| Verifier returns malformed verdict (missing citation) | Reject the verdict. Re-run once. If second attempt also malformed, card status → `escalated`. |
| Verifier and consistency checker disagree | Consistency checker wins for hard structural conflicts (e.g. date order); verifier wins for content. Document per-rule. |
| Card has multiple verdicts of different categories | Most recent verdict wins for status transition; full history retained. |
| Cross-deal actor canonicalization conflict | Deal-local pending state; flagged for human approval before entering canonical actor pool. |
| Linkflow rate limit / 5xx | Exponential backoff, max 5 retries. Then deal-level pause. |
| Calibration set fails before batch | Batch blocks; investigation required. |
| Tool version upgrade after binding | Affected cards flagged for re-binding on next run. |

**Default for ambiguous cards:** do not enter canonical. Surface in CSV with `status=needs_review`. We accept higher human-review burden over forced decisions by agents.

## 13. Build order — vertical slice first

Phased, single deliverable per phase, end-to-end testing at each gate.

**Phase 0 — Smoke tests (1 day)**
- Linkflow tool calling round-trip (30 min).
- DuckDB append-only schema sketches.

**Phase 1 — Atlas + retrieval (3-5 days)**
- Atlas builder over sec2md output. Tested on petsmart-inc.
- Retrieval index with contextual chunking. Hybrid (BM25 + embeddings). Tested for recall@10 on synthetic queries.

**Phase 2 — Tool layer (2-3 days)**
- `verify_quote`, `parse_date`, `parse_money`, `parse_count`, `normalize_actor`, `classify_advisor_type`.
- Pure Python with unit tests. No agents yet.

**Phase 3 — Claim card store (2 days)**
- DuckDB tables for cards, verdicts, conflicts.
- Append-only invariants enforced at the storage layer.
- State machine transitions tested.

**Phase 4 — First end-to-end on petsmart-inc (3-5 days)**
- Plain Python orchestrator.
- Atlas → scout → party/relation extractor only → evidence binder → verifier → canonical compile → CSV.
- Goal: produce ~20 well-bound, well-verdicted claim cards on a single deal, end to end.
- Decision gate: **does the output look like something we'd defend?** If not, iterate before adding more agents.

**Phase 5 — Calibration set construction (5-10 hours of human time)**
- Junyu + Alex grade ~80 cards from Phase 4 output, plus adversarially planted errors.
- Calibration set committed.
- Calibration protocol script written.

**Phase 6 — Full agent team (5-7 days)**
- Add timeline/bid extractor, count/coverage extractor, omission inspector, consistency checker.
- Verifier connected to calibration anchor.
- End-to-end on Reference 9 (all 9 deals).
- Compare exported CSV against Reference 9 ground truth.

**Phase 7 — Decision points (after Phase 6)**
- Framework migration (LangGraph or DSPy)? Decide based on what Phase 6 reveals.
- Delphi-style multi-extractor ensembling for high-stakes claims? Decide based on calibration metrics.
- Scale to 392 deals.

Total estimated calendar time for Phase 0–6: 4–6 weeks of focused work.

## 14. Open questions and proposed defaults

The user will review the spec and may override any of these.

| Question | Proposed default |
|---|---|
| Cross-deal actor canonicalization | Yes; build canonical actor table that grows; updates require human approval; pure proposals stay deal-local until approved. |
| Calibration set composition | 20 confirmed-correct / 20 single-field errors / 20 multi-field errors / 10 plausible hallucinations / 10 ambiguous / 10 coverage gaps. |
| Calibration set construction | Built organically from review work, not as a separate side project. |
| Ambiguous-card default | Do not enter canonical; surface in CSV with `status=needs_review`. |
| Specialist extractor parallelism | Three extractors run concurrently per deal; orchestrator collects. |
| Tool call cap per agent | 50 calls per agent per deal. |
| Specialist extractor timeout | 5 minutes per agent per deal. |
| Verifier model | Same family as extractor (Linkflow constraint), higher reasoning effort. |
| Inter-rater sample size | 10% of cards per deal, random sample. |
| Inter-rater agreement threshold | 85% agreement to avoid escalation. |
| Confirm rate alarm bound | < 70% or > 99% per deal. |

## 15. Success criteria

This redesign is successful if:

1. **Reference 9 dossier quality**: at least 7 of 9 deals produce CSV output where ≥ 80% of cards are confirmed by the verifier without human intervention, AND the rejected/escalated cards are correctly identified (Junyu and Alex agree the system flagged the right ones).
2. **Calibration metrics hold**: verifier scores within proposed bands on the calibration set, run-over-run.
3. **Reproducibility**: Re-running the same deal with the same model version produces graph-level stability (claim cards are equivalent up to ID hashes; verdict reasoning may differ but verdict categories agree ≥ 90%).
4. **Audit story**: For any canonical row, we can trace: which agent proposed it, what tools bound its evidence, what verdict was issued by which verifier, and (if applicable) what human review decided. Trace must be queryable in DuckDB without external joins.
5. **Scale-readiness**: The 9-deal run completes in under 4 hours wall-clock with parallelism. Per-deal cost in Linkflow tokens is logged and trended.

## 16. Out of scope (explicit)

- Dossier UX, embedded review tooling, multi-round review state machines, cross-reviewer disagreement tracking as system features.
- Comparison features against bids_try (no tool, no helper, no answer-key access).
- Cost optimization in Phase 1.
- Tweaking the current `disposition.py` keyword regex layer (it is being deleted).
- Modifying the schema-encoded canonical layer (Pydantic, closed enums, graph integrity).
- Multi-pipeline orchestration, ensembling with bids_try, or any cross-pipeline data flow.
- Web UI, API endpoints, or any human-facing interface beyond CSV export.

## 17. Glossary

- **Atlas**: structured map of a filing (sections, paragraphs, tables, exhibits), built once per deal.
- **Claim card**: append-only record of a typed-fact proposal with provenance, evidence binding, and accumulated verdicts. Replaces the current claim+disposition+evidence triple.
- **Verdict**: a verifier's judgment on a single card. Cards may accumulate multiple verdicts.
- **Deal room**: per-deal persisted state at `runs/<run_id>/<deal_slug>/`.
- **Evidence binder**: deterministic Python step that verifies a card's quote exists verbatim in the filing and normalizes its date/money/actor fields.
- **Calibration set**: ~80 hand-graded cards used to gate verifier acceptance before each batch.
- **Coverage gap**: a structural-skeleton category where no card has been filed; surfaced as a `coverage_gap` card type.
- **Linkflow**: the LLM gateway used for all model calls (existing constraint).
