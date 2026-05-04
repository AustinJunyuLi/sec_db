"""Linkflow LLM call-shape probe matrix runner.

Project context:
    sec_graph (M&A SEC filing extraction) calls the Linkflow proxy
    (https://www.linkflow.run/v1) for gpt-5.5 with strict json_schema
    response_format. We are calibrating which schema shape and prompt shape
    yields the most stable, highest-quality typed-claim extraction.

Methodology:
    - Same input window (PetSmart 30K-char prefix from data/examples/)
      across all probes for direct comparison.
    - Stream via openai.AsyncOpenAI Responses API (matches sec_graph code).
    - reasoning.effort varies per probe (low|medium|high).
    - Fixed obligation list of 10 obligations to test coverage tracking.
    - Each probe records: duration, tokens, claim counts, quote-match-rate
      (verbatim substring search of input window), duplicate-quote count,
      empty-string-date emissions, ISO-format date count, Pydantic gate
      pass/fail (V0 schema only — variant schemas would mismatch).

Schema variants tested (see SCHEMAS dict below):
    V0  current sec_graph (auto from Pydantic model_json_schema())
    V2  rename "<X>_claims" -> "<X>s"
    V4  quote_text:str -> quote_texts:list[str]
    V5  collapse event_type+event_subtype -> single event_kind enum
    V6  add nullable obligation_id field on every claim

Prompt variants tested (see PROMPTS dict below):
    P0  current sec_graph build_window_prompt (single user message)
    P2  XML-tag structured (system+user, <goal>/<true_invariants>/...)
    P3  few-shot with one canonical example per claim type
    P5  validator-aware (system tells model what Python rejects)
    P7  validator-aware AND multi-quote-permissive (custom)

Invocation:
    LINKFLOW_API_KEY=sk-... .venv/bin/python lf_matrix.py V0:P7:low V4:P5:medium

API key handling:
    Read from LINKFLOW_API_KEY env var only. NEVER written to a file.
    Do NOT echo or persist the key.

Output:
    One JSON line per probe to stdout. Order matches argv.
"""
from __future__ import annotations

import asyncio
import copy
import hashlib
import json
import os
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any

from openai import AsyncOpenAI

from sec_graph.extract.llm.linkflow import _semantic_claim_schema

BASE_URL = "https://www.linkflow.run/v1"
MODEL = os.environ.get("LF_MODEL", "gpt-5.5")
TIMEOUT = 1200.0
PETSMART = Path("/Users/austinli/Projects/sec_graph/data/examples/petsmart-inc.md")
WINDOW_CHARS = 30000


def _client() -> AsyncOpenAI:
    api_key = os.environ.get("LINKFLOW_API_KEY")
    if not api_key:
        raise SystemExit("LINKFLOW_API_KEY missing")
    return AsyncOpenAI(api_key=api_key, base_url=BASE_URL, max_retries=0, timeout=TIMEOUT)


# ---------- Schema variants ----------

def schema_v0() -> dict[str, Any]:
    """sec_graph current — 6 separate top-level claim arrays."""
    return _semantic_claim_schema()


def schema_v2() -> dict[str, Any]:
    """V2: rename `<X>_claims` → `<X>s` and require all arrays."""
    s = copy.deepcopy(schema_v0())
    rename = {
        "actor_claims": "actors",
        "event_claims": "events",
        "bid_claims": "bids",
        "participation_count_claims": "participation_counts",
        "actor_relation_claims": "actor_relations",
    }
    new_props = {}
    for k, v in s["properties"].items():
        new_props[rename.get(k, k)] = v
    s["properties"] = new_props
    s["required"] = list(new_props)
    return s


def schema_v4() -> dict[str, Any]:
    """V4: replace quote_text:str with quote_texts:list[str] in each claim."""
    s = copy.deepcopy(schema_v0())
    for arr_key in (
        "actor_claims", "event_claims", "bid_claims",
        "participation_count_claims", "actor_relation_claims",
    ):
        item = s["properties"][arr_key]["items"]
        if "quote_text" in item.get("properties", {}):
            del item["properties"]["quote_text"]
            item["properties"]["quote_texts"] = {
                "type": "array",
                "items": {"type": "string"},
            }
            item["required"] = [
                ("quote_texts" if x == "quote_text" else x)
                for x in item["required"]
            ]
    return s


def schema_v5() -> dict[str, Any]:
    """V5: collapse event_type+event_subtype into combined event_kind."""
    s = copy.deepcopy(schema_v0())
    ev_item = s["properties"]["event_claims"]["items"]
    type_enum = ev_item["properties"]["event_type"]["enum"]
    subtype_enum = ev_item["properties"]["event_subtype"]["enum"]
    combined = sorted({f"{t}_{st}" for t in type_enum for st in subtype_enum})
    del ev_item["properties"]["event_type"]
    del ev_item["properties"]["event_subtype"]
    ev_item["properties"]["event_kind"] = {"type": "string", "enum": combined}
    ev_item["required"] = [
        x for x in ev_item["required"] if x not in {"event_type", "event_subtype"}
    ]
    if "event_kind" not in ev_item["required"]:
        ev_item["required"].insert(1, "event_kind")
    return s


def schema_v6() -> dict[str, Any]:
    """V6: add obligation_id (nullable) to every claim."""
    s = copy.deepcopy(schema_v0())
    for arr_key in (
        "actor_claims", "event_claims", "bid_claims",
        "participation_count_claims", "actor_relation_claims",
    ):
        item = s["properties"][arr_key]["items"]
        item["properties"]["obligation_id"] = {"type": ["string", "null"]}
        if "obligation_id" not in item["required"]:
            item["required"].append("obligation_id")
    return s


SCHEMAS = {
    "V0": schema_v0,
    "V2": schema_v2,
    "V4": schema_v4,
    "V5": schema_v5,
    "V6": schema_v6,
}


# ---------- Prompts ----------

OBLIGATIONS = [
    ("OBL-001", "event", "required", "Sales process initiation"),
    ("OBL-002", "participation_count", "required", "Bidder count at IOI stage"),
    ("OBL-003", "participation_count", "important", "Bidder count at first round"),
    ("OBL-004", "event", "required", "Final round bid receipt"),
    ("OBL-005", "event", "required", "Exclusivity grant"),
    ("OBL-006", "actor", "required", "Target board"),
    ("OBL-007", "actor", "required", "Financial advisor for target"),
    ("OBL-008", "actor", "required", "Legal advisor for target"),
    ("OBL-009", "bid", "required", "Final bid price"),
    ("OBL-010", "actor_relation", "important", "Buyer group composition"),
]
ALLOWED = "actor, event, bid, participation_count, actor_relation"
META = (
    "deal_slug: probe-deal\n"
    "filing_id: probe-filing-001\n"
    "region_id: probe-region-001\n"
    "region_kind: sale_process\n"
    "request_mode: semantic_claims_v1"
)


def obligations_block() -> str:
    return "\n".join(
        f"- {oid}: {kind} | {imp} | {label}"
        for oid, kind, imp, label in OBLIGATIONS
    )


def prompt_p0(text: str) -> tuple[str | None, str]:
    """V0 baseline — single user message."""
    user = (
        "Extract typed semantic claims from this single SEC merger filing window. "
        "Return strict JSON only. You propose meaning; Python proves quotes, "
        "coordinates, IDs, canonical rows, and projection rows.\n"
        "Do not emit char_start, char_end, canonical ids, projection rows, or provider-owned offsets. "
        "Every claim must include quote_text copied exactly from the window and appearing exactly once. "
        "Omit any claim whose quote cannot be copied exactly. Use closed enum values only. "
        "For optional date fields, return YYYY-MM-DD only when the date is explicit; otherwise return null. "
        "Never return an empty string for a date.\n"
        f"Allowed claim types for this request: {ALLOWED}.\n"
        "For each coverage obligation, either emit one or more supported claims or add a coverage result "
        "of no_supported_claim or ambiguous. Do not use missed; Python assigns missed when you fail to account for an obligation.\n\n"
        f"{META}\n\n"
        f"Coverage obligations:\n{obligations_block()}\n\n"
        f"Window paragraphs:\n[PARA-001]\n{text}\n"
    )
    return None, user


def prompt_p2(text: str) -> tuple[str, str]:
    """P2 XML-structured — system + user."""
    system = (
        "You extract typed semantic claims from SEC merger filing windows.\n"
        "<goal>Extract complete typed semantic claims. The window paragraphs are ground truth. "
        "Return strict JSON only conforming to the schema.</goal>\n"
        "<true_invariants>\n"
        "- Every claim must include quote_text copied exactly from the window and appearing exactly once.\n"
        "- Omit any claim whose quote cannot be copied exactly.\n"
        "- All enum fields use only closed values from the schema.\n"
        "- For optional date fields: YYYY-MM-DD when explicit; otherwise null. Never empty string.\n"
        "- For coverage_results: one entry per obligation with result of claims_emitted, no_supported_claim, or ambiguous.\n"
        "- Do not emit char_start, char_end, canonical ids, projection rows, or provider-owned offsets.\n"
        "- Do not use missed; Python assigns missed.\n"
        "</true_invariants>\n"
        "<critical_rules>\n"
        "Quote exactness: quote_text must be a character-exact substring from the window paragraphs. If the substring appears multiple times in the window, you cannot use it; omit the claim.\n"
        "Date discipline: YYYY-MM-DD only if the date is explicitly stated. If the text says 'early 2024' or 'Q2', leave the date null and convey rough timing in description.\n"
        "Enum compliance: use only listed values; no approximations.\n"
        "</critical_rules>\n"
        "<ambiguity_policy>\n"
        "When uncertain: missing fact → null; unsupported event → omit and emit coverage_result with ambiguous or no_supported_claim; ambiguous classification → null + lower confidence.\n"
        "</ambiguity_policy>"
    )
    user = (
        f"<request_metadata>\n{META}\nallowed_claim_types: {ALLOWED}\n</request_metadata>\n"
        f"<coverage_obligations>\n{obligations_block()}\n</coverage_obligations>\n"
        f"<window_paragraphs>\n[PARA-001]\n{text}\n</window_paragraphs>\n"
        "Extract claims. For each obligation, emit claims or a coverage_result. Return JSON only."
    )
    return system, user


def prompt_p3(text: str) -> tuple[str, str]:
    """P3 few-shot — system contains canonical examples."""
    system = (
        "You extract typed semantic claims from SEC merger filings. "
        "Window paragraphs are ground truth. Return strict JSON only matching the schema.\n"
        "<core_rules>\n"
        "- Every claim must include quote_text copied exactly from the window and appearing exactly once.\n"
        "- Omit claims whose quotes cannot be copied exactly.\n"
        "- All enum fields use closed values.\n"
        "- Dates: YYYY-MM-DD when explicit; otherwise null. Never empty string.\n"
        "- One coverage_result per coverage_obligation (claims_emitted | no_supported_claim | ambiguous).\n"
        "- Do not use missed; Python assigns missed.\n"
        "- Do not emit char_start, char_end, canonical ids, or provider-owned offsets.\n"
        "</core_rules>\n"
        "<canonical_examples>\n"
        "ACTOR: {\"claim_type\":\"actor\",\"actor_label\":\"Goldman Sachs\",\"actor_kind\":\"organization\","
        "\"observability\":\"named\",\"confidence\":\"high\","
        "\"quote_text\":\"Goldman Sachs, the target's financial advisor, was retained in April 2024.\"}\n"
        "EVENT: {\"claim_type\":\"event\",\"event_type\":\"process\",\"event_subtype\":\"nda_signed\","
        "\"event_date\":\"2024-05-15\",\"description\":\"Buyer Group A signed confidentiality agreement\","
        "\"actor_label\":\"Buyer Group A\",\"actor_role\":\"potential_buyer\",\"confidence\":\"high\","
        "\"quote_text\":\"On May 15, 2024, the Company signed a confidentiality agreement with Buyer Group A.\"}\n"
        "BID: {\"claim_type\":\"bid\",\"bidder_label\":\"Party X\",\"bid_date\":\"2024-06-10\","
        "\"bid_value\":null,\"bid_value_lower\":32.5,\"bid_value_upper\":null,"
        "\"bid_value_unit\":\"USD_per_share\",\"consideration_type\":\"cash\",\"bid_stage\":\"initial\","
        "\"confidence\":\"high\",\"quote_text\":\"Party X submitted a bid of $32.50 per share in cash.\"}\n"
        "COUNT: {\"claim_type\":\"participation_count\",\"process_stage\":\"first_round\",\"actor_class\":\"financial\","
        "\"count_min\":5,\"count_max\":null,\"count_qualifier\":\"exact\",\"confidence\":\"high\","
        "\"quote_text\":\"Five financial sponsors signed confidentiality agreements during the first round.\"}\n"
        "RELATION: {\"claim_type\":\"actor_relation\",\"subject_label\":\"Goldman Sachs\","
        "\"object_label\":\"Perceptive Equity Partners\",\"relation_type\":\"advises\","
        "\"role_detail\":\"financial advisor\",\"effective_date_first\":null,\"confidence\":\"medium\","
        "\"quote_text\":\"Perceptive Equity Partners, advised by Goldman Sachs, was one of the bidders.\"}\n"
        "</canonical_examples>\n"
        "<quote_discipline>\n"
        "Match exact substring from the window. If the phrase appears multiple times, skip the claim. "
        "Never paraphrase or reword quotes.\n"
        "</quote_discipline>"
    )
    user = (
        f"{META}\n"
        f"allowed_claim_types: {ALLOWED}\n\n"
        f"Coverage obligations:\n{obligations_block()}\n\n"
        f"Window paragraphs:\n[PARA-001]\n{text}\n\n"
        "Extract semantic claims using the canonical examples as a style guide. "
        "For each obligation, emit claims or report no_supported_claim/ambiguous in coverage_results. "
        "Return strict JSON only."
    )
    return system, user


def prompt_p5(text: str) -> tuple[str, str]:
    """P5 validator-aware — system tells the model what Python rejects."""
    system = (
        "You extract typed semantic claims from SEC merger filings. "
        "A deterministic Python validator will check your output. Know what it enforces.\n"
        "<what_python_validates>\n"
        "1. QUOTE EXACTNESS: every quote_text must be a character-exact substring of the window. If absent, the claim is rejected.\n"
        "2. QUOTE UNIQUENESS: if a quote_text appears more than once in the window, the claim is rejected.\n"
        "3. EMPTY-STRING DATES: any date field set to '' is rejected. Use null.\n"
        "4. ENUM COMPLIANCE: enum fields must be exact matches from the closed set; any other value is rejected.\n"
        "5. FIELD OWNERSHIP: bid fields belong to bid_claims only; non-bid claims with bid_value are rejected.\n"
        "6. OBLIGATION ACCOUNTING: one coverage_result per obligation; missing obligations get marked missed by Python.\n"
        "7. NULL DISCIPLINE: optional fields use null, not empty string, not 'unknown'.\n"
        "</what_python_validates>\n"
        "<your_response_rules>\n"
        "- Verify each quote_text exists verbatim and uniquely in the window before including the claim.\n"
        "- For ambiguous quotes (multiple matches), skip the claim and report no_supported_claim/ambiguous.\n"
        "- Use YYYY-MM-DD for dates only when explicit. Otherwise null.\n"
        "- Use only closed enum values; no approximations.\n"
        "- Emit one coverage_result per obligation; never use missed yourself.\n"
        "- Never emit empty string for any field; use null when unknown.\n"
        "- Do not emit char_start/char_end/canonical_ids.\n"
        "</your_response_rules>"
    )
    user = (
        f"{META}\nallowed_claim_types: {ALLOWED}\n\n"
        f"Coverage obligations:\n{obligations_block()}\n\n"
        f"Window paragraphs:\n[PARA-001]\n{text}\n\n"
        "Extract claims. Remember the validator's rules above. Return strict JSON only."
    )
    return system, user


def prompt_p7(text: str) -> tuple[str, str]:
    """P7: validator-aware AND multi-quote-friendly.

    Designed to unlock V4's multi-claim-per-quote freedom while preserving
    P5's obligation discipline and quote rigor.
    """
    system = (
        "You extract typed semantic claims from SEC merger filings. "
        "A deterministic Python validator will check your output. Know what it enforces.\n"
        "<what_python_validates>\n"
        "1. QUOTE EXACTNESS: every quote (or each entry in quote_texts) must be a character-exact substring of the window. If absent, the claim is rejected.\n"
        "2. QUOTE UNIQUENESS-IN-SOURCE: a quote that appears multiple times in the window cannot be unambiguously located. Pick a longer phrase that is unique in the window, OR omit the claim.\n"
        "3. SAME QUOTE ACROSS DIFFERENT CLAIMS IS FINE. One sentence may legitimately support an actor claim, an event claim, and a bid claim. You may emit all three claims pointing to the same quote.\n"
        "4. EMPTY-STRING DATES: any date field set to '' is rejected. Use null.\n"
        "5. ENUM COMPLIANCE: enum fields must be exact matches from the closed set; any other value is rejected.\n"
        "6. FIELD OWNERSHIP: bid fields belong to bid_claims only; non-bid claims with bid_value are rejected.\n"
        "7. OBLIGATION ACCOUNTING: emit exactly one coverage_result for EACH obligation listed. Missing obligations get marked missed by Python.\n"
        "8. NULL DISCIPLINE: optional fields use null, not empty string, not 'unknown'.\n"
        "</what_python_validates>\n"
        "<your_response_rules>\n"
        "- Extract every claim the window supports. Do not under-emit.\n"
        "- A single sentence often supports multiple distinct claims (an actor, an event, a relationship); emit each independently.\n"
        "- Pick quotes that are unique within the window. If a phrase repeats, choose a longer surrounding substring that is unique.\n"
        "- Use YYYY-MM-DD for dates only when explicit. Otherwise null.\n"
        "- Use only closed enum values; no approximations.\n"
        "- Emit one coverage_result per obligation; never use 'missed' yourself.\n"
        "- Never emit empty string for any field; use null when unknown.\n"
        "- Do not emit char_start/char_end/canonical_ids.\n"
        "</your_response_rules>"
    )
    user = (
        f"{META}\nallowed_claim_types: {ALLOWED}\n\n"
        f"Coverage obligations:\n{obligations_block()}\n\n"
        f"Window paragraphs:\n[PARA-001]\n{text}\n\n"
        "Extract every supported claim. Reuse quotes across distinct claims when warranted. "
        "Emit one coverage_result per obligation. Return strict JSON only."
    )
    return system, user


PROMPTS = {
    "P0": prompt_p0,
    "P2": prompt_p2,
    "P3": prompt_p3,
    "P5": prompt_p5,
    "P7": prompt_p7,
}


# ---------- Quality measurement ----------

def pydantic_validate(parsed: dict[str, Any]) -> dict[str, Any]:
    """Try to round-trip through sec_graph's actual SemanticClaimsPayload."""
    try:
        from sec_graph.extract.llm.models import SemanticClaimsPayload
        SemanticClaimsPayload.model_validate(parsed)
        return {"pydantic_ok": True}
    except Exception as exc:
        # Pydantic ValidationError surfaces a list of errors
        errs = []
        if hasattr(exc, "errors"):
            try:
                for e in exc.errors(include_input=False, include_context=False)[:10]:
                    errs.append({
                        "loc": ".".join(str(p) for p in e.get("loc", ())),
                        "type": e.get("type"),
                        "msg": (e.get("msg") or "")[:200],
                    })
            except Exception:
                pass
        return {"pydantic_ok": False, "error_type": type(exc).__name__, "errors_sample": errs}


def measure_quality(text: str, parsed: dict[str, Any], window_text: str) -> dict[str, Any]:
    """Compute quality metrics on a parsed response."""
    quotes: list[tuple[str, str]] = []  # (claim_type, quote)
    arrays = (
        "actor_claims", "actors",
        "event_claims", "events",
        "bid_claims", "bids",
        "participation_count_claims", "participation_counts",
        "actor_relation_claims", "actor_relations",
    )
    date_fields = {"event_date", "bid_date", "effective_date_first"}
    empty_string_dates = 0
    nonempty_dates: list[str] = []
    iso_dates = 0
    for arr_key in arrays:
        if arr_key not in parsed:
            continue
        items = parsed.get(arr_key) or []
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            ct = item.get("claim_type", arr_key)
            for q_key in ("quote_text", "quote_texts"):
                qv = item.get(q_key)
                if isinstance(qv, str):
                    quotes.append((ct, qv))
                elif isinstance(qv, list):
                    for q in qv:
                        if isinstance(q, str):
                            quotes.append((ct, q))
            for df in date_fields:
                v = item.get(df)
                if v == "":
                    empty_string_dates += 1
                elif isinstance(v, str):
                    nonempty_dates.append(v)
                    if len(v) == 10 and v[4] == "-" and v[7] == "-":
                        iso_dates += 1

    in_window = sum(1 for _ct, q in quotes if q and q in window_text)
    quote_counts = Counter(q for _ct, q in quotes if q)
    duplicates_in_response = sum(1 for q, c in quote_counts.items() if c > 1)
    # Window-level uniqueness: how many quotes appear >1 times in source?
    not_unique_in_window = 0
    for q in quote_counts.keys():
        if not q:
            continue
        if window_text.count(q) > 1:
            not_unique_in_window += 1

    return {
        "total_quotes": len(quotes),
        "quotes_in_window_verbatim": in_window,
        "quote_match_rate": round(in_window / len(quotes), 3) if quotes else None,
        "duplicate_quotes_within_response": duplicates_in_response,
        "not_unique_in_source_window": not_unique_in_window,
        "empty_string_dates": empty_string_dates,
        "nonempty_date_count": len(nonempty_dates),
        "iso_format_dates": iso_dates,
    }


def claim_counts(parsed: dict[str, Any]) -> dict[str, int]:
    out: dict[str, int] = {}
    for k, v in parsed.items():
        if isinstance(v, list):
            out[k] = len(v)
    return out


# ---------- Probe runner ----------

async def probe(schema_id: str, prompt_id: str, *, reasoning: str, label: str, window: str) -> dict[str, Any]:
    client = _client()
    schema_fn = SCHEMAS[schema_id]
    prompt_fn = PROMPTS[prompt_id]
    schema = schema_fn()
    schema_str = json.dumps(schema, sort_keys=True)
    schema_sha = hashlib.sha256(schema_str.encode()).hexdigest()[:12]
    system, user = prompt_fn(window)

    record: dict[str, Any] = {
        "label": label,
        "schema_id": schema_id,
        "prompt_id": prompt_id,
        "reasoning": reasoning,
        "window_chars": len(window),
        "schema_chars": len(schema_str),
        "schema_sha12": schema_sha,
        "model": MODEL,
    }
    input_payload = []
    if system:
        input_payload.append({"role": "system", "content": system})
    input_payload.append({"role": "user", "content": user})
    kwargs = {
        "model": MODEL,
        "reasoning": {"effort": reasoning},
        "input": input_payload,
        "text": {
            "format": {
                "type": "json_schema",
                "name": f"sec_graph_{schema_id}_{prompt_id}",
                "strict": True,
                "schema": schema,
            }
        },
    }
    record["prompt_chars_system"] = len(system) if system else 0
    record["prompt_chars_user"] = len(user)

    start = time.monotonic()
    try:
        text_parts: list[str] = []
        final = None
        missing_completed = False
        try:
            async with client.responses.stream(**kwargs) as stream:
                async for event in stream:
                    et = getattr(event, "type", "")
                    if et == "response.output_text.delta":
                        text_parts.append(getattr(event, "delta", "") or "")
                if hasattr(stream, "get_final_response"):
                    final = await stream.get_final_response()
        except RuntimeError as exc:
            if "response.completed" in str(exc) and text_parts:
                missing_completed = True
            else:
                raise
        text = "".join(text_parts)
        usage = getattr(final, "usage", None) if final else None
        record["status"] = getattr(final, "status", None) if final else None
        record["missing_completed"] = missing_completed
        record["input_tokens"] = getattr(usage, "input_tokens", None) if usage else None
        record["output_tokens"] = getattr(usage, "output_tokens", None) if usage else None
        details = getattr(usage, "output_tokens_details", None) if usage else None
        record["reasoning_tokens"] = getattr(details, "reasoning_tokens", None) if details else None
        record["text_chars"] = len(text)
        record["text_sha12"] = hashlib.sha256(text.encode()).hexdigest()[:12]
        record["result"] = "OK"
        try:
            parsed = json.loads(text) if text else {}
            record["claim_counts"] = claim_counts(parsed)
            record["quality"] = measure_quality(text, parsed, window)
            # Only validate against sec_graph Pydantic model when the schema
            # is V0-compatible (V2/V4/V5/V6 mutate keys or fields, so Pydantic
            # would fail for structural mismatch, not data quality).
            if schema_id == "V0":
                record["pydantic"] = pydantic_validate(parsed)
        except json.JSONDecodeError as exc:
            record["json_error"] = str(exc)[:200]
            record["result"] = "JSON_FAIL"
    except BaseException as exc:
        record["result"] = "FAIL"
        record["error_type"] = type(exc).__name__
        msg = str(exc)
        record["error_msg"] = msg[:600]
        status = getattr(exc, "status_code", None)
        if status is None:
            status = getattr(getattr(exc, "response", None), "status_code", None)
        record["http_status"] = status
    finally:
        record["duration_s"] = round(time.monotonic() - start, 2)
        close = getattr(client, "close", None)
        if close is not None:
            try:
                await close()
            except Exception:
                pass
    return record


async def main() -> int:
    petsmart = PETSMART.read_text(encoding="utf-8")
    window = petsmart[:WINDOW_CHARS]
    args = sys.argv[1:] or ["V0:P0:low"]
    for arg in args:
        parts = arg.split(":")
        if len(parts) < 2:
            print(f"bad arg {arg}; expected SCHEMA:PROMPT[:reasoning]", file=sys.stderr)
            continue
        schema_id, prompt_id, reasoning = (
            parts[0], parts[1], parts[2] if len(parts) > 2 else "low"
        )
        if schema_id not in SCHEMAS:
            print(f"unknown schema {schema_id}; known: {list(SCHEMAS)}", file=sys.stderr)
            continue
        if prompt_id not in PROMPTS:
            print(f"unknown prompt {prompt_id}; known: {list(PROMPTS)}", file=sys.stderr)
            continue
        rec = await probe(schema_id, prompt_id, reasoning=reasoning, label=arg, window=window)
        print(json.dumps(rec, sort_keys=True, default=str))
        await asyncio.sleep(1)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
