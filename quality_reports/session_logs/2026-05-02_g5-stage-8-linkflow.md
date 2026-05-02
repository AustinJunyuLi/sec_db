# Session Log: G5 Stage 8 Linkflow

**Date:** 2026-05-02
**Branch:** `main`
**Gate:** G5 - opt-in Linkflow GPT-5.5 extraction
**Status:** Superseded by the hard-cleanse Linkflow contract.

## Hard-Cleanse Update

The earlier Stage 8 proof used an offset-bearing candidate payload and a
non-streaming transport. That proof is no longer valid. The current contract is
defined in `docs/llm-interface.md`:

- Linkflow calls use OpenAI SDK `responses.stream`.
- The request uses strict provider JSON schema.
- Candidate payloads contain no `quote_start` or `quote_end`.
- Python derives source offsets from a unique exact `quote_text` match.
- Old offset payloads are rejected as invalid extra fields.
- No model, provider, reasoning, transport, schema, or payload fallback exists.

The old artifacts under `artifacts/linkflow/2026-05-02_stage8_live/` are stale
offset-contract artifacts and are intentionally removed.

## Current Required Proof

Offline proof:

```bash
PATH=.venv/bin:$PATH python -m pytest tests/test_llm_interface.py tests/test_extract_llm_disabled.py tests/test_linkflow_live.py -q
```

Live proof:

```bash
SEC_GRAPH_LIVE_LINKFLOW=1 SEC_GRAPH_LINKFLOW_EFFORTS=low,high PATH=.venv/bin:$PATH python -m pytest tests/test_linkflow_live.py -q
```

Three-deal pilot:

```bash
python -m sec_graph run --all --llm-provider linkflow --llm-model gpt-5.5 --llm-reasoning-effort high
```

The actual pilot may use an explicit temporary DB and run directory. Exact
commands and outcomes belong in a fresh session log once executed.
