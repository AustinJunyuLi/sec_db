"""Canonical schema primitives for sec_graph."""

from .db import DEFAULT_DB_PATH, apply_ddl, connect
from .evidence import evidence_fingerprint, quote_hash, validate_quote
from .ids import SequenceAllocator, make_id
from .models import (
    Actor,
    ActorClaim,
    ActorRelation,
    ActorRelationClaim,
    BidClaim,
    BidderRow,
    Claim,
    ClaimCoverageLink,
    ClaimDisposition,
    CleanFiling,
    CostRuntimeRecord,
    CoverageObligation,
    CoverageResult,
    Deal,
    Event,
    EventActorLink,
    EventClaim,
    EvidenceRegion,
    Judgment,
    Paragraph,
    ParticipationCount,
    ParticipationCountClaim,
    PointerStatus,
    ProcessCycle,
    ProgressLedgerEntry,
    ProjectionJudgment,
    ProjectionUnit,
    RowEvidence,
    RunManifest,
    RunStatus,
    Section,
    SourceSpan,
    StageArtifact,
    TRUSTED_STATUSES,
    latest_judgments,
    status_from_open_review_count,
)


def _review_row_export():
    from sec_graph.project.review_rows import ReviewRow as _ReviewRow

    return _ReviewRow


def __getattr__(name: str):
    if name == "ReviewRow":
        return _review_row_export()
    raise AttributeError(name)
from .schema_init import init_schema

__all__ = [
    "Actor",
    "ActorClaim",
    "ActorRelation",
    "ActorRelationClaim",
    "BidClaim",
    "BidderRow",
    "Claim",
    "ClaimCoverageLink",
    "ClaimDisposition",
    "CleanFiling",
    "CostRuntimeRecord",
    "CoverageObligation",
    "CoverageResult",
    "DEFAULT_DB_PATH",
    "Deal",
    "Event",
    "EventActorLink",
    "EventClaim",
    "EvidenceRegion",
    "Judgment",
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
    "RunManifest",
    "RunStatus",
    "Section",
    "SequenceAllocator",
    "SourceSpan",
    "StageArtifact",
    "TRUSTED_STATUSES",
    "apply_ddl",
    "connect",
    "evidence_fingerprint",
    "init_schema",
    "make_id",
    "quote_hash",
    "validate_quote",
    "latest_judgments",
    "status_from_open_review_count",
]
