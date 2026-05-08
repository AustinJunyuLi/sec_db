---
title: Linkflow API capability probe — spec
status: DRAFT
date: 2026-05-08
context: Blocking pre-implementation validation for the agentic-review-compiler design (2026-05-08-agentic-review-compiler-design.md)
authors: Junyu Li, Claude (Opus 4.7)
---

# Linkflow API capability probe — spec

## 1. Status

DRAFT. Awaiting user approval before probe implementation begins.

This is a **blocking pre-implementation document** for the agentic-review-compiler redesign. The redesign assumes Linkflow exposes the OpenAI Responses API with full function-calling support. This probe spec validates that assumption (and many others) end-to-end before a single agent line of code is written.

## 2. Context

What we know from the existing `src/sec_graph/extract/llm/linkflow.py` integration:

- Linkflow exposes an OpenAI-compatible Responses API at a configurable `base_url`.
- Authentication via `LINKFLOW_API_KEY` env var, passed as `api_key` to `AsyncOpenAI`.
- Production model is `gpt-5.5` with `medium` reasoning effort.
- Streaming via `client.responses.stream(...)` is the production call shape.
- Strict JSON schema (`response_format: json_schema`) is used for structured output.
- Final response must reach `status="completed"` to be accepted.
- Retryable errors observed in production: HTTP 408, 409, 425, 429, 5xx, `APITimeoutError`, `APIConnectionError`, `RateLimitError`, `InternalServerError`.
- The system uses 3-attempt retry with backoff (5s, 15s).

What we **do not know** and the redesign depends on:

- Tool calling (function calling) — never used in existing code.
- Multi-turn tool loops — never tested.
- Parallel tool calls in a single turn.
- Long-context behavior (filings can be 200K+ tokens).
- Concurrency limits and rate-limit shape.
- Available models beyond `gpt-5.5`.
- Reasoning effort levels' actual effect.
- Prompt caching support.
- Stateful conversations (`previous_response_id`).
- Built-in tools (web_search, file_search, code_interpreter).
- File / PDF input.
- Linkflow-specific quirks (custom headers, filtered fields, error code mapping).
- Logprobs accessibility.
- Batch API support.

Per existing memory (`feedback_linkflow_no_cost_optimization.md`), token cost is not a constraint during this probe. Probes should be exhaustive, not frugal.

## 3. Goals

1. Produce a **definitive capability matrix** — for every Linkflow capability the agentic redesign assumes, mark `supported`, `unsupported`, or `partial` with concrete evidence.
2. **Surface every Linkflow-specific quirk** — anywhere Linkflow's behavior differs from the OpenAI Responses API spec. Each quirk gets a documented workaround or a flag for vendor escalation.
3. **Validate the agentic redesign's blocking assumptions** — if any Tier 1 probe fails, the redesign is paused and the design is revisited.
4. **Produce a reusable probe harness** — probes are versioned, repeatable, archived per-run. Re-running the suite after model upgrades or Linkflow changes detects regressions.

## 4. Probe taxonomy

Three tiers by criticality.

| Tier | Meaning | Action on failure |
|---|---|---|
| **Tier 1 (blocking)** | Required for the redesign to be viable | Pause redesign; escalate to user; investigate workaround or vendor support |
| **Tier 2 (important)** | Shapes design choices and tradeoffs | Document; design adapts |
| **Tier 3 (informational)** | Nice-to-know optimizations or features | Document; future reference |

## 5. Tier 1 probes (blocking)

### 5.1 P1.01 — Basic Responses API connectivity

**Question:** Does the existing call shape work end-to-end against current Linkflow with `gpt-5.5`?

**Method:** Send a trivial unstructured prompt (`"Reply with the single word OK."`), receive a streamed response.

```python
client = AsyncOpenAI(api_key=os.environ["LINKFLOW_API_KEY"], base_url=LINKFLOW_BASE_URL)
async with client.responses.stream(
    model="gpt-5.5",
    input=[{"role": "user", "content": "Reply with the single word OK."}],
) as stream:
    async for event in stream:
        ...
    final = await stream.get_final_response()
```

**Capture:**
- Endpoint URL (full path including version prefix).
- Auth header pattern (Bearer? X-API-Key?).
- Response shape (`final.id`, `final.status`, `final.output`, `final.usage` fields and types).
- Streaming event types observed (`response.created`, `response.output_text.delta`, `response.completed`, etc.).
- Latency (first byte, last byte).

**Pass:** Final response has `status="completed"` and contains text "OK".

### 5.2 P1.02 — Strict JSON schema, simple

**Question:** Does Linkflow honor `response_format: {type: "json_schema", json_schema: {...}, strict: true}` correctly for a simple Pydantic-derived schema?

**Method:** Define a small Pydantic model with closed enums and required fields. Submit a prompt that should produce conforming output. Inspect output.

```python
class TestPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sentiment: Literal["positive", "negative", "neutral"]
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str

schema = TestPayload.model_json_schema()
# strictify (set additionalProperties=false on every object node, all fields required, etc.)

response = client.responses.stream(
    model="gpt-5.5",
    input=[{"role": "user", "content": "Classify the sentiment of: 'I love this.'"}],
    response_format={"type": "json_schema", "name": "test_payload", "strict": True, "schema": schema},
)
```

**Capture:** Whether output validates against `TestPayload`, exact JSON returned, any schema-related error.

**Pass:** Output is valid JSON and `TestPayload.model_validate(...)` succeeds.

### 5.3 P1.03 — Strict JSON schema, complex (claim card shape)

**Question:** Does Linkflow handle a deeply nested, $ref-using, recursively-typed schema like the claim card?

**Method:** Use a stripped-down version of the existing `SemanticClaimsPayload` schema with claims, evidence, parsed dates, etc. Confirm strict mode handles `$defs`, `oneOf`, nullable fields, and tight enum unions correctly.

**Capture:** Schema rejection errors if any. Whether `_inline_refs` and `_strictify` (existing helpers) are still required.

**Pass:** Roundtrip succeeds for at least three claim-payload examples spanning all five claim types.

### 5.4 P1.04 — Single tool call, single round

**Question:** Does Linkflow support OpenAI Responses API tool calling at all?

**Method:** Define one tool, prompt the model to use it, execute the tool locally, return the result, get final response.

```python
tools = [{
    "type": "function",
    "function": {
        "name": "get_weather",
        "description": "Get the current weather for a city.",
        "parameters": {
            "type": "object",
            "properties": {"city": {"type": "string"}},
            "required": ["city"],
            "additionalProperties": False,
        },
        "strict": True,
    },
}]

# Turn 1: model emits tool call
turn1 = await client.responses.create(
    model="gpt-5.5",
    input=[{"role": "user", "content": "What's the weather in Tokyo?"}],
    tools=tools,
)
# Inspect turn1.output for function_call items, extract call_id and args

# Turn 2: send tool result back
turn2 = await client.responses.create(
    model="gpt-5.5",
    input=[
        {"role": "user", "content": "What's the weather in Tokyo?"},
        # ... include the assistant's tool call from turn1 ...
        {"type": "function_call_output", "call_id": "...", "output": "Sunny, 22C"},
    ],
    tools=tools,
)
```

**Capture:**
- Whether `tools` parameter is accepted.
- Tool call output shape (`type`, `call_id`, `name`, `arguments`).
- Whether `function_call_output` is the correct item type for the response (or `tool_result`, or something else).
- The shape of the second-turn response (final answer).
- Whether tool call IDs round-trip correctly.

**Pass:** Final assistant text references "Tokyo" and "Sunny" or "22C" — i.e. it consumed the tool result.

### 5.5 P1.05 — Multi-turn tool loop (≥3 rounds)

**Question:** Does a multi-step agent loop (model calls tool A, gets result, calls tool B, gets result, calls tool C, returns final answer) work end-to-end?

**Method:** Define three tools (`search_filing`, `get_paragraph`, `verify_quote`). Prompt the model with a small synthetic "filing" and ask it to extract a fact. Loop:

```python
input_history = [{"role": "user", "content": "..."}]
while True:
    response = await client.responses.create(model="gpt-5.5", input=input_history, tools=tools)
    tool_calls = [item for item in response.output if item.type == "function_call"]
    if not tool_calls:
        break  # final answer
    input_history.extend(response.output)  # include tool calls in history
    for call in tool_calls:
        result = execute_tool(call.name, json.loads(call.arguments))
        input_history.append({"type": "function_call_output", "call_id": call.call_id, "output": json.dumps(result)})
```

**Capture:** Number of rounds the model uses, whether intermediate tool calls are well-formed, whether `input_history` shape is the correct way to thread state across turns, total tokens consumed across the loop.

**Pass:** Loop terminates within 10 rounds with a final assistant message that uses information from at least 2 of the 3 tools.

### 5.6 P1.06 — Tool calls combined with structured output

**Question:** Can the same call use both `tools` AND `response_format: json_schema` at the same time? This is the agentic redesign's core pattern: the verifier calls retrieval tools and emits a strict-schema verdict.

**Method:** Multi-turn loop where the model uses tools then produces a final structured-schema response.

**Capture:** Whether both parameters are accepted. Whether structured output is enforced on the final turn but not on intermediate tool-calling turns. Failure modes if any.

**Pass:** Final response is a tool-calls-zero turn with valid schema-conforming JSON output.

### 5.7 P1.07 — Reasoning effort levels

**Question:** Do `low`, `medium`, `high` reasoning effort levels behave as documented?

**Method:** Submit identical prompt at each level. Compare:
- Latency (wall-clock)
- Reasoning token count (from usage)
- Output quality (subjective, but probe records both outputs for inspection)

```python
for effort in ["low", "medium", "high"]:
    response = await client.responses.create(
        model="gpt-5.5",
        input=[{"role": "user", "content": SAME_PROMPT}],
        reasoning={"effort": effort},
    )
    record(effort, response.usage, response.output)
```

**Capture:** Per-effort latency, reasoning_tokens, output_tokens, output text. Whether the parameter is accepted at all. Whether `reasoning_tokens` is reported in usage.

**Pass:** All three values accepted; reasoning_tokens at high > medium > low (or at least monotonic).

### 5.8 P1.08 — Linkflow-specific request/response field audit

**Question:** Does Linkflow accept all OpenAI Responses API parameters? Does it return all OpenAI-shaped fields, plus or minus any Linkflow-specific ones?

**Method:** Submit a request with every documented parameter set to a non-default value, log the full request and response for inspection.

Parameters to probe:
- `model`, `input`, `instructions`, `previous_response_id`
- `tools`, `tool_choice`, `parallel_tool_calls`
- `response_format`
- `temperature`, `top_p`, `max_output_tokens`
- `reasoning` (effort, max_tokens)
- `metadata`, `user`
- `stream`, `service_tier`, `prompt_cache_key`
- `truncation`, `store`

**Capture:** Which parameters Linkflow silently ignores, which it errors on, which it forwards to the underlying OpenAI model. Response field deltas vs. OpenAI spec.

**Pass:** This is a discovery probe — there is no pass/fail, only the produced field-by-field capability map.

## 6. Tier 2 probes (important)

### 6.1 P2.01 — Parallel tool calls in a single turn

**Question:** Will Linkflow + GPT-5.5 emit multiple tool calls in one assistant turn (`parallel_tool_calls: true`)?

**Method:** Define two independent tools (`get_weather`, `get_traffic`). Prompt: "Tell me about both Tokyo's weather and Tokyo's traffic." Set `parallel_tool_calls=True`.

**Capture:** Number of tool calls in the first assistant turn. Order. Whether disabling `parallel_tool_calls` changes behavior.

**Pass:** ≥ 2 tool calls in the same turn when enabled.

### 6.2 P2.02 — Long context stress test

**Question:** What's the practical context limit through Linkflow + GPT-5.5? Where does latency become unacceptable?

**Method:** Submit progressively larger contexts: 50K, 100K, 200K, 400K tokens. Measure:
- Whether the call succeeds.
- Time-to-first-token.
- Total latency.
- Output token usage (model should still produce coherent short output even with big context).

**Capture:** Per-size success/failure, latency, error codes if any.

**Pass:** Capture a curve. No specific threshold required, but document the practical ceiling.

### 6.3 P2.03 — Streaming with tool calls

**Question:** Does the streaming API correctly stream tool call arguments as deltas, or are tool calls emitted only at completion?

**Method:** Use `client.responses.stream(...)` with tools. Log every event type and its content during a multi-step tool loop.

**Capture:** Event types observed (`response.function_call.arguments.delta`?, `response.function_call.arguments.done`?, etc.). Whether partial tool call args can be parsed mid-stream. Whether `final_response` after the stream contains all tool call data.

**Pass:** Every tool call's full arguments are recoverable from the stream's final response.

### 6.4 P2.04 — Concurrency stress

**Question:** What's the practical concurrent-request ceiling? What does 429 backoff look like at scale?

**Method:** Fire 10, 50, 100, 200 concurrent requests with `asyncio.gather`. Measure:
- Throughput (RPS sustained).
- 429 frequency.
- 5xx frequency.
- Effective concurrency before queueing degrades latency.

**Capture:** Per-batch metrics. Recommended `Semaphore` size for production.

**Pass:** Capture a curve. The current production code uses a default of 2 concurrent regions per filing; we want to know if we can go higher.

### 6.5 P2.05 — Stateful conversation via `previous_response_id`

**Question:** Does Linkflow support OpenAI Responses API state continuation? Is it stateful server-side or stateless?

**Method:**
1. Send turn 1 with `store=true`, capture `response.id`.
2. Send turn 2 with `previous_response_id=response.id` and a follow-up message.
3. Inspect whether turn 2 has access to turn 1 context implicitly.

**Capture:** Whether `previous_response_id` is accepted. Whether the model demonstrates memory of turn 1 in turn 2. Token usage savings (if any).

**Pass:** Demonstrates memory of turn 1 OR returns a clear error on the parameter.

### 6.6 P2.06 — Available models

**Question:** What models are accessible via Linkflow?

**Method:** GET `/v1/models` (if Linkflow exposes it). Try sending requests to candidate models: `gpt-5.5`, `gpt-5.5-thinking`, `gpt-5`, `gpt-5-mini`, `gpt-4o`, `gpt-4o-mini`, `o1`, `o3`, etc.

**Capture:** Per-model: accessible, context window, capability differences, latency, output quality on a fixed prompt.

**Pass:** At minimum confirm `gpt-5.5` works (already known). Record what else is available.

### 6.7 P2.07 — Tool argument schema strictness

**Question:** When a tool's `parameters` schema has tight enums and nullable fields, does the model adhere strictly, or does it sometimes drift?

**Method:** Define a tool whose `parameters` enum has an unusual member (`"member_of"`). Run 50 invocations across varied prompts. Measure adherence.

**Capture:** Adherence rate. Failure modes (wrong enum value, wrong type, missing required field).

**Pass:** ≥ 95% adherence with `strict: true` on the function definition.

### 6.8 P2.08 — Schema rejection behavior

**Question:** When the model produces an output that violates strict JSON schema, what does Linkflow return — auto-retry, raw output, error?

**Method:** Construct a prompt that should reasonably violate schema (e.g., demand the model output a value outside an enum). Force at low reasoning effort to maximize errors.

**Capture:** Whether Linkflow returns the malformed output, retries automatically, or raises an error. The exact error code/message.

**Pass:** Discovery — we want to know the failure mode, whatever it is.

### 6.9 P2.09 — Tool choice modes

**Question:** Does Linkflow honor `tool_choice` settings: `auto`, `required`, `none`, and specific function targeting?

**Method:** Run identical prompt with each `tool_choice` value. Verify model behavior:
- `auto`: model decides
- `required`: model must call at least one tool
- `none`: model may not call tools
- `{"type": "function", "function": {"name": "..."}}`: model must call this specific tool

**Capture:** Per-mode behavior. Failure modes if `required` is set when no relevant tool exists.

**Pass:** All four modes behave correctly.

### 6.10 P2.10 — Output token cap and truncation

**Question:** What happens when `max_output_tokens` is hit mid-tool-call or mid-structured-output?

**Method:** Set deliberately tight `max_output_tokens` on a request that needs more. Measure failure mode for both unstructured and structured-output cases.

**Capture:** Behavior. Whether output is malformed JSON, whether `truncation` parameter helps, whether finish_reason indicates truncation.

**Pass:** Discovery — record the behavior.

## 7. Tier 3 probes (informational)

### 7.1 P3.01 — Prompt caching

**Question:** Does Linkflow support OpenAI's prompt caching? Does cache benefit show up in usage or pricing?

**Method:** Submit identical 50K-token prefix + small varying suffix, twice. Capture `cached_tokens` field in usage.

**Capture:** Whether `cached_tokens > 0` on the second call. Latency improvement.

### 7.2 P3.02 — File / PDF input

**Question:** Can a SEC filing be uploaded as a PDF and referenced via the Files API or as input?

**Method:** Try both `client.files.create(...)` then referencing the file ID, and try inline `input_file` items.

**Capture:** Whether file API is accessible, supported file types, max size.

### 7.3 P3.03 — Built-in OpenAI tools

**Question:** Are `web_search`, `file_search`, `code_interpreter` accessible via Linkflow?

**Method:** Add each as a `tools` entry. Submit a prompt that should trigger.

**Capture:** Per-tool accessibility. Likely irrelevant for sec_graph but worth knowing.

### 7.4 P3.04 — Logprobs

**Question:** Are `logprobs` accessible? Useful for verifier confidence calibration.

**Method:** Set `logprobs: true` (or whatever the Responses API equivalent is). Inspect output.

**Capture:** Whether parameter is accepted, what's returned.

### 7.5 P3.05 — Batch API

**Question:** Does Linkflow expose OpenAI's Batch API (50% discount for async batch jobs)?

**Method:** Try `client.batches.create(...)`.

**Capture:** Whether batches endpoint works. Per-job lifecycle.

Note: cost savings is not a Phase 1 priority, but for the 800-deal corpus pass, batches could meaningfully shorten wall-clock time.

### 7.6 P3.06 — Models endpoint and metadata

**Question:** Does GET `/v1/models` work and return useful per-model metadata?

**Method:** GET that endpoint with auth.

**Capture:** Response shape, model list, per-model fields (context window, capability flags, etc.).

### 7.7 P3.07 — Error code catalog

**Question:** What error codes / messages does Linkflow return across canonical failure modes?

**Method:** Trigger:
- Bad auth (wrong API key)
- Missing required param
- Schema validation failure
- Oversized prompt (above context window)
- Rate limit (rapid-fire 100+ requests)
- Server-side timeout (force a long-running call)
- Unsupported parameter value

**Capture:** Per-error: HTTP status, OpenAI error code, OpenAI error type, Linkflow message text, headers.

### 7.8 P3.08 — Observability / audit

**Question:** Does Linkflow expose request logs, metrics, or audit endpoints accessible to the user?

**Method:** Check Linkflow documentation. Try common endpoints (`/v1/usage`, `/v1/audit`, etc.).

**Capture:** Whether such endpoints exist and what they return.

## 8. Probe runner architecture

### 8.1 File layout

```
scripts/probe_linkflow/
  __init__.py
  config.py              # base_url, default model, env var name
  harness.py             # shared fixtures: client construction, output writer, retry policy
  run_all.py             # master runner, runs probes in tier order, aggregates findings

  tier1/
    p1_01_basic_responses.py
    p1_02_strict_schema_simple.py
    p1_03_strict_schema_complex.py
    p1_04_single_tool_call.py
    p1_05_multiturn_tool_loop.py
    p1_06_tools_with_structured_output.py
    p1_07_reasoning_effort_levels.py
    p1_08_field_audit.py

  tier2/
    p2_01_parallel_tool_calls.py
    p2_02_long_context.py
    p2_03_streaming_with_tools.py
    p2_04_concurrency_stress.py
    p2_05_previous_response_id.py
    p2_06_available_models.py
    p2_07_tool_argument_strictness.py
    p2_08_schema_rejection.py
    p2_09_tool_choice_modes.py
    p2_10_max_output_tokens.py

  tier3/
    p3_01_prompt_caching.py
    p3_02_file_input.py
    p3_03_builtin_tools.py
    p3_04_logprobs.py
    p3_05_batch_api.py
    p3_06_models_endpoint.py
    p3_07_error_catalog.py
    p3_08_observability.py
```

### 8.2 Per-probe contract

Every probe is a Python file exposing an async `run(harness)` function and a probe-id constant.

```python
PROBE_ID = "p1_04"
PROBE_NAME = "single_tool_call"
PROBE_TIER = 1
PROBE_DESCRIPTION = "Does Linkflow support OpenAI Responses API tool calling at all?"

async def run(harness: ProbeHarness) -> ProbeResult:
    # ... probe logic ...
    return ProbeResult(
        probe_id=PROBE_ID,
        passed=True | False | None,  # None for discovery probes
        observations={...},
        artifacts={...},
        notes="...",
    )
```

### 8.3 Output artifact layout

Per run:

```
tmp/linkflow_probes/<probe_run_id>/
  MASTER_FINDINGS.md           # capability matrix + per-probe summaries
  capability_matrix.json       # machine-readable matrix
  run_manifest.json            # probe versions, model versions, env, timestamp
  per_probe/
    p1_01/
      request.json             # sanitized — no API key
      response.json            # raw response from Linkflow
      stream_events.jsonl      # all streaming events captured
      findings.md              # human-readable probe report
      metrics.json             # latency, tokens, etc.
    p1_02/
      ...
```

`<probe_run_id>` is `linkflow_probe_<timestamp>_<short_uuid>`.

### 8.4 Capability matrix output

`MASTER_FINDINGS.md` headlines a table:

| Capability | Tier | Status | Evidence | Notes |
|---|---|---|---|---|
| Basic Responses API | 1 | ✓ supported | p1_01 | latency 800ms |
| Strict JSON schema | 1 | ✓ supported | p1_02, p1_03 | $defs work after inlining |
| Tool calling (single turn) | 1 | ✓ supported | p1_04 | call_id roundtrip OK |
| Tool calling (multi-turn loop) | 1 | ✓ supported | p1_05 | tested 5 rounds |
| Tools + structured output | 1 | ✓ supported | p1_06 | |
| Parallel tool calls | 2 | ✗ unsupported | p2_01 | model emits sequential only |
| Long context 200K | 2 | partial | p2_02 | 200K works, 400K times out |
| Prompt caching | 3 | ? unknown | p3_01 | cached_tokens always 0 |
| ... | | | | |

`capability_matrix.json` mirrors this in machine-readable form for use as a build gate (CI can `jq` for any tier-1 status not in `["supported"]` and fail the build).

### 8.5 Reproducibility

The harness records, per run:
- Linkflow base_url
- Model + version requested
- openai SDK version
- Python version
- Probe code git SHA
- Wall-clock timestamp

Re-running probes after a Linkflow change diffs the new MASTER_FINDINGS.md against an archived prior run.

### 8.6 Master runner

`scripts/probe_linkflow/run_all.py` accepts:
- `--tier {1,2,3,all}` — defaults to `all`
- `--probe <id>` — run a single probe
- `--archive-prior <path>` — diff against a prior run
- `--bail-on-tier-1` — exit non-zero if any Tier 1 probe fails

Default behavior: run all Tier 1 first, halt on tier-1 failure unless `--continue-on-failure`. Then Tier 2. Then Tier 3.

## 9. Pass/fail policy

- **Tier 1 probe failure** → blocks the agentic redesign. Specific behavior: mark Tier 1 probe `failed` in capability matrix; emit a blocking notice in MASTER_FINDINGS.md; require user review before proceeding with implementation. Possible resolutions: workaround documented in the design spec; vendor escalation to Linkflow; rescope the design to avoid the unsupported capability.
- **Tier 2 probe failure** → design adapts. The capability matrix reflects the constraint, and the design spec is updated with a workaround note before implementation.
- **Tier 3 probe failure** → documented; no design impact unless user prioritizes the missing feature later.
- **Discovery probes (no pass/fail)** → produce findings; no gate.

## 10. Build order

Sequential, with checkpoints. Estimated calendar time: 3-4 days of focused probe work.

1. **Day 1 morning** — Harness scaffolding, `config.py`, `harness.py`, master runner skeleton, output artifact layout. Tier 1 probes P1.01 through P1.03 (basic connectivity, simple schema, complex schema). Approx 4-6 hours.
2. **Day 1 afternoon** — P1.04 (single tool call), P1.05 (multi-turn loop). These are the highest-risk Tier 1 probes; if either fails, halt and discuss with user. Approx 4 hours.
3. **Day 2 morning** — P1.06 (tools + structured output), P1.07 (reasoning effort), P1.08 (field audit). Approx 4-6 hours.
4. **Day 2 afternoon** — Tier 2 probes P2.01 through P2.05 (parallel calls, long context, streaming with tools, concurrency, conversation state). Approx 4-6 hours.
5. **Day 3 morning** — Tier 2 probes P2.06 through P2.10 (models, tool argument strictness, schema rejection, tool choice, output cap). Approx 4 hours.
6. **Day 3 afternoon** — Tier 3 probes P3.01 through P3.05 (caching, file input, builtin tools, logprobs, batch API). Approx 3-4 hours.
7. **Day 4 morning** — P3.06 through P3.08, plus capability matrix authoring, MASTER_FINDINGS.md polish. Approx 3-4 hours.

Decision gates:
- After step 2: if P1.04 or P1.05 failed, **stop**. Surface to user. The agentic redesign cannot proceed without tool calling.
- After step 3: if any Tier 1 probe failed, surface to user before proceeding to Tier 2.
- After step 7: present full capability matrix to user. Update agentic-review-compiler design spec with any constraint-driven adaptations.

## 11. Success criteria

The probe is successful if all of the following hold:

1. **Capability matrix is complete and accurate.** Every Tier 1 capability has a definitive `supported` / `unsupported` / `partial` verdict with evidence pointing to a probe artifact.
2. **All Tier 1 capabilities are supported, OR a viable workaround is documented for any unsupported one.**
3. **All Tier 2 probes have produced findings.** No probe is left as "not run" without justification.
4. **MASTER_FINDINGS.md is human-reviewable.** A reader who has not seen the probe code can understand the verdict and check the evidence.
5. **Probe scripts are persisted in `scripts/probe_linkflow/` and committed to the repository** (per existing memory `feedback_keep_probe_scripts.md` — do not delete after the run).
6. **Re-running the probe suite from clean state produces the same capability matrix** (modulo timing variance and Linkflow non-determinism). This is the regression-detection property.

## 12. Out of scope

- Exhaustive benchmarking of model quality (use Reference 9 evaluation instead).
- Cost analysis (per existing memory, cost is not a Phase 1 concern).
- Pricing or billing endpoint probes.
- SLA verification under sustained production load.
- Failover/HA testing.
- Linkflow's own admin/dashboard features.
- Comparing Linkflow against direct OpenAI access (we use Linkflow per existing constraint; comparison is moot).

## 13. Open questions

User to resolve on review:

1. **Linkflow base URL.** Where is it documented? (Probe defaults assume the existing `LLMProviderConfig.base_url` field captures this; user confirms.)
2. **Linkflow API documentation source.** Is there a public docs site, internal wiki, or vendor contact for unanswered questions?
3. **Vendor escalation path.** If a Tier 1 probe fails, who do we contact? What's the expected response time?
4. **Model variant scope.** Should P2.06 also probe forthcoming models the user expects to use (e.g. `gpt-6` if announced), or only the current production set?
5. **Concurrency probe ceiling.** P2.04 caps at 200 concurrent. Should we go higher? (Higher is better for design margin but more abusive to Linkflow's infrastructure during the probe.)
6. **Probe rerun cadence.** After model upgrades, how often should the probe suite be re-run as a regression check? Quarterly? Per major model version bump? On-demand only?

## 14. Appendix: probe template

For new probes added to the suite later, this is the canonical template.

```python
"""<probe_id>: <one-line description>"""

import asyncio
from typing import Any

from sec_graph.scripts.probe_linkflow.harness import ProbeHarness, ProbeResult

PROBE_ID = "p1_99"
PROBE_NAME = "example"
PROBE_TIER = 1
PROBE_DESCRIPTION = "What question does this probe answer?"


async def run(harness: ProbeHarness) -> ProbeResult:
    client = harness.client()

    # Setup
    request_payload = {...}

    # Execute
    try:
        async with client.responses.stream(**request_payload) as stream:
            events = []
            async for event in stream:
                events.append(harness.serialize_event(event))
                harness.append_event(PROBE_ID, event)
            final = await stream.get_final_response()
    except Exception as exc:
        return harness.failure(PROBE_ID, exception=exc, observations={...})

    # Validate
    passed = ...  # boolean per probe-specific criteria

    # Record
    harness.write_request(PROBE_ID, request_payload)
    harness.write_response(PROBE_ID, harness.serialize(final))
    harness.write_metrics(PROBE_ID, {"latency_ms": ..., "tokens": final.usage.total_tokens})

    return ProbeResult(
        probe_id=PROBE_ID,
        passed=passed,
        observations={...},
        artifacts={...},
        notes="Add probe-specific findings here.",
    )
```

The template is intentionally explicit about request/response/metric serialization — every probe leaves enough on disk that a reviewer can reconstruct what happened without re-running.
