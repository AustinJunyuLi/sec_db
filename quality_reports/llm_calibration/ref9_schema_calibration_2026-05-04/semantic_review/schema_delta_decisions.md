# Claim-Only P8 Schema Delta Decisions

## actor_claims.actor_class

Decision: reject as a production scalar.

Hard facts reviewed: the expanded run emitted 180 actor-class values: 117 `f`,
58 `s`, and 5 `mixed`. The source facts are real in many cases, for example
explicit financial-buyer labels, strategic-buyer labels, private-equity labels,
and industry-participant descriptions. In the ledger, 164 of 180 rows were
recoverable from claim-only quotes in actor, event, bid, or participation-count
claims; 16 rows were prompt-recall gaps, not evidence that the final schema
needs a provider-owned actor-class scalar.

Can Python derive it from claim-only output? Usually yes when the claim-only
quote preserves the source label. For missing rows, the repair is prompt
wording that forces the source label into a normal quote-bearing claim, not a
new `actor_claims.actor_class` field.

Provider-owned judgment risk: high. The tested values `s`, `f`, and `mixed` are
cryptic and can require inference from source text such as industry
participation, rather than direct filing labels.

Docs/spec change if adopted: none recommended. If later adopted, the values
must be plain labels such as `strategic`, `financial`, and `mixed`, and the
field must be source-indicator-only, not a final research classification.

## bid_claims.bid_formality

Decision: reject as a production scalar.

Hard facts reviewed: the expanded run emitted 105 bid-formality values: 61
`formal` and 44 `informal`. The reviewed source language already appears in
claim-only quote text and bid/event fields: written proposals, oral indications,
non-binding proposals, preliminary indications, revised LOIs, and best-and-final
offers.

Can Python derive it from claim-only output? Yes for 103 of 105 ledger rows. The
two remaining rows are prompt-recall issues where claim-only did not carry the
same bid quote, not cases where a formality scalar is the only solution.

Provider-owned judgment risk: medium. Formality is a research label. Linkflow
should preserve the exact source indicator; Python should assign the final
formal/informal boundary.

Docs/spec change if adopted: none recommended. Add prompt wording requiring
bid quotes to retain source indicators such as written, oral, non-binding,
preliminary, revised, final, and definitive.

## bid_claims.proposal_scope

Decision: reject.

Hard facts reviewed: all 148 expanded proposal-scope values were
`whole_company`. The ledger found no material asset-only, business-line,
minority-investment, or other non-whole-company proposal that claim-only failed
to preserve.

Can Python derive it from claim-only output? Yes or not needed. Whole-company
scope is already implied by ordinary bid quote text such as acquisition of the
company, all outstanding shares, merger consideration, or per-share acquisition
price.

Provider-owned judgment risk: medium. Scope should be inferred from source
indicators and should not be added merely for convenience.

Docs/spec change if adopted: none recommended.

## event_claims.drop_agency

Decision: reject as a scalar; keep the underlying source facts in event claims.

Hard facts reviewed: the expanded run emitted 64 drop-agency values:
36 `bidder`, 22 `target`, and 6 `mutual_or_process`. The reviewed facts include
bidder withdrawals, target exclusions, non-responses, cohort closures, and
declined advancement.

Can Python derive it from claim-only output? Yes for 58 of 64 rows using
`event_subtype`, `actor_role`, description, and quote text. The six missing
rows are prompt-recall gaps, not evidence that the scalar is necessary.

Provider-owned judgment risk: medium. The agency label is a derived dropout
classification. Linkflow should emit the event fact and quote; Python should
assign the final dropout taxonomy.

Docs/spec change if adopted: none recommended. Add prompt wording that
withdrawal, exclusion, no-response, and cohort-closure events must preserve the
actor and exact source reason.

## event_claims.drop_reason

Decision: reject as a scalar; keep source-backed event facts.

Hard facts reviewed: the expanded run emitted 63 drop-reason values, including
`withdrew`, `no_response`, `below_market`, `below_minimum`,
`terminated_process`, `never_advanced`, and `other`. Claim-only already uses
event subtypes such as `withdrawn_by_bidder`, `excluded_by_target`,
`non_responsive`, `cohort_closure`, and `advancement_declined` with exact
quotes for the important distinctions.

Can Python derive it from claim-only output? Yes for 57 of 63 rows. The missing
rows should be handled by prompt recall, because the source quote itself is the
needed fact.

Provider-owned judgment risk: medium. The final reason bucket is a projection
decision and should remain Python-owned.

Docs/spec change if adopted: none recommended.

## event_claims.initiation_side

Decision: reject as a scalar.

Hard facts reviewed: the expanded run emitted 264 initiation-side values:
140 `target`, 100 `bidder`, and 24 `mutual_or_process`. Claim-only generally
preserves the operative source language: board-authorized outreach, advisor
contact at committee direction, buyer approaches to management, process letters,
and mutual negotiation context.

Can Python derive it from claim-only output? Yes for 229 of 264 rows. The
remaining 35 rows are prompt-recall gaps where the underlying quote should be
retained in ordinary event claims.

Provider-owned judgment risk: medium to high. Initiation side is a research
classification; Linkflow should provide source-backed contact and outreach
events.

Docs/spec change if adopted: none recommended. Add prompt wording that
unsolicited buyer approaches, target-authorized outreach, advisor-directed
outreach, management-led contact, and mutual process contacts must be captured
as event facts with exact quotes.

## relation label: voting_support_for

Decision: adopt.

Hard facts reviewed: the expanded run emitted 12 `voting_support_for` relation
claims. The facts recur across PetSmart, Mac-Gray, Penford, Providence &
Worcester, and sTec. Claim-only usually preserves the quote as generic
`supports`, but `supports` is overloaded across voting agreements, financing
support, guarantees, non-competes, and other support-like facts.

Can Python derive it from claim-only output? Unclear. Python would have to parse
free-text `role_detail` and quote language to distinguish voting support from
other support. That is avoidable schema ambiguity.

Provider-owned judgment risk: low. A voting-support relation is a source fact
when the filing says a party executed a voting/support agreement or agreed to
vote shares for the transaction.

Docs/spec change if adopted: add `voting_support_for` to the
`actor_relation_claims.relation_type` enum and define direction as shareholder
or support party -> supported buyer, parent, transaction, or adoption proposal,
using the source quote and `role_detail` to disambiguate the object.

## relation label: rollover_holder_for / rollover_holder_of

Decision: revise, not reject.

Hard facts reviewed: `CLAIM_ONLY_P8` already preserves rollover facts through
`rollover_holder_of`; `EXPANDED_CLAIM_ONLY_P8` emits six
`rollover_holder_for` rows for Longview, Mr. MacDonald, and Moab. The source
facts are present in claim-only. The problem is naming and direction, not
missing recall.

Can Python derive it from claim-only output? Yes. Claim-only has the relation
claim and exact quote for the reviewed rollover facts.

Provider-owned judgment risk: low if the relation only records the source fact
that a holder rolls or may roll equity into the transaction. The risk is
directional ambiguity if the object can be buyer vehicle, target stock, or the
transaction itself.

Docs/spec change if adopted: choose one public name and direction. Prefer
`rollover_holder_for`; define subject as the rollover holder and object as the
transaction counterparty, buyer vehicle, target, or transaction object named in
the quote. Do not keep both names.

## relation label: committee_member_of

Decision: adopt.

Hard facts reviewed: the expanded run emitted nine `committee_member_of` rows.
Claim-only sometimes preserves the quote as a generic `member_of` relation or
actor quote, but it misses the typed relation in meaningful cases: Providence &
Worcester's Transaction Committee members, sTec's special committee composition
and later added member, and Penford's SEACOR board representative.

Can Python derive it from claim-only output? No in repeated cases. It would
require parsing names and committee membership out of general actor quotes.

Provider-owned judgment risk: low. Committee membership is a source relation
when the filing says a committee is composed of named people, a person is on a
board, or a person was added to a committee.

Docs/spec change if adopted: add `committee_member_of` to the
`actor_relation_claims.relation_type` enum and define direction as person or
member group -> committee or board.

## relation label: recused_from

Decision: adopt.

Hard facts reviewed: the expanded run emitted three `recused_from` rows:
Mr. MacDonald and Mr. Rothenberg in Mac-Gray, and Alfred P. Smith in Providence
& Worcester. Claim-only sometimes preserves the quote as an event or actor
claim, but not as a typed recusal relation. Stage 4 also showed instability in
the Mac-Gray recusal quote: one replica did not preserve the reviewed quote
while another did.

Can Python derive it from claim-only output? No reliably. Recusal is a
relationship between a person and a board/process context. Existing claim-only
event fields can describe exclusion, but they do not create a stable graph
relation.

Provider-owned judgment risk: low. A recusal/exclusion relation is source-backed
when the filing says a person recused himself or was excluded from a process,
meeting, evaluation, or negotiation.

Docs/spec change if adopted: add `recused_from` to the
`actor_relation_claims.relation_type` enum and define direction as recused or
excluded person -> process, committee, board meeting, negotiation, or evaluation
context named in the source quote.
