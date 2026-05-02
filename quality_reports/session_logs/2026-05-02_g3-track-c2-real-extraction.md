# Session Log: G3 Track C2 Real Extraction

**Date:** 2026-05-02
**Branch:** `track-c/extract-real`
**Gate:** G3 - Track A merged + Track C2 real extraction green

## Scope

Implemented Phase 3 / Track C2 from `quality_reports/plans/2026-05-02_parallel-execution-plan.md`:

- Fixed section detection so body mentions of headings such as `Financing` do not reclassify sale-process background paragraphs.
- Scoped extraction to sale-process paragraphs: `Background of the Merger` and `unknown_section`.
- Extended actor rules for real example aliases including `Industry Participant`, `Buyer Group`, `Bidder N`, `Sponsor X`, `Company X`, `Hudson's Bay` / `Hudson\u2019s Bay`, and `G&W`.
- Reworked dated-event extraction to stop at sentence boundaries without splitting on decimals or initialisms such as `J.P.` and `U.S.`.
- Reworked bid extraction so per-share ranges are single `bid_value` candidates, avoiding duplicate upper-endpoint candidates.
- Changed paragraph traversal to source order (`char_start`) instead of lexicographic paragraph IDs.
- Added PetSmart/Saks real-extraction golden coverage in `tests/fixtures/extract/real_candidate_golden.json`.

## RED Evidence

Command:

```bash
PYTHONPATH=src PATH=/Users/austinli/Projects/sec_graph/.venv/bin:$PATH python -m pytest tests/test_ingest_examples.py::test_section_detection_does_not_promote_body_mentions_to_headings -q
```

Outcome with old section detector: exit 1; PetSmart `On August 13, 2014,...` paragraph was labeled `Financing` instead of `Background of the Merger`.

Command:

```bash
PYTHONPATH=src PATH=/Users/austinli/Projects/sec_graph/.venv/bin:$PATH python -m pytest tests/test_extract_rules_real_examples.py -q
```

Outcome before rule changes: exit 1; three expected failures:

- real alias forms were not extracted;
- dated-event spans consumed multiple sentences;
- bid ranges collapsed to upper endpoints.

Command:

```bash
PYTHONPATH=src PATH=/Users/austinli/Projects/sec_graph/.venv/bin:$PATH python -m pytest tests/test_extract_rules_real_examples.py::test_real_extraction_candidate_sequence_follows_source_order -q
```

Outcome before source-order query fix: exit 1; first PetSmart dated event was `2014-08-13` instead of source-order `2014-05-21`.

## Golden Candidate Contract

PetSmart and Saks projections are exact-hash locked by test:

| Slug | Candidate rows | Projection SHA-256 |
|------|----------------|--------------------|
| `petsmart-inc` | 55 | `17007c7803e62465cdabad5cc5b32bad94db7dfa9f25f10479f7f017d0528a46` |
| `saks` | 153 | `ba44fd1299920906f497943ca7dfa2f6b480638065f83368e0a7c401b2b9040c` |

The fixture also includes visible required rows for key actors, dated events, and bid ranges so the hash is not the only human-readable proof surface.

## Verification

Command:

```bash
PYTHONPATH=src PATH=/Users/austinli/Projects/sec_graph/.venv/bin:$PATH python -m pytest tests/test_extract_rules_real_examples.py tests/test_extract_rules_smoke.py tests/test_ingest_examples.py::test_section_detection_does_not_promote_body_mentions_to_headings -q
```

Outcome: exit 0; 8 passed.

Command:

```bash
PYTHONPATH=src PATH=/Users/austinli/Projects/sec_graph/.venv/bin:$PATH python -m pytest tests/test_extract_rules_real_examples.py -q
```

Outcome: exit 0; 7 passed.

Command:

```bash
PYTHONPATH=src PATH=/Users/austinli/Projects/sec_graph/.venv/bin:$PATH python -m pytest
```

Outcome: exit 0; 36 passed.

Command:

```bash
PYTHONPATH=src PATH=/Users/austinli/Projects/sec_graph/.venv/bin:$PATH python -m pytest tests/ -x --ff
```

Outcome: exit 0; 36 passed.

Command:

```bash
PYTHONPATH=src PATH=/Users/austinli/Projects/sec_graph/.venv/bin:$PATH python -m pytest tests/ -x --ff
```

Outcome: exit 0; 36 passed.

Command:

```bash
PYTHONPATH=src PATH=/Users/austinli/Projects/sec_graph/.venv/bin:$PATH python -m sec_graph ingest --all
```

Outcome: exit 0; ingested 4 filings into `data/pipeline.duckdb`.

Command:

```bash
PYTHONPATH=src PATH=/Users/austinli/Projects/sec_graph/.venv/bin:$PATH python -m sec_graph extract --all
```

Outcome: exit 0; extracted candidates for 4 filings.

Candidate counts from the fresh CLI DuckDB:

| Slug | Actor mentions | Bid values | Dated events |
|------|----------------|------------|--------------|
| `petsmart-inc` | 25 | 12 | 18 |
| `providence-worcester` | 53 | 13 | 18 |
| `saks` | 110 | 14 | 29 |
| `zep` | 6 | 8 | 32 |

Evidence-gap queries on the fresh CLI DuckDB:

- `empty_evidence_candidates`: 0
- `orphan_extract_spans`: 0

## Gate Result

G3 passed for Track C2:

- PetSmart and Saks exact candidate projections match golden hashes.
- Required real actor/event/bid rows are present.
- Every real PetSmart/Saks candidate has at least one evidence ID.
- Every real PetSmart/Saks evidence ID resolves to an extract span inside its parent paragraph seed.
- Rerun extraction is deterministic for PetSmart and Saks.
- The four-example CLI ingest/extract path runs cleanly.
