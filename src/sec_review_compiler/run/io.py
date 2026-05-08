"""Atomic JSON / text writes.

Atomic in the POSIX sense: a successful write replaces the target file in a
single rename; a failed write leaves no partial file behind. Callers never
see a half-written manifest or partial export.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

from ..errors import AtomicWriteError


def atomic_write_text(path: Path, content: str, *, encoding: str = "utf-8") -> None:
    """Write `content` to `path` atomically. Parent dirs are created if absent."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding=encoding) as fh:
            fh.write(content)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_path, path)
    except Exception as exc:  # noqa: BLE001 — wrapped into AtomicWriteError below
        try:
            tmp_path.unlink()
        except FileNotFoundError:
            pass
        raise AtomicWriteError(f"atomic write failed for {path}: {exc}") from exc


def atomic_write_json(
    path: Path,
    obj: Any,
    *,
    indent: int = 2,
    sort_keys: bool = True,
) -> None:
    """JSON-serialise `obj` and atomically write to `path`."""
    text = json.dumps(obj, indent=indent, sort_keys=sort_keys, default=str)
    atomic_write_text(Path(path), text + "\n")
