# LLM Extraction Interface

**Status:** Binding Linkflow typed-claim contract for the 2026-05-03 hard
reset.

Linkflow GPT-5.5 is the primary live provider. Official OpenAI Responses API
and structured-output behavior inform the request shape, but this repository
does not silently switch providers.

## Request Shape

Production requests are evidence-map semantic windows covering one full
`Background of the Merger` / sale-process section region. The production model
does not receive single-paragraph windows, bounded snippets, or whole raw filings.

Each request contains:

- run id;
- request id;
- deal slug;
- filing id;
- region id;
- region kind;
- ordered paragraph references;
- coverage obligations;
- allowed claim types;
- schema and extract versions;
- fixed request mode.

The model sees one filing and one deal only. It receives no cross-deal context.
Default live Linkflow reasoning effort is `high`.

## Response Shape

The model returns strict JSON with typed families:

- `actor_claims`;
- `event_claims`;
- `bid_claims`;
- `participation_count_claims`;
- `actor_relation_claims`;
- `coverage_results`.

Every claim includes exact `quote_text`. The model never returns source
coordinates, canonical ids, projection rows, or provider-specific canonical
fields. V0 quote binding accepts contiguous quote text copied from one ordered
paragraph.

## Python Proof

Python validates every provider result before insertion:

1. The provider completed under the strict Linkflow contract.
2. The payload validates against local Pydantic models.
3. Each `quote_text` resolves uniquely in the assembled source window.
4. The quote resolves to source spans owned by Python.
5. Closed enums validate.
6. The claim is inserted with relational `claim_evidence`.

The same quote may support multiple distinct claims when the source text
warrants that reuse. Quote reuse across claims is valid only when the quote
itself resolves uniquely in the source window. Absent or ambiguous quotes are
rejected. They are not salvaged into canonical rows.

## Provider Artifacts

Sanitized artifacts may contain run id, request id, deal slug, window id,
provider name, model, reasoning effort, finish status, attempt count, latency,
token usage when exposed, response digest, claim counts, inserted-claim count,
and sanitized error type/status.

Artifacts must not contain API keys, authorization headers, raw provider
bodies, full window text, paragraph text, or quote text.

## No Fallbacks

Missing `response.completed`, invalid JSON, invalid schema, unsupported
request parameters, ambiguous quotes, or missing required environment variables
are hard failures. There is no loose JSON reader and no legacy shape reader.
Whole raw filing extraction is not production mode and must not be used as a
fallback. No fallback, backward compatibility, legacy prompt path, flat schema
escape hatch, or loose parsing mode remains in the live contract.
