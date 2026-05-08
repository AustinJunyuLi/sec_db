"""DealRoomRepository: typed entry points for writing into the deal-room.

Agents never call this directly. The orchestrator validates agent
proposals, then asks the repository to commit the corresponding rows.
"""

from __future__ import annotations

import json
import secrets
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Iterable, Sequence

from .lifecycle import (
    AGGREGATION_POLICY_VERSION,
    AggregatedVerdict,
    aggregate_verdicts,
    validate_transition,
)
from .schema import (
    COVERAGE_STATES,
    LIFECYCLE_STATES,
    VERDICT_TYPES,
)


# ---------------------------------------------------------------- typed inputs

@dataclass(frozen=True, slots=True)
class SourceRecord:
    record_type: str
    record_id: str
    filing_id: str
    payload_json: str
    char_start: int | None
    char_end: int | None
    created_at: datetime


@dataclass(frozen=True, slots=True)
class ClaimAttempt:
    attempt_id: str
    claim_fingerprint: str
    deal_slug: str
    claim_type: str
    payload_json: str
    origin_agent_role: str
    origin_agent_run_id: str
    model: str
    prompt_hash: str
    created_sequence: int
    created_at_run_clock: datetime
    status: str
    supersedes_attempt_id: str | None = None


@dataclass(frozen=True, slots=True)
class EvidenceBinding:
    binding_id: str
    attempt_id: str
    evidence_id: str
    filing_id: str
    paragraph_id: str | None
    char_start: int
    char_end: int
    quote_text: str
    quote_text_hash: str
    binding_status: str
    binding_error_code: str | None
    tool_version: str
    created_at_run_clock: datetime


@dataclass(frozen=True, slots=True)
class NormalizedValue:
    normalized_id: str
    attempt_id: str
    field_name: str
    raw_value: str
    normalized_value: str | None
    normalization_state: str  # "normalized" | "unknown" | "ambiguous" | "unparseable"
    created_at_run_clock: datetime


@dataclass(frozen=True, slots=True)
class Verdict:
    verdict_id: str
    attempt_id: str
    verifier_agent_run_id: str
    model: str
    prompt_hash: str
    verdict: str  # one of VERDICT_TYPES
    reasoning_summary: str | None
    supporting_evidence_ids: tuple[str, ...]
    proposed_correction_json: str | None
    confidence: float | None
    created_at_run_clock: datetime


@dataclass(frozen=True, slots=True)
class VerdictAggregateRow:
    aggregate_id: str
    attempt_id: str
    aggregated_verdict: str
    aggregation_policy_version: str
    input_verdict_ids: tuple[str, ...]
    decided_at_run_clock: datetime


@dataclass(frozen=True, slots=True)
class CoverageCheck:
    coverage_id: str
    deal_slug: str
    category: str
    subcategory: str | None
    check_state: str  # one of COVERAGE_STATES
    evidence_id: str | None
    attempt_id: str | None
    required: bool
    notes: str | None
    created_at_run_clock: datetime


@dataclass(frozen=True, slots=True)
class Conflict:
    conflict_id: str
    deal_slug: str
    conflict_type: str
    attempt_ids: tuple[str, ...]
    description: str | None
    resolution_state: str  # "open" | "resolved" | "escalated"
    created_at_run_clock: datetime


@dataclass(frozen=True, slots=True)
class HumanDecision:
    decision_id: str
    attempt_id: str | None
    decision: str  # "accept" | "reject" | "correct" | "defer"
    correction_json: str | None
    reviewer: str
    reviewed_at: datetime
    notes: str | None = None


# ---------------------------------------------------------------- repository

def _new_id(prefix: str) -> str:
    return f"{prefix}:{uuid.uuid4().hex}"


class DealRoomRepository:
    """Thin typed adapter over a DuckDB connection."""

    def __init__(self, connection: Any) -> None:
        self._conn = connection

    # ------------- source records -------------

    def insert_source_record(self, record: SourceRecord) -> str:
        self._conn.execute(
            """
            INSERT INTO source_records
                (source_record_id, record_type, filing_id, payload_json,
                 char_start, char_end, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record.record_id,
                record.record_type,
                record.filing_id,
                record.payload_json,
                record.char_start,
                record.char_end,
                record.created_at,
            ),
        )
        return record.record_id

    # ------------- claim attempts -------------

    def insert_claim_attempt(self, attempt: ClaimAttempt) -> str:
        if attempt.status not in LIFECYCLE_STATES:
            raise ValueError(f"unknown lifecycle state: {attempt.status!r}")
        self._conn.execute(
            """
            INSERT INTO claim_attempts
                (attempt_id, claim_fingerprint, deal_slug, claim_type,
                 payload_json, origin_agent_role, origin_agent_run_id,
                 model, prompt_hash, created_sequence,
                 created_at_run_clock, status, supersedes_attempt_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                attempt.attempt_id,
                attempt.claim_fingerprint,
                attempt.deal_slug,
                attempt.claim_type,
                attempt.payload_json,
                attempt.origin_agent_role,
                attempt.origin_agent_run_id,
                attempt.model,
                attempt.prompt_hash,
                attempt.created_sequence,
                attempt.created_at_run_clock,
                attempt.status,
                attempt.supersedes_attempt_id,
            ),
        )
        self._record_status_history(
            attempt.attempt_id,
            from_status=None,
            to_status=attempt.status,
            reason="initial",
            transitioned_at=attempt.created_at_run_clock,
        )
        return attempt.attempt_id

    def get_attempt_status(self, attempt_id: str) -> str:
        row = self._conn.execute(
            "SELECT status FROM claim_attempts WHERE attempt_id = ?",
            (attempt_id,),
        ).fetchone()
        if row is None:
            raise KeyError(f"unknown attempt_id: {attempt_id!r}")
        return row[0]

    def transition_attempt(
        self,
        attempt_id: str,
        *,
        to_status: str,
        reason: str,
        transitioned_at: datetime,
    ) -> None:
        from_status = self.get_attempt_status(attempt_id)
        validate_transition(from_status=from_status, to_status=to_status)
        self._conn.execute(
            "UPDATE claim_attempts SET status = ? WHERE attempt_id = ?",
            (to_status, attempt_id),
        )
        self._record_status_history(
            attempt_id,
            from_status=from_status,
            to_status=to_status,
            reason=reason,
            transitioned_at=transitioned_at,
        )

    def create_correction(
        self,
        *,
        original_attempt_id: str,
        corrected_payload_json: str,
        claim_fingerprint: str,
        deal_slug: str,
        claim_type: str,
        origin_agent_role: str,
        origin_agent_run_id: str,
        model: str,
        prompt_hash: str,
        created_sequence: int,
        created_at_run_clock: datetime,
        reason: str = "correction_from_partial_verdict",
    ) -> str:
        """Append a corrected attempt and supersede the original.

        Returns the new attempt_id. Never mutates the original payload.
        """
        new_attempt_id = _new_id("attempt")
        new_attempt = ClaimAttempt(
            attempt_id=new_attempt_id,
            claim_fingerprint=claim_fingerprint,
            deal_slug=deal_slug,
            claim_type=claim_type,
            payload_json=corrected_payload_json,
            origin_agent_role=origin_agent_role,
            origin_agent_run_id=origin_agent_run_id,
            model=model,
            prompt_hash=prompt_hash,
            created_sequence=created_sequence,
            created_at_run_clock=created_at_run_clock,
            status="proposed",
            supersedes_attempt_id=original_attempt_id,
        )
        self.insert_claim_attempt(new_attempt)
        self.transition_attempt(
            original_attempt_id,
            to_status="superseded",
            reason=reason,
            transitioned_at=created_at_run_clock,
        )
        return new_attempt_id

    def list_attempts_for_fingerprint(
        self, claim_fingerprint: str
    ) -> list[tuple[str, str]]:
        rows = self._conn.execute(
            "SELECT attempt_id, origin_agent_role FROM claim_attempts "
            "WHERE claim_fingerprint = ? ORDER BY created_sequence",
            (claim_fingerprint,),
        ).fetchall()
        return [(r[0], r[1]) for r in rows]

    # ------------- evidence bindings -------------

    def insert_evidence_binding(self, binding: EvidenceBinding) -> str:
        self._conn.execute(
            """
            INSERT INTO evidence_bindings
                (binding_id, attempt_id, evidence_id, filing_id, paragraph_id,
                 char_start, char_end, quote_text, quote_text_hash,
                 binding_status, binding_error_code, tool_version,
                 created_at_run_clock)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                binding.binding_id,
                binding.attempt_id,
                binding.evidence_id,
                binding.filing_id,
                binding.paragraph_id,
                binding.char_start,
                binding.char_end,
                binding.quote_text,
                binding.quote_text_hash,
                binding.binding_status,
                binding.binding_error_code,
                binding.tool_version,
                binding.created_at_run_clock,
            ),
        )
        return binding.binding_id

    # ------------- normalized values -------------

    def insert_normalized_value(self, value: NormalizedValue) -> str:
        self._conn.execute(
            """
            INSERT INTO normalized_values
                (normalized_id, attempt_id, field_name, raw_value,
                 normalized_value, normalization_state, created_at_run_clock)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                value.normalized_id,
                value.attempt_id,
                value.field_name,
                value.raw_value,
                value.normalized_value,
                value.normalization_state,
                value.created_at_run_clock,
            ),
        )
        return value.normalized_id

    # ------------- verdicts -------------

    def insert_verdict(self, verdict: Verdict) -> str:
        if verdict.verdict not in VERDICT_TYPES:
            raise ValueError(f"unknown verdict type: {verdict.verdict!r}")
        self._conn.execute(
            """
            INSERT INTO verifier_verdicts
                (verdict_id, attempt_id, verifier_agent_run_id, model,
                 prompt_hash, verdict, reasoning_summary,
                 supporting_evidence_ids_json, proposed_correction_json,
                 confidence, created_at_run_clock)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                verdict.verdict_id,
                verdict.attempt_id,
                verdict.verifier_agent_run_id,
                verdict.model,
                verdict.prompt_hash,
                verdict.verdict,
                verdict.reasoning_summary,
                json.dumps(list(verdict.supporting_evidence_ids)),
                verdict.proposed_correction_json,
                verdict.confidence,
                verdict.created_at_run_clock,
            ),
        )
        return verdict.verdict_id

    def list_verdicts(self, attempt_id: str) -> list[Verdict]:
        rows = self._conn.execute(
            """
            SELECT verdict_id, attempt_id, verifier_agent_run_id, model,
                   prompt_hash, verdict, reasoning_summary,
                   supporting_evidence_ids_json, proposed_correction_json,
                   confidence, created_at_run_clock
            FROM verifier_verdicts
            WHERE attempt_id = ?
            ORDER BY created_at_run_clock, verdict_id
            """,
            (attempt_id,),
        ).fetchall()
        return [
            Verdict(
                verdict_id=r[0],
                attempt_id=r[1],
                verifier_agent_run_id=r[2],
                model=r[3],
                prompt_hash=r[4],
                verdict=r[5],
                reasoning_summary=r[6],
                supporting_evidence_ids=tuple(json.loads(r[7])),
                proposed_correction_json=r[8],
                confidence=r[9],
                created_at_run_clock=r[10],
            )
            for r in rows
        ]

    def aggregate_attempt(
        self,
        attempt_id: str,
        *,
        decided_at_run_clock: datetime,
    ) -> AggregatedVerdict:
        """Recompute the aggregate from *all* verdicts and write a fresh row.

        Aggregation never just takes the latest verdict — see
        `lifecycle.aggregate_verdicts` for the policy.
        """
        verdicts = self.list_verdicts(attempt_id)
        aggregated = aggregate_verdicts(verdicts)
        aggregate_id = _new_id("aggregate")
        self._conn.execute(
            """
            INSERT INTO verdict_aggregates
                (aggregate_id, attempt_id, aggregated_verdict,
                 aggregation_policy_version, input_verdict_ids_json,
                 decided_at_run_clock)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                aggregate_id,
                attempt_id,
                aggregated.outcome,
                AGGREGATION_POLICY_VERSION,
                json.dumps([v.verdict_id for v in verdicts]),
                decided_at_run_clock,
            ),
        )
        return aggregated

    # ------------- coverage / conflicts / human decisions -------------

    def insert_coverage_check(self, check: CoverageCheck) -> str:
        if check.check_state not in COVERAGE_STATES:
            raise ValueError(f"unknown coverage state: {check.check_state!r}")
        self._conn.execute(
            """
            INSERT INTO coverage_checks
                (coverage_id, deal_slug, category, subcategory, check_state,
                 evidence_id, attempt_id, required, notes, created_at_run_clock)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                check.coverage_id,
                check.deal_slug,
                check.category,
                check.subcategory,
                check.check_state,
                check.evidence_id,
                check.attempt_id,
                check.required,
                check.notes,
                check.created_at_run_clock,
            ),
        )
        return check.coverage_id

    def list_coverage_checks(self, deal_slug: str) -> list[CoverageCheck]:
        rows = self._conn.execute(
            """
            SELECT coverage_id, deal_slug, category, subcategory, check_state,
                   evidence_id, attempt_id, required, notes, created_at_run_clock
            FROM coverage_checks
            WHERE deal_slug = ?
            ORDER BY created_at_run_clock, coverage_id
            """,
            (deal_slug,),
        ).fetchall()
        return [
            CoverageCheck(
                coverage_id=r[0],
                deal_slug=r[1],
                category=r[2],
                subcategory=r[3],
                check_state=r[4],
                evidence_id=r[5],
                attempt_id=r[6],
                required=bool(r[7]),
                notes=r[8],
                created_at_run_clock=r[9],
            )
            for r in rows
        ]

    def insert_conflict(self, conflict: Conflict) -> str:
        self._conn.execute(
            """
            INSERT INTO conflicts
                (conflict_id, deal_slug, conflict_type, attempt_ids_json,
                 description, resolution_state, created_at_run_clock)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                conflict.conflict_id,
                conflict.deal_slug,
                conflict.conflict_type,
                json.dumps(list(conflict.attempt_ids)),
                conflict.description,
                conflict.resolution_state,
                conflict.created_at_run_clock,
            ),
        )
        return conflict.conflict_id

    def insert_human_decision(self, decision: HumanDecision) -> str:
        self._conn.execute(
            """
            INSERT INTO human_decisions
                (decision_id, attempt_id, decision, correction_json,
                 reviewer, reviewed_at, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                decision.decision_id,
                decision.attempt_id,
                decision.decision,
                decision.correction_json,
                decision.reviewer,
                decision.reviewed_at,
                decision.notes,
            ),
        )
        return decision.decision_id

    # ------------- internals -------------

    def _record_status_history(
        self,
        attempt_id: str,
        *,
        from_status: str | None,
        to_status: str,
        reason: str | None,
        transitioned_at: datetime,
    ) -> None:
        self._conn.execute(
            """
            INSERT INTO claim_attempt_status_history
                (history_id, attempt_id, from_status, to_status, reason,
                 transitioned_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                _new_id("history"),
                attempt_id,
                from_status,
                to_status,
                reason,
                transitioned_at,
            ),
        )
