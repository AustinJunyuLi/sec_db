"""Sanitization and JSON artifact helpers for Linkflow probes."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

SECRET_KEY_FRAGMENTS = (
    "api_key",
    "apikey",
    "authorization",
    "bearer",
    "cookie",
    "secret",
    "token",
)


def to_jsonable(value: Any) -> Any:
    """Convert SDK/Pydantic objects into plain JSON-compatible values."""
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json", exclude_none=True)
    if isinstance(value, dict):
        return {str(key): to_jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_jsonable(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return repr(value)


def sanitize(value: Any) -> Any:
    """Remove secret-bearing fields while preserving diagnostic structure."""
    jsonable = to_jsonable(value)
    if isinstance(jsonable, dict):
        cleaned: dict[str, Any] = {}
        for key, item in jsonable.items():
            lowered = key.lower()
            if lowered.endswith("_present"):
                cleaned[key] = sanitize(item)
            elif any(fragment in lowered for fragment in SECRET_KEY_FRAGMENTS):
                cleaned[key] = "[REDACTED]"
            else:
                cleaned[key] = sanitize(item)
        return cleaned
    if isinstance(jsonable, list):
        return [sanitize(item) for item in jsonable]
    if isinstance(jsonable, str) and jsonable.startswith("sk-"):
        return "[REDACTED]"
    return jsonable


def append_jsonl(path: Path, payload: dict[str, Any]) -> int:
    """Append a sanitized payload and return the one-based JSONL line number."""
    path.parent.mkdir(parents=True, exist_ok=True)
    line_number = 1
    if path.exists():
        with path.open("r", encoding="utf-8") as handle:
            line_number = sum(1 for _ in handle) + 1
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(sanitize(payload), sort_keys=True) + "\n")
    return line_number


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(sanitize(payload), indent=2, sort_keys=True)
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text(encoded + "\n", encoding="utf-8")
    tmp.replace(path)
