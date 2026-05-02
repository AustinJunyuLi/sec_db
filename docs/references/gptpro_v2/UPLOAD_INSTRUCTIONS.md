# v2 Greenfield Packet — Upload Instructions

This folder contains the v2 greenfield clean-room request for GPT-5.5 Pro.

## What gets uploaded

To GPT-5.5 Pro (ChatGPT Pro mode):

1. **Paste the contents of `PROMPT.md` as the chat message.**
2. **Attach as files:**
   - `BRIEF.md`
   - `derive_views.py`
   - `filing_petsmart-inc.md`
   - `filing_providence-worcester.md`
   - `filing_zep.md`
   - `filing_saks.md`

## Packet assembled

All six attachments are already in this folder. **Do not re-copy `raw.md` over the existing `filing_*.md` files** — the existing extracts have been trimmed from full proxy statements (~150k tokens each) to the auction-relevant sections only (~25–35k tokens each). Re-copying would blow the context window.

What's in this folder:

- `PROMPT.md` (paste as chat message)
- `BRIEF.md` (attach)
- `derive_views.py` (attach)
- `filing_petsmart-inc.md` (attach — Background through end of Interests-of-Directors / before Merger Agreement boilerplate)
- `filing_providence-worcester.md` (attach — same scope)
- `filing_zep.md` (attach — same scope)
- `filing_saks.md` (attach — same scope)

Each `filing_<slug>.md` was extracted from the corresponding `data/filings/<slug>/raw.md`. The extraction range is documented in `quality_reports/specs/2026-05-01_gptpro-v2-prompt-design.md`.

## Token budget

Estimated input: ~106k tokens. Comfortably within GPT-5.5 Pro's context window.

Expected output: one zip containing 12 modular markdown files, ~50–80k tokens total.

## ChatGPT settings

- **Mode:** GPT-5.5 Pro (the highest reasoning tier)
- **Reasoning effort:** Pro mode default (high/xhigh). Per OpenAI's GPT-5.5 prompt-guidance, increase effort only when evals show measurable gain — but for a one-shot greenfield design pass, high is appropriate.
- **Time:** allow up to 30 minutes for completion.

## What to expect back

A single zip file containing:

```
00_README.md
01_RESEARCH_TARGET.md
02_DATA_MODEL.md
03_ARCHITECTURE.md
04_INGESTION.md
05_EXTRACTION.md
06_AGGREGATION.md
07_VALIDATION_AND_AUDIT.md
08_TEST_PLAN.md
09_BUILD_SEQUENCE.md
10_DECISIONS.md
11_OPEN_QUESTIONS.md
```

Save it as `gptpro_v2_response.zip` in this folder. Do not unzip and edit before review — the zip is the artifact.

## Two-turn protocol

This is **turn 1 of 2.** Turn 1 produces the conceptual data pipeline design without provider binding. Turn 2 (later, separate session) sends that zip back to GPT-Pro along with `linkflow_constraints.md` to bind the design to a specific LLM provider and surface any architectural costs of the binding.

Do not ship Linkflow constraints in turn 1. They will anchor GPT-Pro's design on LLM-call architectures and may suppress non-LLM design moves prematurely.

## What is deliberately omitted from the v1 packet

- **`CASEBOOK.md`** (v1 anchored hard on the four cases as a stress-test ontology). Replaced by raw filings + `BRIEF.md` framing. GPT-Pro picks its own hard cases.
- **`alex_row_extracts.csv`** (Alex's workbook). The estimator's input contract (`derive_views.py`) is now the calibration target. Alex's intermediate is not in scope.
- **`filing_excerpt_sources.md`** (curated, page-numbered, pre-segmented excerpts). Replaced by full raw filings as `filing_<slug>.md` — no page numbers, no segmentation. GPT-Pro must design provenance from text.
- **`linkflow_constraints.md`**. Deferred to turn 2.

## Before shipping — review checklist

Before uploading to GPT-Pro:

- [ ] Read `BRIEF.md` end-to-end. Confirm it represents the research target accurately. This is the highest-risk artifact; if the brief misframes the research, GPT-Pro builds for the wrong target.
- [ ] Read `PROMPT.md` end-to-end. Confirm scope and success criteria match what we want.
- [ ] Run the `cp` commands above to assemble the packet.
- [ ] Verify all six attachments exist in this folder.
- [ ] Check token count if you have a tokenizer (`tiktoken` against `gpt-4` works as a proxy). Should be ~98k.

## Spec doc

The design rationale for this packet is in:
`quality_reports/specs/2026-05-01_gptpro-v2-prompt-design.md`
