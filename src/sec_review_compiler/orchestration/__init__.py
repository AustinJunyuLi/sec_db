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
from .verifier import (
    OfflineFakeVerifier,
    Verifier,
    VerifierProposal,
)

__all__ = [
    "ConsistencyFindingRecord",
    "ExtractedClaim",
    "NoOpConsistencyChecker",
    "OfflineConfidentialityExtractor",
    "OfflineFakeVerifier",
    "Orchestrator",
    "SliceResult",
    "Verifier",
    "VerifierProposal",
    "compute_initial_coverage_for_slice",
]
