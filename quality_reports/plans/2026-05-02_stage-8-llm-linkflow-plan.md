# Stage 8 LLM Linkflow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a provider-neutral, opt-in LLM extraction pass backed by live Linkflow GPT-5.5 tests, while preserving the default deterministic rules-only pipeline.

**Architecture:** `extract/rules` remains the default candidate producer. `extract/llm` defines provider-neutral request/response models, converts valid LLM payloads into normal `ExtractionCandidate` rows and extract-stage `SourceSpan` rows, and isolates Linkflow in one adapter. CLI flags opt into LLM mode; absent flags must produce bit-identical rules-only candidates.

**Tech Stack:** Python 3.12, DuckDB, Pydantic v2, standard-library `urllib.request` for Linkflow HTTP, pytest with live tests skipped unless `SEC_GRAPH_LIVE_LINKFLOW=1`.

---

## File Map

- Create `src/sec_graph/extract/llm/__init__.py`: public exports.
- Create `src/sec_graph/extract/llm/models.py`: provider-neutral request, response, payload, config, and exception types.
- Create `src/sec_graph/extract/llm/requests.py`: build paragraph-scoped LLM requests from DuckDB.
- Create `src/sec_graph/extract/llm/convert.py`: validate LLM payload quote offsets and insert candidates/spans.
- Create `src/sec_graph/extract/llm/prompt.py`: small prompt builder for JSON-only candidate payloads.
- Create `src/sec_graph/extract/llm/linkflow.py`: Linkflow Responses API adapter.
- Create `src/sec_graph/extract/pipeline.py`: rules-first extraction orchestration with optional LLM provider config.
- Modify `src/sec_graph/cli/extract_cmd.py`: add `--llm-provider`, `--llm-model`, `--llm-reasoning-effort`, `--llm-limit`.
- Modify `src/sec_graph/cli/run_cmd.py`: pass LLM flags through the extract stage.
- Modify `src/sec_graph/cli/__init__.py`: rebuild new LLM CLI args.
- Create `tests/test_llm_interface.py`: offline model/conversion tests.
- Create `tests/test_extract_llm_disabled.py`: rules-only determinism and CLI help tests.
- Create `tests/test_linkflow_live.py`: skipped live Linkflow GPT-5.5 tests for multiple reasoning efforts.
- Add `quality_reports/session_logs/2026-05-02_g5-stage-8-linkflow.md`: final G5 log after execution.

Generated live artifacts go only under `artifacts/linkflow/YYYY-MM-DD_stage8_live/`.

## Task 1: Provider-Neutral Models and Conversion

**Files:**
- Create: `src/sec_graph/extract/llm/__init__.py`
- Create: `src/sec_graph/extract/llm/models.py`
- Create: `src/sec_graph/extract/llm/requests.py`
- Create: `src/sec_graph/extract/llm/convert.py`
- Test: `tests/test_llm_interface.py`

- [ ] **Step 1: Write failing model/conversion tests**

Add `tests/test_llm_interface.py` with tests that:

```python
from pathlib import Path

import pytest

from sec_graph.extract.llm.convert import insert_llm_response
from sec_graph.extract.llm.models import LLMCandidatePayload, LLMContractError, LLMExtractionResponse
from sec_graph.extract.llm.requests import build_llm_requests
from sec_graph.ingest.pipeline import ingest_examples
from sec_graph.schema import connect, init_schema, validate_quote


def _conn():
    conn = connect(":memory:")
    init_schema(conn)
    ingest_examples(conn, examples_dir=Path("data/examples"))
    return conn


def test_build_llm_requests_is_paragraph_scoped_and_evidence_bound():
    conn = _conn()
    requests = build_llm_requests(conn, filing_id="petsmart-inc_filing_1", limit=1)
    request = requests[0]
    assert request.request_id == "petsmart-inc_llmrequest_1"
    assert request.parent_evidence_id
    assert request.paragraph_text
    assert request.allowed_candidate_types == ["actor_mention", "dated_event", "bid_value", "participation_count"]


def test_insert_llm_response_writes_candidates_and_extract_spans():
    conn = _conn()
    request = build_llm_requests(conn, filing_id="petsmart-inc_filing_1", limit=20)[1]
    start = request.paragraph_text.index("Industry Participant")
    response = LLMExtractionResponse(
        request_id=request.request_id,
        provider_name="offline",
        provider_model="mock",
        reasoning_effort="low",
        candidates=[
            LLMCandidatePayload(
                candidate_type="actor_mention",
                raw_value="Industry Participant",
                normalized_value="Industry Participant",
                confidence="high",
                quote_text="Industry Participant",
                quote_start=start,
                quote_end=start + len("Industry Participant"),
                dependencies=[],
            )
        ],
        raw_response_sha256="0" * 64,
        finish_status="completed",
    )
    inserted = insert_llm_response(conn, request, response, run_id="llm-offline")
    assert len(inserted) == 1
    candidate_id = inserted[0].candidate_id
    evidence_id = inserted[0].evidence_ids[0]
    row = conn.execute(
        "SELECT child.char_start, child.char_end, child.quote_hash FROM spans AS child WHERE evidence_id = ?",
        [evidence_id],
    ).fetchone()
    filing_text = Path("data/examples/petsmart-inc.md").read_text(encoding="utf-8")
    assert validate_quote(filing_text, row[0], row[1], row[2])
    assert conn.execute("SELECT count(*) FROM candidates WHERE candidate_id = ?", [candidate_id]).fetchone()[0] == 1


def test_insert_llm_response_fails_on_bad_quote_offsets():
    conn = _conn()
    request = build_llm_requests(conn, filing_id="petsmart-inc_filing_1", limit=1)[0]
    response = LLMExtractionResponse(
        request_id=request.request_id,
        provider_name="offline",
        provider_model="mock",
        reasoning_effort="low",
        candidates=[
            LLMCandidatePayload(
                candidate_type="actor_mention",
                raw_value="Bad",
                normalized_value="Bad",
                confidence="high",
                quote_text="not present",
                quote_start=0,
                quote_end=11,
                dependencies=[],
            )
        ],
        raw_response_sha256="0" * 64,
        finish_status="completed",
    )
    with pytest.raises(LLMContractError):
        insert_llm_response(conn, request, response, run_id="llm-offline")
```

- [ ] **Step 2: Run tests and verify RED**

Run:

```bash
PATH=.venv/bin:$PATH python -m pytest tests/test_llm_interface.py -q
```

Expected: collection fails because `sec_graph.extract.llm` does not exist.

- [ ] **Step 3: Implement models**

Create `src/sec_graph/extract/llm/models.py` with:

```python
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


CandidateType = Literal["actor_mention", "dated_event", "bid_value", "participation_count"]
Confidence = Literal["low", "medium", "high"]
FinishStatus = Literal["completed", "provider_rejected", "provider_incomplete", "contract_invalid"]
ReasoningEffort = Literal["low", "medium", "high", "xhigh"]


class LLMContractError(RuntimeError):
    pass


class LLMExtractionRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    request_id: str
    filing_id: str
    deal_slug: str
    paragraph_id: str
    parent_evidence_id: str
    section: str
    paragraph_text: str
    char_start: int
    char_end: int
    allowed_candidate_types: list[CandidateType] = Field(default_factory=list)
    schema_version: int
    extract_version: int


class LLMCandidatePayload(BaseModel):
    model_config = ConfigDict(frozen=True)

    candidate_type: CandidateType
    raw_value: str
    normalized_value: str
    confidence: Confidence
    quote_text: str
    quote_start: int
    quote_end: int
    dependencies: list[str]


class LLMExtractionResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    request_id: str
    provider_name: str
    provider_model: str
    reasoning_effort: ReasoningEffort
    candidates: list[LLMCandidatePayload]
    raw_response_sha256: str
    finish_status: FinishStatus


class LLMProviderConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    provider_name: Literal["linkflow"]
    model: str
    reasoning_effort: ReasoningEffort
    base_url: str = "https://www.linkflow.run/v1"
    api_key_env: str = "LINKFLOW_API_KEY"
    timeout_seconds: int = 120
```

- [ ] **Step 4: Implement request builder**

Create `src/sec_graph/extract/llm/requests.py` with `build_llm_requests(conn, filing_id, limit=None)` that selects sale-process paragraphs joined to paragraph-seed spans, orders by `paragraphs.char_start`, and returns `LLMExtractionRequest` objects with IDs from `make_id(slug, "llmrequest", sequence)`.

- [ ] **Step 5: Implement conversion**

Create `src/sec_graph/extract/llm/convert.py` with `insert_llm_response(conn, request, response, run_id)`. It must:

- hard-fail unless `response.finish_status == "completed"`;
- hard-fail on request ID mismatch;
- hard-fail if candidate type is not allowed;
- validate `quote_start`, `quote_end`, and exact `quote_text`;
- create `SourceSpan` IDs as `{slug}_llmspan_{sequence}`;
- create `ExtractionCandidate` IDs as `{slug}_llmcandidate_{sequence}`;
- insert into `spans` then `candidates`;
- return inserted `ExtractionCandidate` objects.

- [ ] **Step 6: Export public API**

Create `src/sec_graph/extract/llm/__init__.py` exporting the models, `build_llm_requests`, and `insert_llm_response`.

- [ ] **Step 7: Run tests and commit**

Run:

```bash
PATH=.venv/bin:$PATH python -m pytest tests/test_llm_interface.py -q
```

Expected: 3 passed.

Commit:

```bash
git add src/sec_graph/extract/llm tests/test_llm_interface.py
git commit -m "feat: add provider neutral llm extraction contract"
```

## Task 2: Offline Orchestration and CLI Flags

**Files:**
- Create: `src/sec_graph/extract/pipeline.py`
- Modify: `src/sec_graph/cli/extract_cmd.py`
- Modify: `src/sec_graph/cli/run_cmd.py`
- Modify: `src/sec_graph/cli/__init__.py`
- Test: `tests/test_extract_llm_disabled.py`

- [ ] **Step 1: Write disabled-mode determinism tests**

Create `tests/test_extract_llm_disabled.py` asserting:

- `run_extract(conn, filing_id)` with no LLM config matches the exact rules-only PetSmart/Saks golden hashes from `tests/fixtures/extract/real_candidate_golden.json`;
- `python -m sec_graph extract --help` exposes LLM flags;
- missing provider config never changes default `python -m sec_graph extract --all` output.

- [ ] **Step 2: Run tests and verify RED**

Run:

```bash
PATH=.venv/bin:$PATH python -m pytest tests/test_extract_llm_disabled.py -q
```

Expected: collection fails because `sec_graph.extract.pipeline` does not exist.

- [ ] **Step 3: Implement `run_extract`**

Create `src/sec_graph/extract/pipeline.py` with:

```python
from __future__ import annotations

import duckdb

from sec_graph.extract.rules import run_rules
from sec_graph.extract.llm.models import LLMProviderConfig


def run_extract(
    conn: duckdb.DuckDBPyConnection,
    filing_id: str,
    run_id: str = "extract-smoke",
    llm_config: LLMProviderConfig | None = None,
    llm_limit: int | None = None,
):
    candidates = run_rules(conn, filing_id=filing_id, run_id=run_id)
    if llm_config is None:
        return candidates
    from sec_graph.extract.llm.linkflow import run_linkflow_requests

    llm_candidates = run_linkflow_requests(conn, filing_id=filing_id, run_id=run_id, config=llm_config, limit=llm_limit)
    return [*candidates, *llm_candidates]
```

- [ ] **Step 4: Wire `extract` CLI flags**

Modify `src/sec_graph/cli/extract_cmd.py` to add `--llm-provider`, `--llm-model`, `--llm-reasoning-effort`, `--llm-limit`, build `LLMProviderConfig` only when `--llm-provider` is present, and call `run_extract`.

- [ ] **Step 5: Wire `run` CLI flags**

Modify `src/sec_graph/cli/run_cmd.py` with the same LLM flags and pass them to `run_extract` during the extract stage. Default `run --all` must still use no LLM config.

- [ ] **Step 6: Update dispatcher arg rebuilding**

Modify `src/sec_graph/cli/__init__.py` so `_argv_from_namespace` preserves `llm_provider`, `llm_model`, `llm_reasoning_effort`, and `llm_limit`.

- [ ] **Step 7: Run tests and commit**

Run:

```bash
PATH=.venv/bin:$PATH python -m pytest tests/test_extract_llm_disabled.py tests/test_extract_rules_real_examples.py tests/test_reconcile_real.py -q
```

Expected: all pass.

Commit:

```bash
git add src/sec_graph/extract/pipeline.py src/sec_graph/cli/extract_cmd.py src/sec_graph/cli/run_cmd.py src/sec_graph/cli/__init__.py tests/test_extract_llm_disabled.py
git commit -m "feat: add opt-in llm extraction flags"
```

## Task 3: Linkflow Adapter and Sanitized Artifacts

**Files:**
- Create: `src/sec_graph/extract/llm/prompt.py`
- Create: `src/sec_graph/extract/llm/linkflow.py`
- Test: `tests/test_linkflow_live.py`

- [ ] **Step 1: Write skipped live test**

Create `tests/test_linkflow_live.py`. It must skip unless both `SEC_GRAPH_LIVE_LINKFLOW=1` and `LINKFLOW_API_KEY` are set. When enabled, it should call Linkflow GPT-5.5 on one paragraph for `low` and `high` at minimum, preferably the comma-separated efforts in `SEC_GRAPH_LINKFLOW_EFFORTS` defaulting to `low,medium,high,xhigh`.

- [ ] **Step 2: Implement prompt builder**

Create `src/sec_graph/extract/llm/prompt.py` with a short system prompt requiring strict JSON with a top-level `candidates` array. The prompt must say candidates are not canonical rows and every candidate must use an exact paragraph substring.

- [ ] **Step 3: Implement Linkflow HTTP adapter**

Create `src/sec_graph/extract/llm/linkflow.py` using standard-library `urllib.request`. It must:

- read the API key from `config.api_key_env`;
- hard-fail if the key is missing;
- POST to `{config.base_url.rstrip("/")}/responses`;
- send `model`, `reasoning: {"effort": config.reasoning_effort}`, and paragraph prompt input;
- request prompt-only JSON and rely on strict local validation rather than provider-side schema enforcement;
- parse `output_text` or text content from `output[].content[]`;
- hash the raw response;
- return `LLMExtractionResponse`;
- write sanitized artifact JSON under `artifacts/linkflow/YYYY-MM-DD_stage8_live/` for live calls, excluding headers and secrets.

- [ ] **Step 4: Run offline tests**

Run:

```bash
PATH=.venv/bin:$PATH python -m pytest tests/test_linkflow_live.py -q
```

Expected without live env: skipped.

- [ ] **Step 5: Commit adapter**

Commit:

```bash
git add src/sec_graph/extract/llm/prompt.py src/sec_graph/extract/llm/linkflow.py tests/test_linkflow_live.py
git commit -m "feat: add linkflow llm adapter"
```

## Task 4: Live Linkflow Gate

**Files:**
- Modify: `quality_reports/session_logs/2026-05-02_g5-stage-8-linkflow.md`
- Generated: `artifacts/linkflow/YYYY-MM-DD_stage8_live/*.json`

- [ ] **Step 1: Load secret only into process environment**

Use `LINKFLOW_API_KEY` from the shell if present. If not present, export the provided key only in the current shell command invocation. Never print it, never write it to a tracked file, and never include it in logs.

- [ ] **Step 2: Run live test**

Run:

```bash
SEC_GRAPH_LIVE_LINKFLOW=1 SEC_GRAPH_LINKFLOW_EFFORTS=low,medium,high,xhigh PATH=.venv/bin:$PATH python -m pytest tests/test_linkflow_live.py -q
```

Expected if Linkflow supports the contract: live test passes and writes sanitized artifacts.
The live test is scoped to the shortest real PetSmart paragraph mentioning the
Buyer Group with `allowed_candidate_types=["actor_mention"]`, so it proves live
provider transport, reasoning controls, strict payload validation, exact quote
offset handling, and source-span insertion without making broad paragraph
coverage a release gate.

Expected if Linkflow rejects GPT-5.5 or a reasoning effort: test fails loudly and writes a sanitized hard-failure artifact. Do not downgrade model, provider, or effort.

- [ ] **Step 3: Run opt-in CLI smoke**

Run:

```bash
SEC_GRAPH_LIVE_LINKFLOW=1 PATH=.venv/bin:$PATH python -m sec_graph extract --all --llm-provider linkflow --llm-model gpt-5.5 --llm-reasoning-effort high --llm-limit 1
```

For the live proof run, use a temporary DB and one filing to avoid polluting the
default store:

```bash
PATH=.venv/bin:$PATH python -m sec_graph ingest --all --db tmp/stage8-cli-live.duckdb
SEC_GRAPH_LIVE_LINKFLOW=1 PATH=.venv/bin:$PATH python -m sec_graph extract --filing-id petsmart-inc_filing_1 --db tmp/stage8-cli-live.duckdb --llm-provider linkflow --llm-model gpt-5.5 --llm-reasoning-effort high --llm-limit 1
```

Expected: either succeeds with a sanitized artifact, or fails loudly with a sanitized artifact.

- [ ] **Step 4: Record G5 log**

Create `quality_reports/session_logs/2026-05-02_g5-stage-8-linkflow.md` with exact commands and outcomes. Include artifact paths and counts, never secret values.

- [ ] **Step 5: Commit live gate log and any sanitized artifacts**

Only commit sanitized artifacts if they contain no secrets and are proof-supporting. Generated raw runtime output remains under `artifacts/linkflow/`.

Commit:

```bash
git add quality_reports/session_logs/2026-05-02_g5-stage-8-linkflow.md artifacts/linkflow
git commit -m "chore: record stage 8 live linkflow proof"
```

## Task 5: Final Verification and Secret Hygiene

**Files:**
- Modify only if verification finds a defect.

- [ ] **Step 1: Run required offline verification**

Run:

```bash
PATH=.venv/bin:$PATH python -m pytest
PATH=.venv/bin:$PATH python -m pytest tests/ -x --ff
PATH=.venv/bin:$PATH python -m pytest tests/ -x --ff
PATH=.venv/bin:$PATH python scripts/fetch_filings.py --help
PATH=.venv/bin:$PATH python -m sec_graph --help
PATH=.venv/bin:$PATH python -m sec_graph ingest --all
PATH=.venv/bin:$PATH python -m sec_graph extract --all
PATH=.venv/bin:$PATH python -m sec_graph reconcile
PATH=.venv/bin:$PATH python -m sec_graph validate
PATH=.venv/bin:$PATH python -m sec_graph project
PATH=.venv/bin:$PATH python -m sec_graph run --all
```

Expected: all exit 0. Default `extract` and `run` are rules-only.

- [ ] **Step 2: Secret scan tracked files**

Run a tracked-file scan for secret-like strings without printing secret values. The report should include only path/count information.

- [ ] **Step 3: Completion audit**

Build a prompt-to-artifact checklist covering:

- G0-G4 session logs and commits;
- `docs/llm-interface.md`;
- Stage 8 plan;
- offline tests;
- live Linkflow low/high efforts at minimum;
- CLI commands;
- generated artifacts;
- git status;
- commit list.

Do not mark the long-running objective complete unless every item is covered or an explicit hard failure is recorded for unavailable Linkflow GPT-5.5/reasoning support.

## Plan Self-Review

- Spec coverage: every acceptance item in `docs/llm-interface.md` maps to Tasks 1-5.
- No fallback/backcompat: Linkflow/model/reasoning rejection is a hard failure in Task 4.
- Secret hygiene: key is runtime-only and never written; final tracked-file scan is required.
- Default determinism: Task 2 and Task 5 verify rules-only output remains unchanged when LLM mode is off.
