# Linkflow Calibration — External Reviewer Guide

**Purpose:** Help an independent agent evaluate the methodology and conclusions of the 2026-05-03 Linkflow LLM call-shape calibration campaign.

---

## What was being calibrated

sec_graph (M&A SEC filing extraction pipeline) calls Linkflow's gpt-5.5 proxy with strict `json_schema` response_format. The user reported "lots of hiccups" and asked us to find the most stable, highest-quality call shape.

The goals stated by the user:
- **Stability** > cost (bottomless Linkflow tokens during Phase 1)
- **Highest reliability** for production extraction
- Empirical evidence, not theory

---

## What's where

| Path | What it is |
|---|---|
| `quality_reports/llm_calibration/2026-05-03_linkflow-probe-log.md` | The trying log — every probe round, every result, every interpretation |
| `quality_reports/llm_calibration/probe_lf_matrix.py` | The probe matrix runner (durable copy of `/tmp/lf_matrix.py`) |
| `quality_reports/llm_calibration/probe_lf_scale.py` | The scale-test wrapper (durable copy of `/tmp/lf_scale.py`) |
| `/tmp/lf_matrix.py`, `/tmp/lf_scale.py` | Same scripts at original locations; ephemeral |
| `/tmp/lf_probe*.py` | Earlier diagnostic probes (deleted in earlier session per prior instruction; re-doable from `probe_lf_matrix.py`) |
| `src/sec_graph/extract/llm/linkflow.py` | sec_graph's actual Linkflow adapter (the production target) |
| `src/sec_graph/extract/llm/models.py` | Pydantic models including `SemanticClaimsPayload` |
| `src/sec_graph/extract/llm/prompt.py` | sec_graph's actual prompt builder (`build_window_prompt`) |
| `tmp/redesign-research/agent-{1,2,4,5}-*.md` | Pre-calibration research artifacts from earlier agent dispatches |

---

## Key conclusions to evaluate

The campaign concluded that the production winner is:

> **V0 schema (current sec_graph) + P7 prompt (custom: validator-aware AND multi-quote-permissive) at reasoning="medium"**

Specifically:
1. The schema does NOT need to change — `_semantic_claim_schema()` produces a Linkflow-compatible shape.
2. The prompt (`build_window_prompt`) **does** need to change — the current "appearing exactly once" framing suppresses ~3-5× the legitimate claims.
3. Recommended `LLMProviderConfig` defaults: `reasoning_effort="medium"`, `timeout_seconds=3600` (already applied).

---

## Methodology summary

- Same input window (PetSmart 30K-char prefix from `data/examples/petsmart-inc.md`) used across most probes for direct comparison.
- Streaming `client.responses.stream()` via `openai.AsyncOpenAI` with `base_url=https://www.linkflow.run/v1`.
- Schema delivered as `text.format = {"type": "json_schema", "name": "...", "strict": true, "schema": ...}`.
- Probe records: duration, in/out/reasoning tokens, claim counts, **quote-match rate** (substring search), duplicate-quote count, empty-string-date count, ISO-format date count, **Pydantic validation pass/fail** (V0 schema only).

---

## Things a reviewer should attack

The methodology has gaps. A skeptical reviewer should specifically verify or refute these:

### 1. Single-window comparison risk

Most probes used the same 30K PetSmart prefix. **Generalization across filings is tested only by the Round 4c full-Saks scale test.** If the V0+P7 winner is PetSmart-specific or genre-specific, we wouldn't see it from this corpus alone.

**To check:** Re-run V0+P0 vs V0+P7 on the other example filings (Saks, Providence-Worcester, Zep). If P7 still produces more claims with 100% quote-match across all 4 examples, the conclusion holds.

### 2. Synthetic obligation list

Probes used a hard-coded 10-obligation list invented for the calibration, not the obligations sec_graph's actual `evidence_map.py` would emit. The model is responding to my synthetic obligations.

**To check:** Run sec_graph's actual `extract()` end-to-end on a real filing, capturing the real `LLMWindowRequest` it constructs. Verify P7 still outperforms P0 with real obligations.

### 3. No quality assessment of claims

The probe counts claims but does NOT judge whether they're correct. A response with 42 wrong claims would score the same as a response with 42 right claims.

**To check:** Sample 10 claims from a V0+P7 response and a V0+P0 response on the same input. Manually verify each claim against the source paragraph. Compute precision (true positives / emitted) and recall (true positives / total in window).

### 4. Pydantic gate is not the full validation gate

The probe checks `SemanticClaimsPayload.model_validate(parsed)`. sec_graph's actual `_parse_payload()` does the same Pydantic check, but the broader pipeline also runs evidence-binding (substring resolution against filing source bytes, `quote_hash` computation, FK resolution). A claim could pass Pydantic but fail evidence binding.

**To check:** Wire P7 into sec_graph's actual `extract()` → `evidence-bind` → `reconcile` flow on one real filing. Count claims that pass Pydantic but fail evidence binding.

### 5. Variance sample size

V0+P7 variance was measured with 4 runs at low (42, 44 + earlier 30K runs) and 3 at medium (Round 4b — see log). For a "stability" claim, more runs would tighten confidence intervals. Variance at scale (full filing) was not measured.

**To check:** Run V0+P7+medium on a single filing 5-10 times. Compute coefficient of variation on claim count. If CV > 20%, stability is overstated.

### 6. Reasoning-token reporting quirks

Some probes reported `reasoning_tokens=0` even at low effort. Could be an SDK reporting quirk, could be a real "no reasoning needed" signal. The interpretation is unclear.

**To check:** Look at OpenAI Responses API streaming events; verify whether `output_tokens_details.reasoning_tokens` is reliably populated on every call.

### 7. No 502 reproduction

The earlier dynamic-key-object 502 was reproduced once (probe T7). The retry path was never exercised because no test triggered a transient 502 against the chosen schema. Retry behavior under real failure is untested.

**To check:** Force a 502 (malformed schema, deliberately oversized request, or use a bad endpoint) and verify the retry/backoff in `linkflow.py:225-235` behaves as designed.

### 8. Prompt language stability

P7 was hand-written by me in one pass. Small wording changes ("emit each independently" vs "extract each separately") could swing model behavior significantly.

**To check:** Run V0+P7 with 3 micro-variations of the key sentence ("Same quote across different claims is fine") and measure variance.

---

## Reproducing the campaign

```bash
# From the project root, with .venv activated.
export LINKFLOW_API_KEY=sk-...   # never write this to a file

# Schema variants × prompt variants × reasoning levels:
.venv/bin/python /tmp/lf_matrix.py V0:P0:low V0:P7:low V0:P7:medium

# Scale tests on full filings:
.venv/bin/python /tmp/lf_scale.py
```

Each probe writes one JSON line to stdout. Records are then transcribed manually into the trying log.

---

## What NOT to assume the campaign proves

- That **gpt-5.5 is reliable in production** (only ~25 calls; no longitudinal data).
- That **Linkflow is reliable enough for batch corpus runs** (no concurrent-load test).
- That **V0+P7 will work on every filing** (only PetSmart + 1 Saks call tested).
- That the **quality of extracted claims is good** (only counted, not judged).
- That **Pydantic passing means production-pass** (evidence-binding is a separate gate).

The campaign proves: V0+P7 produces ~3-5× more claims than V0+P0 on PetSmart 30K, all of which pass Pydantic validation, with 100% verbatim quote match.
