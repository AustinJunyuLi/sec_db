"""Single run-id factory and deterministic run clock."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any

_RUN_ID_RE = re.compile(
    r"^(?P<stamp>\d{4}-\d{2}-\d{2}T\d{6}Z)_(?P<scope>[a-z0-9][a-z0-9-]*)_(?P<short_hash>[0-9a-f]{8})$"
)
_HASH_RE = re.compile(r"^[0-9a-f]{8,64}$")
_SECRET_KEY_PARTS = (
    "api_key",
    "authorization",
    "bearer",
    "credential",
    "password",
    "private_key",
    "refresh_token",
    "secret",
    "access_token",
)


@dataclass(frozen=True)
class ParsedRunId:
    run_id: str
    stamp: str
    scope: str
    short_hash: str


def stable_config_hash(payload: dict[str, Any]) -> str:
    _reject_secret_payload(payload)
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


config_hash = stable_config_hash


def make_run_id(*, scope: str, started_at: dt.datetime | str, config_hash: str | None = None, input_hash: str | None = None) -> str:
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", scope):
        raise ValueError("run scope must contain only lowercase letters, digits, and hyphens")
    if isinstance(started_at, str):
        stamp = started_at
    else:
        if started_at.tzinfo is None:
            raise ValueError("started_at must be timezone-aware")
        stamp = started_at.astimezone(dt.UTC).strftime("%Y-%m-%dT%H%M%SZ")
    digest = config_hash or input_hash
    if not digest:
        raise ValueError("config_hash or input_hash is required")
    if _HASH_RE.fullmatch(digest) is None:
        raise ValueError("config_hash or input_hash must be lowercase sha256 hex, at least 8 characters")
    return f"{stamp}_{scope}_{digest[:8]}"


def validate_run_id(run_id: str) -> ParsedRunId:
    match = _RUN_ID_RE.match(run_id)
    if match is None:
        raise ValueError("run_id must match YYYY-MM-DDTHHMMSSZ_<scope>_<short-hash>")
    dt.datetime.strptime(match.group("stamp"), "%Y-%m-%dT%H%M%SZ")
    return ParsedRunId(run_id=run_id, **match.groupdict())


class RunClock:
    """Deterministic run clock derived from run id and config hash."""

    def __init__(self, run_id: str, config_hash: str | None = None) -> None:
        parsed = validate_run_id(run_id)
        self.run_id = run_id
        self.config_hash = config_hash or (parsed.short_hash + "0" * 56)
        self.started_at_iso = _stamp_to_iso(parsed.stamp)
        self.started_at = self.started_at_iso

    @classmethod
    def from_run_id(cls, run_id: str, *, config_hash: str) -> "RunClock":
        return cls(run_id, config_hash=config_hash)

    def timestamp(self, label: str = "run", sequence: int = 0) -> str:
        base = dt.datetime.strptime(self.started_at_iso, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=dt.UTC)
        digest = hashlib.sha256(f"{self.config_hash}\0{label}\0{sequence}".encode("utf-8")).hexdigest()
        offset = int(digest[:8], 16) % 86400
        return (base + dt.timedelta(seconds=offset)).strftime("%Y-%m-%dT%H:%M:%SZ")


def _stamp_to_iso(stamp: str) -> str:
    return dt.datetime.strptime(stamp, "%Y-%m-%dT%H%M%SZ").replace(tzinfo=dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _reject_secret_payload(payload: object) -> None:
    if isinstance(payload, dict):
        for key, value in payload.items():
            key_text = str(key).casefold()
            if any(part in key_text for part in _SECRET_KEY_PARTS):
                raise ValueError(f"refusing to hash secret-like config key {key!r}")
            _reject_secret_payload(value)
    elif isinstance(payload, list | tuple):
        for value in payload:
            _reject_secret_payload(value)
