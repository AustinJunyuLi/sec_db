"""Consistency checking — minimal stub for US-007.

The vertical slice has at most a handful of independent attempts, so
consistency findings are typically empty. Real cross-claim checks land
in US-010 (full agent surface). This module exposes the interface so
the orchestrator can call it uniformly.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from ..store.repository import ClaimAttempt


@dataclass(frozen=True, slots=True)
class ConsistencyFindingRecord:
    finding_type: str
    attempt_ids: tuple[str, ...]
    description: str
    severity: str  # info | warning | blocking


class NoOpConsistencyChecker:
    """Returns no findings. Used by the offline vertical slice."""

    def check(
        self, attempts: Sequence[ClaimAttempt]
    ) -> list[ConsistencyFindingRecord]:
        return []
