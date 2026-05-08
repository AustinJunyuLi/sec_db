---
title: Linkflow API capability probe - clean-slate spec
status: DRAFT
date: 2026-05-08
blocks: docs/superpowers/specs/2026-05-08-agentic-review-compiler-design.md
---

# Linkflow API capability probe - clean-slate spec

## 1. Authority

This document defines the blocking Linkflow capability probe for the clean-slate
agentic SEC filing review compiler.

The compiler design assumes Linkflow can support structured model calls,
tool-using agent loops, verifier outputs, bounded concurrency, and provider
contract auditing. Those assumptions must be tested before extraction agents are
implemented.

This probe is not an extraction pipeline. It is a provider-discovery harness.

## 2. Non-negotiables

- Use Linkflow direct SDK calls only.
- Do not call any non-Linkflow model provider.
- Do not print, commit, or persist API keys.
- Read secrets only from environment variables.
- Store sanitized request and response artifacts.
- Capture enough evidence to reproduce every capability decision.
- Treat unsupported provider behavior as design input, not as something to
  paper over with loose parsing.
- Do not implement extraction agents until Tier 1 probes pass or the compiler
  architecture is revised.

## 3. Environment contract

Required environment variables:

```text
LINKFLOW_API_KEY
LINKFLOW_BASE_URL
```

Default `LINKFLOW_BASE_URL`, if not supplied, should be documented by the probe
implementation and recorded in the probe manifest.

The probe runner must refuse to start if `LINKFLOW_API_KEY` is absent. It must
log only whether the key was present, never the value.

## 4. Probe outputs

Each probe run writes:

```text
runs/linkflow-probe/<probe_run_id>/
  probe_manifest.json
  capability_matrix.json
  sanitized_calls.jsonl
  raw_shape_samples.jsonl
  failures.jsonl
  README.md
```

`probe_manifest.json` records:

- probe run id;
- run timestamp;
- SDK package and version;
- Python version;
- Linkflow base URL;
- model names tested;
- environment variable presence;
- git commit if available;
- probe suite version.

`capability_matrix.json` records one entry per capability:

```json
{
  "capability": "tool_call_single_round",
  "tier": 1,
  "status": "supported",
  "evidence_artifacts": ["sanitized_calls.jsonl:12"],
  "notes": "single function call round-tripped with call_id"
}
```

Allowed statuses:

- `supported`;
- `partial`;
- `unsupported`;
- `inconclusive`;
- `not_tested`.

## 5. Sanitization rules

Sanitized artifacts may include:

- model;
- endpoint path;
- request parameter names;
- response ids;
- response statuses;
- response output item types;
- structured JSON outputs from synthetic prompts;
- token usage;
- latency;
- error type and status code;
- tool call names and synthetic arguments.

Sanitized artifacts must not include:

- API keys;
- authorization headers;
- cookies;
- real filing text;
- personal data;
- proprietary deal data;
- raw provider debug dumps that include secrets.

The probe uses synthetic text only.

## 6. Tier meanings

| Tier | Meaning | Failure response |
|---|---|---|
| Tier 1 | Required for the compiler architecture | Stop agent implementation and revise architecture |
| Tier 2 | Important for implementation choices | Record limitation and adapt design |
| Tier 3 | Useful for future optimization | Record for reference |

## 7. Tier 1 probes

### P1.01 - SDK connectivity

Question: can the direct SDK reach Linkflow and receive a completed response?

Method:

- create the SDK client using `LINKFLOW_API_KEY` and `LINKFLOW_BASE_URL`;
- send a trivial prompt: `Reply with exactly: OK`;
- test non-streaming first;
- test streaming separately if non-streaming passes.

Pass:

- final response is completed;
- output text contains exactly `OK` or a documented harmless variant;
- latency and response shape are recorded.

Blocks if:

- authentication fails;
- endpoint shape is unknown;
- no completed response can be obtained.

### P1.02 - Model and reasoning parameter acceptance

Question: which model names and reasoning effort values does Linkflow accept?

Method:

- test the intended default model;
- test `low`, `medium`, and `high` reasoning effort if accepted by the API;
- record whether usage exposes reasoning tokens.

Pass:

- at least one model and one reasoning setting can be used reliably.

Partial:

- reasoning effort is ignored or usage does not expose reasoning tokens, but
  calls still complete.

### P1.03 - Strict structured output, minimal schema

Question: can Linkflow enforce a small strict JSON schema?

Synthetic schema:

```json
{
  "type": "object",
  "additionalProperties": false,
  "properties": {
    "label": { "type": "string", "enum": ["yes", "no"] },
    "confidence": { "type": "number" },
    "reason": { "type": "string" }
  },
  "required": ["label", "confidence", "reason"]
}
```

Pass:

- response validates locally against the schema;
- no extra fields are returned.

### P1.04 - Strict structured output, provider-safe nested schema

Question: what nested schema subset can Linkflow handle reliably?

Method:

- test nested objects;
- test arrays of objects;
- test nullable scalar fields;
- test enums;
- test `$defs` before and after inlining;
- test `anyOf` or `oneOf` only as discovery, not as required behavior.

Pass:

- a provider-safe schema transform is identified and documented.

Blocks if:

- no nested strict schema can be made reliable enough for claim attempts and
  verdicts.

### P1.05 - Single tool call

Question: can Linkflow request a function/tool call and consume the result?

Synthetic tool:

```json
{
  "name": "lookup_case",
  "description": "Return a synthetic fact for a synthetic case id.",
  "parameters": {
    "type": "object",
    "additionalProperties": false,
    "properties": {
      "case_id": { "type": "string" }
    },
    "required": ["case_id"]
  }
}
```

Method:

- ask the model to look up case `A1`;
- execute the tool locally with a fixed synthetic result;
- return the tool result;
- ask for a final answer.

Capture:

- request parameter name for tools;
- output item type for tool calls;
- tool call id field;
- argument serialization shape;
- required shape for returning tool output.

Pass:

- final answer uses the synthetic tool result.

### P1.06 - Multi-turn tool loop

Question: can Linkflow support a loop with multiple sequential tool calls?

Synthetic tools:

- `search_text`;
- `get_paragraph`;
- `verify_quote`.

Method:

- provide a tiny synthetic filing in local Python state;
- ask the model to extract one fact with evidence;
- force the model to use at least two tools before final output;
- cap at 10 rounds.

Pass:

- the loop terminates;
- at least two tool results are consumed;
- the final answer cites the synthetic paragraph id and quote.

### P1.07 - Tool use plus final structured output

Question: can the final answer after tool use be strict structured JSON?

Method:

- run a multi-turn tool loop;
- require the final no-tool response to conform to a strict verdict schema.

Synthetic final schema:

```json
{
  "type": "object",
  "additionalProperties": false,
  "properties": {
    "verdict": { "type": "string", "enum": ["confirm", "reject", "ambiguous"] },
    "paragraph_id": { "type": "string" },
    "quote": { "type": "string" },
    "reason": { "type": "string" }
  },
  "required": ["verdict", "paragraph_id", "quote", "reason"]
}
```

Pass:

- final response validates locally;
- intermediate tool-call turns do not break structured final output.

Blocks if:

- tools and structured output cannot be combined in any reliable call pattern.

### P1.08 - Error and retry taxonomy

Question: which Linkflow errors are retryable, fatal, or malformed-contract
failures?

Method:

- intentionally trigger invalid model;
- intentionally trigger invalid schema;
- intentionally trigger malformed tool output;
- run enough parallel calls to observe rate-limit behavior if safe;
- record timeout behavior with a short client timeout.

Pass:

- the probe can classify common errors into retryable, fatal, and contract
  invalid buckets.

### P1.09 - Bounded concurrency

Question: what low concurrency level is safe for per-deal and per-corpus runs?

Method:

- run 1, 2, 4, and 8 synthetic calls concurrently;
- keep prompts small;
- record latency, error rates, and rate-limit headers or messages.

Pass:

- a conservative default concurrency is identified.

Partial:

- concurrency above 1 is unreliable, but sequential calls are stable.

## 8. Tier 2 probes

### P2.01 - Streaming event shapes

Test streaming and record all event types. Determine whether streaming is
required, optional, or harmful for the compiler.

### P2.02 - Stateful response ids

Test `previous_response_id` if exposed. Determine whether the compiler can rely
on provider-managed conversation state. The default design should not require
it unless this probe is reliable.

### P2.03 - Parallel tool calls in one turn

Test whether the model can request multiple tool calls in one response and
whether Linkflow returns them in a stable shape. The compiler can operate
without this, but support may improve latency.

### P2.04 - Long context

Use synthetic repeated text at increasing sizes. Record maximum reliable input
size, truncation behavior, latency, and error modes. This does not authorize
whole-filing prompting; it informs region sizing.

### P2.05 - Token usage reporting

Record whether input, output, cached, and reasoning token counts are exposed.
The compiler must log cost if available and mark it unavailable otherwise.

### P2.06 - Prompt caching

Probe any prompt-cache parameter Linkflow accepts. This is optional and must not
be required for correctness.

### P2.07 - File or PDF input

Probe only with synthetic files. The compiler should remain text-first unless
file input proves reliable and useful.

## 9. Tier 3 probes

- built-in web search;
- built-in file search;
- code interpreter;
- logprobs;
- batch API;
- metadata and user fields;
- service tier controls;
- request storage controls.

These are not required for the clean-slate compiler. Record support for future
use only.

## 10. Probe harness design

The harness should be a small Python package with:

```text
linkflow_probe/
  __init__.py
  cli.py
  client.py
  schemas.py
  sanitize.py
  probes/
    p1_connectivity.py
    p1_structured_output.py
    p1_tools.py
    p1_errors.py
    p1_concurrency.py
    p2_streaming.py
    p2_context.py
  report.py
tests/
  test_sanitize.py
  test_schema_transforms.py
  test_matrix_report.py
```

The CLI should support:

```bash
python -m linkflow_probe run --tier 1
python -m linkflow_probe run --all
python -m linkflow_probe summarize runs/linkflow-probe/<probe_run_id>
```

## 11. Provider-safe schema transform

The harness must include a schema transformer that can be reused by the
compiler if it passes probes.

Transformer responsibilities:

- inline `$defs` when required;
- set `additionalProperties: false` on every object;
- make required fields explicit;
- avoid provider-hostile constructs discovered by probes;
- preserve closed enums;
- preserve nullable scalar fields only in supported form;
- reject recursive or unconstrained schemas.

The transformer must be tested without live Linkflow calls.

## 12. Decision gate

After Tier 1 probes, produce a short gate report:

```text
GO
GO_WITH_LIMITATIONS
NO_GO
```

`GO` requires all Tier 1 probes supported.

`GO_WITH_LIMITATIONS` is allowed only when the compiler design has an explicit
adaptation. Examples:

- no streaming, but non-streaming works;
- no `previous_response_id`, but full explicit history works;
- no parallel tool calls, but sequential tool loops work;
- concurrency limited to 1, but calls are stable.

`NO_GO` is required when:

- strict structured output is unavailable;
- tool calls are unavailable;
- tool use cannot be combined with final structured output;
- provider failures cannot be classified enough to fail loudly;
- no stable model call can complete.

## 13. Acceptance criteria

The probe implementation is acceptable only if:

- Tier 1 probes can be run with one command;
- all artifacts are sanitized;
- missing credentials fail before any network request;
- capability matrix entries cite evidence artifacts;
- schema transform behavior is unit-tested;
- tool-loop behavior is covered by live probe artifacts;
- the final gate report clearly says whether the compiler can proceed.

## 14. Implementation-agent instruction

Build and run this probe before building extraction agents. Do not infer
Linkflow behavior from OpenAI documentation alone. The compiler architecture
must follow the observed Linkflow behavior recorded by this probe.
