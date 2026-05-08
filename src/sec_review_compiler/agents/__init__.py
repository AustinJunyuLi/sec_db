"""Compiler agents — proposal-only, never write to DuckDB or filesystem.

Per design spec §11/§12 agents return structured proposals to the
orchestrator. The orchestrator validates and commits. This module is
deliberately import-free of the deal-room store and DuckDB.
"""

from .outputs import (
    ClaimAttemptOutput,
    ConsistencyFinding,
    EvidenceCitation,
    ProposedCorrection,
    ScoutMap,
    ScoutRegion,
    VerifierVerdict,
)
from .prompts import role_prompt
from .roles import AgentRole

__all__ = [
    "AgentRole",
    "ClaimAttemptOutput",
    "ConsistencyFinding",
    "EvidenceCitation",
    "ProposedCorrection",
    "ScoutMap",
    "ScoutRegion",
    "VerifierVerdict",
    "role_prompt",
]
