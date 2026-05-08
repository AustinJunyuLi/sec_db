"""Strict JSON schemas for compiler agent outputs.

These schemas are submitted to Linkflow via `response_format={"type":
"json_schema", "name": ..., "strict": True, "schema": ...}` so the
provider enforces shape on the way out. We reuse the probe's
`strictify_schema` to guarantee `additionalProperties=false` on every
object node and `required` on every property.
"""

from __future__ import annotations

from typing import Any

from linkflow_probe.schemas import strict_json_schema, strictify_schema


_EVIDENCE_ITEM: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "paragraph_id": {"type": "string"},
        "quote": {"type": "string"},
    },
    "required": ["paragraph_id", "quote"],
}


def scout_region_map_schema() -> dict[str, Any]:
    """Where the scout believes important deal facts live."""
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "regions": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "name": {"type": "string"},
                        "paragraph_ids": {"type": "array", "items": {"type": "string"}},
                        "search_keywords": {"type": "array", "items": {"type": "string"}},
                        "confidence": {
                            "type": "string",
                            "enum": ["high", "medium", "low"],
                        },
                    },
                    "required": ["name", "paragraph_ids", "search_keywords", "confidence"],
                },
            },
        },
        "required": ["regions"],
    }


def extractor_claim_schema() -> dict[str, Any]:
    """A specialist extractor's claim attempt with mandatory citations."""
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "claim_type": {"type": "string"},
            "claim_fingerprint": {"type": "string"},
            "payload_json": {"type": "string"},
            "evidence": {
                "type": "array",
                "items": _EVIDENCE_ITEM,
            },
        },
        "required": ["claim_type", "claim_fingerprint", "payload_json", "evidence"],
    }


def verifier_verdict_schema() -> dict[str, Any]:
    """An independent verifier's verdict on one bound claim attempt."""
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "verdict": {
                "type": "string",
                "enum": ["confirm", "partial", "reject", "ambiguous"],
            },
            "reasoning_summary": {"type": "string"},
            "supporting_evidence": {
                "type": "array",
                "items": _EVIDENCE_ITEM,
            },
            "proposed_correction_json": {
                "type": ["string", "null"],
            },
            "confidence": {
                "type": "number",
            },
        },
        "required": [
            "verdict",
            "reasoning_summary",
            "supporting_evidence",
            "proposed_correction_json",
            "confidence",
        ],
    }


def consistency_finding_schema() -> dict[str, Any]:
    """A consistency-checker finding across multiple attempts."""
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "finding_type": {
                "type": "string",
                "enum": [
                    "contradictory_dates",
                    "incompatible_bids",
                    "actor_identity_mismatch",
                    "duplicate_claim",
                    "graph_invariant",
                ],
            },
            "attempt_ids": {"type": "array", "items": {"type": "string"}},
            "description": {"type": "string"},
            "severity": {
                "type": "string",
                "enum": ["info", "warning", "blocking"],
            },
        },
        "required": ["finding_type", "attempt_ids", "description", "severity"],
    }


def strict_response_format(name: str, schema: dict[str, Any]) -> dict[str, Any]:
    """Wrap `schema` as a strict response_format payload for the API call."""
    return strict_json_schema(name=name, schema=schema)


__all__ = [
    "consistency_finding_schema",
    "extractor_claim_schema",
    "scout_region_map_schema",
    "strict_response_format",
    "strictify_schema",
    "verifier_verdict_schema",
]
