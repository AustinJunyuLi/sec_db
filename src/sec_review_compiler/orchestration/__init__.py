"""Orchestration: the per-deal pipeline coordinator.

The orchestrator owns Linkflow dispatch, tool execution, database writes,
state transitions, canonical compilation, and publication (design spec
§13). Agents emit proposals; the orchestrator validates and commits.
"""

from .consistency import (
    ConsistencyFindingRecord,
    NoOpConsistencyChecker,
)
from .coverage import compute_initial_coverage_for_slice
from .orchestrator import (
    Orchestrator,
    SliceResult,
    OfflineConfidentialityExtractor,
    ExtractedClaim,
)
from .live_extractor import LiveLinkflowExtractor
from .live_verifier import LiveLinkflowVerifier
from .recorders import ProviderCallRecorder, ToolCallRecorder
from .tool_handlers import build_tool_definitions
from .verifier import (
    OfflineFakeVerifier,
    Verifier,
    VerifierProposal,
)

__all__ = [
    "ConsistencyFindingRecord",
    "ExtractedClaim",
    "LiveLinkflowExtractor",
    "LiveLinkflowVerifier",
    "NoOpConsistencyChecker",
    "OfflineConfidentialityExtractor",
    "OfflineFakeVerifier",
    "Orchestrator",
    "ProviderCallRecorder",
    "SliceResult",
    "ToolCallRecorder",
    "Verifier",
    "VerifierProposal",
    "build_tool_definitions",
    "compute_initial_coverage_for_slice",
]
