# Claim-Only P8 Meaning Gate Final Recommendation

## Recommendation

Freeze a minimally revised claim-only schema with named relation-label
additions.

Do not freeze `CLAIM_ONLY_P8` as-is. Do not promote
`EXPANDED_CLAIM_ONLY_P8` wholesale. The scalar expanded fields do not justify
provider-owned research labels, but the relation-label review found real graph
meaning that generic claim-only relation labels lose or make unstable.

## Evidence

The review used the completed Reference-9 Stage 2 artifacts:

- `CLAIM_ONLY_P8`: 88/88 completed, mean quote match 0.9974.
- `EXPANDED_CLAIM_ONLY_P8`: 88/88 completed, mean quote match 0.9935.
- `CLAIM_ONLY_P8` Stage 4 variance: 72/72 completed.

The semantic ledger covers all nine deals and 854 reviewed facts:

- 180 actor-class rows;
- 105 bid-formality rows;
- 148 proposal-scope rows;
- 64 drop-agency rows;
- 63 drop-reason rows;
- 264 initiation-side rows;
- 30 relation-label delta rows.

For scalar expanded fields, the source facts were mostly preserved by
claim-only through existing quote-bearing claims: actor/event/bid/count claims,
event subtypes, actor roles, bid stage/value fields, participation-count
`actor_class`, and relation `role_detail`. Missing scalar rows were prompt
recall gaps, not proof that the scalar should become production output.

For relation labels, the expanded candidate recovered necessary graph meaning:

- `voting_support_for` separates voting/support agreements from generic
  `supports`, which also covers financing support, guarantees, and other
  support-like facts.
- `committee_member_of` captures committee composition and board-member facts
  that claim-only sometimes leaves inside general actor quotes.
- `recused_from` captures recusal/exclusion as a graph relation rather than a
  loose event or actor quote.
- `rollover_holder_of` already preserves rollover source facts, but the final
  schema should use one clearer name and direction.

The failure ledger contains 24 real claim-only relation failures or label
collapses: 12 voting-support, 9 committee-member, and 3 recusal cases. These
are not region-selection misses; the selected windows contain the reviewed
source quotes.

No fresh Linkflow call was needed for this gate because the plan's required
candidate artifacts were already complete and the relation-label evidence is
present in the existing Stage 2 expanded outputs.

## Schema Changes

Adopt these relation labels in the final claim-only schema:

- `voting_support_for`
- `committee_member_of`
- `recused_from`

Revise the rollover label:

- Replace `rollover_holder_of` with one public label, preferably
  `rollover_holder_for`, and define direction explicitly.
- Do not keep both `rollover_holder_of` and `rollover_holder_for`.

Reject these scalar expanded fields:

- `actor_claims.actor_class`
- `bid_claims.bid_formality`
- `bid_claims.proposal_scope`
- `event_claims.drop_agency`
- `event_claims.drop_reason`
- `event_claims.initiation_side`

Prompt wording should still be tightened so claim-only extraction preserves
source indicators for strategic/financial labels, written/oral/non-binding bid
formality, dropout mode, dropout reason, and initiation source in ordinary
quote-backed claims.

## Remaining Risk

The main residual risk is prompt recall, not schema transport. The ledger marks
65 scalar rows as `fix_prompt_instruction`: these are cases where expanded
found a useful quote that claim-only did not preserve in the same reviewed
source-fact path. The fix should be targeted prompt wording and validation over
the same Reference-9 windows, not adoption of scalar provider judgments.

Rollover direction also needs a human-readable schema definition. The source
object can be a buyer vehicle, target, transaction, or rolled security. The
binding docs must define the object rule before implementation.

## Required Follow-Through

Update these files next:

- `docs/spec.md`
- `docs/llm-interface.md`
- `src/sec_graph/extract/llm/models.py`
- `src/sec_graph/extract/llm/convert.py`
- `src/sec_graph/extract/llm/prompt.py`
- `tests/test_llm_p7_contract.py`
- `tests/test_hard_reset_schema.py`

The follow-through should freeze a relation-revised claim-only P8 contract,
delete the scalar expanded fields from the production path, add tests for the
new relation labels, and keep Python ownership over coverage, source
coordinates, dispositions, canonicalization, and projection judgments.
