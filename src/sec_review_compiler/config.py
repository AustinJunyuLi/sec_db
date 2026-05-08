"""Compiler-wide constants and config-hash helper.

The Linkflow probe gate is captured here as a single source of truth: every
run manifest records which probe run it inherits its provider-contract
guarantees from.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

# The committed Linkflow probe run that produced Gate: GO. Bumping this
# constant requires a new probe run committed under runs/linkflow-probe/.
LINKFLOW_PROBE_RUN_ID = "20260508T123815Z"


def config_hash(config: dict[str, Any]) -> str:
    """Return a deterministic SHA-256 over a JSON-serialised config dict.

    Keys are sorted; separators are minimised so semantically-equal configs
    always hash the same regardless of dict order or whitespace.
    """
    blob = json.dumps(config, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()
