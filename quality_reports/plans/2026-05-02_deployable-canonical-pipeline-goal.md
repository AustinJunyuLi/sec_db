# /goal Handoff: Deployable Canonical Pipeline With Live Reference Proof

Use this document as the `/goal` objective for a long-running agent. It wraps
the implementation plan plus the live Linkflow proof sequence.

## Objective

Execute `quality_reports/plans/2026-05-02_deployable-canonical-pipeline-plan.md`
end to end, using `docs/spec.md` §1A as the binding schema contract. Then prove
the implemented pipeline with Linkflow GPT-5.5 on PetSmart first. Continue to
the nine-deal reference batch only if PetSmart is judged sound under the rubric
below. The final deliverable is a fail-loud, source-backed canonical extraction
pipeline with auditable run snapshots, validation reports, projections, and
judgment memos for all reference deals.

## Binding Authorities

- `docs/spec.md` is the binding architecture and schema authority. §1A is the
  binding deployable schema contract for this goal.
- `docs/llm-interface.md` is the binding Linkflow/LLM contract.
- `quality_reports/plans/2026-05-02_deployable-canonical-pipeline-plan.md`
  is the binding implementation plan.
- `docs/prior-pipeline-lessons.md` and `quality_reports/specs/*` are
  failure-mode context only.
- This file controls goal sequencing, live-proof gates, soundness judgment, and
  final handoff requirements.

## Non-Negotiables

- Zero fallbacks of any flavor: not for model selection, not for provider, not
  for transport, not for schema, not for payload shape.
- No backward-compatibility reader or migration path for stale contracts.
- No provider-owned source offsets. Linkflow may emit `quote_text`; Python owns
  exact substring validation and span derivation.
- No raw provider bodies, API keys, authorization headers, full paragraph text,
  or quote text in tracked Linkflow artifacts.
- No canonical facts from manifest metadata alone.
- No projection row unless canonical facts and current judgments justify it.
- No catch-all, provider-owned, fallback, or backward-compatible enum values.
- No retired row-first actor, participation-count, or legacy judgment fields in
  the deployable schema; `docs/spec.md` §1A lists the active field names.
- No PetSmart-only table and no deal-specific hardcoding.
- Do not proceed from PetSmart to the reference-nine batch if PetSmart is not
  sound.

## Reference Deals

The reference-nine batch is:

```text
imprivata
mac-gray
medivation
penford
petsmart-inc
providence-worcester
saks
stec
zep
```

All live proof must use local filing artifacts under
`data/filings/{deal_slug}/`. If any required `raw.md` or `manifest.json` is
missing, regenerate it with `scripts/fetch_filings.py`; do not import state
from outside this repository.

## Phase 1: Execute The Implementation Plan

1. Inspect the current worktree before editing:

   ```bash
   git status --short
   ```

   Preserve unrelated dirty files. Stage only files attributable to this goal.

2. Execute the tasks in
   `quality_reports/plans/2026-05-02_deployable-canonical-pipeline-plan.md`
   in the listed order. Do not skip the red tests. Do not start extraction,
   reconciliation, projection, or Linkflow work before the §1A schema tasks pass.

3. Keep commit boundaries close to the plan tasks. Each durable commit must have
   passing targeted tests for the code it introduces.

4. After the implementation plan is complete, run:

   ```bash
   python -m pytest -q
   ```

   Expected: pass. If it fails, debug and fix before requesting or using a
   Linkflow key.

5. Run the stale-contract scan from Task 15 of the implementation plan. Active
   code and binding docs must not contain stale row-first,
   downstream-model-specific, fallback-enum, or legacy-judgment contracts except
   in intentionally historical material that explicitly points to `docs/spec.md`
   §1A.

6. Confirm the run command supports fetched filings, explicit slugs, explicit
   run IDs, Linkflow flags, validation output, projection output, and immutable
   `runs/{run_id}/` snapshots. If the command surface differs from the plan,
   update the plan or session log with the exact final commands before live
   execution.

## Phase 2: Linkflow Key Handling

After Phase 1 passes offline verification, ask Austin for the Linkflow API key
or use an already-present untracked environment source. Keep the secret out of
terminal output, docs, commits, generated artifacts, and logs.

Accepted setup patterns:

```bash
export LINKFLOW_API_KEY='...'
export SEC_GRAPH_LIVE_LINKFLOW=1
```

or an untracked `.env` file that is already excluded by `.gitignore`.

Before live calls, verify only presence, not value:

```bash
python - <<'PY'
import os
for name in ("LINKFLOW_API_KEY", "SEC_GRAPH_LIVE_LINKFLOW"):
    print(f"{name}=set" if os.environ.get(name) else f"{name}=missing")
PY
```

If the key is missing, stop and ask for it. Do not run a mock provider or a
rules-only proof in place of live Linkflow validation.

## Phase 3: PetSmart Live Pilot

Run PetSmart first with Linkflow GPT-5.5 and explicit high reasoning effort.
Use a fresh run ID and a fresh run directory. Do not overwrite an existing run.

Command shape, adjusted only if Phase 1 deliberately changed the CLI:

```bash
RUN_ID="$(date -u +%Y-%m-%dT%H%M%SZ)_petsmart_linkflow_high"
python -m sec_graph run \
  --source filings \
  --slugs petsmart-inc \
  --run-id "$RUN_ID" \
  --run-dir "runs/$RUN_ID" \
  --llm-provider linkflow \
  --llm-model gpt-5.5 \
  --llm-reasoning-effort high
```

Expected operational result:

- the command exits 0;
- `runs/$RUN_ID/run_manifest.json` exists;
- `runs/$RUN_ID/canonical.duckdb` exists;
- `runs/$RUN_ID/validation_report.json` exists and has no hard
  failures;
- projection artifacts exist under the same run directory;
- sanitized Linkflow artifacts exist under `artifacts/linkflow/`;
- no tracked or generated artifact contains secrets or raw provider bodies.

## Phase 4: Judge PetSmart Soundness

Do not treat successful command exit as enough. Inspect the PetSmart run and
write:

```text
quality_reports/session_logs/2026-05-02_petsmart-live-soundness-judgment.md
```

The memo must include:

- run ID, command, model, reasoning effort, and input hashes;
- validation hard-failure status and soft ambiguity counts;
- candidate counts by type and rejected LLM payload counts;
- canonical summary for actors, actor relations, events, event-actor links,
  participation counts, judgments, and projection rows;
- source-evidence checks for Buyer Group, BC Partners, CDPQ, GIC, StepStone,
  Longview, late Longview rollover/support, acquisition vehicles, and financing;
- projection check proving count-only, financing-only, support-only, advisor,
  counsel, and vehicle-only facts did not become bidder-cycle rows without a
  current `projection_eligibility` judgment;
- explicit verdict: `SOUND`, `UNSOUND`, or `BLOCKED`.

PetSmart is sound only if all of these are true:

- every accepted LLM candidate has exact local source-span proof;
- every canonical fact used by projection has at least one valid evidence ID;
- validation has no hard failures;
- no canonical row uses stale fallback enum values or legacy judgment fields;
- unsupported projection rows are absent;
- expected PetSmart relation facts are represented generically, not through
  PetSmart-only logic;
- the ambiguity queue contains only genuine review issues, not hidden pipeline
  failures;
- generated artifacts are sanitized.

If the verdict is `UNSOUND` or `BLOCKED`, stop. Fix the pipeline if the defect is
inside implementation scope, then rerun the PetSmart pilot. Do not continue to
the reference-nine batch until a fresh PetSmart judgment memo says `SOUND`.

## Phase 5: Reference-Nine Live Batch

After PetSmart is judged `SOUND`, run the full reference-nine batch with the same
provider, model, reasoning effort, schema, and validation contract. Include
PetSmart in the batch; the pilot does not substitute for a full-batch snapshot.

Command shape, adjusted only if Phase 1 deliberately changed the CLI:

```bash
RUN_ID="$(date -u +%Y-%m-%dT%H%M%SZ)_reference9_linkflow_high"
python -m sec_graph run \
  --source filings \
  --slugs imprivata mac-gray medivation penford petsmart-inc providence-worcester saks stec zep \
  --run-id "$RUN_ID" \
  --run-dir "runs/$RUN_ID" \
  --llm-provider linkflow \
  --llm-model gpt-5.5 \
  --llm-reasoning-effort high
```

Expected operational result:

- the command exits 0;
- the run manifest lists exactly the nine slugs above;
- the run manifest includes source hashes for each `data/filings/{slug}/raw.md`;
- validation has no hard failures;
- projection artifacts are written only for projection-eligible actor-cycle
  decision units;
- the run directory is immutable and not overwritten by later attempts.

## Phase 6: Judge Reference-Nine Soundness

Write:

```text
quality_reports/session_logs/2026-05-02_reference9-live-soundness-judgment.md
```

The memo must include:

- run ID, command, model, reasoning effort, and input hashes;
- one per-deal section for all nine reference deals;
- validation hard-failure status and ambiguity counts by deal;
- candidate and canonical row counts by deal;
- projection row counts by deal;
- rejected Linkflow payload count and reason summary;
- source-evidence audit for the deal-specific cases listed below;
- final verdict for each deal and an overall verdict.

Deal-specific evidence cases:

- `petsmart-inc`: Buyer Group, BC Partners, CDPQ, GIC, StepStone, Longview, late
  Longview rollover/support, acquisition vehicles, financing.
- `saks`: Sponsor A/Sponsor E/Sponsor G joint group changes and go-shop.
- `zep`: 50 contacted, 25 confidentiality agreements, five indications,
  terminated process, later restarted process, go-shop.
- `providence-worcester`: strategic/financial contacted counts, Party D/E
  reengagement, Party F financing support, CVR then all-cash bid change.
- `mac-gray`: CSC/Pamplona structure, acquisition vehicles,
  guaranty/support/voting facts represented through `finances` or `supports`
  plus `role_detail`, non-cash option proposal from Party B.
- `stec`: multi-actor final-round invitation, WDC vs Company D divergence,
  asset-only interested parties.
- `imprivata`: advisor-driven process letters, sponsor screening, explicit no
  management participation condition.
- `penford`: historical contacts vs current sale process, support-holder facts,
  prior discussions.
- `medivation`: tender-offer/acquisition vehicle structure, unsolicited proposal
  history, no financing condition.

Overall reference-nine soundness requires:

- every deal verdict is `SOUND`;
- validation has no hard failures;
- every accepted LLM candidate has exact local source-span proof;
- no canonical row uses stale fallback enum values or legacy judgment fields;
- every projected row is justified by canonical facts and current judgments;
- count-only cohorts, advisors, counsel, vehicles without bid evidence,
  support-only holders, financing-only sources, and process milestones do not
  become bidder-cycle rows;
- all generated proof artifacts are sanitized.

If any deal is `UNSOUND` or `BLOCKED`, fail loudly. Write the defect and next
remediation step in the judgment memo, fix implementation defects that are in
scope, and rerun the affected proof. Do not mark the goal complete with an
unsound reference-nine verdict.

## Final Verification

Before declaring the goal complete, run:

```bash
python -m pytest -q
git status --short
```

Also run a secret scan over the files to be committed and generated proof
artifacts:

```bash
python - <<'PY'
from pathlib import Path
import re

patterns = {
    "bearer_token": re.compile(r"Authorization:\s*Bearer\s+[A-Za-z0-9._-]{20,}", re.I),
    "secret_key_value": re.compile(r"\b(?:sk|lf|lk)-[A-Za-z0-9_-]{20,}\b"),
}
roots = [Path("docs"), Path("quality_reports"), Path("src"), Path("tests"), Path("artifacts"), Path("runs")]
hits = []
for root in roots:
    if not root.exists():
        continue
    for path in root.rglob("*"):
        if not path.is_file() or path.suffix not in {".md", ".py", ".json", ".jsonl", ".csv", ".txt"}:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for name, pattern in patterns.items():
            if pattern.search(text):
                hits.append(f"{path}: {name}")
if hits:
    raise SystemExit("\n".join(hits))
print("secret scan passed")
PY
```

Expected final state:

- implementation plan tasks complete;
- offline tests pass;
- PetSmart live pilot judged `SOUND`;
- reference-nine live batch judged `SOUND`;
- stale row-first contracts removed from active docs, source, and tests;
- generated proof artifacts are committed only where they support the proof and
  contain no secrets or raw provider bodies;
- unrelated dirty worktree files are preserved and not swept into commits.
