"""Deal-room store: DuckDB schema, lifecycle, and repository.

Per design spec §9 the deal-room database is the queryable authority for
one deal's state. JSONL audit logs are not the source of truth for
compilation — this store is. Append-orientation is enforced at the
repository boundary; corrections create new `attempt_id` values and never
mutate accepted claims.
"""

from .lifecycle import (
    AGGREGATION_POLICY_VERSION,
    AggregatedVerdict,
    aggregate_verdicts,
    can_publish_trusted,
    validate_transition,
)
from .migrations import apply_schema
from .repository import (
    ClaimAttempt,
    Conflict,
    CoverageCheck,
    DealRoomRepository,
    EvidenceBinding,
    HumanDecision,
    NormalizedValue,
    SourceRecord,
    Verdict,
    VerdictAggregateRow,
)
from .schema import (
    COVERAGE_STATES,
    DDL_STATEMENTS,
    LIFECYCLE_STATES,
    TERMINAL_STATES,
    TRANSITIONS,
    VERDICT_TYPES,
)

__all__ = [
    "AGGREGATION_POLICY_VERSION",
    "AggregatedVerdict",
    "ClaimAttempt",
    "COVERAGE_STATES",
    "Conflict",
    "CoverageCheck",
    "DDL_STATEMENTS",
    "DealRoomRepository",
    "EvidenceBinding",
    "HumanDecision",
    "LIFECYCLE_STATES",
    "NormalizedValue",
    "SourceRecord",
    "TERMINAL_STATES",
    "TRANSITIONS",
    "VERDICT_TYPES",
    "Verdict",
    "VerdictAggregateRow",
    "aggregate_verdicts",
    "apply_schema",
    "can_publish_trusted",
    "validate_transition",
]
