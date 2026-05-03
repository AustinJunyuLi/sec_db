"""Atomic artifact writes with secret scanning."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Iterable


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


class RunSecretError(RuntimeError):
    """Raised before writing payloads that look like secrets."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


file_sha256 = sha256_file


def atomic_write_text(path: Path, text: str) -> str:
    _reject_secret_text(text)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
        _fsync_dir(path.parent)
    except Exception:
        try:
            tmp.unlink()
        except FileNotFoundError:
            pass
        raise
    return sha256_file(path)


def atomic_write_json(path: Path, payload: dict[str, object]) -> str:
    _reject_secret_payload(payload)
    return atomic_write_text(path, json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n")


def atomic_write_jsonl(path: Path, rows: Iterable[dict[str, object]]) -> str:
    materialized = list(rows)
    for row in materialized:
        _reject_secret_payload(row)
    return atomic_write_text(path, "".join(json.dumps(row, sort_keys=True, default=str) + "\n" for row in materialized))


def append_jsonl_atomic(path: Path, row: dict[str, object]) -> str:
    rows = []
    if path.exists():
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    rows.append(row)
    return atomic_write_jsonl(path, rows)


def _reject_secret_payload(payload: object) -> None:
    if isinstance(payload, dict):
        for key, value in payload.items():
            key_text = str(key).casefold()
            if any(part in key_text for part in _SECRET_KEY_PARTS):
                raise RunSecretError(f"refusing to write secret-like key {key!r}")
            _reject_secret_payload(value)
    elif isinstance(payload, list):
        for value in payload:
            _reject_secret_payload(value)
    elif isinstance(payload, str):
        _reject_secret_text(payload)


def _reject_secret_text(text: str) -> None:
    if "Authorization: Bearer" in text or "sk-" in text:
        raise RunSecretError("refusing to write secret-like text")


def _fsync_dir(path: Path) -> None:
    if not hasattr(os, "O_DIRECTORY"):
        return
    try:
        fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    except OSError:
        return
    try:
        os.fsync(fd)
    finally:
        os.close(fd)
