# Reference-9 Correctness Repair Design

**Date:** 2026-05-04
**Status:** Design approved for implementation planning.
**Parent authority:** `docs/superpowers/specs/2026-05-03-pipeline-hard-reset-design.md`

## Purpose

The Reference-9 P8 region-applicability work is not finished until the offline
gate stops approving false facts. Passing tests are not enough if the expected
answers are wrong. This repair is correctness-first: it should make bad source
interpretations fail loudly even if the next live Reference-9 run still fails
validation.

The central rule is:

```text
A filing topic mention is not proof that the positive fact happened.
```

For example, "exclusivity was requested" or "exclusivity was declined" is not
an exclusivity grant. "The board determined not to form a transaction
committee" is not committee membership. A bidder not participating is not a
director recusal. A heading plus a cross-reference is not a substantive
sale-process region.

## Non-Negotiable Boundaries

- No fallbacks.
- No backward compatibility paths.
- No provider-owned coverage results.
- No provider-owned source offsets.
- The Linkflow P8 response contract remains frozen: positive typed claim arrays
  only, with exact `quote_text` and one scalar `coverage_obligation_id`.
- Python owns source regions, applicability, quote binding, durable proof links,
  coverage results, validation, projection, and proof metadata.
- `data/filings/` is local research data and must not be deleted.
- Generated run payloads stay under ignored `runs/`, `artifacts/`, or `tmp/`.

## Repair Strategy

Use Approach A: correctness gate first.

The immediate objective is not to make every live run green. The objective is to
make the offline Reference-9 gate honest. A red live run is acceptable when it
points to true missing support, true model recall failure, or true ambiguity.
What is not acceptable is a green test suite that blesses false positives.

## Components

### 1. Region Builder

The region builder decides what text becomes an extraction window.

Required behavior:

- Build regions from contiguous paragraph runs.
- Do not merge two same-named section headings across an intervening section.
- Reject heading-only, cross-reference-only, and non-substantive candidates.
- Preserve exact paragraph ids and source order for every accepted region.
- Keep deterministic ordering across runs.

Current risk to fix: repeated sale-process headings with another section between
them can be merged into one non-contiguous window. Medivation's
`Past Contacts, Transactions, Negotiations and Agreements` region also appears
to include only a heading/cross-reference and should not become a live extraction
window unless the source text contains substantive sale-process facts.

### 2. Applicability Engine

The applicability engine decides which obligations are fair to ask for a region.

Required behavior:

- Separate a topic trigger from proof of the positive fact.
- Treat negated, declined, hypothetical, requested-only, or unrelated mentions
  as insufficient for positive applicability unless the specific obligation is
  defined to cover those cases.
- Add explicit positive and negative patterns for fragile obligations:
  exclusivity, committee, recusal, voting support, rollover, buyer group, and
  financing.
- Record deterministic reason codes and basis snippets for both applicable and
  not-applicable decisions.
- Never ask Linkflow to emit absence judgments.

Examples:

- `granted exclusivity` can support asking for `exclusivity_grant`.
- `requested exclusivity`, `declined exclusivity`, or `exclusivity was not
  justified` cannot by itself support `exclusivity_grant`.
- `formed a transaction committee` can support committee obligations.
- `determined not to form a transaction committee` cannot.
- `director recused himself from the board's evaluation` can support recusal.
- `Company F did not participate in an offer` cannot.

### 3. Reference-9 Fact Ledger

The Reference-9 fixture should become a compact source-truth ledger, not just a
count-and-trigger fixture.

Required behavior:

- Preserve the nine-deal acceptance set:
  `providence-worcester`, `medivation`, `imprivata`, `zep`, `petsmart-inc`,
  `penford`, `mac-gray`, `saks`, and `stec`.
- For each deal, record selected substantive regions and rejected candidate
  regions when relevant.
- For fragile obligations, record small positive and negative source facts with
  line/snippet references or exact short snippets.
- Make the offline gate compare production behavior to these source facts.
- Do not commit full filing text.

Known fact-check repairs required:

- Penford: declined or not-justified exclusivity must not become an exclusivity
  grant; conditional recusal language must not become actual recusal when the
  condition is disclaimed.
- Zep: a board decision not to form a transaction committee must not become a
  special committee obligation.
- Saks: bidder non-participation must not become board/member recusal.
- Medivation: a cross-reference-only `Past Contacts` region must not become a
  substantive extraction region.

### 4. Coverage Link Table

The database must retain which claim satisfied which obligation.

Required behavior:

- Persist a durable claim-to-obligation relation after Python validates the
  provider's `coverage_obligation_id`.
- Allow the same claim to support exactly the obligation id it named, and no
  broad claim-type matching.
- Make `coverage_results.claim_count` auditable from persisted links.
- Validation should fail if `claims_emitted` has no persisted linked claim.
- The proof surface should let an operator trace:

```text
coverage obligation -> coverage result -> linked claim -> quote -> source span
```

The provider response shape must not change. This is a Python/DuckDB proof
repair, not a Linkflow schema widening.

### 5. Validation And Proof

Validation should reject misleading proof rows.

Required behavior:

- Every current applicable obligation must have exactly one current coverage
  result.
- Current not-applicable obligations must not have current coverage results.
- Required or important applicable obligations whose result is `missed`,
  `no_supported_claim`, or `ambiguous` remain hard failures.
- `claims_emitted` must be backed by persisted claim-to-obligation links.
- Final proof artifacts should use current rows or expose enough history fields
  to make superseded rows obvious.
- Failed-validation live runs should still leave concise metadata that explains
  what happened without pretending projection completed.

Proof metadata should include exact commands, run ids, run dirs, resolved commit,
provider settings, request mode, reasoning effort, elapsed/runtime information,
sanitized provider artifact counts, validation verdict, and unresolved
obligations.

### 6. Tender-Offer Fail-Loud Ingest

Ingest must independently enforce the tender-offer source rule.

Required behavior:

- If a manifest says the parent filing is `SC TO-T` or `SC TO-T/A`, ingest must
  verify that the selected document is the `EX-99.(A)(1)(A)` Offer to Purchase
  exhibit.
- A cover-form or stale/bad manifest must fail loudly.
- The Medivation Reference-9 fixture remains the positive tender-offer case.
- Add a negative ingest test with a manifest that claims `SC TO-T` but does not
  select the required exhibit.

## Data Flow

The repaired flow is:

```text
raw filing text
-> section assignment
-> contiguous region candidates
-> reject empty/cross-reference-only regions
-> applicability decisions with positive/negative evidence
-> Linkflow request with applicable obligations only
-> Linkflow positive claims
-> Python quote binding
-> persisted claim-to-obligation links
-> Python coverage results
-> validation
-> proof logs
```

There are two different evidence roles:

- Applicability evidence says it is fair to ask about a topic in this region.
- Support evidence says the filing actually supports the positive fact.

These must not be collapsed. A trigger phrase can make a question relevant
without proving that the answer is positive.

## Testing Requirements

Tests should be added in red-first order.

1. Raw-fact negative tests:
   - Penford declined/not-justified exclusivity.
   - Penford conditional recusal disclaimed by later text.
   - Zep no transaction committee.
   - Saks bidder non-participation.
   - Medivation cross-reference-only `Past Contacts` region.

2. Continuous-region tests:
   - Repeated sale-process headings separated by another section do not become
     one merged region.
   - Non-substantive candidates are rejected or recorded as rejected candidates,
     not sent to Linkflow.

3. Applicability positive/negative tests:
   - Positive phrases make obligations applicable.
   - Negated, declined, requested-only, hypothetical, or unrelated mentions do
     not create false applicability.

4. Coverage-link tests:
   - Inserted claims persist their validated obligation link.
   - `coverage_results.claim_count` agrees with persisted links.
   - `claims_emitted` without a linked claim fails validation.

5. Validation tests:
   - A not-applicable obligation with a current coverage result fails.
   - Required/important unresolved applicable obligations fail.
   - Superseded or historical rows do not silently pollute final proof outputs.

6. Proof tests:
   - Failed-validation live-like runs leave enough metadata to audit the failure.
   - Logs and docs do not claim proof artifacts that the production CLI cannot
     actually emit.

## Local-Agent Fact-Check Model

Before implementation rewrites fixtures, deploy read-only local agents over
separate fact lanes. This is a bounded Reference-9 fact-check test suite, not a
corpus-scale review. Its purpose is to check whether the system is mature enough
to handle the nine reference deals honestly. Agents must not be asked to read or
fact-check the 400-deal corpus as part of this repair.

The local agents' job is to read Reference-9 source text and authority docs, not
to optimize code style.

Required lanes:

1. Raw Reference-9 fact ledger:
   - Read `data/filings/*/raw.md` only for the nine Reference-9 deals.
   - Produce compact positive facts, negative facts, cross-reference-only
     sections, and exact line/snippet references.

2. Applicability false-positive review:
   - Check conditional obligations for trigger words that do not support the
     positive fact.
   - Focus on exclusivity, committee, recusal, voting support, rollover, buyer
     group, and financing.

3. Region substance review:
   - Label selected regions as substantive narrative, cross-reference-only,
     heading-only, duplicated/non-contiguous, or ambiguous.

4. Coverage/audit schema review:
   - Check whether every claimed coverage result can be traced from obligation
     to claim to quote to source span.

5. Proof/docs review:
   - Check active docs, session logs, commands, and proof metadata for
     reproducibility and stale claims.

Disagreement rule:

```text
filing text wins
then docs/spec.md and docs/llm-interface.md
then implementation plans
then current tests
```

## Acceptance

The repair is complete when:

- Full tests pass.
- Reference-9 offline gate passes with corrected source facts.
- False-positive applicability cases are covered by tests.
- Region windows are contiguous and substantive.
- Claim-to-obligation proof is persisted and validated.
- Tender-offer ingest fails loudly on bad selected documents.
- Active docs and session logs no longer claim more proof than the committed
  artifacts support.
- Live proof is rerun if credentials are available; red validation is acceptable
  if the failure is honest and well logged.

## Out Of Scope

- Reopening the P8 provider schema.
- Adding provider-owned absence judgments.
- Tuning prompts merely to make live validation pass.
- Full-corpus execution beyond Reference-9.
- Deleting local filing source material.
