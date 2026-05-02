# LLM Extraction Interface

**Status:** Binding contract. Currently being repaired from paragraph-local
requests to within-deal narrative windows under
`quality_reports/plans/2026-05-02_stale-scaffold-hard-cleanse-repair-plan.md`,
Phase 7. The window-based contract below is binding; any remaining
paragraph-only request paths in source are being replaced.
**Date:** 2026-05-02
**Binding with:** `docs/spec.md`, `docs/prior-pipeline-lessons.md`,
`quality_reports/plans/2026-05-02_stale-scaffold-hard-cleanse-repair-plan.md`,
`quality_reports/plans/2026-05-02_deployable-canonical-pipeline-goal.md`.

## Purpose

The LLM is an opt-in candidate producer. It is never the canonical writer. It
may emit candidate payloads only; Python validates those payloads and then
writes normal `ExtractionCandidate` rows plus extract-stage `SourceSpan` rows.

The default pipeline remains deterministic and rules-only. When LLM flags are
absent, extraction output must stay byte-stable against the rules-only golden
hashes.

## Non-Negotiables

- Zero fallbacks of any flavor: model selection, provider, transport,
  reasoning effort, schema, and payload shape are each fixed at call time.
- Old LLM payload shapes are not read by current code; there is no shim.
- No whole-filing repair loop and no canonical-row emission by the model.
- No provider-specific fields in canonical tables.
- No secret-bearing request headers, API keys, or raw provider bodies in
  tracked files.
- No cross-deal context. The window memory model is within-one-deal only.

Any violation is a hard `LLMContractError` or a failing test.

## Request Contract: Within-Deal Narrative Windows

The request contract is being moved from single-paragraph requests to
within-deal narrative windows. A window is built from ordered paragraphs
inside a single filing so that earlier paragraphs can inform interpretation of
later paragraphs. The model never sees more than one filing's content per
window, and never sees content from another deal.

`LLMExtractionRequest` for a within-deal window contains:

- `request_id`: deterministic `{slug}_llmrequest_{sequence}`;
- `deal_id`;
- `filing_id`;
- `window_id`: deterministic per-(filing, window-kind, sequence);
- `window_kind`: closed enum identifying the window-construction policy
  (e.g., `section_block`, `bid_thread`, `cycle_segment`);
- `ordered_paragraph_refs`: an ordered list of paragraph references, each
  with `paragraph_id`, `source_span_id`, `char_start`, `char_end`, and the
  paragraph text payload assembled from the source spans;
- `prior_deal_memory`: a compact summary inside the same deal of resolved
  actor aliases, prior events, active cycle candidates, and unresolved
  references — produced by Python from earlier windows in the same filing,
  not by the model;
- `extraction_task_list`: the closed set of candidate types this window may
  emit;
- `schema_version`;
- `extract_version`.

Python owns source coordinates. The provider never produces or echoes
`char_start` / `char_end`. Python derives offsets from a unique exact
`quote_text` substring match against the assembled window text, then
re-resolves the span back to the underlying paragraph source span before
insertion.

Old paragraph-only request fields (`paragraph_id`-only requests,
`paragraph_text` as the only payload, model-emitted `quote_start`/`quote_end`)
are no longer accepted.

## Candidate Payload Contract

`LLMCandidatePayload` contains exactly:

- `candidate_type`;
- `raw_value`;
- `normalized_value`;
- `confidence`;
- `quote_text`;
- `dependencies`.

The Pydantic model forbids extra fields. In particular, `quote_start` and
`quote_end` fields are invalid and must be rejected by both provider-side
strict schema and local validation.

`quote_text` must be an exact, unique substring of the assembled window text.
Python owns offset derivation:

1. If the quote is absent, fail.
2. If the quote appears more than once in the window, fail.
3. Otherwise derive `(quote_start, quote_end)` locally and create the span
   under the underlying paragraph source-span parent.

This keeps evidence coordinates under local deterministic control instead of
trusting a model to count characters.

`actor_relation` is not a flat candidate payload. It must either be removed
entirely from `candidate_type` or be expressed as a first-class typed relation
payload. JSON-in-string relation payloads are forbidden as a hidden legacy
surface.

## Response Contract

`LLMExtractionResponse` contains:

- `request_id`;
- `provider_name`;
- `provider_model`;
- `reasoning_effort`;
- `candidates`;
- `raw_response_sha256`;
- `finish_status`.

`finish_status` is one of:

- `completed`;
- `provider_rejected`;
- `provider_incomplete`;
- `contract_invalid`.

Only `completed` responses can be inserted. All other statuses are hard
failures.

A provider response without an explicit `response.completed` event must not
be promoted to `finish_status="completed"`. Streamed transport that loses the
`response.completed` event fails loudly under the current no-fallback policy
unless the provider-status proves completion through another explicit
provider signal.

## Linkflow Adapter

`src/sec_graph/extract/llm/linkflow.py` is the only Linkflow-specific module.
It calls Linkflow through the OpenAI Python SDK:

- client: `AsyncOpenAI`;
- `base_url`: `https://www.linkflow.run/v1` by default;
- endpoint: `responses.stream`;
- model: explicit caller-provided model, currently `gpt-5.5`;
- reasoning: explicit caller-provided `low`, `medium`, `high`, or `xhigh`.

The request uses provider-side strict JSON schema with a tiny schema shape:

- no `oneOf`;
- no dynamic schema-valued `additionalProperties`;
- no nested provider-hostile schema tricks;
- candidate objects have `additionalProperties: false`.

The adapter has no non-streaming HTTP branch and no prompt-only JSON branch.
Transient transport errors may retry the same exact request. They must not
downgrade model, provider, reasoning effort, schema strictness, or payload
shape.

Default request timeout is 240 seconds. Timeout changes are transport tuning
only; they do not change provider, model, reasoning effort, schema, or payload
shape.

## Streaming Completion Policy

If the stream emits output text but the SDK raises a missing
`response.completed` event, the adapter must not emit
`finish_status="completed"`. Under the current no-fallback policy the
preferred behavior is a hard `LLMContractError`. If recovery from already
streamed text is ever permitted, the resulting response must carry an
explicit non-completed finish status, every other strict check (Pydantic,
quote-text validation, span insertion) must still pass, and the change must
be reflected here in writing first.

## Runtime Flags

LLM extraction is disabled unless the caller supplies LLM flags.

Examples:

```bash
python -m sec_graph extract --all
python -m sec_graph extract --all --llm-provider linkflow --llm-model gpt-5.5 --llm-reasoning-effort high
python -m sec_graph run --all --llm-provider linkflow --llm-model gpt-5.5 --llm-reasoning-effort high
```

Environment variables:

- `LINKFLOW_API_KEY`: required for live Linkflow calls.
- `LINKFLOW_BASE_URL`: optional, defaults to Linkflow's OpenAI-compatible base URL.
- `SEC_GRAPH_LIVE_LINKFLOW=1`: required by live tests.
- `SEC_GRAPH_LINKFLOW_EFFORTS`: optional comma-separated live-test matrix.

Missing live credentials are a hard failure for live calls and a skip
condition for default tests.

## Artifact Contract

Sanitized artifacts are written under:

```text
artifacts/linkflow/YYYY-MM-DD_stage8_live/
```

Artifacts may include:

- request ID;
- provider name;
- model;
- reasoning effort;
- finish status;
- response digest;
- candidate count;
- attempt count;
- latency;
- sanitized error class/status.

Artifacts must not include API keys, authorization headers, raw provider body,
window text, paragraph text, or quote text.

Old paragraph-scoped Linkflow proof artifacts are obsolete and must stay
deleted. New proof artifacts are regenerated under the within-deal-window
contract.

## Testing Contract

Default tests must prove:

- prompt and provider schema do not mention `quote_start` or `quote_end`;
- old offset payloads are rejected as extra fields;
- non-exact quote text fails;
- ambiguous quote text fails;
- streamed Linkflow responses use strict schema and requested reasoning
  effort;
- missing `response.completed` cannot produce `finish_status="completed"`;
- LLM-disabled extraction equals rules-only extraction;
- request payloads are within-deal narrative windows with ordered paragraph
  refs and Python-owned source coordinates;
- no cross-deal context appears in any window.

Live tests must:

- skip unless `SEC_GRAPH_LIVE_LINKFLOW=1` and `LINKFLOW_API_KEY` are set;
- call Linkflow GPT-5.5 for at least `low` and `high`;
- fail if a requested model or reasoning effort is unavailable;
- insert at least one valid candidate for each requested effort;
- write sanitized artifacts only.

## Acceptance

The LLM extraction interface is valid only when:

1. `docs/spec.md` points to this file as the binding LLM contract.
2. Offline tests pass without live credentials.
3. Rules-only extraction remains unchanged with LLM mode off.
4. Live Linkflow GPT-5.5 passes for at least `low` and `high`, or fails
   loudly with a sanitized hard-failure artifact.
5. Session logs record exact commands and outcomes without secrets.
6. Every accepted candidate has exact local source-span proof against the
   underlying paragraph source span.
