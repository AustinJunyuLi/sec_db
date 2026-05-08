"""Agent roles. Each value names a distinct agent identity."""

from __future__ import annotations

from enum import Enum


class AgentRole(str, Enum):
    SCOUT = "scout"
    EXTRACTOR_PARTY = "extractor:party"
    EXTRACTOR_TIMELINE = "extractor:timeline"
    EXTRACTOR_BIDS = "extractor:bids"
    EXTRACTOR_COUNTS = "extractor:counts"
    OMISSION_INSPECTOR = "omission_inspector"
    VERIFIER = "verifier"
    CONSISTENCY_CHECKER = "consistency_checker"
