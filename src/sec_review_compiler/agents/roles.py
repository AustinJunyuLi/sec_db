"""Agent roles. Each value names a distinct agent identity.

The seven roles below cover the V1 surface (design spec §11). The
orchestrator may dispatch them in parallel within bounded concurrency,
but no role ever writes truth directly — agents return proposals.
"""

from __future__ import annotations

from enum import Enum


class AgentRole(str, Enum):
    SCOUT = "scout"
    PARTY_RELATION_EXTRACTOR = "party_relation_extractor"
    TIMELINE_BID_EXTRACTOR = "timeline_bid_extractor"
    COUNT_COVERAGE_EXTRACTOR = "count_coverage_extractor"
    OMISSION_INSPECTOR = "omission_inspector"
    VERIFIER = "verifier"
    CONSISTENCY_CHECKER = "consistency_checker"


ROLE_ORDER: tuple[AgentRole, ...] = (
    AgentRole.SCOUT,
    AgentRole.PARTY_RELATION_EXTRACTOR,
    AgentRole.TIMELINE_BID_EXTRACTOR,
    AgentRole.COUNT_COVERAGE_EXTRACTOR,
    AgentRole.OMISSION_INSPECTOR,
    AgentRole.VERIFIER,
    AgentRole.CONSISTENCY_CHECKER,
)
