"""Schema fixtures and provider-safe schema transforms."""

from __future__ import annotations

import copy
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class MinimalPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str


def minimal_schema() -> dict[str, Any]:
    schema = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "label": {"type": "string", "enum": ["yes", "no"]},
            "confidence": {"type": "number"},
            "reason": {"type": "string"},
        },
        "required": ["label", "confidence", "reason"],
    }
    return schema


def nested_claim_schema(nullable: bool = True) -> dict[str, Any]:
    note_type: Any = ["string", "null"] if nullable else "string"
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "claim_type": {"type": "string", "enum": ["event"]},
            "payload": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "event_subtype": {"type": "string", "enum": ["nda_signed", "final_bid"]},
                    "event_date": {"type": "string"},
                    "actor_label": {"type": "string"},
                    "note": {"type": note_type},
                },
                "required": ["event_subtype", "event_date", "actor_label", "note"],
            },
            "evidence": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "paragraph_id": {"type": "string"},
                        "quote": {"type": "string"},
                    },
                    "required": ["paragraph_id", "quote"],
                },
            },
        },
        "required": ["claim_type", "payload", "evidence"],
    }


def verdict_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "verdict": {"type": "string", "enum": ["confirm", "reject", "ambiguous"]},
            "paragraph_id": {"type": "string"},
            "quote": {"type": "string"},
            "reason": {"type": "string"},
        },
        "required": ["verdict", "paragraph_id", "quote", "reason"],
    }


def strict_json_schema(name: str, schema: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "json_schema",
        "name": name,
        "strict": True,
        "schema": strictify_schema(schema),
    }


def strictify_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Return a provider-oriented strict schema without mutating input."""
    cloned = copy.deepcopy(schema)
    _strictify_node(cloned)
    return cloned


def _strictify_node(node: Any) -> None:
    if isinstance(node, dict):
        for keyword in ("default", "examples", "format", "title", "minimum", "maximum"):
            node.pop(keyword, None)
        if node.get("type") == "object":
            node["additionalProperties"] = False
            properties = node.get("properties", {})
            if isinstance(properties, dict):
                node["required"] = list(properties.keys())
        for item in node.values():
            _strictify_node(item)
    elif isinstance(node, list):
        for item in node:
            _strictify_node(item)
