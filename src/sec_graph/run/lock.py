"""Run directory locking."""

from __future__ import annotations

import fcntl
import json
import os
from pathlib import Path


class RunLockError(RuntimeError):
    """Raised when a run directory already has an active writer."""


class RunLock:
    def __init__(self, run_dir: Path, run_id: str, config_hash: str | None = None) -> None:
        self.run_dir = run_dir
        self.run_id = run_id
        self.config_hash = config_hash
        self.path = run_dir / "run.lock"
        self._handle = None

    @classmethod
    def acquire(cls, run_dir: Path, *, run_id: str, config_hash: str | None = None) -> "RunLock":
        lock = cls(run_dir, run_id, config_hash)
        lock._acquire()
        return lock

    def __enter__(self) -> "RunLock":
        if self._handle is not None:
            return self
        self._acquire()
        return self

    def _acquire(self) -> None:
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self._handle = self.path.open("a+", encoding="utf-8")
        try:
            fcntl.flock(self._handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            self._handle.close()
            self._handle = None
            raise RunLockError(f"run {self.run_id} is already locked") from exc
        self._handle.seek(0)
        self._handle.truncate()
        payload = {"run_id": self.run_id, "config_hash": self.config_hash, "pid": os.getpid()}
        self._handle.write(json.dumps(payload, sort_keys=True))
        self._handle.flush()
        os.fsync(self._handle.fileno())

    def __exit__(self, exc_type, exc, tb) -> None:
        if self._handle is None:
            return
        fcntl.flock(self._handle.fileno(), fcntl.LOCK_UN)
        self._handle.close()
        self._handle = None
        try:
            self.path.unlink()
        except FileNotFoundError:
            pass
