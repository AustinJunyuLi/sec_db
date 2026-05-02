# Stage 8 LLM Extraction Interface

**Status:** Stage 8 design contract.
**Date:** 2026-05-02
**Binding with:** `docs/spec.md`, `docs/prior-pipeline-lessons.md`, `quality_reports/plans/2026-05-02_parallel-execution-plan.md`.

## Purpose

Stage 8 adds an optional LLM-assisted extraction pass without changing the
canonical-store contract. The LLM is a candidate producer only. It must never
write `deals`, `process_cycles`, `actors`, `events`, `event_actor_links`,
`judgments`, `participation_counts`, or projection artifacts directly.

The deterministic rules-only pipeline remains the default and must be bit-stable
when LLM mode is disabled.

## Design Choice

Three approaches were considered:

1. **Provider-neutral interface plus Linkflow adapter.** Define a small internal
   request/response contract, then implement Linkflow behind it. This is the
   chosen approach because it lets provider constraints live outside canonical
   schema and outside deterministic reconciliation.
2. **Linkflow-first implementation.** Faster to test live, but it would encode
   provider behavior directly into extraction semantics. Rejected.
3. **Offline/mock-only interface.** Safest for default tests, but it would not
   satisfy the Stage 8 live-provider gate. Rejected as incomplete.

## Scope

Stage 8 implements:

- `src/sec_graph/extract/llm/` as an opt-in candidate producer.
- Provider-neutral dataclasses or Pydantic models for request, response, and
  candidate payloads.
- A Linkflow adapter that is used only when explicitly enabled.
- Offline tests proving that disabled LLM mode leaves rules-only candidates
  unchanged.
- Live tests gated by environment variables and excluded from default pytest.
- Sanitized live artifacts under `artifacts/linkflow/`.

Stage 8 does not implement:

- canonical row writing by the LLM;
- provider-specific fields in canonical tables;
- silent model/provider fallback;
- backward-compatible readers for older LLM payload shapes;
- prompt repair loops that rewrite whole canonical outputs.

## Interface Contract

### Request

An `LLMExtractionRequest` contains:

- `request_id`: deterministic ID, `{slug}_llmrequest_{sequence}`;
- `filing_id`;
- `deal_slug`;
- `paragraph_id`;
- `parent_evidence_id`: the paragraph seed span;
- `section`;
- `paragraph_text`;
- `char_start`;
- `char_end`;
- `allowed_candidate_types`: bounded list of candidate families;
- `schema_version` and `extract_version`.

The request is paragraph-scoped. Stage 8 does not send the whole filing as a
single provider input. This keeps provider failures local and avoids the repair
collapse pattern described in `docs/prior-pipeline-lessons.md`.

### Response

An `LLMExtractionResponse` contains:

- `request_id`;
- `provider_name`;
- `provider_model`;
- `reasoning_effort`;
- `candidates`;
- `raw_response_sha256`;
- `finish_status`.

`finish_status` is provider-neutral and one of:

- `completed`;
- `provider_rejected`;
- `provider_incomplete`;
- `contract_invalid`.

Any status other than `completed` is a hard failure for live tests. The adapter
does not salvage partial output into active candidates.

### Candidate Payload

An `LLMCandidatePayload` contains:

- `candidate_type`: one of the existing `ExtractionCandidate` candidate types;
- `raw_value`;
- `normalized_value`;
- `confidence`: `low`, `medium`, or `high`;
- `quote_text`: exact substring from the paragraph;
- `quote_start`: paragraph-local start offset;
- `quote_end`: paragraph-local end offset;
- `dependencies`: list of candidate IDs, usually empty at Stage 8.

The adapter converts payloads to normal `ExtractionCandidate` rows plus
extract-stage `SourceSpan` rows. It must validate:

- candidate type is allowed;
- quote offsets are inside the paragraph;
- quote text exactly equals the paragraph substring;
- quote hash matches the emitted span;
- every candidate has at least one evidence ID;
- every extract span has `parent_evidence_id` set to the paragraph seed.

Contract violations fail loudly and write a sanitized failure artifact.

## Provider Isolation

Provider adapters implement one interface:

```text
extract(request: LLMExtractionRequest, config: LLMProviderConfig) -> LLMExtractionResponse
```

Provider config is runtime-only:

- `provider_name`;
- `model`;
- `reasoning_effort`;
- `api_key_env`;
- timeout / retry limit.

No API keys are stored in tracked files, run logs, or artifacts. Missing keys
are hard failures when live mode is requested. Default offline tests must not
require a key.

Linkflow-specific behavior is confined to `extract/llm/linkflow.py`.

## Feature Flags

LLM mode is disabled by default.

CLI behavior:

- `python -m sec_graph extract --all` remains rules-only.
- `python -m sec_graph extract --all --llm-provider linkflow --llm-model gpt-5.5 --llm-reasoning-effort high` enables LLM extraction.
- `python -m sec_graph run --all` remains rules-only.
- `python -m sec_graph run --all --llm-provider linkflow ...` enables LLM during the extract stage.

Environment variables:

- `LINKFLOW_API_KEY`: required only for live Linkflow calls.
- `SEC_GRAPH_LIVE_LINKFLOW=1`: required by live tests.

If LLM flags are absent, the candidate table and spans produced by extraction
must match the rules-only golden hashes.

## Live Linkflow Gate

The live gate probes GPT-5.5 through Linkflow using at least:

- `low`;
- `high`.

It should also try:

- `medium`;
- `xhigh`.

If Linkflow rejects GPT-5.5 or any requested reasoning control, the run stops
and records a hard failure. It does not downgrade model, provider, or reasoning
effort.

Live artifacts are written under:

```text
artifacts/linkflow/YYYY-MM-DD_stage8_live/
```

Artifacts may include:

- sanitized request metadata;
- response metadata;
- candidate projection hashes;
- per-effort success/failure manifests;
- sanitized error class and status.

Artifacts must not include API keys. They may include paragraph text and quote
text because filing text is research data already inside this repository.

## Testing Contract

Default offline tests:

- validate request/response models;
- validate payload-to-candidate conversion;
- prove invalid quote offsets fail loudly;
- prove LLM-disabled extract output matches rules-only output exactly;
- prove CLI help exposes LLM flags without requiring live credentials.

Live tests:

- skipped unless `SEC_GRAPH_LIVE_LINKFLOW=1` and `LINKFLOW_API_KEY` are set;
- call Linkflow GPT-5.5 for each requested reasoning effort;
- fail if provider/model/reasoning is unavailable;
- write sanitized artifacts under `artifacts/linkflow/`.

## Acceptance

Stage 8 passes only when:

1. `docs/spec.md` references this interface as the Stage 8 binding contract.
2. Offline pytest passes with no live credentials.
3. Rules-only extraction hashes remain unchanged with LLM mode off.
4. LLM-enabled extraction writes only `candidates` and extract-stage `spans`.
5. Live Linkflow GPT-5.5 tests pass for at least `low` and `high`, or stop with
   an explicit hard-failure artifact if Linkflow does not support the requested
   contract.
6. Session logs record exact commands and outcomes without secrets.
