# Session Log: P8 Region Applicability — Phase 0 + Phase 1

**Date:** 2026-05-04
**Branch:** `main`
**Plan:** `quality_reports/plans/2026-05-04_p8_region_applicability_ref9_plan.md`

## Scope

Phase 0 (preflight) and Phase 1 (region selection) from the active plan. The
P8 claim-only Linkflow contract is not touched; this work only modifies
ingest-time section detection, evidence-map region selection, and the offline
Reference-9 gate.

## Phase 0 Preflight

- Working tree contained the new active plan plus archived legacy plan; no
  unrelated WIP that needed preserving.
- All nine Reference-9 raw filings were already present under
  `data/filings/<slug>/raw.md`.
- Baseline command:

  ```bash
  UV_CACHE_DIR=/private/tmp/uv-cache PYTHONDONTWRITEBYTECODE=1 uv run pytest \
    -q -p no:cacheprovider tests/test_llm_p8_contract.py \
    tests/test_coverage_semantics.py tests/test_hard_reset_schema.py
  ```

  Result: 23 passed (frozen P8 contract green before any change).

## Phase 1 Findings (Pre-Change)

Probing the current path against all nine local filings exposed two failure
modes that were invisible in the trimmed `data/examples/` fixtures:

| Slug | Bg paragraphs (before) | Issue |
|------|-----------------------:|-------|
| medivation | 0 | Heading `***Background of the Offer***` not in vocabulary; tender-offer process_scope rejected EX-99.(A)(1)(A) |
| stec | 1273 | `**sTec's Reasons for the Merger**` not recognized as a heading, so the BG label spilled over the rest of the filing |
| imprivata | 100 | Plausible but at the high end |
| others | 41–103 | Plausible |

The plan's Phase 1 acceptance demands that all nine local filings yield at
least one validated sale-process region offline. This required three
coupled changes.

## Phase 1 Implementation

### 1. Heading vocabulary expanded (`src/sec_graph/ingest/section_vocabulary.py`)

Added the sale-process variants the Reference-9 set actually uses:

```text
Background of the Offer and Merger      (longest first to win prefix ties)
Background of the Solicitation
Background of the Offer
Background of the Merger
Past Contacts, Transactions, Negotiations and Agreements
Past Contacts and Negotiations
Background and Reasons for the Recommendation
```

`SALE_PROCESS_HEADINGS`, `OTHER_HEADINGS`, `SECTION_HEADINGS`,
`SALE_PROCESS_SECTIONS`, and `NON_CANONICAL_HEADING` are exported by name.

### 2. Strict-then-heuristic detection (`src/sec_graph/ingest/sections.py`)

- Sale-process headings now use exact match (after stripping markdown
  emphasis, COMMAND-styling, leading section numbers like `10.`, and
  trailing period/colon). Body sentences that begin with the heading words
  are no longer promoted.
- Other vocabulary headings (`Reasons for the Merger`, `Opinion of`, ...)
  retain prefix matching for advisor-specific suffixes.
- A new `_looks_like_heading` heuristic returns the `__other_heading__`
  sentinel when a paragraph is structurally heading-like but not in the
  vocabulary. Triggers:
  - Markdown emphasis wrapper (`**X**`, `***X***`, `__X__`) or ATX `#`,
  - Numbered subsection prefix (`12. The Merger Agreement.`),
  - Body length ≤ 120 chars and ≤ 15 words after stripping markup,
  - Not a TOC table row (lines starting with `|`).
- `assign_sections` resets the running section to `unknown_section` when
  the sentinel fires, so sticky sale-process labels stop spreading.

### 3. Multi-region evidence map (`src/sec_graph/extract/evidence_map.py`)

- Each distinct sale-process section in a filing now produces one region in
  encounter order. Medivation gets two regions
  (`Background of the Offer` and `Past Contacts, ...`).
- Obligation IDs use a global counter across regions so multi-region
  filings do not collide.
- Failure mode: a filing with no recognized sale-process paragraphs raises
  with a clear `ValueError` mentioning `sale-process` and the canonical
  heading examples.

### 4. Tender-offer ingest (`src/sec_graph/ingest/pipeline.py`)

Mapped `EX-99.(A)(1)(A)` to `bidder_partial_schedule_to`. The fetcher
records the exhibit form_type, not the parent SC TO-T, so without this
mapping `medivation` failed at ingest before region selection could run.
The CLAUDE.md rule "no fallback to the cover form" is unchanged: failure
still occurs when no Offer to Purchase exhibit was selected upstream.

## Phase 1 Findings (Post-Change)

| Slug | Sale-process region(s) | Paragraph count(s) |
|------|------------------------|--------------------|
| providence-worcester | Background of the Merger | 39 |
| medivation | Background of the Offer + Past Contacts, ... | 38, 2 |
| imprivata | Background of the Merger | 96 |
| zep | Background of the Merger | 66 |
| petsmart-inc | Background of the Merger | 41 |
| penford | Background of the Merger | 91 |
| mac-gray | Background of the Merger | 103 |
| saks | Background of the Merger | 67 |
| stec | Background of the Merger | 101 |

All nine slugs produce at least one validated sale-process region. The
medivation tender-offer case correctly emits two regions corresponding to
its `***Background of the Offer***` and
`***Past Contacts, ...***` subsection headings.

## Tests Added

| File | Purpose |
|------|---------|
| `tests/test_section_selection.py` | 14 unit tests covering plain/bold/italic/styled headings, TOC rejection, cross-reference rejection, sticky-section reset by `__other_heading__`, page-marker stability, and vocabulary ordering invariants. |
| `tests/test_reference9_offline_regions.py` | Parametrized over all nine slugs: ingests from `data/filings/`, builds the evidence map, asserts region kind/priority/section/paragraph-count band, paragraph-section consistency, expected claim types, LLM window construction, and a fail-loud case for filings without sale-process paragraphs. Bands live in `tests/fixtures/reference9_region_expectations.json`. |

The existing
`tests/test_hard_reset_schema.py::test_evidence_map_fails_loudly_without_background_section`
was updated to assert both `sale-process` and the canonical heading
examples in the error message.

## Verification

```bash
UV_CACHE_DIR=/private/tmp/uv-cache PYTHONDONTWRITEBYTECODE=1 uv run pytest \
  -q -p no:cacheprovider tests/test_section_selection.py \
  tests/test_reference9_offline_regions.py
# 26 passed in 9.42s

UV_CACHE_DIR=/private/tmp/uv-cache PYTHONDONTWRITEBYTECODE=1 uv run pytest \
  -q -p no:cacheprovider
# 86 passed in 13.65s
```

## Frozen P8 Boundary

Untouched by this phase (verified by the green
`tests/test_llm_p8_contract.py` baseline both before and after):

- Request mode `claim_only_p8_relation_v1`.
- Default Linkflow reasoning `medium`.
- Provider response shape (five positive claim arrays, no
  `coverage_results`, no source coordinates, no scalar judgments).
- `data/filings/` and `quality_reports/llm_calibration/` are untouched.

## Open Questions / Phase 2 Hand-Off

- Multi-region medivation currently gets the same 10-obligation bundle on
  both regions, which inflates obligation counts to 20 for that filing.
  Phase 2 (applicability-aware obligations) is the right place to resolve
  this, since it requires source-signal driven obligation generation
  rather than a static bundle.
- The `_looks_like_heading` length and word bounds (120 chars, 15 words)
  are wide enough for every Reference-9 case observed; they may need
  tuning when the corpus expands. The tests pin the current bounds via
  `test_long_bold_paragraph_is_not_treated_as_heading`.
- No live Linkflow run was attempted in this session; that remains Phase 6
  work and is gated on this offline test plus credential availability.
