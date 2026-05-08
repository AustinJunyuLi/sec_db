# Final acceptance audit — sec_review_compiler

**Story:** US-013 (Phase 12 — Final Acceptance Audit)
**Branch:** `clean-slate/agentic-review-compiler`
**Audit date:** 2026-05-08

## Authorities

- Design spec: `docs/superpowers/specs/2026-05-08-agentic-review-compiler-design.md`
- Linkflow probe spec: `docs/superpowers/specs/2026-05-08-linkflow-api-probe-spec.md`
- Binding plan: `docs/superpowers/plans/2026-05-08-agentic-review-compiler-ralph-implementation.md`
- Story list: `ralph/prd.json`

## Run identities

| Artifact                             | Identity                                      |
|--------------------------------------|-----------------------------------------------|
| Linkflow capability probe (committed)| `runs/linkflow-probe/20260508T123815Z/`       |
| Live synthetic vertical slice (latest)| `runs/live/20260508T142803Z_synthetic-demo_d1ad89b4/` |
| Live slice session log               | `quality_reports/session_logs/2026-05-08_live_vertical_slice.md` |

## Acceptance gates — exact command outputs

### `python3 -m pytest -q`

```
........................................................................ [ 29%]
........................................................................ [ 58%]
........................................................................ [ 87%]
..............................                                           [100%]
246 passed in 1.70s
```

### `python3 -m linkflow_probe summarize runs/linkflow-probe/20260508T123815Z`

```
Gate: GO
sdk_connectivity: supported - completed with text='OK'
model_and_reasoning_acceptance: supported - supported=['low', 'medium', 'high']; failures=[]
strict_structured_output_minimal: supported - validated=True; keys=['confidence', 'label', 'reason']
strict_structured_output_nested: supported - nullable:supported; nonnullable:supported
tool_call_single_round: supported
tool_call_multi_turn_loop: supported
tool_use_plus_final_structured_output: supported
error_and_retry_taxonomy: supported
bounded_concurrency: supported - max_supported=8
streaming_event_shapes: supported
```

### Source-tree stale-surface scan

```
$ git grep -n 'bids_try\|old pipeline\|previous pipeline\|disposition\.py\|docs/spec\.md' HEAD \
    -- ':!docs/superpowers/plans/2026-05-08-agentic-review-compiler-ralph-implementation.md' \
       ':!ralph/prd.json'
(empty)
```

No live authority references to forbidden prior surfaces.

### Secret scan

```
$ git grep -n 'sk-[A-Za-z0-9]\{20,\}\|Authorization: Bearer' HEAD \
    -- ':!docs/superpowers/plans/2026-05-08-agentic-review-compiler-ralph-implementation.md'
(empty)

$ git log --all --pretty=format:%H -60 | while read sha; do
    git show --format= --no-color "$sha" | grep -E 'sk-[A-Za-z0-9]{20,}' && echo "FOUND in $sha"
  done
(empty)
```

No real credential is present in the working tree or in the last 60
commits.

### File inventory check

```
$ git ls-tree -r --name-only HEAD | grep -E '\.env$|\.venv|__pycache__|\.pytest_cache|\.DS_Store|linkflow\.env'
(empty)
```

No `.env`, `.venv`, `__pycache__`, `.pytest_cache`, `.DS_Store`, or raw
provider secret file in the tracked tree.

## Story-by-story summary

| Story  | Phase | Title                                                    | Commit       |
|--------|-------|----------------------------------------------------------|--------------|
| US-001 | 0     | Freeze Linkflow GO evidence and Ralph governance         | `ee965d5`    |
| US-002 | 1     | Create package skeleton and run kernel                   | `ff536d6`    |
| US-003 | 2     | Build filing package and atlas                           | `8fa87a4`    |
| US-004 | 3     | Add retrieval index and deterministic tools              | `003287b`    |
| US-005 | 4     | Create deal-room DuckDB schema and lifecycle             | `a981a1c`    |
| US-006 | 5     | Implement Linkflow adapter and tool loop                 | `21ac9da`    |
| US-007 | 6     | Prove first offline vertical slice                       | `13e2c91`    |
| US-008 | 7     | Add deterministic canonical compiler                     | `683f848`    |
| US-009 | 8     | Add human decision import and coverage ledger            | `17cf84b`    |
| US-010 | 9     | Add full agent role surface                              | `c3881fd`    |
| US-011 | 10    | Run live synthetic Linkflow vertical slice               | `408cbd7`    |
| US-012 | 11    | Add verifier calibration seed                            | `5dd338b`    |
| US-013 | 12    | Final acceptance audit                                   | (this log)   |

Each story's `notes` field in `ralph/prd.json` records the verification
commands, files touched, evidence (test counts, fixture paths), and the
LINKFLOW_REASONING level used per role for any agent calls.

## Live slice numbers (from US-011)

```
Provider (Linkflow) calls       13
Tool dispatches                 24
Claim attempts proposed         12
Accepted attempts                4
Escalated attempts               8
Verifier verdicts: confirm       4
Verifier verdicts: ambiguous     8
Canonical rows: deal             1
Canonical rows: filing           1
Canonical rows: source_span      4
Canonical rows: event            4
Open review queue size           8
can_publish_trusted          True
```

Reasoning effort per role:

- **timeline_bid_extractor:** `low` (decisive on the synthetic fixture;
  medium exhausted the 16-turn cap by chaining redundant tool calls).
- **verifier:** `high` (adjudication-class call).

## Adapter corrections discovered during the build

1. The OpenAI Responses API uses `text={"format": <strict_schema>}` for
   structured output, not `response_format`. Fixed in `llm/tool_loop.py`
   during US-011; verified against `linkflow_probe/runner.py:225` which
   used the same idiom.
2. Multi-turn tool loops require echoing every output item
   (function_call, message, reasoning) back into `input` history before
   appending function_call_output records. Fixed in US-011; verified
   against `linkflow_probe/runner.py:396-401`.

Both fixes preserved offline tests (`tests/test_tool_loop_offline.py`
unchanged in semantics, only updated assertion key names).

## Known limitations

- The live extractor uses a single timeline_bid_extractor role; the
  party_relation, count_coverage, omission_inspector, and
  consistency_checker roles are wired structurally (schemas, prompts,
  output models, tool allowlists) but the orchestrator does not yet
  dispatch them in the synthetic slice.
- The canonical event compile derives `event_type` from
  `payload['event_type']` or the attempt's `claim_type`. Domain-specific
  validation (e.g. enforcing a closed enum of event types) is not yet
  in place.
- Calibration runs against the offline rule-based verifier in tests.
  Running the seed cards through a live Linkflow verifier is not yet
  automated; the runner accepts any Verifier so it is straightforward
  to add.
- The retrieval index does not yet expose embeddings; BM25 + literal +
  regex is sufficient for the synthetic vertical slice but the design
  spec §8 marks embeddings as optional pending probe extension.
- Concurrency is single-threaded today; `LINKFLOW_MAX_CONCURRENCY`
  is parsed and validated [1, 8] but not yet exercised by the
  orchestrator.

## Next recommended extension

Move from a single timeline-bid extractor to the full agent team in the
live path: dispatch party_relation, count_coverage, and
omission_inspector calls in parallel under
`LINKFLOW_MAX_CONCURRENCY`, then run consistency_checker over the
collected attempts. Each role already has its own strict schema, prompt,
prompt hash, and tool allowlist, so the orchestrator change is pure
wiring (no schema or doctrine work).

After that: a live verifier calibration pass — run the 12-card seed
through `LiveLinkflowVerifier` at reasoning=`high`, capture the report,
and compare match_rate against the offline baseline. That establishes
the verifier-quality baseline the design spec §11.7 calls for.

## Doctrine status

All doctrine guarantees are upheld:

- Linkflow direct SDK calls only — verified by `tests/test_linkflow_adapter.py`.
- Strict structured outputs — every role has a strict JSON schema and a
  pydantic mirror; `tests/test_agent_roles.py::TestEveryRoleHasArtifacts`
  asserts `additionalProperties=False` and required keys.
- Plain Python orchestrator — no LangChain or agent frameworks anywhere.
- No fallbacks; live mode without credentials fails before network
  (`tests/test_cli_run_synthetic.py::test_live_mode_without_key_fails_before_network`).
- Filing text is truth, Python owns evidence identity — covered by
  `tests/test_canonical_compile.py::test_payload_offsets_are_ignored_by_compiler`.
- Append-only attempts; corrections create new attempt_ids — covered by
  `tests/test_lifecycle.py::test_partial_correction_creates_new_attempt_id`.
- No latest-verdict-wins — verified by
  `tests/test_lifecycle.py::test_confirm_then_reject_aggregates_to_escalated_not_rejected`
  feeding `{confirm, reject}` in both orders and asserting both yield
  `escalated`.
- `failed_to_check` blocks publication —
  `tests/test_canonical_compile.py::test_failed_to_check_coverage_blocks_publication`.
- Credentials only from env vars — `tests/test_linkflow_adapter.py::TestPreNetworkCredentialGate`.
- Agents never write the deal-room store —
  `tests/test_agent_roles.py::TestAgentsModuleIsolation`.

## Final state

```
$ git log --oneline -3
5dd338b feat(US-012): add verifier calibration seed
408cbd7 feat(US-011): prove live synthetic vertical slice
c3881fd feat(US-010): add full agent role surface

$ git status -sb
## clean-slate/agentic-review-compiler...origin/clean-slate/agentic-review-compiler
```

The branch tracks `origin/clean-slate/agentic-review-compiler`. The
commit recording this audit will land before `RALPH-COMPLETE` is
emitted.
