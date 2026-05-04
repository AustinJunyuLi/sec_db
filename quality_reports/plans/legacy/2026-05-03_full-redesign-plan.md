# sec_graph Full Redesign Plan

- **Status:** DRAFT (awaiting approval)
- **Date:** 2026-05-03
- **Branch:** `canonical-narrative-live-refactor`
- **Supersedes:** all prior plans (deleted 2026-05-03)
- **Authority:** binds together with `docs/spec.md` §1A. CLAUDE.md "Current Authority Chain" section will be rewritten on plan approval.

---

## 1. Goal

A pipeline that robustly extracts canonical M&A deal data from 400 SEC filings, with headroom to 700–800. Two equal-priority operational modes:

- **Interactive:** 3–5 deal batches, iterating on prompts/rules. Wall-clock target: < 5 min per 5-deal batch.
- **Batch:** full corpus weekly/monthly. Cost target: < $500/full-corpus pass at 800 deals; wall-clock < 12 h.

Two operational phases:

- **Phase 1 (now → ~30–40 reference deals stable):** Linkflow proxy + `gpt-5.5`. Same code as Phase 2; only `base_url` and key change. Phase 1 caching/Batch are best-effort, not budgeted.
- **Phase 2 (post-stability gate):** direct OpenAI Responses API. Unlocks Batch API, reliable extended caching, Flex tier, snapshot pinning.

---

## 2. Non-negotiable invariants

Carried forward from `docs/spec.md`:

1. **Evidence binding.** Every canonical fact references one or more `SourceSpan` ids whose `quote_hash` resolves against filing source bytes and whose `(char_start, char_end)` coordinates verify against those bytes.
2. **Deterministic IDs.** Form `{slug}_{type}_{sequence}`. Same input bytes → same IDs forever.
3. **Append-only judgments.** Reviewer overrides chain via `supersedes_judgment_id`. No stage wipes `judgments`.
4. **Closed enums.** No `unknown` / `other` / fallback values anywhere.
5. **Per-stage version stamps.** PARSER / INGEST / EXTRACT / RECONCILE / VALIDATE / PROJECT.
6. **Python owns offsets, hashes, IDs, FK construction.** LLM emits `quote_text` only; Python re-resolves.
7. **No fallbacks. No backward compatibility. Fail loud.**

---

## 3. Architecture: Two-Pass LLM (Locate then Extract)

```
fetch ──► ingest ──► locate(Pass1) ──► extract(Pass2 × N regions) ──► evidence-bind ──► reconcile-lite ──► validate ──► project
                          │                       │                          │
                  filing_text + offset_table  region_text + offset_map  spans + candidates
                  one cheap call/filing      one focused call/region   Python-resolved
```

### Pass 1 — locate (one LLM call per filing)
- **Input:** full filing text (typical 80–250K tokens; 1M context easily fits)
- **Output (strict JSON-schema):** `{regions: [{start_paragraph_id, end_paragraph_id, region_kind}]}`
- **Closed `region_kind` enum:** `sale_process` | `financing` | `board` | `reasons` | `opinions`
- **Reasoning effort:** `low`
- **Cache prefix (Phase 2):** static system + schema; cache key = `sha256(filing_text)`
- **No `quote_text`** at this stage — Pass 1 emits paragraph IDs only; Python validates IDs exist.
- **Recall floor:** after Pass 1 returns, Python runs the existing sale-process regex (`_SALE_PROCESS_RE`) over all paragraphs not covered by any region. Any hit outside the regions is logged to an **ambiguity queue**, not auto-fallback. Persistent miss-pattern → human-readable signal to iterate the Pass-1 prompt.

### Pass 2 — extract (one LLM call per region; ~2–5 regions per filing)
- **Input:** stitched `region_text` + per-paragraph offset map
- **Output (strict JSON-schema, `canonical_graph_v1`):**
  - `actors[]` (with `actor_kind`, `observability`, optional `member_of` index)
  - `cycles[]` (with `cycle_label`, anchor event index)
  - `events[]` (with `event_type`, `event_subtype`, `cycle_index`, `quote_text`)
  - `event_actor_links[]` (with `event_index`, `actor_index`, `role`)
  - `actor_relations[]` (with `relation_type`, source/target actor indices, `quote_text`)
  - `bid_values[]` (with `unit`, `consideration_type`, numeric value, `quote_text`)
  - `participation_counts[]` (with count, `count_kind`, `quote_text`)
  - Every entity carries `quote_text`; cross-references are by integer index inside the response, not by ID.
- **Reasoning effort:** `medium` baseline; `high` only on flagged-failed regions
- **Cache key (Phase 2):** `sha256(region_text + schema_version + extract_version)`
- **Calls run in parallel** via `asyncio.gather` with a per-key concurrency limit (start 4, tune empirically)

### Python responsibilities (between Pass 2 and DB)
1. For each entity, substring-search `quote_text` against `region_text`. **Reject if not unique or absent.**
2. Resolve `(paragraph_id, char_start, char_end)` from the offset map.
3. Compute `quote_hash = sha256(filing_id || char_start || char_end || quote_bytes)` (note: includes filing+offsets, not just text — defends against cross-filing collisions).
4. Insert `SourceSpan` rows (parent_evidence_id = paragraph_seed for that paragraph, span_kind = `phrase`).
5. Resolve cross-region duplicates by `(canonical_label, quote_hash)` — first occurrence wins for ID minting; later occurrences become evidence on the existing canonical row.
6. Mint deterministic IDs: sort entities by `(canonical_label, quote_hash)` then assign `{slug}_{type}_{1..N}`.
7. Write canonical Parquet partitions.

### Why C (two-pass) over B (whole-filing one-shot)
- **Failure isolation.** One bad region quarantines into the ambiguity queue; the rest of the filing canonicalizes. B has no graceful partial.
- **Closed-enum reasoning load is concentrated.** Pass 2 sees ~20K tokens of focused narrative + the canonical schema, not 150K + the full schema. Recall on `event_subtype`, `role`, `relation_type` is the tightest spec constraint and B's weakest axis.
- **Cost on full corpus is comparable.** Cost-modeler agent: B = $640 / 400 deals direct, C = $454 / 400 deals direct. C **cheaper** at scale.
- **Phase-1 latency tradeoff.** B = ~30 s/filing sequential; C = 4 calls/filing. Mitigation: parallelize Pass 2 via `asyncio.gather` (per-region calls are independent). Empirical target for 5-deal interactive batch: < 2 min Phase 1.

---

## 4. Substrate: Parquet + DuckDB-as-query-engine

DuckDB is **demoted from storage substrate to query engine.** Per-deal Parquet partitions become the storage truth.

```
runs/{run_id}/
    manifest.json                          # immutable manifest with sha256 of every Parquet
    paragraphs/<deal_slug>.parquet
    spans/<deal_slug>.parquet
    candidates/<deal_slug>.parquet         # raw LLM output + resolution result
    actors/<deal_slug>.parquet
    cycles/<deal_slug>.parquet
    events/<deal_slug>.parquet
    event_actor_links/<deal_slug>.parquet
    actor_relations/<deal_slug>.parquet
    bid_values/<deal_slug>.parquet
    participation_counts/<deal_slug>.parquet
    judgments/
        pipeline/<deal_slug>.parquet           # pipeline-derived; rerun overwrites
        reviewer/append_{ts}_{user}.parquet    # append-only; pipeline never touches
    state/
        progress.json                      # per-deal status (atomic + flock)
        progress.lock
```

- **Each extractor process writes its own `<deal_slug>.parquet`** — no shared writer, no locks, no contention.
- **Snapshot immutability** = `chmod -R a-w runs/{run_id}/` after manifest write.
- **Determinism gate** = filesystem-level `sha256` diff over Parquet files. Pin: writer version, compression codec/level, dictionary encoding, pre-write row sort key.
- **Reviewer judgments live in their own append-only directory** that pipeline reruns never touch. Resolves the open question in `docs/spec.md` §10.2 by physics, not policy.
- **DuckDB queries** read via `read_parquet('runs/{run_id}/spans/*.parquet')` patterns. Working `data/pipeline.duckdb` is retired — there is no "working" canonical store; only run snapshots exist.

---

## 5. Determinism contract (fixes from critique)

Hard problems with the current code (cited by critique agent):

- `created_at = "2026-05-02T00:00:00+00:00"` literal in `reconcile/pipeline.py:483, 621`
- Sequence numbers depend on `rows[0].paragraph_text.find(label)` — most labels return `-1`
- Two `_utc_run_id` definitions drift by 1 second between extract and reconcile
- `quote_hash` is text-only; common phrases collide across filings

Fixes:

1. **Single `deterministic_timestamp(input_hash) -> str`** function. Replaces every `datetime.now()`. The `created_at` for any record derives from the sha256 of its input bytes (via a stable mapping, not the wall clock).
2. **Single `run_id(slug, schema_version, extract_version, filing_bytes_hash) -> str`** function in `sec_graph.run.ids`. Both extract and reconcile import it.
3. **Sequence numbers from sorted `(canonical_label, quote_hash)`**, not from text-search positions.
4. **`quote_hash = sha256(filing_id || char_start || char_end || quote_bytes)`** — collision-free across filings.
5. **Determinism gate test:** rerun against frozen example filings produces bit-identical Parquet partitions (sha256 over file bytes).

---

## 6. Operational hardening (recovered from `bids_try`)

The critique agent flagged: a `SIGKILL` 600 deals into an 800-deal run loses every prior deal, because `run_dir.exists()` aborts and there's no per-deal progress state. `bids_try/pipeline/core.py` solved this; sec_graph regressed.

| Capability | `bids_try` source | sec_graph implementation |
|---|---|---|
| Atomic writes | `core.py:53-75` `_atomic_write_text` | `sec_graph.run.io.atomic_write` — tmp + `os.fsync` + `os.replace` |
| Serialized state mutation | `core.py:78-100` flock(LOCK_EX) | `sec_graph.run.lock.state_lock(state_dir)` — context manager, flock-based |
| Per-deal progress | `core.py:2073-2128` `state/progress.json` | Same shape: `{slug, status, last_run_id, schema_version, extract_version, error?}` per deal |
| Idempotent rerun | implicit via state | `--resume` skips deals at `passed_clean` status; reruns `failed` deals |
| Per-deal recovery | per-slug try/except | One failing deal does not abort the corpus run; it `mark_failed`s and the run continues |

**`run_id` semantics:** `runs/{run_id}/` is created on first deal, `mkdir(exist_ok=True)`. The current `FileExistsError` guard in `cli/run_cmd.py` is removed. Idempotency is enforced per-deal via `progress.json`, not at the run-directory level.

---

## 7. LLM contract

```python
class LLMProviderConfig(BaseModel):
    provider_name: Literal["linkflow", "openai"]   # closed enum
    base_url: str
    api_key_env: str
    model: str = "gpt-5.5-2026-04-23"              # snapshot-pinned
    reasoning_effort_locate: ReasoningEffort = "low"
    reasoning_effort_extract: ReasoningEffort = "medium"
    response_api: Literal["responses"] = "responses"   # Chat Completions retired
    use_batch_api: bool = False                    # Phase 2 only
    use_extended_cache: bool = True                # 24h cache; both phases
    parallel_extract_calls: int = 4
    timeout_seconds: int = 90                      # tightened from 240
```

- **API:** OpenAI Responses API only. Chat Completions path retired.
- **Strict JSON schema:** Pydantic root model → JSON-schema export → `response_format = {type: "json_schema", strict: true, schema: ...}`. `additionalProperties: false`; every field `required`; nullables expressed as `["type", "null"]`.
- **`prompt_cache_key = sha256(deal_slug)`** for routing stickiness. Phase 1: best-effort (Linkflow load-balances; cache fragmentation expected — do not budget the savings). Phase 2: contractual.
- **Provider-completion gate.** Reject any response without an explicit `response.completed` event. No fallback to "looks complete." `LinkflowProviderContractError` raises.
- **Configuration-time validation.** When constructing the request, validate the active provider supports every parameter in the body. Linkflow + Batch endpoint = build-time error, not runtime fallback.

---

## 8. What dies (kill list)

```
src/sec_graph/extract/rules/                    DELETE entire directory
    ├── __init__.py
    ├── actors.py                               (regex actor extraction)
    ├── bids.py
    ├── counts.py
    ├── events.py
    └── relations.py

src/sec_graph/extract/llm/requests.py           DELETE (window construction)
src/sec_graph/extract/llm/prompt.py             REWRITE (locate + extract prompts)
src/sec_graph/extract/llm/_build_prior_memory   DELETE function
src/sec_graph/extract/pipeline.py               REWRITE
src/sec_graph/extract/llm/linkflow.py           REWRITE (single-provider transport, no window loop)

src/sec_graph/reconcile/pipeline.py:
    - _actor_shape                              DELETE (LLM emits actor_kind)
    - _classify_*                               DELETE (LLM classifies)
    - _collect_actor_records                    REWRITE (FK + dedupe only)
    - boundary classification                   DELETE
    - bid → final_round inference               DELETE (LLM emits)
    - hardcoded "per_share" / "cash"            DELETE
    Net: ~600 lines down to ~150 lines

src/sec_graph/schema/models/                    UPDATE
    - add canonical_graph_v1.py (LLM Pass-2 root + JSON-schema export)
    - quote_hash signature changes (filing_id + offsets + bytes)

data/pipeline.duckdb                            DELETE (no working store)
```

Tests, fixtures, and CLI flags following the same path are also retired. Specific file list assembled in Phase A step A0.

---

## 9. Implementation phases

### Phase A — Build new architecture (target: 2 weeks)

| Step | Deliverable | Verification |
|---|---|---|
| A0 | Discard in-progress refactor (`git status` shows 14 modified files toward the deprecated narrative-window approach). User decides: stash or `git checkout --`. | Clean `git status`. |
| A1 | `src/sec_graph/run/` module: `ids.py`, `io.atomic_write`, `lock.state_lock`, `progress.py` | unit tests pass; flock test under concurrent processes |
| A2 | Substrate: Parquet writer + manifest + immutability (`chmod -R a-w`) | round-trip read via DuckDB matches Pydantic models |
| A3 | `canonical_graph_v1` Pydantic schema + JSON-schema export | strict-mode export validates against OpenAI structured-outputs requirements |
| A4 | Pass-1 schema + prompt + locate function | unit test against PetSmart paragraphs returns 1+ region |
| A5 | Pass-2 schema + prompt + extract function | unit test against one PetSmart region returns valid graph |
| A6 | Evidence-bind module (substring resolve, hash, span insert) | quote-uniqueness rejection test |
| A7 | Reconcile-lite (FK, dedupe, projection eligibility) | replaces ~400 lines of regex-translation logic |
| A8 | CLI: `python -m sec_graph run --slugs X,Y,Z --resume` with per-deal progress | SIGKILL mid-run + resume produces same final output as uninterrupted run |
| A9 | Determinism gate test: bit-identical Parquet on rerun | sha256 over Parquet files matches |
| A10 | Kill list executed (delete `extract/rules/`, etc.) | tests still pass |

### Phase B — Validate at 30–40 deals (target: 1 week)

| Step | Deliverable | Acceptance |
|---|---|---|
| B1 | End-to-end on the 4 example filings (PetSmart, Saks, Providence, Zep) | ≥30 events/filing, every event quote unique, every actor has `actor_kind`, no out-of-enum values |
| B2 | Run against 30 reference deals from `seeds.csv` (`is_reference` rows) on Linkflow | per-deal `passed_clean` status; ambiguity queue has fewer than 5% of paragraphs that match `_SALE_PROCESS_RE` outside any Pass-1 region |
| B3 | Iterate Pass-1 prompt on observed misses | regex-floor coverage ≥ 95% |
| B4 | Determinism rerun gate | sha256 over Parquet matches across reruns |
| B5 | Cost & wall-clock measurement | < $50 for 30 deals, < 30 min wall-clock |

**Stability gate metric:** 30 reference deals + 10 hold-out deals all `passed_clean` for two consecutive reruns producing bit-identical Parquet. Then Phase 2.

### Phase C — Scale (target: 1 week)

| Step | Deliverable | Acceptance |
|---|---|---|
| C1 | Swap `provider_name="openai"` + direct `base_url`. Verify `cached_tokens` in `usage` returns substantial hit rate | cache hit rate observed > 70% on Pass-1, > 50% on Pass-2 reruns |
| C2 | Wire Batch API path (Phase-2-only). JSONL submit/poll/ingest | 50% cost reduction confirmed on a 10-deal trial |
| C3 | Run full 400-deal corpus | < $500 spend, < 12 h wall-clock, < 5% ambiguity-queue rate |
| C4 | Scale to 800 deals | same code, no architectural change; verify Tier 3 RPM/TPM headroom |

---

## 10. Risks

| Risk | Severity | Mitigation |
|---|---|---|
| Pass 1 misses sale-process regions on novel filings | HIGH | Regex floor check after Pass 1; ambiguity queue surfaces misses; prompt iteration in Phase B |
| Strict JSON schema rejection rate on unusual filings | MEDIUM | Bound closed enums tightly; `effort=high` retry on flagged regions; A/B against current schema in Phase B |
| Quote ambiguity (common phrases like "On May 12, 2026") | HIGH | `quote_hash` includes `(filing_id, char_start, char_end)`; Pass-2 prompt requires longer phrases when ambiguous; reject-don't-fallback on non-unique substring |
| Linkflow rate-limit surprises | MEDIUM | Start with `parallel_extract_calls=1`; profile RPM/TPM in Phase B; tune to 4 |
| Linkflow cache fragmentation undermines Phase-1 cost model | LOW | Phase-1 budget assumes no cache savings; Phase-2 unlock is the cache-payoff phase |
| GPT-5.5 model snapshot drift | MEDIUM | Pin `gpt-5.5-2026-04-23` snapshot; use Evals API in Phase 2 for regression detection |
| Substrate change adds Phase A complexity | LOW | Substrate is mechanically simple (Parquet writers); operational hardening is the real work |

---

## 11. Out of scope

- Multi-modal (image/PDF) extraction — defer; sec2md markdown is the input.
- Fine-tuning on domain corpus — `gpt-5.5` does not advertise FT availability; not blocking.
- Streaming partial recovery on failed Pass-2 calls — forbidden by no-fallback principle.
- Cross-deal reasoning ("did this advisor also work on deal X?") — not a goal of extraction; downstream concern.

---

## 12. Approval checklist for the user

Before Phase A starts, confirm:

- [ ] Architecture C (two-pass: locate then extract) is the right call vs. one-shot whole-filing
- [ ] Substrate change to Parquet + DuckDB-as-query-engine is in scope (vs. deferring to Phase C)
- [ ] Pass-1 reasoning effort `low`, Pass-2 reasoning effort `medium` baseline (vs. `high` everywhere)
- [ ] In-progress refactor (14 modified files) is OK to discard via `git checkout --`
- [ ] CLAUDE.md authority chain is OK to rewrite on plan approval
- [ ] Phase B stability gate: 30 reference + 10 hold-out deals all `passed_clean` × 2 bit-identical reruns

---

## Appendix: research artifacts (read-only, will not be committed)

- `tmp/redesign-research/agent-1-capabilities.md` — GPT-5.5 + Linkflow feature inventory
- `tmp/redesign-research/agent-2-substrate.md` — substrate evaluation (Parquet recommended)
- `tmp/redesign-research/agent-4-critique.md` — adversarial critique of current sec_graph (top-5 CRITICAL findings cited inline above)
- `tmp/redesign-research/agent-5-cost-runtime.md` — cost & runtime modeling (Designs A/B/C × 2 phases × 4 scale tiers)

Architecture proposal returned inline by the Plan agent has been folded into §3 above.
