# LLM Extraction Interface

**Status:** Binding relation-revised claim-only P8 Linkflow contract for the
2026-05-04 schema freeze.

Linkflow GPT-5.5 is the primary live provider. Official OpenAI Responses API
and structured-output behavior inform the request shape, but this repository
does not silently switch providers.

## Request Shape

Production requests are evidence-map semantic windows covering one full
sale-process section region. Filings may yield multiple regions (e.g., a
tender-offer Offer to Purchase typically produces a `Background of the
Offer` region and a `Past Contacts, Transactions, Negotiations and
Agreements` region). The production model does not receive
single-paragraph windows, bounded snippets, or whole raw filings.

Each request contains:

- run id;
- request id;
- deal slug;
- filing id;
- region id;
- region kind;
- ordered paragraph references;
- applicable coverage obligations only (Python filters out the inapplicable
  audit rows before the request is built);
- allowed claim types (derived from the applicable obligations in the
  window);
- schema and extract versions;
- request mode `claim_only_p8_relation_v1`.

Linkflow never receives inapplicable obligations and is never asked to
emit absence judgments. Python alone decides whether an obligation is
applicable to a region (universal/conditional-with-trigger/scope-driven)
and writes that decision to `coverage_obligations` for audit before any
request is built.

The model sees one filing and one deal only. It receives no cross-deal context.
Default live Linkflow reasoning effort is `medium`. The only production request
mode is `claim_only_p8_relation_v1`; no legacy request mode is accepted.

## Response Shape

The model returns strict JSON with claim arrays only:

- `actor_claims`;
- `event_claims`;
- `bid_claims`;
- `participation_count_claims`;
- `actor_relation_claims`.

Every claim includes exact `quote_text` and one scalar
`coverage_obligation_id` naming the specific same-type obligation supported by
that claim. The request-specific schema constrains claim-family obligation ids,
so an actor claim cannot name an actor-relation obligation. The model never
returns source coordinates, canonical ids, projection rows, or provider-specific
canonical fields. P8 quote binding accepts one contiguous exact quote copied
from one ordered paragraph.

Provider responses are prohibited from containing:

```text
coverage_results
actor_claims.actor_class
bid_claims.bid_formality
bid_claims.proposal_scope
event_claims.drop_agency
event_claims.drop_reason
event_claims.initiation_side
source offsets
canonical ids
projection rows
```

The final actor relation enum is:

```text
member_of
affiliate_of
controls
acquisition_vehicle_of
advises
finances
supports
voting_support_for
rollover_holder_for
committee_member_of
recused_from
```

Relation directions are source-facing:

```text
voting_support_for: subject is the shareholder, officer, director, trust, or
supporting party; object is the buyer, parent, transaction, merger agreement,
or voting proposal named in the quote.

rollover_holder_for: subject is the holder rolling, contributing, or retaining
equity; object is the buyer vehicle, surviving company, target, transaction, or
rolled-security context named in the quote.

committee_member_of: subject is the person, director, representative, or named
member group; object is the committee or board named in the quote.

recused_from: subject is the recused or excluded person; object is the board,
committee, meeting, process, negotiation, evaluation, or transaction context
named in the quote.
```

## Python Proof

Python validates every provider result before insertion:

1. The provider completed under the strict Linkflow contract.
2. The payload validates against local Pydantic models.
3. Each `quote_text` resolves uniquely in the assembled source window.
4. The quote resolves to source spans owned by Python.
5. Closed enums validate.
6. Each claim's `coverage_obligation_id` exists in the request and matches the
   claim's type.
7. The claim is inserted with relational `claim_evidence`.

Coverage proof is obligation-specific. Python assigns `claims_emitted` only
from validated claim-to-obligation links, never from broad `claim_type` counts.
The validated claim-to-obligation edge is persisted in `claim_coverage_links`
and must agree with `coverage_results.claim_count`.
Python assigns `missed` when the applicable request window contains source
support but Linkflow returns no validated claim linked to the obligation.
Python assigns `no_supported_claim` when the window is relevant but contains no
source support for the applicable obligation, and `ambiguous` when Python cannot
safely classify source support after region and applicability review. Linkflow
does not return coverage results; Python alone writes the `coverage_results`
table after quote binding and claim-to-obligation validation.

The same quote may support multiple distinct claims when the source text
warrants that reuse. Quote reuse across claims is valid only when the quote
itself resolves uniquely in the source window. Absent or ambiguous quotes are
rejected. They are not salvaged into canonical rows.

## Provider Artifacts

Sanitized artifacts may contain run id, request id, deal slug, window id,
provider name, model, reasoning effort, finish status, attempt count, latency,
token usage when exposed, response digest, claim counts, inserted-claim count,
coverage obligation counts sourced from the request, and sanitized error
type/status.

Artifacts must not contain API keys, authorization headers, raw provider
bodies, full window text, paragraph text, or quote text.

## No Fallbacks

Missing `response.completed`, invalid JSON, invalid schema, unsupported
request parameters, ambiguous quotes, or missing required environment variables
are hard failures. There is no loose JSON reader and no legacy shape reader.
Whole raw filing extraction is not production mode and must not be used as a
fallback. No fallback, backward compatibility, legacy prompt path, flat schema
escape hatch, or loose parsing mode remains in the live contract.
