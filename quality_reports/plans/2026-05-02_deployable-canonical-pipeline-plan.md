# Deployable Canonical Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn `sec_graph` into a fail-loud canonical extraction pipeline whose schema, validation, projection, run snapshots, and Linkflow proof path match `docs/spec.md` §1A.

**Architecture:** Evidence is stored first, then closed-enum canonical facts, then two-axis judgments, then deterministic projections. No extraction/reconciliation step writes fallback enum values, row-shaped bidder identities, free-form judgment categories, or projection rows without current `projection_eligibility` judgments.

**Tech Stack:** Python 3.11+, Pydantic v2, DuckDB, pytest, local EDGAR/sec2md artifacts in `data/filings/`, optional Linkflow GPT-5.5 via `docs/llm-interface.md`.

---

## Authority

Execute this plan only through the `/goal` handoff:

```text
quality_reports/plans/2026-05-02_deployable-canonical-pipeline-goal.md
```

Binding authorities:

- `docs/spec.md`, especially §1A, is the schema and architecture authority.
- `docs/llm-interface.md` is the Linkflow/LLM authority.
- This file is the implementation plan.
- `docs/prior-pipeline-lessons.md` is failure-mode context only.
- Deleted historical specs and the deleted parallel-execution plan are not
  inputs to this implementation plan.

If any older doc or fixture conflicts with `docs/spec.md` §1A, update or supersede the older artifact. Do not preserve compatibility with stale schema shapes.

## Non-Negotiables

- Closed enums only. No `unknown`, `other`, catch-all, provider-owned, fallback, or backward-compatible enum value.
- If a source fact cannot be classified into a closed enum, do not write the canonical row. Preserve it as a candidate, validation failure, or ambiguity artifact.
- No `actor_type`, `bidder_subtype`, or `is_anonymous` in deployable `actors`.
- No `actor_creation_required` in `participation_counts`.
- No free-form `judgment_type` / `judgment_value` judgment surface.
- No unconditional deletion of `data/pipeline.duckdb`.
- No overwrite of existing `runs/{run_id}/` directories.
- No projection row without current two-axis `projection_eligibility`.
- No PetSmart-only table, no deal-specific hardcoding, no provider-owned source offsets.
- No secrets, raw provider bodies, full paragraph text, or quote text in tracked Linkflow artifacts.

## File Map

Modify:

- `docs/spec.md` - keep §1A as binding schema authority.
- `docs/prior-pipeline-lessons.md` - cleanse stale `GroupMembership` and row-first language.
- `src/sec_graph/schema/models/filings.py` - add `process_scope`.
- `src/sec_graph/schema/models/canonical.py` - actor redesign, `ActorRelation`, `event_subtype`, event roles.
- `src/sec_graph/schema/models/participation_counts.py` - cohort-count model.
- `src/sec_graph/schema/models/judgments.py` - two-axis judgment model.
- `src/sec_graph/schema/models/__init__.py`, `src/sec_graph/schema/__init__.py`, `src/sec_graph/schema/schema_init.py` - exports and DDL order.
- `src/sec_graph/ingest/pipeline.py`, `src/sec_graph/cli/ingest_cmd.py`, `src/sec_graph/cli/run_cmd.py` - no unconditional wipe; fetched-filing source support; run snapshots.
- `src/sec_graph/extract/rules/*.py`, `src/sec_graph/extract/pipeline.py`, `src/sec_graph/extract/llm/*.py` - closed-enum candidate production and Linkflow conversion.
- `src/sec_graph/reconcile/*.py` - source-backed canonical construction, no constants.
- `src/sec_graph/validate/integrity.py`, `src/sec_graph/validate/flags.py` - §1A integrity checks.
- `src/sec_graph/project/bidder_rows.py`, `src/sec_graph/project/summaries.py`, `src/sec_graph/cli/project_cmd.py` - projection from current eligibility judgments only.

Create:

- `src/sec_graph/schema/models/actor_relations.py` if `canonical.py` becomes too large.
- `tests/test_schema_closed_enums.py`
- `tests/test_actor_relations_schema.py`
- `tests/test_event_subtypes_schema.py`
- `tests/test_participation_counts_schema.py`
- `tests/test_judgments_two_axis.py`
- `tests/test_run_snapshots.py`
- `tests/test_reconcile_reference_relations.py`
- `tests/test_validate_relations_and_projection.py`
- `tests/test_project_projection_preconditions.py`
- `tests/fixtures/raw_snippets/`
- `tests/fixtures/canonical/petsmart_relations.json`
- `tests/fixtures/canonical/saks_joint_groups.json`
- `tests/fixtures/canonical/zep_counts.json`
- `tests/fixtures/canonical/providence_reentry.json`
- `tests/fixtures/canonical/mac_gray_vehicle_support.json`
- `quality_reports/session_logs/2026-05-02_petsmart-live-soundness-judgment.md`
- `quality_reports/session_logs/2026-05-02_reference9-live-soundness-judgment.md`

Do not create:

- `consortium_membership`
- any PetSmart-only schema table
- any row-shaped downstream export table as canonical storage
- any compatibility reader for stale judgment or participation-count shapes

## Task 1: Freeze Authority And Stale-Doc Boundaries

**Purpose:** Make `docs/spec.md` §1A the binding target before code changes.

**Files:**

- Modify: `docs/spec.md`
- Modify: `docs/prior-pipeline-lessons.md`
- Test: `tests/test_validate_project.py`

- [ ] **Step 1: Add a stale-authority test**

  Add this test to `tests/test_validate_project.py`:

  ```python
  from pathlib import Path


  def test_deployable_goal_has_single_binding_schema_authority() -> None:
      spec = Path("docs/spec.md").read_text(encoding="utf-8")
      assert "## 1A. Deployable Canonical Schema Contract" in spec

      assert not (Path("quality_reports") / "specs").exists()
      assert not any(Path("quality_reports/plans").glob("*parallel*"))
  ```

- [ ] **Step 2: Run the stale-authority test and verify failure**

  Run:

  ```bash
  python -m pytest tests/test_validate_project.py::test_deployable_goal_has_single_binding_schema_authority -q
  ```

  Expected: failure until deleted context docs are absent and `docs/spec.md` §1A exists.

- [ ] **Step 3: Update context documents**

  In `docs/prior-pipeline-lessons.md`, replace `GroupMembership` references with `actor_relations`. Keep the file as lessons, not as migration instruction.

- [ ] **Step 4: Re-run the test**

  Run:

  ```bash
  python -m pytest tests/test_validate_project.py::test_deployable_goal_has_single_binding_schema_authority -q
  ```

  Expected: pass.

- [ ] **Step 5: Commit**

  ```bash
  git add docs/spec.md docs/prior-pipeline-lessons.md tests/test_validate_project.py
  git commit -m "docs: make deployable schema contract binding"
  ```

## Task 2: Gate Database Wipes Before Schema Migration

**Purpose:** Prevent early tasks from deleting reviewer state or proof databases.

**Files:**

- Modify: `src/sec_graph/ingest/pipeline.py`
- Modify: `src/sec_graph/cli/ingest_cmd.py`
- Modify: `src/sec_graph/cli/run_cmd.py`
- Create: `tests/test_run_snapshots.py`

- [ ] **Step 1: Write failing wipe-gate tests**

  Create `tests/test_run_snapshots.py`:

  ```python
  from pathlib import Path

  import pytest

  from sec_graph.ingest.pipeline import ingest_examples_to_db


  def test_ingest_refuses_to_delete_existing_db_without_fresh_flag(tmp_path: Path) -> None:
      db_path = tmp_path / "pipeline.duckdb"
      db_path.write_bytes(b"existing")
      with pytest.raises(FileExistsError):
          ingest_examples_to_db(db_path, fresh=False)


  def test_ingest_can_create_fresh_db_explicitly(tmp_path: Path) -> None:
      db_path = tmp_path / "pipeline.duckdb"
      db_path.write_bytes(b"existing")
      # Use an empty examples dir to stop after the explicit wipe path is exercised.
      examples_dir = tmp_path / "examples"
      examples_dir.mkdir()
      with pytest.raises(FileNotFoundError):
          ingest_examples_to_db(db_path, examples_dir=examples_dir, fresh=True)
      assert db_path.exists() is False
  ```

- [ ] **Step 2: Run the tests and verify failure**

  Run:

  ```bash
  python -m pytest tests/test_run_snapshots.py -q
  ```

  Expected: failure because `fresh` does not exist and the DB is unlinked unconditionally.

- [ ] **Step 3: Add explicit fresh behavior**

  Change the signature:

  ```python
  def ingest_examples_to_db(db_path: Path, examples_dir: Path = DEFAULT_EXAMPLES_DIR, *, fresh: bool = False) -> list[CleanFiling]:
      if db_path.exists():
          if not fresh:
              raise FileExistsError(f"{db_path} exists; pass fresh=True to replace it")
          db_path.unlink()
      db_path.parent.mkdir(parents=True, exist_ok=True)
      conn = connect(db_path)
      init_schema(conn)
      return ingest_examples(conn, examples_dir=examples_dir)
  ```

  Update CLI code to pass `fresh=True` only when the caller supplies an explicit fresh flag.

- [ ] **Step 4: Run wipe-gate tests**

  Run:

  ```bash
  python -m pytest tests/test_run_snapshots.py tests/test_ingest_examples.py -q
  ```

  Expected: pass after tests are updated for explicit fresh behavior.

- [ ] **Step 5: Commit**

  ```bash
  git add src/sec_graph/ingest/pipeline.py src/sec_graph/cli/ingest_cmd.py src/sec_graph/cli/run_cmd.py tests/test_run_snapshots.py tests/test_ingest_examples.py
  git commit -m "run: require explicit fresh database creation"
  ```

## Task 3: Replace Actor Identity With Closed Canonical Fields

**Purpose:** Remove row-shaped actor identity before relation/reconcile work.

**Files:**

- Modify: `src/sec_graph/schema/models/canonical.py`
- Modify: `src/sec_graph/schema/models/__init__.py`
- Modify: `src/sec_graph/schema/__init__.py`
- Modify: `tests/fixtures/smoke_canonical.json`
- Create: `tests/test_schema_closed_enums.py`
- Create: `tests/test_actor_relations_schema.py`

- [ ] **Step 1: Write failing actor tests**

  ```python
  import pytest
  from pydantic import ValidationError

  from sec_graph.schema import Actor


  def test_actor_identity_uses_closed_kind_and_observability() -> None:
      actor = Actor(
          actor_id="petsmart_actor_2",
          run_id="run_1",
          deal_id="petsmart_deal_1",
          actor_label="Buyer Group",
          actor_kind="group",
          observability="named",
          evidence_ids=["petsmart_evidence_1"],
          lead_arranger_label="BC Partners",
          member_count_known=5,
          has_strategic_member=False,
          has_sovereign_wealth_member=True,
      )
      assert actor.actor_kind == "group"
      assert not hasattr(actor, "actor_type")
      assert not hasattr(actor, "bidder_subtype")
      assert not hasattr(actor, "is_anonymous")


  @pytest.mark.parametrize("field,value", [("actor_kind", "unknown"), ("observability", "inferred_projection")])
  def test_actor_rejects_fallback_values(field: str, value: str) -> None:
      payload = {
          "actor_id": "petsmart_actor_2",
          "run_id": "run_1",
          "deal_id": "petsmart_deal_1",
          "actor_label": "Buyer Group",
          "actor_kind": "group",
          "observability": "named",
          "evidence_ids": ["petsmart_evidence_1"],
          "lead_arranger_label": None,
          "member_count_known": None,
          "has_strategic_member": None,
          "has_sovereign_wealth_member": None,
      }
      payload[field] = value
      with pytest.raises(ValidationError):
          Actor(**payload)
  ```

- [ ] **Step 2: Run actor tests and verify failure**

  Run:

  ```bash
  python -m pytest tests/test_actor_relations_schema.py::test_actor_identity_uses_closed_kind_and_observability tests/test_actor_relations_schema.py::test_actor_rejects_fallback_values -q
  ```

  Expected: failure because current `Actor` still uses `actor_type`, `bidder_subtype`, and `is_anonymous`.

- [ ] **Step 3: Implement `Actor`**

  Use exactly the actor fields in `docs/spec.md` §1A. Add DDL checks for closed `actor_kind` and `observability`. Add group-only nullable columns.

- [ ] **Step 4: Update smoke fixtures and inserts**

  Replace every fixture `actor_type`, `bidder_subtype`, and `is_anonymous` field with:

  ```json
  "actor_kind": "organization",
  "observability": "named",
  "lead_arranger_label": null,
  "member_count_known": null,
  "has_strategic_member": null,
  "has_sovereign_wealth_member": null
  ```

- [ ] **Step 5: Run schema tests**

  Run:

  ```bash
  python -m pytest tests/test_actor_relations_schema.py tests/test_stage1b_canonical_walkthrough.py -q
  ```

  Expected: pass.

- [ ] **Step 6: Commit**

  ```bash
  git add src/sec_graph/schema tests/fixtures/smoke_canonical.json tests/test_actor_relations_schema.py tests/test_schema_closed_enums.py tests/test_stage1b_canonical_walkthrough.py
  git commit -m "schema: replace row-shaped actor identity"
  ```

## Task 4: Add Generic Actor Relations With Cycle Frames

**Purpose:** Represent memberships, vehicles, advisors, financing, support, and rollover facts without deal-specific tables.

**Files:**

- Modify: `src/sec_graph/schema/models/canonical.py` or create `src/sec_graph/schema/models/actor_relations.py`
- Modify: `src/sec_graph/schema/models/__init__.py`
- Modify: `src/sec_graph/schema/__init__.py`
- Modify: `src/sec_graph/schema/schema_init.py`
- Modify: `tests/fixtures/smoke_canonical.json`
- Create/modify: `tests/test_actor_relations_schema.py`

- [ ] **Step 1: Write failing relation tests**

  ```python
  import datetime as dt
  import pytest
  from pydantic import ValidationError

  from sec_graph.schema import ActorRelation


  def test_actor_relation_has_cycle_and_date_frames() -> None:
      relation = ActorRelation(
          relation_id="petsmart_relation_1",
          run_id="run_1",
          deal_id="petsmart_deal_1",
          subject_actor_id="petsmart_actor_longview",
          object_actor_id="petsmart_actor_buyer_group",
          relation_type="member_of",
          role_detail="joined buyer group after final bid process authorization",
          cycle_id_first_observed="petsmart_cycle_2",
          cycle_id_last_observed=None,
          effective_date_first=dt.date(2014, 12, 12),
          effective_date_last=None,
          confidence="high",
          evidence_ids=["petsmart_evidence_1"],
      )
      assert relation.relation_type == "member_of"
      assert relation.cycle_id_first_observed == "petsmart_cycle_2"


  @pytest.mark.parametrize("relation_type", ["unknown", "guarantees", "voting_support_for"])
  def test_actor_relation_rejects_non_spec_relation_values(relation_type: str) -> None:
      with pytest.raises(ValidationError):
          ActorRelation(
              relation_id="petsmart_relation_1",
              run_id="run_1",
              deal_id="petsmart_deal_1",
              subject_actor_id="petsmart_actor_longview",
              object_actor_id="petsmart_actor_buyer_group",
              relation_type=relation_type,
              role_detail=None,
              cycle_id_first_observed="petsmart_cycle_2",
              cycle_id_last_observed=None,
              effective_date_first=None,
              effective_date_last=None,
              confidence=None,
              evidence_ids=["petsmart_evidence_1"],
          )
  ```

- [ ] **Step 2: Run relation tests and verify failure**

  Run:

  ```bash
  python -m pytest tests/test_actor_relations_schema.py -q
  ```

  Expected: failure because `ActorRelation` and cycle-frame fields do not exist.

- [ ] **Step 3: Implement `ActorRelation`**

  Implement exactly the relation fields and enum in `docs/spec.md` §1A. DDL must include FKs to `deals`, `actors`, and nullable cycle references, plus:

  ```sql
  CHECK (cycle_id_first_observed IS NOT NULL OR effective_date_first IS NOT NULL),
  CHECK (effective_date_last IS NULL OR effective_date_first IS NULL OR effective_date_last >= effective_date_first)
  ```

- [ ] **Step 4: Add smoke relation fixture**

  Add a fixture relation with `relation_type="member_of"`, one `cycle_id_first_observed`, and evidence IDs.

- [ ] **Step 5: Run schema walkthrough tests**

  Run:

  ```bash
  python -m pytest tests/test_actor_relations_schema.py tests/test_stage1b_canonical_walkthrough.py -q
  ```

  Expected: pass.

- [ ] **Step 6: Commit**

  ```bash
  git add src/sec_graph/schema tests/fixtures/smoke_canonical.json tests/test_actor_relations_schema.py tests/test_stage1b_canonical_walkthrough.py
  git commit -m "schema: add cycle-framed actor relations"
  ```

## Task 5: Add Event Subtypes And Closed Event Roles

**Purpose:** Put event verbs on events and actor roles on event links.

**Files:**

- Modify: `src/sec_graph/schema/models/canonical.py`
- Modify: `tests/fixtures/smoke_canonical.json`
- Create: `tests/test_event_subtypes_schema.py`

- [ ] **Step 1: Write failing event tests**

  ```python
  import pytest
  from pydantic import ValidationError

  from sec_graph.schema import Event, EventActorLink


  def test_event_subtype_stores_event_verb() -> None:
      event = Event(
          event_id="stec_event_1",
          run_id="run_1",
          deal_id="stec_deal_1",
          cycle_id="stec_cycle_1",
          event_type="process",
          event_subtype="excluded_by_target",
          event_date=None,
          description="special committee did not invite asset-only parties to continue",
          bid_value=None,
          bid_value_lower=None,
          bid_value_upper=None,
          bid_value_unit=None,
          consideration_type=None,
          evidence_ids=["stec_evidence_1"],
      )
      assert event.event_subtype == "excluded_by_target"


  @pytest.mark.parametrize("value", ["other", "unknown", "withdrew"])
  def test_event_subtype_rejects_fallback_or_role_values(value: str) -> None:
      with pytest.raises(ValidationError):
          Event(
              event_id="stec_event_1",
              run_id="run_1",
              deal_id="stec_deal_1",
              cycle_id="stec_cycle_1",
              event_type="process",
              event_subtype=value,
              event_date=None,
              description="bad subtype",
              bid_value=None,
              bid_value_lower=None,
              bid_value_upper=None,
              bid_value_unit=None,
              consideration_type=None,
              evidence_ids=["stec_evidence_1"],
          )


  def test_event_actor_link_role_is_not_event_verb() -> None:
      link = EventActorLink(
          link_id="petsmart_link_1",
          run_id="run_1",
          event_id="petsmart_event_1",
          actor_id="petsmart_actor_longview",
          role="rollover_holder",
          role_detail="Longview agreed to roll over shares",
          evidence_ids=["petsmart_evidence_1"],
      )
      assert link.role == "rollover_holder"
  ```

- [ ] **Step 2: Run event tests and verify failure**

  Run:

  ```bash
  python -m pytest tests/test_event_subtypes_schema.py -q
  ```

  Expected: failure because `event_subtype` and closed roles are absent.

- [ ] **Step 3: Implement event and link fields**

  Add `event_subtype` with the exact enum in `docs/spec.md` §1A. Replace link role enum with the exact closed enum and add `role_detail: str | None`.

- [ ] **Step 4: Update SQL and fixtures**

  Update DDL and every event/event-link insert to include `event_subtype` and `role_detail`.

- [ ] **Step 5: Run tests**

  Run:

  ```bash
  python -m pytest tests/test_event_subtypes_schema.py tests/test_stage1b_canonical_walkthrough.py -q
  ```

  Expected: pass.

- [ ] **Step 6: Commit**

  ```bash
  git add src/sec_graph/schema tests/fixtures/smoke_canonical.json tests/test_event_subtypes_schema.py tests/test_stage1b_canonical_walkthrough.py
  git commit -m "schema: add event subtypes and closed event roles"
  ```

## Task 6: Add Filing Process Scope

**Purpose:** Make partial source coverage explicit for Schedule TO and amendment filings.

**Files:**

- Modify: `src/sec_graph/schema/models/filings.py`
- Modify: `src/sec_graph/ingest/pipeline.py`
- Modify: `src/sec_graph/cli/ingest_cmd.py`
- Modify: `tests/test_ingest_examples.py`
- Create: `tests/test_schema_closed_enums.py`

- [ ] **Step 1: Write failing filing-scope tests**

  ```python
  import pytest
  from pydantic import ValidationError

  from sec_graph.schema import CleanFiling


  def test_clean_filing_has_process_scope() -> None:
      filing = CleanFiling(
          filing_id="medivation_filing_1",
          deal_slug="medivation",
          source_path="data/filings/medivation/raw.md",
          raw_sha256="a" * 64,
          parser_version=1,
          page_count=10,
          section_count=3,
          process_scope="bidder_partial_schedule_to",
      )
      assert filing.process_scope == "bidder_partial_schedule_to"


  def test_clean_filing_rejects_unknown_scope() -> None:
      with pytest.raises(ValidationError):
          CleanFiling(
              filing_id="bad_filing_1",
              deal_slug="bad",
              source_path=None,
              raw_sha256="a" * 64,
              parser_version=1,
              page_count=None,
              section_count=None,
              process_scope="unknown",
          )
  ```

- [ ] **Step 2: Run filing-scope tests and verify failure**

  Run:

  ```bash
  python -m pytest tests/test_schema_closed_enums.py::test_clean_filing_has_process_scope tests/test_schema_closed_enums.py::test_clean_filing_rejects_unknown_scope -q
  ```

  Expected: failure because `process_scope` is absent.

- [ ] **Step 3: Implement `process_scope`**

  Add the exact enum in `docs/spec.md` §1A. Default examples to `target_full_proxy`. For fetched filings, derive scope from manifest form type:

  ```text
  DEFM14A/PREM14A -> target_full_proxy
  SC TO-T/SC TO-T/A -> bidder_partial_schedule_to
  DEFA14A or amendment-only source -> amendment_only
  go-shop-only supplement -> go_shop_only
  ```

  If the form type cannot be mapped, fail ingestion; do not write `unknown`.

- [ ] **Step 4: Run ingest tests**

  Run:

  ```bash
  python -m pytest tests/test_schema_closed_enums.py tests/test_ingest_examples.py tests/test_edgar.py -q
  ```

  Expected: pass.

- [ ] **Step 5: Commit**

  ```bash
  git add src/sec_graph/schema/models/filings.py src/sec_graph/ingest/pipeline.py src/sec_graph/cli/ingest_cmd.py tests/test_schema_closed_enums.py tests/test_ingest_examples.py
  git commit -m "schema: require filing process scope"
  ```

## Task 7: Replace Participation Counts With Closed Cohort Observations

**Purpose:** Preserve aggregate sale-process facts without creating actors.

**Files:**

- Modify: `src/sec_graph/schema/models/participation_counts.py`
- Modify: `src/sec_graph/schema/schema_init.py`
- Modify: `tests/fixtures/smoke_canonical.json`
- Create: `tests/test_participation_counts_schema.py`

- [ ] **Step 1: Write failing count tests**

  ```python
  import pytest
  from pydantic import ValidationError

  from sec_graph.schema import ParticipationCount


  def test_participation_count_is_closed_cohort_observation() -> None:
      count = ParticipationCount(
          participation_count_id="zep_count_1",
          run_id="run_1",
          deal_id="zep_deal_1",
          cycle_id="zep_cycle_1",
          event_id=None,
          process_stage="nda_signed",
          actor_class="financial",
          count_min=25,
          count_max=25,
          count_qualifier="exact",
          named_subset_actor_ids=["zep_actor_party_x"],
          anonymous_remainder_count=24,
          evidence_ids=["zep_evidence_1"],
      )
      assert count.anonymous_remainder_count == 24
      assert not hasattr(count, "actor_creation_required")


  @pytest.mark.parametrize("field,value", [("process_stage", "unknown"), ("actor_class", "potential_buyer"), ("actor_class", "shareholder")])
  def test_participation_count_rejects_fallback_or_role_values(field: str, value: str) -> None:
      payload = {
          "participation_count_id": "zep_count_1",
          "run_id": "run_1",
          "deal_id": "zep_deal_1",
          "cycle_id": "zep_cycle_1",
          "event_id": None,
          "process_stage": "nda_signed",
          "actor_class": "financial",
          "count_min": 25,
          "count_max": 25,
          "count_qualifier": "exact",
          "named_subset_actor_ids": [],
          "anonymous_remainder_count": 25,
          "evidence_ids": ["zep_evidence_1"],
      }
      payload[field] = value
      with pytest.raises(ValidationError):
          ParticipationCount(**payload)
  ```

- [ ] **Step 2: Run count tests and verify failure**

  Run:

  ```bash
  python -m pytest tests/test_participation_counts_schema.py -q
  ```

  Expected: failure because old `actor_creation_required` model is still present.

- [ ] **Step 3: Implement the model**

  Use exactly the `participation_counts` model in `docs/spec.md` §1A. DDL checks:

  ```sql
  CHECK (count_min >= 0),
  CHECK (count_max IS NULL OR count_max >= count_min),
  CHECK (anonymous_remainder_count >= 0)
  ```

- [ ] **Step 4: Update fixtures**

  Replace all `count_type`, `count_unit`, `bidder_subtype_split`, and `actor_creation_required` fields with the new model.

- [ ] **Step 5: Run count and walkthrough tests**

  Run:

  ```bash
  python -m pytest tests/test_participation_counts_schema.py tests/test_stage1b_canonical_walkthrough.py -q
  ```

  Expected: pass.

- [ ] **Step 6: Commit**

  ```bash
  git add src/sec_graph/schema tests/fixtures/smoke_canonical.json tests/test_participation_counts_schema.py tests/test_stage1b_canonical_walkthrough.py
  git commit -m "schema: model participation counts as closed cohorts"
  ```

## Task 8: Replace Judgments With Two-Axis Model

**Purpose:** Eliminate the free-form judgment dumping ground before projection/reconcile work.

**Files:**

- Modify: `src/sec_graph/schema/models/judgments.py`
- Modify: `src/sec_graph/schema/schema_init.py`
- Modify: `tests/fixtures/smoke_canonical.json`
- Create: `tests/test_judgments_two_axis.py`

- [ ] **Step 1: Write failing judgment tests**

  ```python
  import pytest
  from pydantic import ValidationError

  from sec_graph.schema import Judgment, latest_judgments


  def test_projection_eligibility_judgment_shape() -> None:
      judgment = Judgment(
          judgment_id="petsmart_judgment_1",
          run_id="run_1",
          judgment_kind="projection_eligibility",
          target_table=None,
          target_id=None,
          target_column=None,
          prior_value=None,
          new_value=None,
          projection_name="bidder_cycle_baseline_v1",
          actor_id="petsmart_actor_buyer_group",
          included=True,
          rule_id="bidder_cycle_baseline_v1.consortium_collapse",
          evidence_ids=["petsmart_evidence_1"],
          supersedes_judgment_id=None,
          created_at="2026-05-02T00:00:00+00:00",
          created_by="test",
      )
      assert judgment.judgment_kind == "projection_eligibility"
      assert not hasattr(judgment, "judgment_type")
      assert not hasattr(judgment, "judgment_value")


  def test_judgment_rejects_legacy_type_value_shape() -> None:
      with pytest.raises(ValidationError):
          Judgment(
              judgment_id="bad_judgment_1",
              run_id="run_1",
              judgment_type="formal_boundary",
              judgment_value="event_1",
              confidence="high",
              evidence_ids=["evidence_1"],
          )


  def test_latest_judgments_uses_supersession_chain() -> None:
      old = Judgment(
          judgment_id="judgment_1",
          run_id="run_1",
          judgment_kind="projection_eligibility",
          target_table=None,
          target_id=None,
          target_column=None,
          prior_value=None,
          new_value=None,
          projection_name="bidder_cycle_baseline_v1",
          actor_id="actor_1",
          included=False,
          rule_id="bidder_cycle_baseline_v1.admission",
          evidence_ids=["evidence_1"],
          supersedes_judgment_id=None,
          created_at="2026-05-02T00:00:00+00:00",
          created_by="test",
      )
      new = old.model_copy(update={"judgment_id": "judgment_2", "included": True, "supersedes_judgment_id": "judgment_1"})
      assert latest_judgments([old, new]) == [new]
  ```

- [ ] **Step 2: Run judgment tests and verify failure**

  Run:

  ```bash
  python -m pytest tests/test_judgments_two_axis.py -q
  ```

  Expected: failure because old `judgment_type` / `judgment_value` shape is still present.

- [ ] **Step 3: Implement two-axis `Judgment`**

  Use exactly the fields in `docs/spec.md` §1A. Configure the model to forbid extra fields. Add validators:

  ```text
  fact_correction requires target_table, target_id, target_column, prior_value, new_value.
  projection_eligibility requires projection_name, actor_id, included, rule_id.
  The two axes must not populate each other's required fields.
  ```

- [ ] **Step 4: Update fixtures**

  Replace boundary/admission/dropout judgment fixture rows with either canonical facts or `projection_eligibility` judgments using one of the initial `bidder_cycle_baseline_v1.*` rule IDs.

- [ ] **Step 5: Run judgment and walkthrough tests**

  Run:

  ```bash
  python -m pytest tests/test_judgments_two_axis.py tests/test_stage1b_canonical_walkthrough.py -q
  ```

  Expected: pass.

- [ ] **Step 6: Commit**

  ```bash
  git add src/sec_graph/schema tests/fixtures/smoke_canonical.json tests/test_judgments_two_axis.py tests/test_stage1b_canonical_walkthrough.py
  git commit -m "schema: replace freeform judgments with two-axis judgments"
  ```

## Task 9: Strengthen Evidence Integrity And Closed-Enum Validation

**Purpose:** Make invalid canonical states fail before export.

**Files:**

- Modify: `src/sec_graph/validate/integrity.py`
- Modify: `src/sec_graph/validate/flags.py`
- Modify: `tests/test_validate_project.py`
- Create: `tests/test_validate_relations_and_projection.py`

- [ ] **Step 1: Write failing validation tests**

  ```python
  def test_validation_rejects_relation_without_cycle_or_date(conn_with_relation_without_temporal_marker) -> None:
      report = validate_database(conn_with_relation_without_temporal_marker)
      assert any(failure.detail == "actor relation lacks cycle/date first-observed marker" for failure in report.hard_failures)


  def test_validation_rejects_group_event_member_without_active_relation(conn_with_invalid_group_event) -> None:
      report = validate_database(conn_with_invalid_group_event)
      assert any("group event member lacks active member_of relation" in failure.detail for failure in report.hard_failures)


  def test_validation_rejects_projection_actor_without_current_eligibility(conn_with_missing_projection_eligibility) -> None:
      report = validate_database(conn_with_missing_projection_eligibility)
      assert any("missing current projection_eligibility" in failure.detail for failure in report.hard_failures)


  def test_validation_rejects_non_target_full_proxy_for_baseline_projection(conn_with_bidder_partial_scope_projection) -> None:
      report = validate_database(conn_with_bidder_partial_scope_projection)
      assert any("process_scope" in failure.detail for failure in report.hard_failures)
  ```

- [ ] **Step 2: Run validation tests and verify failure**

  Run:

  ```bash
  python -m pytest tests/test_validate_relations_and_projection.py -q
  ```

  Expected: failure because new checks are absent.

- [ ] **Step 3: Add FK and evidence checks**

  Extend validation for:

  ```text
  actor_relations.subject_actor_id -> actors.actor_id
  actor_relations.object_actor_id -> actors.actor_id
  actor_relations.cycle_id_first_observed -> process_cycles.cycle_id when non-null
  actor_relations.cycle_id_last_observed -> process_cycles.cycle_id when non-null
  participation_counts.named_subset_actor_ids[*] -> actors.actor_id
  judgments.actor_id -> actors.actor_id for projection_eligibility
  judgments.supersedes_judgment_id -> judgments.judgment_id
  ```

- [ ] **Step 4: Add structural checks**

  Enforce:

  ```text
  actor_relations has cycle_id_first_observed or effective_date_first.
  event_actor_links for group bid-stage events respect active member_of relations.
  projection_eligibility judgments populate only the projection axis.
  fact_correction judgments populate only the correction axis.
  count-only actors and unsupported source scopes cannot enter bidder_cycle_baseline_v1.
  ```

- [ ] **Step 5: Run validation tests**

  Run:

  ```bash
  python -m pytest tests/test_validate_relations_and_projection.py tests/test_validate_project.py -q
  ```

  Expected: pass.

- [ ] **Step 6: Commit**

  ```bash
  git add src/sec_graph/validate tests/test_validate_relations_and_projection.py tests/test_validate_project.py
  git commit -m "validate: enforce deployable canonical integrity"
  ```

## Task 10: Expand Extraction Candidates Without Writing Fallback Facts

**Purpose:** Produce source-backed candidates for actors, relations, event subtypes, counts, and projection eligibility without canonical writes by the model.

**Files:**

- Modify: `src/sec_graph/schema/models/extraction.py`
- Modify: `src/sec_graph/extract/rules/actors.py`
- Modify: `src/sec_graph/extract/rules/counts.py`
- Modify: `src/sec_graph/extract/rules/events.py`
- Modify: `src/sec_graph/extract/rules/bids.py`
- Modify: `src/sec_graph/extract/pipeline.py`
- Modify: `src/sec_graph/extract/llm/models.py`
- Modify: `src/sec_graph/extract/llm/convert.py`
- Modify: `src/sec_graph/extract/llm/prompt.py`
- Create: `tests/fixtures/raw_snippets/`
- Create: `tests/test_extract_reference_snippets.py`

- [ ] **Step 1: Write failing reference-snippet tests**

  Add short exact snippets from `data/filings/{slug}/raw.md` under `tests/fixtures/raw_snippets/`. Keep them small so tests are fast; each copied snippet must include its source path and approximate line in a comment.

  Add tests asserting:

  ```text
  PetSmart Buyer Group candidates include group actor and member_of relation signals.
  Zep count prose emits participation_count candidate, not actor candidates for anonymous parties.
  STEC asset-only exclusion emits excluded_by_target event_subtype candidate.
  Saks joint-group changes emit relation-window candidates with cycle markers when dates are absent.
  Mac-Gray support/voting facts map to supports relation candidates, not voting_support_for enum values.
  ```

- [ ] **Step 2: Run snippet tests and verify failure**

  Run:

  ```bash
  python -m pytest tests/test_extract_reference_snippets.py -q
  ```

  Expected: failure until candidate extraction supports these shapes.

- [ ] **Step 3: Update candidate contract**

  Candidate payloads may name only spec values. Reject payloads containing `unknown`, `other`, `guarantees`, `voting_support_for`, `judgment_type`, `judgment_value`, `actor_type`, `bidder_subtype`, `is_anonymous`, or `actor_creation_required`.

- [ ] **Step 4: Update rules and LLM conversion**

  Convert rules/LLM outputs into candidate shapes that can reconcile into:

  ```text
  actor_kind / observability
  relation_type plus cycle/date frame hints
  event_type / event_subtype
  event_actor_links.role
  participation_counts.process_stage / actor_class / counts
  projection_eligibility rule hints
  ```

  Linkflow remains paragraph-scoped and quote-text only. Python derives spans.

- [ ] **Step 5: Run extraction tests**

  Run:

  ```bash
  python -m pytest tests/test_extract_reference_snippets.py tests/test_extract_rules_smoke.py tests/test_extract_rules_real_examples.py tests/test_llm_interface.py -q
  ```

  Expected: pass.

- [ ] **Step 6: Commit**

  ```bash
  git add src/sec_graph/extract src/sec_graph/schema/models/extraction.py tests/fixtures/raw_snippets tests/test_extract_reference_snippets.py tests/test_extract_rules_smoke.py tests/test_extract_rules_real_examples.py tests/test_llm_interface.py
  git commit -m "extract: emit closed canonical candidates"
  ```

## Task 11: Reconcile Canonical Facts Against §1A

**Purpose:** Build canonical rows from candidates without deal-specific constants or legacy judgment categories.

**Files:**

- Modify: `src/sec_graph/reconcile/aliases.py`
- Modify: `src/sec_graph/reconcile/boundaries.py`
- Modify: `src/sec_graph/reconcile/cycles.py`
- Modify: `src/sec_graph/reconcile/pipeline.py`
- Create: `tests/test_reconcile_reference_relations.py`
- Create: `tests/fixtures/canonical/petsmart_relations.json`
- Create: `tests/fixtures/canonical/saks_joint_groups.json`
- Create: `tests/fixtures/canonical/zep_counts.json`
- Create: `tests/fixtures/canonical/providence_reentry.json`
- Create: `tests/fixtures/canonical/mac_gray_vehicle_support.json`

- [ ] **Step 1: Write failing reconcile tests**

  Tests must assert:

  ```text
  PetSmart Buyer Group has member_of relation rows; Longview has date/cycle marker.
  Saks Sponsor A/E/G changes use relation windows, not joint-string actors.
  Zep count facts create participation_counts and no anonymous bidder actors.
  Providence Party D/E reengagement and Party F financing support are separate facts.
  Mac-Gray voting/support facts use supports relation with role_detail.
  ```

- [ ] **Step 2: Run reconcile tests and verify failure**

  Run:

  ```bash
  python -m pytest tests/test_reconcile_reference_relations.py -q
  ```

  Expected: failure until reconcile writes the new canonical shape.

- [ ] **Step 3: Remove constants instead of migrating them**

  Delete hardcoded target/subtype maps and deal-specific alias constants. Build only from source-backed candidates and evidence. If a candidate cannot classify actor kind, relation type, event subtype, source scope, or projection rule, do not write the canonical row.

- [ ] **Step 4: Construct canonical facts**

  Reconcile into:

  ```text
  actors with actor_kind/observability/group-only fields
  actor_relations with relation_type, role_detail, cycle/date frames
  events with event_subtype
  event_actor_links with closed roles
  participation_counts with closed process_stage and actor_class
  judgments with judgment_kind="projection_eligibility" or "fact_correction"
  ```

- [ ] **Step 5: Construct projection-eligibility judgments**

  For `bidder_cycle_baseline_v1`, write current `projection_eligibility` judgments for candidate projection actors using the initial rule IDs in `docs/spec.md` §1A. Do not write `formal_boundary`, `admission`, or `dropout_mechanism` as judgment types.

- [ ] **Step 6: Run reconcile tests**

  Run:

  ```bash
  python -m pytest tests/test_reconcile_reference_relations.py tests/test_reconcile_real.py -q
  ```

  Expected: pass after old golden expectations are updated away from row collapse.

- [ ] **Step 7: Commit**

  ```bash
  git add src/sec_graph/reconcile tests/test_reconcile_reference_relations.py tests/test_reconcile_real.py tests/fixtures/canonical
  git commit -m "reconcile: build deployable canonical facts"
  ```

## Task 12: Make Projection Judgment-Only And Deterministic

**Purpose:** Prevent projection from inventing eligibility, admission, atomization, or actor rows.

**Files:**

- Modify: `src/sec_graph/project/bidder_rows.py`
- Modify: `src/sec_graph/project/summaries.py`
- Modify: `src/sec_graph/cli/project_cmd.py`
- Create: `tests/test_project_projection_preconditions.py`

- [ ] **Step 1: Write failing projection tests**

  ```python
  def test_projection_uses_latest_projection_eligibility_judgment(conn_with_superseded_judgments) -> None:
      rows = bidder_rows(conn_with_superseded_judgments, projection_name="bidder_cycle_baseline_v1")
      assert [row["actor_id"] for row in rows] == ["petsmart_actor_buyer_group"]


  def test_projection_does_not_emit_without_current_eligibility(conn_with_missing_projection_eligibility) -> None:
      rows = bidder_rows(conn_with_missing_projection_eligibility, projection_name="bidder_cycle_baseline_v1")
      assert rows == []


  def test_projection_rejects_count_only_actor(conn_with_count_only_actor) -> None:
      rows = bidder_rows(conn_with_count_only_actor, projection_name="bidder_cycle_baseline_v1")
      assert rows == []
  ```

- [ ] **Step 2: Run projection tests and verify failure**

  Run:

  ```bash
  python -m pytest tests/test_project_projection_preconditions.py -q
  ```

  Expected: failure because current projection uses legacy judgment shape and implicit admission.

- [ ] **Step 3: Rewrite judgment selection**

  Use `latest_judgments` over two-axis `Judgment` rows. Projection must select:

  ```sql
  judgment_kind = 'projection_eligibility'
  projection_name = ?
  included = true
  ```

  Scope rule details through `rule_id`, not `judgment_type`.

- [ ] **Step 4: Remove legacy projection assumptions**

  Remove:

  ```text
  actors.actor_type = 'bidder'
  actors.bidder_subtype
  judgment_type / judgment_value queries
  implicit admitted = bF exists
  JOIN filings ON filings.deal_slug = deals.deal_slug
  ```

  Replace the cycle query with:

  ```sql
  SELECT process_cycles.cycle_id, process_cycles.deal_id, deals.deal_slug
  FROM process_cycles
  JOIN deals USING (deal_id)
  ORDER BY process_cycles.cycle_id
  ```

- [ ] **Step 5: Require projection name**

  CLI must require:

  ```bash
  python -m sec_graph project --projection bidder_cycle_baseline_v1
  ```

  No default if multiple projections exist.

- [ ] **Step 6: Run projection tests**

  Run:

  ```bash
  python -m pytest tests/test_project_projection_preconditions.py tests/test_reconcile_real.py -q
  ```

  Expected: pass.

- [ ] **Step 7: Commit**

  ```bash
  git add src/sec_graph/project src/sec_graph/cli/project_cmd.py tests/test_project_projection_preconditions.py tests/test_reconcile_real.py
  git commit -m "project: require current eligibility judgments"
  ```

## Task 13: Implement Immutable Run Snapshots

**Purpose:** Make proof artifacts reproducible and fail-loud.

**Files:**

- Modify: `src/sec_graph/cli/run_cmd.py`
- Modify: `src/sec_graph/cli/validate_cmd.py`
- Modify: `src/sec_graph/cli/project_cmd.py`
- Modify: `src/sec_graph/schema/models/runtime.py`
- Modify: `tests/test_run_snapshots.py`

- [ ] **Step 1: Write failing snapshot test**

  ```python
  from pathlib import Path

  import pytest

  from sec_graph.cli.run_cmd import run_pipeline


  def test_run_pipeline_writes_immutable_snapshot(tmp_path: Path) -> None:
      run_id = "2026-05-02T120000Z_petsmart-inc_<short-input-hash>"
      run_dir = tmp_path / run_id
      run_pipeline(run_id=run_id, run_dir=run_dir, source="examples", slugs=["petsmart-inc"], projection_name="bidder_cycle_baseline_v1")
      assert (run_dir / "canonical.duckdb").exists()
      assert (run_dir / "run_manifest.json").exists()
      assert (run_dir / "validation_report.json").exists()


  def test_run_pipeline_refuses_existing_run_dir(tmp_path: Path) -> None:
      run_id = "2026-05-02T120000Z_petsmart-inc_<short-input-hash>"
      run_dir = tmp_path / run_id
      run_dir.mkdir()
      with pytest.raises(FileExistsError):
          run_pipeline(run_id=run_id, run_dir=run_dir, source="examples", slugs=["petsmart-inc"], projection_name="bidder_cycle_baseline_v1")
  ```

- [ ] **Step 2: Run snapshot tests and verify failure**

  Run:

  ```bash
  python -m pytest tests/test_run_snapshots.py -q
  ```

  Expected: failure because immutable snapshots are not implemented.

- [ ] **Step 3: Implement run IDs and manifests**

  Reject implicit run IDs such as `run-all`. Require:

  ```text
  YYYY-MM-DDTHHMMSSZ_<slug-or-scope>_<short-input-hash>
  ```

  Write `runs/{run_id}/run_manifest.json` with source, slugs, module versions, input hashes, model/provider fields when LLM is enabled, and projection name.

- [ ] **Step 4: Write frozen DB**

  On successful validation/projection, copy the working DB to:

  ```text
  runs/{run_id}/canonical.duckdb
  ```

  Existing run directories hard fail.

- [ ] **Step 5: Run snapshot tests**

  Run:

  ```bash
  python -m pytest tests/test_run_snapshots.py tests/test_validate_project.py -q
  ```

  Expected: pass.

- [ ] **Step 6: Commit**

  ```bash
  git add src/sec_graph/cli src/sec_graph/schema/models/runtime.py tests/test_run_snapshots.py tests/test_validate_project.py
  git commit -m "run: write immutable proof snapshots"
  ```

## Task 14: Nine-Deal Offline Proof

**Purpose:** Prove the corrected pipeline against local reference filings before Linkflow.

**Files:**

- Modify: `tests/test_reconcile_real.py`
- Modify: `tests/test_validate_project.py`
- Generated: `runs/{run_id}/`
- Create: `quality_reports/session_logs/2026-05-02_reference9_offline-proof.md`

- [ ] **Step 1: Run reference-nine offline command**

  Run:

  ```bash
  RUN_ID="$(date -u +%Y-%m-%dT%H%M%SZ)_9-deals_<short-input-hash>"
  python -m sec_graph run \
    --source filings \
    --slugs imprivata mac-gray medivation penford petsmart-inc providence-worcester saks stec zep \
    --run-id "$RUN_ID" \
    --run-dir "runs/$RUN_ID" \
    --projection bidder_cycle_baseline_v1
  ```

  Expected: command exits 0 or fails loudly with a validation report that identifies real unsupported facts.

- [ ] **Step 2: Inspect canonical facts**

  Verify:

  ```text
  PetSmart relation facts are generic actor_relations.
  Saks relation windows use cycle markers.
  Zep count facts do not create bidder actors.
  Medivation has bidder_partial_schedule_to process_scope.
  STEC exclusions use excluded_by_target.
  ```

- [ ] **Step 3: Write proof memo**

  Record command, run ID, hard failures, soft ambiguities, per-deal row counts, and unresolved cases in:

  ```text
  quality_reports/session_logs/2026-05-02_reference9_offline-proof.md
  ```

- [ ] **Step 4: Run full tests**

  Run:

  ```bash
  python -m pytest -q
  ```

  Expected: pass.

- [ ] **Step 5: Commit**

  ```bash
  git add tests quality_reports/session_logs/2026-05-02_reference9_offline-proof.md runs/{run_id}/run_manifest.json runs/{run_id}/validation_report.json runs/{run_id}/run_memo.md
  git commit -m "test: prove deployable canonical pipeline offline"
  ```

  Do not add raw SEC downloads or unrelated dirty files in this commit.

## Task 15: Stale Contract Cleanse

**Purpose:** Remove active docs/tests that steer future agents back to stale schema shapes.

**Files:**

- Modify: `docs/prior-pipeline-lessons.md`
- Modify: `tests/fixtures/**/*.json`
- Modify: `tests/**/*.py`

- [ ] **Step 1: Run stale-contract scan**

  Run:

  ```bash
  python - <<'PY'
  from pathlib import Path

  banned = [
      "actor_type",
      "bidder_subtype",
      "is_anonymous",
      "actor_creation_required",
      "judgment_type",
      "judgment_value",
      "voting_support_for",
      "guarantees",
      "inferred_projection",
      '"unknown"',
      '"other"',
      "GroupMembership",
      "consortium_membership",
  ]
  roots = [Path("docs"), Path("quality_reports"), Path("src"), Path("tests")]
  allowed = {
      Path("docs/spec.md"),
      Path("quality_reports/plans/2026-05-02_deployable-canonical-pipeline-plan.md"),
  }
  hits = []
  for root in roots:
      for path in root.rglob("*"):
          if not path.is_file() or path.suffix not in {".md", ".py", ".json", ".jsonl"}:
              continue
          text = path.read_text(encoding="utf-8")
          for token in banned:
              if token in text and path not in allowed:
                  hits.append(f"{path}: {token}")
  if hits:
      raise SystemExit("\n".join(hits))
  print("stale-contract scan passed")
  PY
  ```

  Expected: failure until stale active docs/tests are rewritten or marked context-only.

- [ ] **Step 2: Clean active docs and fixtures**

  Rewrite active docs and tests to use §1A names. Historical docs may mention stale terms only if they explicitly say the term is rejected and point to `docs/spec.md` §1A.

- [ ] **Step 3: Re-run stale scan and focused tests**

  Run:

  ```bash
  python -m pytest tests/test_validate_project.py tests/test_schema_closed_enums.py tests/test_judgments_two_axis.py -q
  ```

  Expected: pass.

- [ ] **Step 4: Commit**

  ```bash
  git add docs quality_reports tests
  git commit -m "docs: cleanse stale canonical contracts"
  ```

## Task 16: Linkflow PetSmart Pilot And Soundness Judgment

**Purpose:** Live-test the corrected pipeline on PetSmart before the reference-nine batch.

**Files:**

- Generated: `runs/{run_id}/`
- Generated: `artifacts/linkflow/`
- Create: `quality_reports/session_logs/2026-05-02_petsmart-live-soundness-judgment.md`

- [ ] **Step 1: Verify live credentials are present without printing secrets**

  Run:

  ```bash
  python - <<'PY'
  import os
  for name in ("LINKFLOW_API_KEY", "SEC_GRAPH_LIVE_LINKFLOW"):
      print(f"{name}=set" if os.environ.get(name) else f"{name}=missing")
  PY
  ```

  Expected: both set. If missing, stop and ask Austin for the key.

- [ ] **Step 2: Run PetSmart live pilot**

  Run:

  ```bash
  RUN_ID="$(date -u +%Y-%m-%dT%H%M%SZ)_petsmart-inc_<short-input-hash>"
  python -m sec_graph run \
    --source filings \
    --slugs petsmart-inc \
    --run-id "$RUN_ID" \
    --run-dir "runs/$RUN_ID" \
    --projection bidder_cycle_baseline_v1 \
    --llm-provider linkflow \
    --llm-model gpt-5.5 \
    --llm-reasoning-effort high
  ```

  Expected: command exits 0, or fails loudly with sanitized artifacts.

- [ ] **Step 3: Judge PetSmart soundness**

  Inspect run artifacts and write:

  ```text
  quality_reports/session_logs/2026-05-02_petsmart-live-soundness-judgment.md
  ```

  Required verdict values: `SOUND`, `UNSOUND`, or `BLOCKED`.

  PetSmart is `SOUND` only if validation has no hard failures, every accepted LLM candidate has exact local source-span proof, expected Buyer Group/member/relation facts are generic canonical facts, and projection rows are justified by current eligibility judgments.

- [ ] **Step 4: Stop unless PetSmart is sound**

  If verdict is not `SOUND`, fix implementation defects and rerun PetSmart. Do not proceed to Task 17.

- [ ] **Step 5: Commit proof artifacts**

  ```bash
  git add quality_reports/session_logs/2026-05-02_petsmart-live-soundness-judgment.md runs/{run_id}/run_manifest.json runs/{run_id}/validation_report.json runs/{run_id}/run_memo.md artifacts/linkflow
  git commit -m "test: prove live petsmart extraction sound"
  ```

  Do not add secrets, raw provider bodies, full paragraph text, or quote text.

## Task 17: Linkflow Reference-Nine Proof And Final Goal Verification

**Purpose:** Run the full reference-nine live proof only after PetSmart is sound.

**Files:**

- Generated: `runs/{run_id}/`
- Generated: `artifacts/linkflow/`
- Create: `quality_reports/session_logs/2026-05-02_reference9-live-soundness-judgment.md`

- [ ] **Step 1: Run reference-nine live batch**

  Run:

  ```bash
  RUN_ID="$(date -u +%Y-%m-%dT%H%M%SZ)_9-deals_<short-input-hash>"
  python -m sec_graph run \
    --source filings \
    --slugs imprivata mac-gray medivation penford petsmart-inc providence-worcester saks stec zep \
    --run-id "$RUN_ID" \
    --run-dir "runs/$RUN_ID" \
    --projection bidder_cycle_baseline_v1 \
    --llm-provider linkflow \
    --llm-model gpt-5.5 \
    --llm-reasoning-effort high
  ```

  Expected: command exits 0, or fails loudly with sanitized artifacts.

- [ ] **Step 2: Judge all nine deals**

  Write:

  ```text
  quality_reports/session_logs/2026-05-02_reference9-live-soundness-judgment.md
  ```

  Include per-deal verdicts, validation status, ambiguity counts, candidate counts, canonical row counts, projection row counts, rejected Linkflow payload reasons, and source-evidence audits for every reference deal.

- [ ] **Step 3: Run final tests and scans**

  Run:

  ```bash
  python -m pytest -q
  git status --short
  ```

  Then run:

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

  Expected: tests pass and secret scan passes.

- [ ] **Step 4: Commit final proof**

  ```bash
  git add quality_reports/session_logs/2026-05-02_reference9-live-soundness-judgment.md runs/{run_id}/run_manifest.json runs/{run_id}/validation_report.json runs/{run_id}/run_memo.md artifacts/linkflow
  git commit -m "test: prove live reference-nine extraction sound"
  ```

  Do not sweep unrelated dirty files into the commit.

## Execution Order

Required order:

1. Task 1: authority and stale-doc boundaries.
2. Task 2: DB wipe gate.
3. Task 3: actor identity.
4. Task 4: actor relations.
5. Task 5: event subtypes and event roles.
6. Task 6: filing process scope.
7. Task 7: participation counts.
8. Task 8: two-axis judgments.
9. Task 9: validation.
10. Task 10: extraction candidates.
11. Task 11: reconciliation.
12. Task 12: projection.
13. Task 13: run snapshots.
14. Task 14: offline reference-nine proof.
15. Task 15: stale contract cleanse.
16. Task 16: PetSmart live pilot.
17. Task 17: reference-nine live proof.

Do not start Linkflow validation until offline tests and the offline reference proof have completed.

## First-Principles Checks For Reviewers

Reject the implementation if any of these are true:

- A closed enum contains `unknown`, `other`, or equivalent fallback values.
- A count-only phrase creates anonymous bidder actors.
- A relation lacks both cycle and date first-observed markers.
- A withdrawal/exclusion/advancement verb is stored as an event-actor role.
- A judgment row uses `judgment_type` or `judgment_value`.
- A projection row exists without current `projection_eligibility`.
- A partial filing scope enters a target-full baseline projection silently.
- A pipeline command deletes an existing DB or run directory implicitly.
- A Linkflow artifact includes secrets, raw provider bodies, full paragraph text, or quote text.

## Evidence Cases That Must Stay Covered

- `petsmart-inc`: Buyer Group, BC Partners, CDPQ, GIC, StepStone, Longview, late Longview rollover/support, acquisition vehicles, financing.
- `saks`: Sponsor A/Sponsor E/Sponsor G joint group changes and go-shop.
- `zep`: 50 contacted, 25 confidentiality agreements, five indications, terminated process, later restarted process, go-shop.
- `providence-worcester`: strategic/financial contacted counts, Party D/E reengagement, Party F financing support, CVR then all-cash bid change.
- `mac-gray`: CSC/Pamplona structure, acquisition vehicles, guaranty/support/voting facts via `finances` or `supports` with `role_detail`, non-cash option proposal from Party B.
- `stec`: multi-actor final-round invitation, WDC vs Company D divergence, asset-only interested parties as `excluded_by_target`.
- `imprivata`: advisor-driven process letters, sponsor screening, explicit no management participation condition.
- `penford`: historical contacts vs current sale process, support-holder facts, prior discussions.
- `medivation`: bidder-side Schedule TO scope, tender-offer/acquisition vehicle structure, unsolicited proposal history, no financing condition.
