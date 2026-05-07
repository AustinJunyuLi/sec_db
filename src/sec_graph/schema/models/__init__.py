"""Schema model exports."""

from .canonical import (
    CANONICAL_DDL,
    Actor,
    ActorRelation,
    BidderRow,
    Deal,
    Event,
    EventActorLink,
    ProcessCycle,
    ProjectionJudgment,
    ProjectionUnit,
    RowEvidence,
)
from .extraction import (
    EXTRACTION_DDL,
    ActorClaim,
    ActorRelationClaim,
    BidClaim,
    Claim,
    ClaimCoverageLink,
    ClaimDisposition,
    CoverageObligation,
    CoverageResult,
    EventClaim,
    EvidenceRegion,
    ParticipationCountClaim,
)
from .filings import CleanFiling, FILINGS_DDL, Paragraph, Section, SourceSpan
from .judgments import JUDGMENTS_DDL, Judgment, latest_judgments
from .participation_counts import PARTICIPATION_COUNTS_DDL, ParticipationCount
from .runtime import (
    RUN_METADATA_DDL,
    CostRuntimeRecord,
    PointerStatus,
    ProgressLedgerEntry,
    RunManifest,
    RunStatus,
    StageArtifact,
    TRUSTED_STATUSES,
    status_from_open_review_count,
)


def _review_row_export():
    from sec_graph.project.review_rows import ReviewRow as _ReviewRow

    return _ReviewRow


def __getattr__(name: str):
    if name == "ReviewRow":
        return _review_row_export()
    raise AttributeError(name)


__all__ = [
    "Actor",
    "ActorClaim",
    "ActorRelation",
    "ActorRelationClaim",
    "BidClaim",
    "BidderRow",
    "CANONICAL_DDL",
    "Claim",
    "ClaimCoverageLink",
    "ClaimDisposition",
    "CleanFiling",
    "CostRuntimeRecord",
    "CoverageObligation",
    "CoverageResult",
    "Deal",
    "Event",
    "EventActorLink",
    "EventClaim",
    "EvidenceRegion",
    "EXTRACTION_DDL",
    "FILINGS_DDL",
    "JUDGMENTS_DDL",
    "Judgment",
    "latest_judgments",
    "PARTICIPATION_COUNTS_DDL",
    "Paragraph",
    "ParticipationCount",
    "ParticipationCountClaim",
    "PointerStatus",
    "ProcessCycle",
    "ProgressLedgerEntry",
    "ProjectionJudgment",
    "ProjectionUnit",
    "ReviewRow",
    "RowEvidence",
    "RUN_METADATA_DDL",
    "RunManifest",
    "RunStatus",
    "Section",
    "SourceSpan",
    "StageArtifact",
    "TRUSTED_STATUSES",
    "status_from_open_review_count",
]
