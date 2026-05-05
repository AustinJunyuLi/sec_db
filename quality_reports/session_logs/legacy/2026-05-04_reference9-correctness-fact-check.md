# Session Log: Reference-9 Correctness Fact Check

**Date:** 2026-05-04
**Scope:** Bounded local-agent fact-check suite over the nine Reference-9 deals only.

## Boundary

This fact check read only the nine Reference-9 local filings under `data/filings/`.
It did not inspect or characterize any 400-deal corpus.

The implementation target state differed from the repair plan's preflight
snapshot. The plan expected `main...origin/main [ahead 4]` with
`b07c0cb docs: design Reference-9 correctness repair` at the top of the recent
log. The live checkout was clean on `main...origin/main [ahead 5]`, with
`f096e77 docs: plan Reference-9 correctness repair` above `b07c0cb`. Work then
continued on branch `codex/reference9-correctness-repair`.

All Reference-9 filings were present locally.

## Confirmed False Positives

| Deal | Current expectation | Source truth | Evidence |
|---|---|---|---|
| Penford | `exclusivity_grant` is applicable. | Exclusivity was requested and declined, not granted. | `data/filings/penford/raw.md:1038` says the proposed price did not justify exclusivity; `data/filings/penford/raw.md:1044` says Penford again declined exclusive negotiations. |
| Penford | `recusal` is applicable. | Recusal language was conditional; the potentially conflicted SEACOR representative later reported SEACOR was not interested. | `data/filings/penford/raw.md:1026` contains conditional recusal language; `data/filings/penford/raw.md:1028` says SEACOR was not interested in a sale process at that time. |
| Zep | `special_committee` is applicable. | The board explicitly determined not to form a transaction committee. | `data/filings/zep/raw.md:866` says the board determined not to form a transaction committee. |
| Saks | `recusal` is applicable. | The only sale-process `did not participate` hit is unrelated bidder nonparticipation, not a director or fiduciary recusal. | `data/filings/saks/raw.md:902` says Company F did not participate in the offer submitted by Sponsor A and Sponsor G. |
| Medivation | `Past Contacts, Transactions, Negotiations and Agreements` is a selected extraction region. | The section is cross-reference-only and does not contain substantive sale-process narrative. | `data/filings/medivation/raw.md:630` is the heading; `data/filings/medivation/raw.md:632` points readers to other sections; the next section begins at `data/filings/medivation/raw.md:634`. |

## Region Substance Findings

| Deal | Candidate section | Classification | Evidence |
|---|---|---|---|
| Providence-Worcester | `Background of the Merger` | Substantive narrative | Heading at `data/filings/providence-worcester/raw.md:961`; dated process narrative starts at `data/filings/providence-worcester/raw.md:963`; next section at `data/filings/providence-worcester/raw.md:1049`. |
| Medivation | `Background of the Offer` | Substantive narrative | Heading at `data/filings/medivation/raw.md:554`; narrative begins at `data/filings/medivation/raw.md:558`; section runs through `data/filings/medivation/raw.md:628`. |
| Medivation | `Past Contacts, Transactions, Negotiations and Agreements` | Cross-reference-only | Heading at `data/filings/medivation/raw.md:630`; only cross-reference text at `data/filings/medivation/raw.md:632`; next section at `data/filings/medivation/raw.md:634`. |
| Imprivata | `Background of the Merger` | Substantive narrative | Heading at `data/filings/imprivata/raw.md:901`; material process facts continue through `data/filings/imprivata/raw.md:1113`. |
| Zep | `Background of the Merger` | Substantive narrative | Heading at `data/filings/zep/raw.md:744`; process narrative continues through `data/filings/zep/raw.md:910`. |
| PetSmart | `Background of the Merger` | Substantive narrative; current generated selection risk is wrong occurrence/TOC anchoring | Actual substantive heading at `data/filings/petsmart-inc/raw.md:1113`; TOC hit at `data/filings/petsmart-inc/raw.md:217` must be rejected. |
| Penford | `Background of the Merger` | Substantive narrative | Heading at `data/filings/penford/raw.md:968`; process narrative continues through `data/filings/penford/raw.md:1168`. |
| Mac-Gray | `Background of the Merger` | Substantive narrative; generated selection should not truncate mid-region | Heading at `data/filings/mac-gray/raw.md:726`; narrative continues through `data/filings/mac-gray/raw.md:984`; next section at `data/filings/mac-gray/raw.md:996`. |
| Saks | `Background of the Merger` | Substantive narrative | Heading at `data/filings/saks/raw.md:848`; process narrative continues through `data/filings/saks/raw.md:980`. |
| sTec | `Background of the Merger` | Substantive narrative | Heading at `data/filings/stec/raw.md:993`; process narrative continues through `data/filings/stec/raw.md:1217`. |

Table-of-contents or heading-only sale-process hits were identified for all
nine deals and must not be selected as substantive extraction regions:
Providence-Worcester `data/filings/providence-worcester/raw.md:184`,
Medivation `data/filings/medivation/raw.md:72`, Imprivata
`data/filings/imprivata/raw.md:157`, Zep `data/filings/zep/raw.md:182`,
PetSmart `data/filings/petsmart-inc/raw.md:217`, Penford
`data/filings/penford/raw.md:208`, Mac-Gray `data/filings/mac-gray/raw.md:175`,
Saks `data/filings/saks/raw.md:171`, and sTec `data/filings/stec/raw.md:238`.

## Coverage/Audit Findings

`coverage_results` is not currently auditable from DuckDB back to exact claims,
quotes, and source spans. The current converter increments an in-memory
`coverage_claim_counts` dictionary but does not persist the claim-to-obligation
edge after validating `payload.coverage_obligation_id`. Validation is therefore
count-only for emitted claims, and the proof CSV omits linked claim ids.

Required implementation consequence:

- Add `claim_coverage_links`.
- Populate it in `src/sec_graph/extract/llm/convert.py` after each claim insert.
- Validate `claims_emitted` and `claim_count` against persisted links.
- Export linked claim ids in the coverage proof surface.

## Proof/Docs Findings

Failed-validation runs currently stop after `validation_report.json`; projection
proof artifacts are only written after validation passes. The CLI must write a
concise `failed_validation_proof.json` before raising so red live runs remain
reproducible and auditable.

Active stale language found during review:

- `quality_reports/plans/2026-05-04_p8_region_applicability_ref9_plan.md`
  still says every current obligation needs a result, but current authority is
  every current applicable obligation.
- `quality_reports/session_logs/README.md` points to `docs/spec.md §1A`, while
  the live spec section is `docs/spec.md` `Schema Authority`.
- `docs/spec.md` and `docs/llm-interface.md` do not yet name the durable
  `claim_coverage_links` table.

## Implementation Consequences

- Source support must distinguish topic mentions from positive source facts.
- Fragile conditional obligations must not keep broad positive triggers for
  exclusivity, committee formation, recusal, rollover, voting support, buyer
  group, or financing.
- Region selection must operate on contiguous substantive runs and reject
  cross-reference-only candidates.
- Tender-offer ingest must independently enforce `EX-99.(A)(1)(A)` selection.
- Coverage proof must persist and validate claim-to-obligation links.
- Failed-validation runs must write proof metadata before aborting.
