"""Mutable latest-trusted pointer over immutable run directories.

The pointer file lives at ``{runs_root}/latest/{deal_slug}.json`` and
indexes the latest *attempted* run and the latest *trusted* run for a
deal. Pointer status follows the five-value vocabulary defined in
``schema/models/runtime.py``:

- ``passed_clean``, ``needs_review``, ``high_burden``: mirror a trusted
  ``latest_attempt``.
- ``failed_system``: latest attempt failed and no prior trusted run
  exists.
- ``stale_after_failure``: latest attempt failed but a prior trusted run
  remains preserved in ``latest_trusted``.

A run record never carries ``stale_after_failure``; only the pointer
file does.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any

from sec_graph.run.io import atomic_write_json
from sec_graph.schema import TRUSTED_STATUSES

POINTER_SCHEMA_VERSION = "sec_graph_latest_pointer_v1"


def update_latest_pointer(
    run_dir: Path,
    run_record: dict[str, Any],
    *,
    runs_root: Path,
) -> Path:
    """Write the latest pointer for ``run_record`` and return its path.

    ``run_record`` must contain at least ``run_id``, ``deal_slug``, and
    ``status`` (one of the four ``RunStatus`` values).
    """

    deal_slug = str(run_record["deal_slug"])
    status = str(run_record["status"])
    run_id = str(run_record["run_id"])

    pointer_path = _pointer_path(runs_root, deal_slug)
    prior = read_latest_pointer(deal_slug, runs_root=runs_root)

    attempt_payload = {
        "run_id": run_id,
        "run_dir": run_dir.as_posix(),
        "status": status,
    }

    pointer_status: str
    latest_trusted: dict[str, Any] | None
    if status in TRUSTED_STATUSES:
        pointer_status = status
        latest_trusted = dict(attempt_payload)
    else:
        # status is failed_system. Try to preserve prior trusted run if it
        # is still on disk and its stage_artifacts.jsonl still validates.
        prior_trusted = _verified_prior_trusted(prior)
        if prior_trusted is None:
            pointer_status = "failed_system"
            latest_trusted = None
        else:
            pointer_status = "stale_after_failure"
            latest_trusted = prior_trusted

    payload: dict[str, Any] = {
        "schema_version": POINTER_SCHEMA_VERSION,
        "deal_slug": deal_slug,
        "pointer_status": pointer_status,
        "latest_attempt": attempt_payload,
        "latest_trusted": latest_trusted,
        "updated_at": _now_iso(),
    }

    atomic_write_json(pointer_path, payload)
    return pointer_path


def read_latest_pointer(
    deal_slug: str,
    *,
    runs_root: Path,
) -> dict[str, Any] | None:
    """Return the parsed pointer JSON for ``deal_slug`` or None."""

    pointer_path = _pointer_path(runs_root, deal_slug)
    if not pointer_path.exists():
        return None
    try:
        payload = json.loads(pointer_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    return payload


# --------------------------------------------------------------------------- #
# Helpers                                                                     #
# --------------------------------------------------------------------------- #


def _pointer_path(runs_root: Path, deal_slug: str) -> Path:
    return runs_root / "latest" / f"{deal_slug}.json"


def _verified_prior_trusted(
    prior: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Return the prior trusted descriptor iff still valid on disk.

    A prior trusted run is preserved if:
    - it exists in the pointer payload as ``latest_trusted``;
    - its ``run_dir`` exists on disk;
    - its ``stage_artifacts.jsonl`` exists.

    The integrity contract is "exists and is structurally complete"; full
    digest re-verification is performed by the run kernel during resume,
    so the pointer is intentionally lightweight.
    """
    if prior is None:
        return None
    trusted = prior.get("latest_trusted")
    if not isinstance(trusted, dict):
        return None
    run_dir_str = trusted.get("run_dir")
    if not isinstance(run_dir_str, str):
        return None
    run_dir = Path(run_dir_str)
    if not run_dir.exists():
        return None
    stage_artifacts = run_dir / "stage_artifacts.jsonl"
    if not stage_artifacts.exists():
        return None
    return {
        "run_id": str(trusted.get("run_id", "")),
        "run_dir": run_dir_str,
        "status": str(trusted.get("status", "")),
    }


def _now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
