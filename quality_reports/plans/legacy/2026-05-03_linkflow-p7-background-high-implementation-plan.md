# Linkflow Background P7/High Implementation Plan

## Goal

Make production LLM extraction match the calibration winner:

- **Input scope:** one coherent `Background of the Merger` / sale-process section, not tiny paragraph-local windows and not whole raw filings.
- **Model call:** Linkflow `gpt-5.5`, strict V0 `SemanticClaimsPayload`, Responses API streaming.
- **Reasoning default:** `high`.
- **Prompt:** P7-style validator-aware prompt that allows the same source sentence/quote to support multiple distinct claims.
- **Policy:** no fallbacks, no backward compatibility, no old prompt path, no flat-schema escape hatch.

## Current Repo Truth

The implementation agent must verify this first:

- `LLMProviderConfig.reasoning_effort` is already `"high"` in `src/sec_graph/extract/llm/models.py`; keep it and add a regression test.
- Production prompt is still stale in `src/sec_graph/extract/llm/prompt.py`: it says quote text must be “appearing exactly once,” which suppresses extraction.
- Production Linkflow request still sends only one user message in `src/sec_graph/extract/llm/linkflow.py`.
- Production evidence map still builds bounded local windows around matched paragraphs in `src/sec_graph/extract/evidence_map.py`; replace this for LLM extraction with full Background-section regions.

## Implementation Tasks

### 1. Add Regression Tests First

Modify `tests/test_hard_reset_schema.py` or create a focused LLM test file.

Required tests:

- `test_default_linkflow_reasoning_effort_is_high`
  - Assert `LLMProviderConfig(provider_name="linkflow").reasoning_effort == "high"`.

- `test_prompt_allows_cross_claim_quote_reuse`
  - Build an `LLMWindowRequest`.
  - Assert prompt/system text includes “same quote across different claims is fine” or equivalent.
  - Assert it does **not** contain “appearing exactly once.”

- `test_linkflow_payload_uses_system_and_user_messages`
  - Call `_response_payload(...)`.
  - Assert `input[0]["role"] == "system"` and `input[1]["role"] == "user"`.

- Replace stale bounded-window test:
  - Delete/replace `test_evidence_map_builds_bounded_local_windows_not_pattern_wide_unions`.
  - New expectation: the evidence map creates one full `sale_process_narrative` region containing all paragraphs whose section is `Background of the Merger`.

- Add section-heading test:
  - Styled Zep headings like `COMMAND=STYLE_ADDED... Background of the Merger` must be recognized by ingestion section assignment.

### 2. Replace Evidence-Map Windowing With Background Region

Modify `src/sec_graph/extract/evidence_map.py`.

Required behavior:

- Remove bounded local-window routing as the production LLM path.
- Select all ordered paragraphs where `paragraphs.section == "Background of the Merger"`.
- Create exactly one primary region:
  - `region_kind = "sale_process_narrative"`
  - priority `1`
  - `paragraph_ids_json` contains every Background paragraph id in source order.
- If no Background section exists, raise a hard `ValueError`.
- Do **not** fall back to raw filing, first paragraph, keyword scan, or old bounded windows.

Use the 10 calibrated obligations:

```python
_BACKGROUND_OBLIGATIONS = (
    ("event", "Sales process initiation", "required"),
    ("participation_count", "Bidder count at IOI stage", "required"),
    ("participation_count", "Bidder count at first round", "important"),
    ("event", "Final round bid receipt", "required"),
    ("event", "Exclusivity grant", "required"),
    ("actor", "Target board", "required"),
    ("actor", "Financial advisor for target", "required"),
    ("actor", "Legal advisor for target", "required"),
    ("bid", "Final bid price", "required"),
    ("actor_relation", "Buyer group composition", "important"),
)
```

Allowed claim types for the region should be the unique claim types from those obligations.

### 3. Replace Production Prompt With P7

Modify `src/sec_graph/extract/llm/prompt.py`.

Implement:

- `build_system_prompt() -> str`
- `build_window_prompt(window: LLMWindowRequest) -> str`
- optionally `build_window_messages(window) -> list[dict[str, str]]`

Core system rules must say:

- Extract every supported sale-process semantic claim.
- Exact quote copying is required.
- A quote must be unique in the input; if too short/ambiguous, choose a longer unique quote or omit.
- Same quote across different claims is fine.
- One sentence may support actor, event, bid, count, and relation claims.
- Dates use `YYYY-MM-DD` only when explicit; otherwise `null`.
- Never emit `char_start`, `char_end`, canonical ids, projection rows, or provider offsets.
- Emit one `coverage_result` per obligation; never emit `missed`.

Keep the final user-message reminder after the window text:

```text
Extract every supported claim. Reuse quotes across distinct claims when warranted. Emit one coverage_result per obligation. Return strict JSON only.
```

Do not add examples unless a later eval proves they help. Do not add P8 yet.

### 4. Update Linkflow Request Shape

Modify `src/sec_graph/extract/llm/linkflow.py`.

- `_response_payload(...)` must send system + user messages.
- Keep strict `json_schema` with current V0 `SemanticClaimsPayload`.
- Keep no `max_output_tokens`.
- Keep fail-loud behavior for missing completion, invalid JSON, invalid schema, quote mismatch, and ambiguous quote.
- Update cost estimation to count both system and user prompt text if it currently only counts `build_window_prompt(request)`.

Do not add medium retry, flat-schema fallback, loose JSON parser, or provider-owned source offsets.

### 5. Update Docs

Update only live authority docs, not historical logs:

- `docs/llm-interface.md`
  - State default live reasoning is `high`.
  - State request scope is full Background/sale-process section.
  - Clarify quote rule: a quote may be reused across claims, but must resolve uniquely in the source window.
  - State whole raw filing extraction is not production mode.

- `docs/spec.md`
  - Update any stale mention of paragraph-local or bounded windows.
  - Keep the canonical proof rule: Python owns source coordinates and rejects quote failures.

### 6. Verification

Run offline:

```bash
UV_CACHE_DIR=/private/tmp/uv-cache PYTHONDONTWRITEBYTECODE=1 uv run pytest -q -p no:cacheprovider
```

Run live high-only Background proof for the three calibrated deals:

```bash
set -a; . ./.env; set +a
export SEC_GRAPH_LIVE_LINKFLOW=1
export UV_CACHE_DIR=/private/tmp/uv-cache
PYTHONDONTWRITEBYTECODE=1 uv run python -m sec_graph run \
  --source filings \
  --slugs mac-gray petsmart-inc zep \
  --projection bidder_cycle_baseline_v1 \
  --llm-provider linkflow \
  --llm-model gpt-5.5 \
  --llm-reasoning-effort high
```

Inspect artifacts and summaries:

- each deal should have one Background LLM request unless the pipeline has a documented deterministic non-LLM stage;
- provider completion must be normal, not salvaged;
- Pydantic must pass;
- coverage must be 10/10;
- quote binding must reject zero valid Background-high claims in the target proof;
- generated artifacts must not contain API keys, raw filing text, prompt text, provider output, or quote text.

### 7. Aggressive Staleness Cleanse

After implementation and verification, slash stale surfaces aggressively.

Search:

```bash
rg -n "appearing exactly once|bounded local windows|full filing fallback|flat schema|medium.*default|paragraph-local|provider_incomplete_salvaged|legacy|backward compatibility|fallback" .
```

Required cleanup rules:

- Delete stale tests that bless bounded local windows.
- Delete or rewrite stale docs that suggest medium default, raw whole-filing production mode, paragraph-local extraction, flat-schema fallback, loose parsing, or backward-compatible prompt behavior.
- Remove temporary dry-run artifacts and scratch calibration scripts unless they are intentionally preserved as historical evidence under `quality_reports/llm_calibration/`.
- Preserve `data/filings/`.
- Do not revert unrelated dirty worktree changes.
- Stage only files touched for this implementation.

Final verification after cleanup:

```bash
UV_CACHE_DIR=/private/tmp/uv-cache PYTHONDONTWRITEBYTECODE=1 uv run pytest -q -p no:cacheprovider
git status --short
```

### 8. Commit

Commit after all checks pass.

Suggested commit:

```bash
git add docs/spec.md docs/llm-interface.md \
  src/sec_graph/extract/evidence_map.py \
  src/sec_graph/extract/llm/prompt.py \
  src/sec_graph/extract/llm/linkflow.py \
  src/sec_graph/extract/llm/models.py \
  tests
git commit -m "feat: use high-reasoning P7 background extraction"
```

The commit must not include secrets, `.env`, raw generated provider output, or unrelated user changes.
