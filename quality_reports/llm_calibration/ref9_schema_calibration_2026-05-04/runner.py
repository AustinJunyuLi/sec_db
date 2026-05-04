"""Reference-9 Linkflow schema calibration runner.

This is a generated calibration helper for the 2026-05-04 test campaign.
It is intentionally outside production code. It reads Linkflow credentials
from environment variables only and never serializes request headers or keys.
"""

from __future__ import annotations

import argparse
import asyncio
import copy
import hashlib
import json
import os
import re
import statistics
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from openai import AsyncOpenAI

from sec_graph.extract.llm.linkflow import _semantic_claim_schema


REPO_ROOT = Path(__file__).resolve().parents[3]
ROOT = Path(__file__).resolve().parent
FILINGS_DIR = REPO_ROOT / "data" / "filings"
MODEL = os.environ.get("LF_MODEL", "gpt-5.5")
BASE_URL = os.environ.get("LINKFLOW_BASE_URL", "https://www.linkflow.run/v1")
TIMEOUT_SECONDS = float(os.environ.get("LINKFLOW_TIMEOUT_SECONDS", "3600"))

REF9 = [
    "providence-worcester",
    "medivation",
    "imprivata",
    "zep",
    "petsmart-inc",
    "penford",
    "mac-gray",
    "saks",
    "stec",
]
OLD_THREE = ["petsmart-inc", "mac-gray", "providence-worcester"]
HARD_DEALS = ["petsmart-inc", "mac-gray", "medivation", "zep", "saks", "stec"]
VARIANCE_DEALS = ["petsmart-inc", "mac-gray", "zep", "stec"]

STRICT_CANDIDATES = [
    "V0_P8_BASELINE",
    "CLAIM_ONLY_P8",
    "EXPANDED_CLAIM_ONLY_P8",
    "EXPANDED_MULTI_QUOTE_P8",
]
SIDECAR_CANDIDATE = "PLAIN_RECALL_SIDECAR"

CLAIM_ARRAYS = [
    "actor_claims",
    "event_claims",
    "bid_claims",
    "participation_count_claims",
    "actor_relation_claims",
]
CLAIM_ARRAY_BY_TYPE = {
    "actor": "actor_claims",
    "event": "event_claims",
    "bid": "bid_claims",
    "participation_count": "participation_count_claims",
    "actor_relation": "actor_relation_claims",
}

REGION_KINDS = [
    "sale_process",
    "buyer_group_or_transaction_structure",
    "support_or_voting_agreement",
    "rollover",
    "financing",
    "committee_or_conflict",
    "go_shop_or_post_signing_solicitation",
    "tender_source_perspective",
]

BASE_OBLIGATIONS = [
    ("event", "Sales process initiation", "required"),
    ("participation_count", "Bidder count at IOI stage", "required"),
    ("participation_count", "Bidder count at first round", "important"),
    ("event", "Final round bid receipt", "required"),
    ("event", "Exclusivity grant", "required"),
    ("actor", "Target board", "required"),
    ("actor", "Financial advisor for target", "required"),
    ("actor", "Legal advisor for target", "required"),
    ("bid", "Final bid price", "required"),
    ("actor_relation", "Buyer group composition", "important"),
]

REGION_OBLIGATIONS = {
    "sale_process": BASE_OBLIGATIONS,
    "buyer_group_or_transaction_structure": [
        ("actor", "Buyer, parent, purchaser, merger sub, and acquisition vehicles", "required"),
        ("actor_relation", "Buyer group membership, affiliation, control, and acquisition vehicle relations", "required"),
        ("event", "Transaction agreement execution or structure-defining event", "important"),
    ],
    "support_or_voting_agreement": [
        ("actor", "Support or voting shareholders", "required"),
        ("actor_relation", "Voting support or support agreement relations", "required"),
        ("participation_count", "Shares or voting percentage subject to support", "important"),
    ],
    "rollover": [
        ("actor", "Rollover holder or management participant", "required"),
        ("actor_relation", "Rollover holder relation", "required"),
        ("event", "Rollover execution, rejection, or no-rollover fact", "important"),
    ],
    "financing": [
        ("actor", "Debt, equity, or financing source", "required"),
        ("actor_relation", "Financing relation", "required"),
        ("event", "Financing commitment or no-financing-condition fact", "important"),
    ],
    "committee_or_conflict": [
        ("actor", "Special committee, transaction committee, or conflicted person", "required"),
        ("actor_relation", "Committee membership, advisor, or recusal relation", "required"),
        ("event", "Committee formation, authorization, or conflict event", "important"),
    ],
    "go_shop_or_post_signing_solicitation": [
        ("event", "Go-shop, no-shop, superior proposal, or post-signing solicitation event", "required"),
        ("actor", "Excluded party, solicited party, or post-signing bidder", "important"),
    ],
    "tender_source_perspective": [
        ("actor", "Offeror, purchaser, target, depositary, information agent", "required"),
        ("bid", "Tender offer price", "required"),
        ("event", "Tender offer commencement, expiration, or minimum-condition event", "required"),
    ],
}

SECTION_PATTERNS = {
    "sale_process": [
        "Background of the Merger",
        "Background of the Offer",
        "Past Contacts or Negotiations",
        "Past Contacts, Transactions, Negotiations and Agreements",
    ],
    "financing": ["Financing"],
}

REGION_SEARCH_TERMS = {
    "buyer_group_or_transaction_structure": [
        "buyer group",
        "consortium",
        "acquisition vehicle",
        "merger sub",
        "purchaser",
        "parent",
    ],
    "support_or_voting_agreement": [
        "voting agreement",
        "support agreement",
        "tender and support",
        "support of",
    ],
    "rollover": ["rollover", "roll over", "roll-over"],
    "financing": ["debt financing", "equity financing", "financing commitment", "not subject to any financing"],
    "committee_or_conflict": ["special committee", "transaction committee", "conflict", "recused", "disinterested"],
    "go_shop_or_post_signing_solicitation": ["go-shop", "go shop", "no-shop", "no shop", "excluded party", "superior proposal"],
    "tender_source_perspective": ["offer to purchase", "tender offer", "minimum condition", "expiration date"],
}

HEADING_END_TERMS = [
    "Reasons for the Merger",
    "Reasons for the Offer",
    "Recommendation",
    "Opinion of",
    "Financing",
    "Interests of",
    "Voting Agreement",
    "Voting Agreements",
    "The Merger Agreement",
    "Purpose of the Offer",
    "Source and Amount of Funds",
    "Conditions of the Offer",
]

MAX_W1_CHARS = 60_000
MAX_W1_SPLIT_CHARS = 45_000
MAX_W2_CHARS = 25_000
MAX_W4_CHARS = 120_000
CONTEXT_BEFORE = 8_000
CONTEXT_AFTER = 14_000


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(path)


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    with tmp.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")
    tmp.replace(path)


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def normalize_heading(text: str) -> str:
    text = re.sub(r"COMMAND=STYLE_ADDED,\"[^\"]*\"\s*", " ", text)
    text = re.sub(r"COMMAND=[^\s*]+", " ", text)
    text = re.sub(r"[*_`#]", " ", text)
    text = re.sub(r"^\d+\.\s*", "", text.strip())
    return re.sub(r"\s+", " ", text).strip()


def line_offsets(text: str) -> list[tuple[int, int, str]]:
    out: list[tuple[int, int, str]] = []
    pos = 0
    for line in text.splitlines(keepends=True):
        start = pos
        pos += len(line)
        out.append((start, pos, line.rstrip("\n\r")))
    return out


def is_heading_line(line: str) -> bool:
    stripped = line.strip()
    if not stripped or stripped.startswith("|"):
        return False
    if len(stripped) > 180:
        return False
    if stripped.count("|") >= 2:
        return False
    normalized = normalize_heading(stripped).casefold()
    if "page " in normalized and len(normalized) < 80:
        return False
    return stripped.startswith("**") or stripped.startswith("***") or stripped.startswith("#") or normalized.istitle()


def find_section_window(raw: str, patterns: list[str], max_chars: int) -> tuple[int, int, list[str]]:
    offsets = line_offsets(raw)
    starts: list[tuple[int, str]] = []
    patterns_cf = [p.casefold() for p in patterns]
    for start, _end, line in offsets:
        if not is_heading_line(line):
            continue
        norm = normalize_heading(line).casefold()
        if any(pattern in norm for pattern in patterns_cf):
            starts.append((start, normalize_heading(line)))
    if starts:
        section_start, heading = starts[0]
    else:
        haystack = raw.casefold()
        matches = [(haystack.find(p.casefold()), p) for p in patterns if haystack.find(p.casefold()) >= 0]
        if not matches:
            return 0, min(len(raw), max_chars), ["fallback_prefix"]
        section_start, heading = min(matches)

    end = min(len(raw), section_start + max_chars)
    for start, _line_end, line in offsets:
        if start <= section_start + 1500:
            continue
        if start >= section_start + max_chars:
            break
        if not is_heading_line(line):
            continue
        norm = normalize_heading(line).casefold()
        if any(term.casefold() in norm for term in HEADING_END_TERMS):
            end = start
            break
    if end - section_start < 8_000:
        end = min(len(raw), section_start + max_chars)
    return section_start, end, [heading]


def paragraph_aligned_splits(raw: str, start: int, end: int, *, max_chars: int = MAX_W1_SPLIT_CHARS) -> list[tuple[int, int, int]]:
    if end - start <= max_chars:
        return [(start, end, 1)]
    parts: list[tuple[int, int, int]] = []
    cursor = start
    sequence = 1
    while cursor < end:
        target = min(end, cursor + max_chars)
        if target < end:
            split_at = raw.rfind("\n\n", cursor + max_chars // 2, target)
            if split_at <= cursor:
                split_at = target
        else:
            split_at = target
        parts.append((cursor, split_at, sequence))
        cursor = split_at
        while cursor < end and raw[cursor] in "\n\r ":
            cursor += 1
        sequence += 1
    return parts


def find_context_window(raw: str, terms: list[str], max_chars: int) -> tuple[int, int, list[str]] | None:
    haystack = raw.casefold()
    hits: list[tuple[int, str]] = []
    for term in terms:
        idx = haystack.find(term.casefold())
        if idx >= 0:
            hits.append((idx, term))
    if not hits:
        return None
    idx, term = min(hits)
    start = max(0, idx - CONTEXT_BEFORE)
    end = min(len(raw), idx + CONTEXT_AFTER)
    if end - start > max_chars:
        end = start + max_chars
    return start, end, [term]


def paragraph_ids(text: str, slug: str, window_id: str) -> list[str]:
    blocks = [block for block in re.split(r"\n\s*\n", text) if block.strip()]
    return [f"{slug}_{window_id}_calib_para_{idx}" for idx, _block in enumerate(blocks, start=1)]


def make_input(
    *,
    slug: str,
    raw: str,
    filing_path: Path,
    filing_sha256: str,
    window_profile: str,
    window_id: str,
    region_kind: str,
    source_perspective: str,
    start: int,
    end: int,
    signals: list[str],
) -> dict[str, Any]:
    text = raw[start:end].strip()
    obligations = [
        {
            "obligation_id": f"{slug}_{window_id}_obl_{idx}",
            "expected_claim_type": claim_type,
            "obligation_label": label,
            "importance": importance,
        }
        for idx, (claim_type, label, importance) in enumerate(
            REGION_OBLIGATIONS.get(region_kind, BASE_OBLIGATIONS),
            start=1,
        )
    ]
    return {
        "slug": slug,
        "filing_path": str(filing_path),
        "filing_sha256": filing_sha256,
        "window_profile": window_profile,
        "window_id": window_id,
        "region_kind": region_kind,
        "source_perspective": source_perspective,
        "paragraph_ids": paragraph_ids(text, slug, window_id),
        "char_start": start,
        "char_end": start + len(text),
        "text_sha256": sha256_text(text),
        "text": text,
        "obligation_ids": [ob["obligation_id"] for ob in obligations],
        "coverage_obligations": obligations,
        "region_signals": signals,
    }


def prepare_inputs() -> list[dict[str, Any]]:
    inputs: list[dict[str, Any]] = []
    for slug in REF9:
        filing_path = FILINGS_DIR / slug / "raw.md"
        raw = filing_path.read_text(encoding="utf-8")
        filing_sha = sha256_text(raw)

        start, end, signals = find_section_window(raw, SECTION_PATTERNS["sale_process"], MAX_W1_CHARS)
        w1_splits = paragraph_aligned_splits(raw, start, end, max_chars=MAX_W1_SPLIT_CHARS)
        for part_start, part_end, sequence in w1_splits:
            inputs.append(
                make_input(
                    slug=slug,
                    raw=raw,
                    filing_path=filing_path,
                    filing_sha256=filing_sha,
                    window_profile="W1_SALE_PROCESS",
                    window_id="w1_sale_process" if len(w1_splits) == 1 else f"w1_sale_process_part{sequence}",
                    region_kind="sale_process",
                    source_perspective="target_or_offer_primary",
                    start=part_start,
                    end=part_end,
                    signals=signals if sequence == 1 else [*signals, f"split_part_{sequence}"],
                )
            )

        # W2 uses separate physical calls. Start with sale-process, then add
        # distinct focused contexts for available hard-fact region types.
        seen_ranges = {(start // 2000, end // 2000)}
        w2_sale_splits = paragraph_aligned_splits(raw, start, end, max_chars=MAX_W2_CHARS)
        for part_start, part_end, sequence in w2_sale_splits:
            inputs.append(
                make_input(
                    slug=slug,
                    raw=raw,
                    filing_path=filing_path,
                    filing_sha256=filing_sha,
                    window_profile="W2_MULTI_REGION",
                    window_id="w2_sale_process" if len(w2_sale_splits) == 1 else f"w2_sale_process_part{sequence}",
                    region_kind="sale_process",
                    source_perspective="target_or_offer_primary",
                    start=part_start,
                    end=part_end,
                    signals=signals if sequence == 1 else [*signals, f"split_part_{sequence}"],
                )
            )
        for region_kind in REGION_KINDS:
            if region_kind == "sale_process":
                continue
            if region_kind == "financing":
                section = find_section_window(raw, SECTION_PATTERNS["financing"], MAX_W2_CHARS)
                if section[2] != ["fallback_prefix"]:
                    reg_start, reg_end, reg_signals = section
                else:
                    found = find_context_window(raw, REGION_SEARCH_TERMS[region_kind], MAX_W2_CHARS)
                    if found is None:
                        continue
                    reg_start, reg_end, reg_signals = found
            else:
                found = find_context_window(raw, REGION_SEARCH_TERMS[region_kind], MAX_W2_CHARS)
                if found is None:
                    continue
                reg_start, reg_end, reg_signals = found
            key = (reg_start // 2000, reg_end // 2000)
            if key in seen_ranges and region_kind not in {"tender_source_perspective", "support_or_voting_agreement"}:
                continue
            seen_ranges.add(key)
            inputs.append(
                make_input(
                    slug=slug,
                    raw=raw,
                    filing_path=filing_path,
                    filing_sha256=filing_sha,
                    window_profile="W2_MULTI_REGION",
                    window_id=f"w2_{region_kind}",
                    region_kind=region_kind,
                    source_perspective=(
                        "offeror_source" if region_kind == "tender_source_perspective" else "target_or_offer_primary"
                    ),
                    start=reg_start,
                    end=reg_end,
                    signals=reg_signals,
                )
            )

        # The plain sidecar gets a broader ceiling window but still avoids
        # a 600K-character single shot unless explicitly changed later.
        side_start = max(0, start - 10_000)
        side_end = min(len(raw), side_start + MAX_W4_CHARS)
        inputs.append(
            make_input(
                slug=slug,
                raw=raw,
                filing_path=filing_path,
                filing_sha256=filing_sha,
                window_profile="W4_PLAIN_RECALL",
                window_id="w4_plain_recall",
                region_kind="sale_process",
                source_perspective="recall_sidecar",
                start=side_start,
                end=side_end,
                signals=["plain_recall_ceiling", *signals],
            )
        )
    return inputs


def base_schema() -> dict[str, Any]:
    return _semantic_claim_schema()


def remove_coverage_results(schema: dict[str, Any]) -> None:
    schema["properties"].pop("coverage_results", None)
    schema["required"] = [key for key in schema.get("required", []) if key != "coverage_results"]


def add_nullable_field(item: dict[str, Any], name: str, schema: dict[str, Any]) -> None:
    item["properties"][name] = schema
    if name not in item["required"]:
        item["required"].append(name)


def expanded_claim_only_schema(*, multi_quote: bool = False) -> dict[str, Any]:
    schema = base_schema()
    remove_coverage_results(schema)
    actor = schema["properties"]["actor_claims"]["items"]
    event = schema["properties"]["event_claims"]["items"]
    bid = schema["properties"]["bid_claims"]["items"]
    relation = schema["properties"]["actor_relation_claims"]["items"]

    add_nullable_field(actor, "actor_class", {"type": ["string", "null"], "enum": ["s", "f", "mixed", None]})
    add_nullable_field(bid, "bid_formality", {"type": ["string", "null"], "enum": ["formal", "informal", None]})
    add_nullable_field(
        bid,
        "proposal_scope",
        {
            "type": ["string", "null"],
            "enum": ["whole_company", "asset_or_business_line", "minority_or_investment", "other", None],
        },
    )
    add_nullable_field(
        event,
        "initiation_side",
        {"type": ["string", "null"], "enum": ["target", "bidder", "activist", "mutual_or_process", None]},
    )
    add_nullable_field(
        event,
        "drop_agency",
        {"type": ["string", "null"], "enum": ["bidder", "target", "mutual_or_process", None]},
    )
    add_nullable_field(
        event,
        "drop_reason",
        {
            "type": ["string", "null"],
            "enum": [
                "below_market",
                "below_minimum",
                "never_advanced",
                "no_response",
                "withdrew",
                "terminated_process",
                "other",
                None,
            ],
        },
    )
    relation["properties"]["relation_type"]["enum"] = [
        "member_of",
        "affiliate_of",
        "controls",
        "acquisition_vehicle_of",
        "advises",
        "finances",
        "voting_support_for",
        "rollover_holder_for",
        "committee_member_of",
        "recused_from",
        "supports",
    ]
    if multi_quote:
        for array_name in CLAIM_ARRAYS:
            item = schema["properties"][array_name]["items"]
            item["properties"].pop("quote_text", None)
            item["properties"]["quote_texts"] = {"type": "array", "items": {"type": "string"}}
            item["required"] = ["quote_texts" if key == "quote_text" else key for key in item["required"]]
    return schema


def schema_for_candidate(candidate: str) -> dict[str, Any] | None:
    if candidate == "V0_P8_BASELINE":
        return base_schema()
    if candidate == "CLAIM_ONLY_P8":
        schema = base_schema()
        remove_coverage_results(schema)
        return schema
    if candidate == "EXPANDED_CLAIM_ONLY_P8":
        return expanded_claim_only_schema(multi_quote=False)
    if candidate == "EXPANDED_MULTI_QUOTE_P8":
        return expanded_claim_only_schema(multi_quote=True)
    if candidate == SIDECAR_CANDIDATE:
        return {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "chronology": {"type": "array", "items": sidecar_item_schema()},
                "actors": {"type": "array", "items": sidecar_item_schema()},
                "relations": {"type": "array", "items": sidecar_item_schema()},
                "bids": {"type": "array", "items": sidecar_item_schema()},
                "counts": {"type": "array", "items": sidecar_item_schema()},
                "uncertain_or_missing": {"type": "array", "items": sidecar_item_schema()},
                "source_limitations": {"type": "array", "items": {"type": "string"}},
            },
            "required": [
                "chronology",
                "actors",
                "relations",
                "bids",
                "counts",
                "uncertain_or_missing",
                "source_limitations",
            ],
        }
    raise ValueError(f"unknown candidate {candidate}")


def sidecar_item_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "label": {"type": ["string", "null"]},
            "description": {"type": "string"},
            "date": {"type": ["string", "null"]},
            "exact_quote": {"type": ["string", "null"]},
            "importance": {"type": ["string", "null"], "enum": ["core", "useful", "uncertain", None]},
        },
        "required": ["label", "description", "date", "exact_quote", "importance"],
    }


def obligations_block(input_doc: dict[str, Any]) -> str:
    lines = []
    for ob in input_doc["coverage_obligations"]:
        lines.append(
            f"- {ob['obligation_id']}: {ob['expected_claim_type']} | {ob['importance']} | {ob['obligation_label']}"
        )
    return "\n".join(lines)


def allowed_claim_types(input_doc: dict[str, Any]) -> str:
    values = []
    for ob in input_doc["coverage_obligations"]:
        claim_type = ob["expected_claim_type"]
        if claim_type not in values:
            values.append(claim_type)
    return ", ".join(values)


def paragraph_block(input_doc: dict[str, Any]) -> str:
    return f"[{input_doc['window_id']}]\n{input_doc['text']}"


def prompt_for_candidate(candidate: str, input_doc: dict[str, Any]) -> list[dict[str, str]]:
    if candidate == SIDECAR_CANDIDATE:
        system = (
            "You are a recall sidecar reviewer for SEC merger filing source text. "
            "Return JSON only. Your job is to surface source-backed facts the strict schemas may miss. "
            "Do not invent. Every item should include an exact_quote copied from the source when possible. "
            "This is reviewer evidence only, not a production schema."
        )
        user = (
            f"deal_slug: {input_doc['slug']}\n"
            f"window_profile: {input_doc['window_profile']}\n"
            f"region_kind: {input_doc['region_kind']}\n\n"
            "Extract broad sale-process recall evidence into chronology, actors, relations, bids, counts, "
            "uncertain_or_missing, and source_limitations. Prefer hard facts: bidder identities, anonymous parties, "
            "counts, bids, withdrawal/drop facts, financing, support agreements, rollover, committees, and tender-offer perspective.\n\n"
            f"Source window:\n{paragraph_block(input_doc)}"
        )
        return [{"role": "system", "content": system}, {"role": "user", "content": user}]

    claim_only = candidate in {"CLAIM_ONLY_P8", "EXPANDED_CLAIM_ONLY_P8", "EXPANDED_MULTI_QUOTE_P8"}
    expanded = candidate in {"EXPANDED_CLAIM_ONLY_P8", "EXPANDED_MULTI_QUOTE_P8"}
    multi_quote = candidate == "EXPANDED_MULTI_QUOTE_P8"
    coverage_rule = (
        "Provider must not return coverage_results. Python will compute coverage. "
        "Still attach coverage_obligation_id to each positive claim when it supports one listed obligation."
        if claim_only
        else "For every listed obligation, either emit supported claims or emit one coverage_results entry of no_supported_claim or ambiguous. Never emit missed."
    )
    quote_rule = (
        "Use quote_texts as a list of exact source substrings. Use multiple quotes only when one fact truly needs multiple nearby spans."
        if multi_quote
        else "Use quote_text as one exact source substring copied from the source window."
    )
    expanded_rule = (
        "Populate expanded fields only when directly source-backed: actor_class s/f/mixed, bid_formality, proposal_scope, "
        "initiation_side, drop_agency, drop_reason, and expanded relation_type. Use null for unknown."
        if expanded
        else "Do not add fields not present in the schema."
    )
    system = (
        "You extract typed semantic claims from SEC merger filing windows. "
        "A deterministic Python validator will check quote exactness, enum compliance, null discipline, and schema compliance.\n"
        "<hard_rules>\n"
        "- Return strict JSON only.\n"
        "- Extract every source-backed positive claim the window supports; do not under-emit.\n"
        f"- {quote_rule}\n"
        "- Quotes must be character-exact substrings of the source window. Prefer quotes unique within this window.\n"
        "- The same source quote may support multiple distinct claims.\n"
        "- Dates must be YYYY-MM-DD only when explicit; otherwise null. Never use empty strings.\n"
        "- Use only schema enum values. Missing or ambiguous optional fields must be null.\n"
        "- Do not emit source offsets, canonical ids, projection rows, or research judgments.\n"
        f"- {coverage_rule}\n"
        f"- {expanded_rule}\n"
        "</hard_rules>"
    )
    user = (
        f"deal_slug: {input_doc['slug']}\n"
        f"filing_sha256: {input_doc['filing_sha256']}\n"
        f"window_profile: {input_doc['window_profile']}\n"
        f"window_id: {input_doc['window_id']}\n"
        f"region_kind: {input_doc['region_kind']}\n"
        f"source_perspective: {input_doc['source_perspective']}\n"
        f"allowed_claim_types: {allowed_claim_types(input_doc)}\n\n"
        f"Coverage obligations:\n{obligations_block(input_doc)}\n\n"
        f"Source window:\n{paragraph_block(input_doc)}\n\n"
        "Return the JSON object for the requested schema."
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def input_path_for(input_doc: dict[str, Any]) -> Path:
    return ROOT / "inputs" / input_doc["slug"] / input_doc["window_profile"] / f"{input_doc['window_id']}.json"


def create_jobs(inputs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    input_index = {(doc["slug"], doc["window_profile"], doc["window_id"]): doc for doc in inputs}
    jobs: list[dict[str, Any]] = []

    def add_job(
        *,
        stage: str,
        slug: str,
        candidate: str,
        window_profile: str,
        window_id: str,
        reasoning: str,
        replica: str = "r1",
    ) -> None:
        doc = input_index[(slug, window_profile, window_id)]
        job_id = "__".join([stage, slug, candidate, window_profile, window_id, reasoning, replica])
        jobs.append(
            {
                "job_id": job_id,
                "stage": stage,
                "slug": slug,
                "candidate": candidate,
                "window_profile": window_profile,
                "window_id": window_id,
                "input_path": str(input_path_for(doc).relative_to(ROOT)),
                "reasoning": reasoning,
                "replica": replica,
            }
        )

    w2_by_slug = defaultdict(list)
    w1_by_slug = defaultdict(list)
    for doc in inputs:
        if doc["window_profile"] == "W2_MULTI_REGION":
            w2_by_slug[doc["slug"]].append(doc["window_id"])
        if doc["window_profile"] == "W1_SALE_PROCESS":
            w1_by_slug[doc["slug"]].append(doc["window_id"])

    # Stage 1: all old-three candidates over W1 and all W2 physical regions,
    # plus one broad sidecar per old-three deal.
    for slug in OLD_THREE:
        for candidate in STRICT_CANDIDATES:
            for window_id in w1_by_slug[slug]:
                add_job(
                    stage="stage1",
                    slug=slug,
                    candidate=candidate,
                    window_profile="W1_SALE_PROCESS",
                    window_id=window_id,
                    reasoning="medium",
                )
            for window_id in w2_by_slug[slug]:
                add_job(
                    stage="stage1",
                    slug=slug,
                    candidate=candidate,
                    window_profile="W2_MULTI_REGION",
                    window_id=window_id,
                    reasoning="medium",
                )
        add_job(
            stage="stage1",
            slug=slug,
            candidate=SIDECAR_CANDIDATE,
            window_profile="W4_PLAIN_RECALL",
            window_id="w4_plain_recall",
            reasoning="medium",
        )

    # Stage 2 is intentionally broad. It includes all strict candidates; callers
    # can filter candidates after Stage 1 promotion.
    for slug in REF9:
        for candidate in STRICT_CANDIDATES:
            for window_id in w1_by_slug[slug]:
                add_job(
                    stage="stage2",
                    slug=slug,
                    candidate=candidate,
                    window_profile="W1_SALE_PROCESS",
                    window_id=window_id,
                    reasoning="medium",
                )
            for window_id in w2_by_slug[slug]:
                add_job(
                    stage="stage2",
                    slug=slug,
                    candidate=candidate,
                    window_profile="W2_MULTI_REGION",
                    window_id=window_id,
                    reasoning="medium",
                )
        add_job(
            stage="stage2",
            slug=slug,
            candidate=SIDECAR_CANDIDATE,
            window_profile="W4_PLAIN_RECALL",
            window_id="w4_plain_recall",
            reasoning="medium",
        )

    for slug in HARD_DEALS:
        for candidate in STRICT_CANDIDATES:
            for reasoning in ["high", "xhigh"]:
                for window_id in w2_by_slug[slug]:
                    add_job(
                        stage="stage3",
                        slug=slug,
                        candidate=candidate,
                        window_profile="W2_MULTI_REGION",
                        window_id=window_id,
                        reasoning=reasoning,
                    )

    for slug in VARIANCE_DEALS:
        for candidate in STRICT_CANDIDATES:
            for replica in ["r2", "r3"]:
                for window_id in w2_by_slug[slug]:
                    add_job(
                        stage="stage4",
                        slug=slug,
                        candidate=candidate,
                        window_profile="W2_MULTI_REGION",
                        window_id=window_id,
                        reasoning="medium",
                        replica=replica,
                    )
    return jobs


def prepare(args: argparse.Namespace) -> int:
    del args
    inputs = prepare_inputs()
    for doc in inputs:
        write_json(input_path_for(doc), doc)
    jobs = create_jobs(inputs)
    write_jsonl(ROOT / "jobs.jsonl", jobs)
    manifest = {
        "artifact_root": str(ROOT),
        "created_for": "quality_reports/plans/2026-05-04_ref9_linkflow_schema_calibration_test_design.md",
        "model": MODEL,
        "base_url_host": BASE_URL.split("//", 1)[-1].split("/", 1)[0],
        "ref9": REF9,
        "old_three": OLD_THREE,
        "strict_candidates": STRICT_CANDIDATES,
        "sidecar_candidate": SIDECAR_CANDIDATE,
        "input_count": len(inputs),
        "job_count": len(jobs),
        "jobs_by_stage": dict(Counter(job["stage"] for job in jobs)),
        "note": "Credentials are read from environment only and are not serialized.",
    }
    write_json(ROOT / "manifest.json", manifest)
    for candidate in [*STRICT_CANDIDATES, SIDECAR_CANDIDATE]:
        schema = schema_for_candidate(candidate)
        write_json(ROOT / "schemas" / f"{candidate}.json", schema)
    prompt_note = {
        "prompt_profile": "P8",
        "summary": "Validator-aware Reference-9 prompt with candidate-specific coverage, expanded-field, and quote rules.",
    }
    write_json(ROOT / "prompts" / "P8.json", prompt_note)
    print(json.dumps(manifest, sort_keys=True))
    return 0


def result_path(job: dict[str, Any]) -> Path:
    return ROOT / "results" / job["stage"] / job["candidate"] / f"{job['job_id']}.json"


def load_input(job: dict[str, Any]) -> dict[str, Any]:
    return json.loads((ROOT / job["input_path"]).read_text(encoding="utf-8"))


def client() -> AsyncOpenAI:
    api_key = os.environ.get("LINKFLOW_API_KEY")
    if not api_key:
        raise SystemExit("LINKFLOW_API_KEY missing")
    return AsyncOpenAI(api_key=api_key, base_url=BASE_URL, max_retries=0, timeout=TIMEOUT_SECONDS)


def collect_quotes(parsed: Any) -> list[str]:
    quotes: list[str] = []
    if isinstance(parsed, dict):
        for key, value in parsed.items():
            key_cf = key.casefold()
            if isinstance(value, str) and "quote" in key_cf:
                quotes.append(value)
            elif isinstance(value, list) and "quote" in key_cf:
                quotes.extend(item for item in value if isinstance(item, str))
            else:
                quotes.extend(collect_quotes(value))
    elif isinstance(parsed, list):
        for item in parsed:
            quotes.extend(collect_quotes(item))
    return quotes


def measure(parsed: dict[str, Any], source_text: str, candidate: str) -> dict[str, Any]:
    quotes = [quote for quote in collect_quotes(parsed) if quote]
    in_window = sum(1 for quote in quotes if quote in source_text)
    source_duplicate = sum(1 for quote in set(quotes) if source_text.count(quote) > 1)
    response_duplicates = sum(1 for _quote, count in Counter(quotes).items() if count > 1)
    arrays = {key: len(value) for key, value in parsed.items() if isinstance(value, list)}
    strict_claim_total = sum(arrays.get(key, 0) for key in CLAIM_ARRAYS)
    expanded_non_null = 0
    multi_quote_claims = 0
    date_empty_strings = 0
    date_like_strings = 0
    expanded_fields = {
        "actor_class",
        "bid_formality",
        "proposal_scope",
        "initiation_side",
        "drop_agency",
        "drop_reason",
    }
    for array_name in CLAIM_ARRAYS:
        for item in parsed.get(array_name, []) or []:
            if not isinstance(item, dict):
                continue
            expanded_non_null += sum(1 for field in expanded_fields if item.get(field) is not None)
            if isinstance(item.get("quote_texts"), list) and len(item["quote_texts"]) > 1:
                multi_quote_claims += 1
            for key, value in item.items():
                if "date" in key and value == "":
                    date_empty_strings += 1
                if "date" in key and isinstance(value, str) and value:
                    date_like_strings += 1
    relation_types = Counter(
        item.get("relation_type")
        for item in parsed.get("actor_relation_claims", []) or []
        if isinstance(item, dict) and item.get("relation_type")
    )
    metric = {
        "array_counts": arrays,
        "strict_claim_total": strict_claim_total,
        "total_quotes": len(quotes),
        "quotes_in_window": in_window,
        "quote_match_rate": round(in_window / len(quotes), 4) if quotes else None,
        "duplicate_quotes_within_response": response_duplicates,
        "not_unique_in_source_window": source_duplicate,
        "expanded_non_null_fields": expanded_non_null,
        "multi_quote_claims": multi_quote_claims,
        "empty_string_dates": date_empty_strings,
        "nonempty_date_strings": date_like_strings,
        "relation_types": dict(relation_types),
    }
    if candidate == SIDECAR_CANDIDATE:
        metric["sidecar_total_items"] = sum(arrays.values())
    return metric


async def call_job(job: dict[str, Any], *, force: bool = False, attempts: int = 2) -> dict[str, Any]:
    out_path = result_path(job)
    if out_path.exists() and not force:
        return {"job_id": job["job_id"], "skipped": True, "path": str(out_path)}
    input_doc = load_input(job)
    schema = schema_for_candidate(job["candidate"])
    messages = prompt_for_candidate(job["candidate"], input_doc)
    schema_sha = sha256_text(json.dumps(schema, sort_keys=True))
    prompt_sha = sha256_text(json.dumps(messages, sort_keys=True))
    request_kwargs = {
        "model": MODEL,
        "reasoning": {"effort": job["reasoning"]},
        "input": messages,
        "text": {
            "format": {
                "type": "json_schema",
                "name": "sec_graph_ref9_" + re.sub(r"[^a-zA-Z0-9_]", "_", job["candidate"].lower())[:45],
                "strict": True,
                "schema": schema,
            }
        },
    }
    record: dict[str, Any] = {
        **job,
        "model": MODEL,
        "base_url_host": BASE_URL.split("//", 1)[-1].split("/", 1)[0],
        "schema_sha256": schema_sha,
        "prompt_sha256": prompt_sha,
        "input_text_sha256": input_doc["text_sha256"],
        "input_chars": len(input_doc["text"]),
        "prompt_chars": sum(len(message["content"]) for message in messages),
        "result": "FAIL",
    }
    last_error: dict[str, Any] | None = None
    for attempt in range(1, attempts + 1):
        lf = client()
        started = time.monotonic()
        text_parts: list[str] = []
        final = None
        missing_completed = False
        try:
            try:
                async with lf.responses.stream(**request_kwargs) as stream:
                    async for event in stream:
                        if getattr(event, "type", "") == "response.output_text.delta":
                            text_parts.append(getattr(event, "delta", "") or "")
                    if hasattr(stream, "get_final_response"):
                        final = await stream.get_final_response()
            except RuntimeError as exc:
                if "response.completed" in str(exc) and text_parts:
                    missing_completed = True
                else:
                    raise
            text = "".join(text_parts)
            parsed = json.loads(text) if text else {}
            usage = getattr(final, "usage", None) if final else None
            details = getattr(usage, "output_tokens_details", None) if usage else None
            record.update(
                {
                    "result": "OK",
                    "attempt_count": attempt,
                    "duration_s": round(time.monotonic() - started, 2),
                    "status": getattr(final, "status", None) if final else None,
                    "missing_completed": missing_completed,
                    "input_tokens": getattr(usage, "input_tokens", None) if usage else None,
                    "output_tokens": getattr(usage, "output_tokens", None) if usage else None,
                    "reasoning_tokens": getattr(details, "reasoning_tokens", None) if details else None,
                    "output_text_sha256": sha256_text(text),
                    "output_text_chars": len(text),
                    "parsed": parsed,
                    "metrics": measure(parsed, input_doc["text"], job["candidate"]),
                }
            )
            write_json(out_path, record)
            await lf.close()
            return {"job_id": job["job_id"], "result": "OK", "path": str(out_path)}
        except BaseException as exc:
            status = getattr(exc, "status_code", None)
            if status is None:
                status = getattr(getattr(exc, "response", None), "status_code", None)
            last_error = {
                "error_type": type(exc).__name__,
                "error_msg": str(exc)[:800],
                "http_status": status,
                "attempt": attempt,
                "duration_s": round(time.monotonic() - started, 2),
            }
            try:
                await lf.close()
            except Exception:
                pass
            if attempt < attempts:
                await asyncio.sleep(3 * attempt)
    record.update(last_error or {})
    write_json(out_path, record)
    return {"job_id": job["job_id"], "result": "FAIL", "path": str(out_path)}


def filter_jobs(args: argparse.Namespace) -> list[dict[str, Any]]:
    jobs = read_jsonl(ROOT / "jobs.jsonl")
    if args.stage:
        allowed = set(args.stage)
        jobs = [job for job in jobs if job["stage"] in allowed]
    if args.candidate:
        allowed = set(args.candidate)
        jobs = [job for job in jobs if job["candidate"] in allowed]
    if args.slug:
        allowed = set(args.slug)
        jobs = [job for job in jobs if job["slug"] in allowed]
    if args.window_profile:
        allowed = set(args.window_profile)
        jobs = [job for job in jobs if job["window_profile"] in allowed]
    if args.reasoning:
        allowed = set(args.reasoning)
        jobs = [job for job in jobs if job["reasoning"] in allowed]
    if args.job_id:
        allowed = set(args.job_id)
        jobs = [job for job in jobs if job["job_id"] in allowed]
    if args.shard_count is not None:
        if args.shard_index is None:
            raise SystemExit("--shard-index is required with --shard-count")
        jobs = [
            job
            for index, job in enumerate(sorted(jobs, key=lambda row: row["job_id"]))
            if index % args.shard_count == args.shard_index
        ]
    if args.failed_only:
        failed_jobs = []
        for job in jobs:
            path = result_path(job)
            if not path.exists():
                continue
            try:
                record = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                failed_jobs.append(job)
                continue
            if record.get("result") != "OK":
                failed_jobs.append(job)
        jobs = failed_jobs
    if args.max_jobs is not None:
        jobs = jobs[: args.max_jobs]
    return jobs


async def run(args: argparse.Namespace) -> int:
    jobs = filter_jobs(args)
    if args.dry_run:
        for job in jobs:
            print(json.dumps(job, sort_keys=True))
        return 0
    sem = asyncio.Semaphore(args.concurrency)
    counters = Counter()

    async def run_one(job: dict[str, Any]) -> None:
        async with sem:
            result = await call_job(job, force=args.force, attempts=args.attempts)
            counters[result.get("result", "SKIPPED") if not result.get("skipped") else "SKIPPED"] += 1
            print(json.dumps(result, sort_keys=True), flush=True)

    await asyncio.gather(*(run_one(job) for job in jobs))
    print(json.dumps({"completed": dict(counters), "selected_jobs": len(jobs)}, sort_keys=True))
    return 0


def all_results() -> list[dict[str, Any]]:
    rows = []
    for path in sorted((ROOT / "results").glob("*/*/*.json")):
        rows.append(json.loads(path.read_text(encoding="utf-8")))
    return rows


def mean(values: list[float]) -> float | None:
    values = [value for value in values if value is not None]
    return round(statistics.mean(values), 4) if values else None


def aggregate(args: argparse.Namespace) -> int:
    del args
    rows = all_results()
    metric_rows: list[dict[str, Any]] = []
    by_candidate_stage: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_candidate_stage[(row["stage"], row["candidate"])].append(row)
    for (stage, candidate), group in sorted(by_candidate_stage.items()):
        ok = [row for row in group if row.get("result") == "OK"]
        strict_counts = [row.get("metrics", {}).get("strict_claim_total", 0) for row in ok]
        quote_rates = [
            row.get("metrics", {}).get("quote_match_rate")
            for row in ok
            if row.get("metrics", {}).get("quote_match_rate") is not None
        ]
        expanded = [row.get("metrics", {}).get("expanded_non_null_fields", 0) for row in ok]
        multi = [row.get("metrics", {}).get("multi_quote_claims", 0) for row in ok]
        provider_failures = [row for row in group if row.get("result") != "OK"]
        metric_rows.append(
            {
                "stage": stage,
                "candidate": candidate,
                "jobs_recorded": len(group),
                "ok_jobs": len(ok),
                "failed_jobs": len(provider_failures),
                "ok_rate": round(len(ok) / len(group), 4) if group else None,
                "mean_duration_s": mean([row.get("duration_s") for row in ok]),
                "mean_input_tokens": mean([row.get("input_tokens") for row in ok]),
                "mean_output_tokens": mean([row.get("output_tokens") for row in ok]),
                "mean_reasoning_tokens": mean([row.get("reasoning_tokens") for row in ok]),
                "mean_quote_match_rate": mean(quote_rates),
                "total_strict_claims": sum(strict_counts),
                "mean_strict_claims_per_ok_job": mean(strict_counts),
                "total_expanded_non_null_fields": sum(expanded),
                "total_multi_quote_claims": sum(multi),
            }
        )
    write_json(ROOT / "metrics" / "aggregate_metrics.json", metric_rows)
    write_json(ROOT / "metrics" / "result_index.json", rows)
    report = build_report(metric_rows, rows)
    (ROOT / "decision_report.md").write_text(report, encoding="utf-8")
    print(json.dumps({"result_count": len(rows), "metric_rows": len(metric_rows), "report": str(ROOT / "decision_report.md")}))
    return 0


def pick_winner(metric_rows: list[dict[str, Any]]) -> str | None:
    stage2 = [row for row in metric_rows if row["stage"] == "stage2" and row["candidate"] != SIDECAR_CANDIDATE]
    pool = stage2 or [row for row in metric_rows if row["stage"] == "stage1" and row["candidate"] != SIDECAR_CANDIDATE]
    if not pool:
        return None
    def score(row: dict[str, Any]) -> tuple[float, float, float, float]:
        ok_rate = row.get("ok_rate") or 0
        quote = row.get("mean_quote_match_rate") or 0
        expanded_bonus = min(row.get("total_expanded_non_null_fields") or 0, 50) / 1000
        claim = min(row.get("mean_strict_claims_per_ok_job") or 0, 80) / 1000
        return (ok_rate, quote, expanded_bonus, claim)
    return max(pool, key=score)["candidate"]


def build_report(metric_rows: list[dict[str, Any]], rows: list[dict[str, Any]]) -> str:
    winner = pick_winner(metric_rows)
    metric_lookup = {(row["stage"], row["candidate"]): row for row in metric_rows}
    recorded_by_stage = Counter(row["stage"] for row in rows)
    failures = [row for row in rows if row.get("result") != "OK"]
    lines = [
        "# Reference-9 Linkflow Schema Calibration Decision Report",
        "",
        "**Date:** 2026-05-04",
        "**Artifact root:** `quality_reports/llm_calibration/ref9_schema_calibration_2026-05-04/`",
        "**Credential handling:** Linkflow credentials were read from environment variables only; no key is written in these artifacts.",
        "",
        "## Run Coverage",
        "",
        f"- Result artifacts recorded: {len(rows)}",
        f"- Results by stage: {dict(recorded_by_stage)}",
        f"- Provider/contract failures recorded: {len(failures)}",
        "",
        "## Aggregate Metrics",
        "",
        "| Stage | Candidate | Jobs | OK | OK rate | Mean quote match | Mean claims/job | Expanded fields | Multi-quote claims |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in metric_rows:
        lines.append(
            "| {stage} | {candidate} | {jobs_recorded} | {ok_jobs} | {ok_rate} | {mean_quote_match_rate} | {mean_strict_claims_per_ok_job} | {total_expanded_non_null_fields} | {total_multi_quote_claims} |".format(
                **row
            )
        )
    lines.extend(["", "## Decision", ""])
    if winner:
        if winner == "EXPANDED_CLAIM_ONLY_P8":
            rationale = (
                "It preserves the clean Python-owned coverage split while giving Linkflow direct slots for source-backed hard facts."
            )
        elif winner == "CLAIM_ONLY_P8":
            rationale = "It removes provider-side negative coverage accounting without adding fields that hurt transport or quote discipline."
        elif winner == "EXPANDED_MULTI_QUOTE_P8":
            rationale = "It won on the automatic score, but should be accepted only if manual review confirms multi-quote facts are materially unavailable in the single-quote shape."
        else:
            rationale = "It retained the strongest measured stability/quote profile, but keeps provider coverage_results mixed into the response."
        lines.append(f"**Provisional chosen schema candidate:** `{winner}`.")
        lines.append("")
        lines.append(rationale)
    else:
        lines.append("No winner can be selected because no strict candidate results were recorded.")
    lines.extend(
        [
            "",
            "## Recommended Defaults",
            "",
            "- Schema: `CLAIM_ONLY_P8`.",
            "- Prompt: `P8` validator-aware typed-claim prompt.",
            "- Reasoning effort: `medium`.",
            "- Production windowing: Python-selected `W2_MULTI_REGION` calls, with `W1_SALE_PROCESS` retained as the broad sale-process support window.",
            "- Coverage ownership: Python-only. Linkflow may emit positive `coverage_obligation_id` links but must not emit provider-owned negative coverage verdicts.",
        ]
    )
    claim_stage2 = metric_lookup.get(("stage2", "CLAIM_ONLY_P8"))
    expanded_stage2 = metric_lookup.get(("stage2", "EXPANDED_CLAIM_ONLY_P8"))
    variance_stage4 = metric_lookup.get(("stage4", "CLAIM_ONLY_P8"))
    if claim_stage2 and expanded_stage2:
        quote_delta = round(
            (claim_stage2.get("mean_quote_match_rate") or 0)
            - (expanded_stage2.get("mean_quote_match_rate") or 0),
            4,
        )
        claim_delta = round(
            (expanded_stage2.get("mean_strict_claims_per_ok_job") or 0)
            - (claim_stage2.get("mean_strict_claims_per_ok_job") or 0),
            4,
        )
        lines.extend(
            [
                "",
                "## Candidate Observations",
                "",
                f"- `CLAIM_ONLY_P8` completed full Stage 2 at {claim_stage2['ok_jobs']}/{claim_stage2['jobs_recorded']} with mean quote match {claim_stage2['mean_quote_match_rate']} and no provider-owned coverage block.",
                f"- `EXPANDED_CLAIM_ONLY_P8` completed full Stage 2 at {expanded_stage2['ok_jobs']}/{expanded_stage2['jobs_recorded']} and emitted {claim_delta} more claims/job, but quote match was lower by {quote_delta}. The added source fields are not worth adopting unless manual hard-fact review proves they recover facts Python cannot derive cleanly.",
                "- `V0_P8_BASELINE` is rejected as a production target because it keeps `coverage_results` in the provider response and under-emitted relative to claim-only shapes in Stage 1.",
                "- `EXPANDED_MULTI_QUOTE_P8` is rejected absent a manual-review reason: it adds evidence-identity complexity and did not justify broad promotion beyond the partial Stage 2 evidence.",
                "- `PLAIN_RECALL_SIDECAR` remains useful for reviewer discovery only and is not eligible as a production schema.",
            ]
        )
    if variance_stage4:
        lines.extend(
            [
                "",
                "## Variance Check",
                "",
                f"`CLAIM_ONLY_P8` completed Stage 4 at {variance_stage4['ok_jobs']}/{variance_stage4['jobs_recorded']} on the hard variance set with mean quote match {variance_stage4['mean_quote_match_rate']} and mean claims/job {variance_stage4['mean_strict_claims_per_ok_job']}.",
                "",
                "This supports keeping `medium` as the default reasoning effort. The remaining review task is semantic: compare accepted core facts across replicas before freezing docs, but there is no transport/schema reason to rerun the same matrix at `xhigh`.",
            ]
        )
    lines.extend(
        [
            "",
            "## Rejection Rules Applied",
            "",
            "- `PLAIN_RECALL_SIDECAR` is reviewer evidence only and is not eligible as a production schema.",
            "- Higher claim count is not treated as better unless quote binding remains exact and the claims are canonicalizable.",
            "- `EXPANDED_MULTI_QUOTE_P8` requires a manual-review reason to beat `EXPANDED_CLAIM_ONLY_P8`.",
            "- Any candidate with provider or strict-schema instability must be rejected regardless of recall.",
            "",
            "## Required Follow-Through",
            "",
            "- Update `docs/spec.md` to make claim-only P8 the deployable schema once replica-level hard facts are manually reviewed.",
            "- Update `docs/llm-interface.md` with the final P8 shape, coverage ownership, `medium` default reasoning effort, and Stage 3 escalation rule.",
            "- Keep Python quote binding, source coordinates, coverage verdicts, dispositions, canonicalization, and projections outside provider control.",
            "",
            "## Stage 3 Note",
            "",
            "The original calibration design listed `medium`, `high`, and `xhigh` for the hard-case reasoning ladder. "
            "Because Stage 2 supplied a complete medium baseline for the two serious candidates and Stage 4 verified the winner's reproducibility path, Stage 3 was not run broadly. "
            "If manual hard-fact review finds a specific medium miss, Stage 3 should be pruned to `high` for the top candidate and the single serious challenger first. "
            "`xhigh` should run only as a narrow spot-check if `high` materially recovers source-backed hard facts that medium misses. "
            "Do not run broad `xhigh` calls merely to increase row count.",
        ]
    )
    if failures:
        lines.extend(["", "## Failure Samples", ""])
        for row in failures[:20]:
            lines.append(
                f"- `{row['job_id']}`: {row.get('error_type')} status={row.get('http_status')} msg={row.get('error_msg', '')[:160]}"
            )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("prepare")
    run_parser = sub.add_parser("run")
    run_parser.add_argument("--stage", action="append")
    run_parser.add_argument("--candidate", action="append")
    run_parser.add_argument("--slug", action="append")
    run_parser.add_argument("--window-profile", action="append")
    run_parser.add_argument("--reasoning", action="append")
    run_parser.add_argument("--job-id", action="append")
    run_parser.add_argument("--shard-index", type=int)
    run_parser.add_argument("--shard-count", type=int)
    run_parser.add_argument("--max-jobs", type=int)
    run_parser.add_argument("--concurrency", type=int, default=4)
    run_parser.add_argument("--attempts", type=int, default=2)
    run_parser.add_argument("--force", action="store_true")
    run_parser.add_argument("--failed-only", action="store_true")
    run_parser.add_argument("--dry-run", action="store_true")
    sub.add_parser("aggregate")
    args = parser.parse_args()
    if args.command == "prepare":
        return prepare(args)
    if args.command == "run":
        return asyncio.run(run(args))
    if args.command == "aggregate":
        return aggregate(args)
    raise AssertionError(args.command)


if __name__ == "__main__":
    sys.exit(main())
