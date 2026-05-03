# 2026-05-03 Taxonomy Refactor — Supplement

## Purpose

This document is supplementary to
`quality_reports/plans/2026-05-03_taxonomy-refactor-handoff.md` (referred to
below as "the handoff"). It assumes the handoff is the binding taxonomy
authority — including its decisions on:

- Auction as deterministic Python derivation, NOT an LLM-emitted field
- NDA type distinction (target-bidder vs bidder-bidder consortium CA vs
  rollover/support side agreement)
- Drop agency × drop reason as orthogonal axes
- Silent fate as derived projection
- Per-event initiation (with `mutual_or_process` and `unknown/null` values)
- Per-bidder advancement separated from per-bidder submission
- `null` permitted where source genuinely does not support a value

This supplement adds the implementation-side material that the handoff does
not specify: the validation mechanism, named-entity registry, cohort
inheritance contract, Pydantic model placement, migration sequence, and cost
envelope. It changes none of the handoff's taxonomic decisions.

If the handoff and this supplement ever conflict, the handoff wins.

---

## 1. Validator Architecture

The handoff says (paraphrasing §2): "If an LLM supplies the classification,
the evidence should be source-span backed and auditable." This supplement
specifies the auditing mechanism.

### 1.1 Three layers

| Layer | Mechanism | Cost | Purpose |
|---|---|---|---|
| L1 | In-prompt confidence emission | Negligible | Per-claim certainty signal |
| L2 | Multi-pass agreement | N×primary | Resolve high-stakes inferential variance |
| L3 | Validator agent re-pass | +1 LLM call | Verify quote actually supports claim |

### 1.2 Routing matrix

Apply layers selectively by stake. The matrix below assumes the handoff's
axes; adjust as axes change.

| Field | L1 | L2 (N=3) | L3 |
|---|---|---|---|
| `bid_formality` | yes | yes | yes |
| `initiation_side` | yes | yes | yes |
| `drop_reason` | yes | yes | yes |
| `actor_class` (named or anonymous) | yes | no | yes |
| `agreement_kind` (NDA type) | yes | yes | yes |
| Final-round advancement events | yes | no | yes |
| `consideration_*` (whichever encoding) | yes | no | no |
| `event_subtype` | yes | no | no |
| `relation_type` | yes | no | no |

Auction and silent fate are NOT in the matrix — both are deterministic
projections per the handoff.

### 1.3 Confidence emission contract

Every classification carries a paired confidence field. Closed three-value
enum:

```python
Literal["high", "medium", "low"]
```

No `null` on confidence. If a classification is emitted, its confidence is
required. If the LLM emits `null` for the classification (per the handoff's
null-permitted rule), confidence is also `null` — both fields move together.

**Rubric (universal):**

- `high`: Evidence quote contains explicit categorical wording that
  unambiguously supports the classification.
- `medium`: Classification is supported by structural signals (sequence,
  count, range, format) but lacks explicit categorical wording in the
  immediate evidence quote.
- `low`: Classification is inferred from surrounding paragraphs; the
  immediate evidence quote alone does not support it.

**Pairing rule:** confidence is emitted in the SAME JSON object as its
paired classification. Validation rejects any classification field present
without its paired confidence (and vice versa).

**Downstream interpretation:**

- `high` → committed to canonical without queue.
- `medium` → committed to canonical, logged for batch quality review.
- `low` → committed to canonical, queued for human review via `judgments`
  table with `judgment_kind = "semantic_validation"`, `status = "queued"`.

### 1.4 Multi-pass aggregation rules

For L2 fields, run extraction N=3 times independently. Aggregation:

```
3/3 agree on value → commit, effective_confidence = max(emitted confidences)
2/3 agree on value → commit majority value, effective_confidence = "medium",
                     log dissenting run for telemetry
1/1/1 (all differ) → emit null for this field,
                     queue judgment with status = "ambiguous_multi_pass"
```

If the values include `null`, count `null` as a distinct value. A pattern
of `value/value/null` collapses to 2/3 agreement on the value.

### 1.5 L3 validator pass contract

After primary extraction (and L2 aggregation if applicable), a separate LLM
call re-reads each classification's evidence quote and emits a verdict:

```python
class ValidatorVerdict(BaseModel):
    field: str
    value: str | None  # the classification value (None if extractor emitted null)
    quote: str
    verdict: Literal["yes_supported", "no_contradicts", "insufficient_context"]
    reasoning: str  # short explanation
```

If `verdict != "yes_supported"`, the original claim is queued for human
review with `judgment_kind = "semantic_validation"`. The original claim is
NOT committed to canonical until the queue entry is resolved.

### 1.6 Validator pass is BLOCKING

The validator pass runs synchronously before the reconcile stage. No claim
proceeds to canonical commit while a validator disagreement is pending.
This preserves the fail-loud invariant: every canonical fact has either
passed validation or been explicitly resolved by human judgment.

### 1.7 Disagreement queue lifecycle

```
Extractor emits → Validator disagrees → Judgment queued (status="queued")
                                           ↓
                                        Reviewer (human) processes
                                           ↓
                                        Judgment resolved (status="resolved")
                                           ↓
                                        supersedes_judgment_id chain extended
                                           ↓
                                        Canonical fact committed
```

No automatic resolution. No timeout-based defaults. Human review is the
only resolver.

### 1.8 Where to implement

- Multi-pass orchestration: new module
  `src/sec_graph/extract/multi_pass.py`
- Validator agent: new module `src/sec_graph/extract/validator.py`
- Aggregation logic: new module `src/sec_graph/extract/aggregation.py`
- Judgment queue interaction: extend `src/sec_graph/reconcile/pipeline.py`

---

## 2. Named-Entity Registry

The handoff treats `actor_class` for named actors as an LLM emission. This
supplement adds a deterministic Python anchor for repeat-appearing named
entities (Apollo, KKR, Pamplona, Carlyle, Pfizer, etc.), so the registry's
classification can override or corroborate the LLM's per-filing emission.

### 2.1 Format and location

```
data/registry/known_actors.yaml
```

Single YAML file, version-controlled. Two top-level lists keyed by
`actor_class`:

```yaml
financial_sponsors:
  - canonical_name: "Apollo Global Management"
    aliases: ["Apollo", "Apollo Management Holdings", "Apollo Capital"]
    actor_class: "f"
    sub_type: "private_equity"
    parent_of: []
    source: "manual_curation_2026Q2"
    confidence: "high"
    notes: ""

  - canonical_name: "Pamplona Capital Management"
    aliases: ["Pamplona", "Pamplona Capital"]
    actor_class: "f"
    sub_type: "private_equity"
    parent_of: ["Pamplona Capital Acquisition Corp."]
    source: "extracted_from_macgray_2013"
    confidence: "high"
    notes: ""

strategic_acquirers:
  - canonical_name: "CSC ServiceWorks"
    aliases: ["CSC", "CSC Holdings"]
    actor_class: "s"
    sub_type: "operating_company"
    parent_of: ["CSC ServiceWorks Sub Inc."]
    source: "extracted_from_macgray_2013"
    confidence: "high"
    notes: ""
```

(Values use the handoff's short-form `s/f/mixed/null`.)

### 2.2 Lookup logic

```python
def resolve_actor_class(actor_name: str, registry: Registry) -> RegistryHit | None:
    # Order of attempts:
    # 1. Exact case-sensitive alias match
    # 2. Case-insensitive alias match
    # 3. Substring match against canonical_name
    # 4. Suffix-stripped match
    #    (drop "Sub Inc.", "Holdings", "Acquisition Corp.", "Inc.", "Corp.",
    #    "LLC", "LP", "Ltd."; re-run steps 1-3 on stripped form)
    # 5. Fuzzy match (Levenshtein <= 3)
    #    -- flag as fuzzy_match for review; do not auto-commit
    ...
```

Implementation lives in `src/sec_graph/extract/registry.py` (new module).

### 2.3 LLM ↔ registry interaction

```
LLM emits actor_class for actor X
    ↓
Python: registry lookup for X.canonical_name
    ↓
Match found?
├─ Yes, registry confidence=high, agrees with LLM → commit (high)
├─ Yes, registry confidence=high, disagrees with LLM →
│      prefer registry, log discrepancy, queue judgment for review
├─ Yes, registry confidence=medium/low → prefer LLM (live context wins)
└─ No match →
       use LLM's emission as-is
       log to "unknown_named_actors" curation queue
```

### 2.4 Bootstrap: corpus-driven seed

1. Run new extraction on the 9-deal proof corpus.
2. Collect every named actor (`observability == "named"`) with an
   `actor_class` emission.
3. Hand-validate the top 50 most-frequent actors (covers expected ~80% of
   repeat appearances in the proof set).
4. Seed `data/registry/known_actors.yaml` with the validated entries.
5. Grow organically as new filings are processed; new named actors
   accumulate in the curation queue.

### 2.5 Vehicle, subsidiary, and consortium handling

- **Vehicles** (e.g., "Pamplona Capital Acquisition Corp."): suffix-stripped
  to parent (Pamplona Capital). Vehicle inherits parent's `actor_class`.
- **Subsidiaries**: listed under `parent_of` in the parent's registry entry;
  inherit similarly.
- **Consortia** (`actor_kind == "group"`): NOT looked up directly. Their
  `actor_class` is derived from members:

```python
def derive_consortium_class(group_actor: Actor, members: list[Actor]) -> str | None:
    classes = {m.actor_class for m in members if m.actor_class is not None}
    if not classes:
        return None  # no member has a known class
    if "f" in classes and "s" in classes:
        return "mixed"
    if classes == {"f"}:
        return "f"
    if classes == {"s"}:
        return "s"
    raise ContractViolation(
        f"Consortium {group_actor.id} has unexpected member classes: {classes}"
    )
```

The LLM may also emit `actor_class` directly on the consortium actor. Python
validates that the emission matches the derived value. Disagreement → flag.

---

## 3. Cohort Inheritance Contract

The handoff (§1, lines 118-120) treats cohort-level `mixed` as legitimate
("11 strategic and 14 financial parties is mixed at the cohort/count
level"). This supplement specifies how individual actors derived from a
cohort inherit `actor_class`.

### 3.1 Rule

When a single-actor descriptor in narrative is "Party A, one of the
financial bidders" (referring to a typed cohort actor like "16 financial
bidders"), the individual party's `actor_class` MUST match the cohort's
`actor_class`.

### 3.2 Emission

Both fields are LLM-emitted independently:

- The cohort actor receives `actor_class` based on the cohort descriptor
  ("16 financial bidders" → `f`).
- Individual actors derived from the cohort receive `actor_class` from
  their own descriptor (which references the cohort).

The LLM is responsible for emitting both consistently. Python does NOT
auto-derive the individual's class from the cohort's class.

### 3.3 Validation

Python checks:

```python
for relation in actor_relations.where(type="member_of"):
    member = actors[relation.source]
    cohort = actors[relation.target]
    if cohort.actor_class is None or member.actor_class is None:
        continue  # null is acceptable per handoff's null-permitted rule
    if cohort.actor_class != "mixed" and cohort.actor_class != member.actor_class:
        flag(member, cohort, "cohort_class_inconsistency")
```

Inconsistencies are flagged but not auto-corrected. Flagged claims enter
the judgment queue.

### 3.4 Why not auto-derive

Two reasons:

1. **Provenance integrity.** The narrative cue is what justifies the
   classification. Auto-derivation from a relation graph would lose the
   binding to the descriptor sentence.
2. **Robustness to extraction error.** If the LLM misses the `member_of`
   relation but catches the descriptor, derived inheritance silently loses
   the classification. Independent emission of both fields preserves the
   information through partial extraction failure.

---

## 4. consideration_type — Encoding Choice

The handoff (§9, lines 339-358) lists consideration components without
fixing the encoding. This supplement offers a closed-enum alternative as a
decision point.

### 4.1 Option A: composable booleans (per handoff's implicit framing)

```python
class BidConsideration(BaseModel):
    has_cash: bool
    has_stock: bool
    has_cvr: bool
    has_earnout: bool
    has_other: bool
    other_description: str | None
    aggregate_value_disclosed: bool
```

**Pros:** flexible, captures multi-component bids without enum
proliferation, naturally records "cash + stock + earnout" combinations.

**Cons:** SQL query for "all-cash bids" requires `has_cash AND NOT has_stock
AND NOT has_cvr AND NOT has_earnout AND NOT has_other` — verbose.

### 4.2 Option B: closed enum with escape valve

```python
consideration_type: Literal[
    "all_cash",
    "all_stock",
    "cash_and_stock",
    "cash_and_assumption_of_debt",
    "cash_and_earnout",
    "complex_other",
]
```

For `complex_other`, an evidence quote describing the unusual structure is
mandatory.

**Pros:** SQL-friendly single-column predicate, forces commitment to a
named structure.

**Cons:** unusual structures collapse into `complex_other` losing detail
unless paired with a free-text annotation.

### 4.3 Recommendation

If downstream analysis is dominated by "is this an all-cash deal" type
queries, **Option B** is more ergonomic. If downstream analysis routinely
inspects multi-component structures, **Option A** is more honest.

The handoff's reference to old-pipeline lessons suggests downstream
analysis cares mostly about cash vs mixed (per the `all_cash` deal-level
rule it cites). On that signal, Option B is preferred. Decision deferred to
the next agent or to a follow-up discussion.

---

## 5. Pydantic Model Location Map

The handoff names which surface each axis lives on (Phase 2). This
supplement maps every field addition to the corresponding model file under
`src/sec_graph/schema/models/`.

### 5.1 `canonical.py`

| Axis | Field(s) | On entity |
|---|---|---|
| Bidder economic class | `actor_class: Literal["s","f","mixed"] | None` | Actor |
| Bid formality | `bid_formality: Literal["informal","formal"] | None`, `bid_formality_confidence` | Event (when `event_type == "bid"`) |
| Initiation side | `initiator_role: Literal["target","bidder","activist","mutual_or_process","unknown"] | None`, `initiator_confidence` | Event (process/contact events) |
| Final-round structure | extend `event_subtype` with: `final_round_announced`, `final_round_extended`, `advanced_to_final_round`, `not_advanced` | Event |
| Drop agency + reason | `drop_agency: Literal["target","bidder","unknown"] | None`, `drop_reason: Literal[...] | None` | Event (drop events) |
| NDA type | `agreement_kind: Literal["target_bidder_nda","bidder_bidder_consortium_ca","rollover_support"]` | Event (when `event_subtype == "agreement_executed"` or similar) |
| Consideration | per Option A or B above | Event (when `event_type == "bid"`) |
| Go-shop | `event_subtype = "go_shop_period_opened"` and `"go_shop_period_closed"` | Event |
| Deal-level all_cash | `all_cash: bool` (Python-derived) | Deal |

### 5.2 `extraction.py`

Mirror the canonical fields on the corresponding claim payload classes
(`ActorClaim`, `EventClaim`, `ParticipationCountClaim`,
`ActorRelationClaim`).

Add a new `validator_verdict` optional field on every claim payload to
carry L3 validator results:

```python
validator_verdict: ValidatorVerdict | None = None
```

### 5.3 `judgments.py`

`judgment_kind` already includes `semantic_validation`. No structural
change required, but verify the judgment payload supports the new fields'
value types (especially the union-with-null types).

### 5.4 `participation_counts.py`

No change. `actor_class` on `ParticipationCount` (using the existing
`financial`/`strategic`/`mixed` values) continues to exist for cohort
counts. Optional: rename to `s/f/mixed` for consistency with the
handoff's short-form, but this is cosmetic.

### 5.5 `runtime.py`, `filings.py`, `evidence.py`

No change.

### 5.6 New module skeletons

| Module | Purpose |
|---|---|
| `src/sec_graph/extract/registry.py` | Named-entity lookup (per §2 above) |
| `src/sec_graph/extract/multi_pass.py` | L2 multi-pass orchestration |
| `src/sec_graph/extract/validator.py` | L3 validator agent |
| `src/sec_graph/extract/aggregation.py` | L2 aggregation rules |
| `src/sec_graph/project/auction.py` | Deterministic auction derivation (per handoff §8) |
| `src/sec_graph/project/silent_fate.py` | Silent-dropout derivation (per handoff §6) |

---

## 6. Migration Sequence

The handoff's Phase 1-6 work plan is sequenced at workstream level. This
supplement gives the file-level rollout order.

```
1. Update docs/spec.md §1A with the handoff's taxonomy decisions
   (binding contract update). Get user signoff.

2. Update Pydantic models in src/sec_graph/schema/models/ per §5 above.

3. Update DDL in src/sec_graph/schema/__init__.py:
   - DROP all canonical tables (no in-place migration per fail-loud).
   - CREATE with new columns.
   - Bump schema_version.

4. Update src/sec_graph/extract/llm/linkflow.py:
   - _semantic_claim_schema() includes new fields and confidence enums.

5. Update src/sec_graph/extract/llm/prompt.py:
   - Add classification rubrics (per handoff's §1-§9) inline.
   - Add confidence rubric (§1.3 above).
   - Add cohort inheritance rule (§3 above).
   - Add mandatory-pairing rule (classification + confidence together).

6. Implement src/sec_graph/extract/registry.py per §2 above.

7. Implement src/sec_graph/extract/multi_pass.py,
   src/sec_graph/extract/validator.py,
   src/sec_graph/extract/aggregation.py per §1 above.

8. Implement src/sec_graph/project/auction.py
   (target-bidder NDA count >= 2 per cycle → auction = true)
   and src/sec_graph/project/silent_fate.py
   (NDA-signer with no later observed event → fate = silent)
   per handoff §6 and §8.

9. Bump version counters:
   - EXTRACT_VERSION += 1
   - RECONCILE_VERSION += 1
   - PROJECT_VERSION += 1

10. Drop existing canonical store: rm data/pipeline.duckdb.

11. Re-extract proof corpus end-to-end:
    python -m sec_graph run --source filings --slugs <each of 9 deals>

12. Run validator pass end-to-end. Confirm judgment queue populates only
    for genuinely ambiguous claims.

13. Bootstrap registry per §2.4.

14. Re-run validate stage; confirm projection_eligibility judgments still
    pass for bidder rows. Confirm auction projections agree with the new
    NDA-count rule.

15. Update tests in tests/:
    - Tests for each new closed enum
    - Tests for null-permitted fields (confirm null commits cleanly)
    - Tests for multi-pass aggregation (3/3, 2/3, 1/1/1 cases)
    - Tests for validator pass disagreement queueing
    - Tests for registry lookup (exact, case-insensitive, suffix-strip,
      fuzzy)
    - Tests for cohort inheritance validation
    - Tests for auction derivation (>=2 target-bidder NDAs → auction)
    - Tests for silent-fate derivation (NDA without later event)
    - Tests for NDA type distinction (auction count excludes consortium CAs)
```

### 6.1 Sequencing constraint

Step 5 (prompt) MUST occur AFTER step 4 (schema function) so that the
prompt rubrics align with the JSON schema the LLM is asked to satisfy.

Step 8 (auction projection) MUST occur AFTER step 2 (NDA `agreement_kind`
field exists) — without typed NDAs, the auction count is contaminated by
consortium CAs.

### 6.2 Non-migrating artifacts

- Old `runs/{run_id}/` directories: retained as historical archive,
  flagged stale by version-counter mismatch.
- Old `judgments` table entries: append-only chain breaks at version
  boundary; old entries are evidence only, not actionable.
- Old extracted claims in `data/pipeline.duckdb`: discarded.

---

## 7. Operational Cost Envelope

The handoff does not quantify validation cost. This supplement projects
LLM call volume, wall time, and corpus-scale throughput so resource
decisions are explicit.

### 7.1 Per-deal call count

For a deal with one Background-region extraction:

- Primary extraction: 1 LLM call
- L2 multi-pass (high-stakes fields only): +2 LLM calls (3 total)
- L3 validator pass (covers all emitted classifications): +1 LLM call

Total per deal: **~4 LLM calls** with full validation, vs ~1 for
single-pass.

### 7.2 Per-deal wall time (mac-gray Background scale)

Per the probe log
(`quality_reports/llm_calibration/2026-05-03_linkflow-probe-log.md`),
mac-gray Background single-pass = ~2 minutes at gpt-5.5 / P7 / medium.

Full validation per deal:

- 3 × primary extraction = ~6 minutes (parallelizable)
- 1 × validator pass = ~2 minutes
- **Total: ~8 minutes per deal sequentially, ~4 minutes if multi-pass
  runs concurrently.**

### 7.3 Corpus-scale projections

| Corpus | Deals | Sequential time | Concurrency-10 time |
|---|---|---|---|
| Proof set | 9 | ~72 min | ~10 min |
| Reference set | ~50 | ~7 hr | ~45 min |
| Full corpus | 401 | ~54 hr | ~5–6 hr |

User has authorized bottomless Linkflow tokens during Phase 1 (per memory
entry `feedback_linkflow_no_cost_optimization.md`). Cost not a budget
constraint. Wall time is the only resource limit.

### 7.4 Recommended concurrency posture

- Proof corpus runs (9 deals): single-threaded is fine; ~1 hour total.
- Reference set runs (~50 deals): concurrency 5; ~1.5 hours.
- Full corpus runs (401 deals): concurrency 10–20; ~3–5 hours.

Linkflow throttling is unknown at scale. Probe at concurrency 5 first;
ramp if no errors.

---

## 8. Closed-Enum Exhaustiveness — One Caveat

The handoff implies closed enums everywhere. This supplement notes one
intentional escape valve consistent with the handoff's null-permitted
rule:

- `null` is permitted on all classifications where the source genuinely
  does not support a value (per handoff §1, §2, §6).
- `null` is NOT permitted as a substitute for a real classification when
  the source DOES support one — that is fail-loud behavior (the LLM is
  guessing-by-omission).

The validator pass (§1.5 above) is what distinguishes these cases. If the
validator says "insufficient_context", `null` is the correct value; if the
validator says "no_contradicts" with a contradicting value, the original
is wrong and must be queued for human review.

`null` is not the same as `unknown` or `other` — it is the absence of an
emission, not a closed-enum value. There is no `"unknown"` value in any
enum.

---

## 9. Cross-References

- `quality_reports/plans/2026-05-03_taxonomy-refactor-handoff.md` — the
  handoff this document supplements.
- `quality_reports/llm_calibration/2026-05-03_linkflow-probe-log.md` —
  empirical basis for cost projections (single-pass timings) and for the
  multi-pass requirement (76→95 claim variance observed on mac-gray).
- `quality_reports/plans/2026-05-02_stale-scaffold-hard-cleanse-repair-plan.md` —
  active repair plan; the migration sequence above must not conflict with
  any open phase.
- `data/registry/known_actors.yaml` (to be created) — registry seed file.
- `src/sec_graph/extract/registry.py` (to be created) — lookup module.
- `src/sec_graph/extract/multi_pass.py` (to be created) — multi-pass
  orchestrator.
- `src/sec_graph/extract/validator.py` (to be created) — validator agent.

---

## 10. What This Supplement Does NOT Specify

The following are intentionally left to the handoff or to follow-up
discussion:

- The taxonomy axes themselves (handoff §1-§10).
- The auction derivation rule (handoff §8).
- The drop reason enum cardinality (handoff §6 lists candidates).
- Process cycle boundary detection logic.
- Bidder-rows projection contract.
- The choice between Option A and Option B for `consideration_type`
  encoding (this supplement offers both; user/next-agent decides).
- IB engagement events as separate event_subtypes (deferred per the
  handoff's silence on the topic).
- Date precision flag (precise vs rough) — deferred.

---

**End of supplement.**
