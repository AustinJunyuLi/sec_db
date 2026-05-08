"""Compiler agents — proposal-only, never write to DuckDB or filesystem.

Per design spec §11/§12 agents return structured proposals to the
orchestrator. The orchestrator validates and commits. This module is
deliberately import-free of the deal-room store and DuckDB.
"""

from .outputs import (
    ClaimAttemptOutput,
    ConsistencyFinding,
    ConsistencyFindings,
    EvidenceCitation,
    ExtractorBatchOutput,
    OmissionCoverageProposal,
    OmissionInspectorOutput,
    ProposedCorrection,
    ROLE_OUTPUT_MODEL,
    ScoutMap,
    ScoutRegion,
    VerifierVerdict,
    role_output_model,
)
from .prompts import role_prompt, role_prompt_hash
from .roles import AgentRole, ROLE_ORDER
from .tool_surface import (
    FORBIDDEN_TOOL_NAMES,
    tools_for_role,
)

__all__ = [
    "AgentRole",
    "ClaimAttemptOutput",
    "ConsistencyFinding",
    "ConsistencyFindings",
    "EvidenceCitation",
    "ExtractorBatchOutput",
    "FORBIDDEN_TOOL_NAMES",
    "OmissionCoverageProposal",
    "OmissionInspectorOutput",
    "ProposedCorrection",
    "ROLE_ORDER",
    "ROLE_OUTPUT_MODEL",
    "ScoutMap",
    "ScoutRegion",
    "VerifierVerdict",
    "role_output_model",
    "role_prompt",
    "role_prompt_hash",
    "tools_for_role",
]
