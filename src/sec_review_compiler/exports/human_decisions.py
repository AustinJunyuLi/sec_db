"""Human decision import — CSV reader + lifecycle applier.

A reviewer fills the `human_decisions_template.csv` exported by US-007
and re-imports it. Decisions are written as `human_decisions` rows; the
applier drives the matching lifecycle transitions and creates correction
attempts where appropriate. The original attempt's payload is never
mutated (design spec §10.9).
"""

from __future__ import annotations

import csv
import secrets
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Sequence

from ..errors import CompilerError
from ..store.lifecycle import IllegalTransitionError
from ..store.repository import (
    ClaimAttempt,
    DealRoomRepository,
    HumanDecision,
)


VALID_DECISIONS: frozenset[str] = frozenset({"accept", "reject", "correct", "defer"})


# ---------------------------------------------------------------- types

class HumanDecisionImportError(CompilerError):
    """Raised when an imported decision violates the contract."""


@dataclass(frozen=True, slots=True)
class HumanDecisionImport:
    attempt_id: str
    decision: str
    correction_json: str | None
    reviewer: str
    reviewed_at: datetime
    notes: str | None


@dataclass(frozen=True, slots=True)
class AppliedDecision:
    decision_id: str
    attempt_id: str
    decision: str
    new_attempt_id: str | None
    final_status: str
    note: str


@dataclass(frozen=True, slots=True)
class HumanDecisionApplyResult:
    applied: tuple[AppliedDecision, ...]


# ---------------------------------------------------------------- CSV

def _parse_iso(value: str, *, field_name: str) -> datetime:
    text = value.strip()
    if not text:
        raise HumanDecisionImportError(f"{field_name} is empty")
    try:
        # Accept naive or tz-aware. Treat naive as UTC.
        dt = datetime.fromisoformat(text)
    except ValueError as exc:
        raise HumanDecisionImportError(
            f"{field_name}={text!r} is not ISO 8601"
        ) from exc
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def parse_human_decisions_csv(path: Path) -> list[HumanDecisionImport]:
    """Read `path` and return validated `HumanDecisionImport` records."""
    decisions: list[HumanDecisionImport] = []
    with Path(path).open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        required_cols = {"attempt_id", "decision", "reviewer", "reviewed_at"}
        if reader.fieldnames is None:
            raise HumanDecisionImportError("CSV is empty (no header)")
        missing_cols = required_cols - set(reader.fieldnames)
        if missing_cols:
            raise HumanDecisionImportError(
                f"missing required columns: {sorted(missing_cols)}"
            )
        for row_number, raw in enumerate(reader, start=2):  # header is line 1
            attempt_id = (raw.get("attempt_id") or "").strip()
            if not attempt_id:
                raise HumanDecisionImportError(
                    f"row {row_number}: attempt_id is empty"
                )
            decision = (raw.get("decision") or "").strip().lower()
            if decision not in VALID_DECISIONS:
                raise HumanDecisionImportError(
                    f"row {row_number}: decision={decision!r} not in {sorted(VALID_DECISIONS)}"
                )
            correction_json = raw.get("correction_json") or ""
            correction_json = correction_json if correction_json.strip() else None
            reviewer = (raw.get("reviewer") or "").strip()
            if not reviewer:
                raise HumanDecisionImportError(
                    f"row {row_number}: reviewer is empty"
                )
            reviewed_at = _parse_iso(
                raw.get("reviewed_at") or "", field_name=f"row {row_number} reviewed_at"
            )
            notes = raw.get("notes") or ""
            notes = notes if notes.strip() else None
            decisions.append(
                HumanDecisionImport(
                    attempt_id=attempt_id,
                    decision=decision,
                    correction_json=correction_json,
                    reviewer=reviewer,
                    reviewed_at=reviewed_at,
                    notes=notes,
                )
            )
    return decisions


# ---------------------------------------------------------------- lifecycle paths

# Legal lifecycle paths a human decision is allowed to drive. Each path
# is a list of intermediate states leading to the final state. We follow
# the existing TRANSITIONS map; the applier will refuse if the current
# state cannot reach the target via any of these paths.
_ACCEPT_PATHS: dict[str, tuple[str, ...]] = {
    "accepted": (),
    "consistent": ("accepted",),
    "escalated": ("accepted",),
    "verified_confirmed": ("consistent", "accepted"),
    "verified_partial": ("escalated", "accepted"),
    "verified_rejected": ("escalated", "accepted"),
}

# Reject lifecycle paths. Terminal -> raise.
_REJECT_PATHS: dict[str, tuple[str, ...]] = {
    "verified_confirmed": ("superseded",),
    "verified_partial": ("superseded",),
    "verified_rejected": ("superseded",),
    "escalated": ("superseded",),
    "consistent": ("escalated", "superseded"),
    "accepted": ("superseded",),
}


# ---------------------------------------------------------------- applier

def _new_id(prefix: str) -> str:
    return f"{prefix}:{secrets.token_hex(8)}"


def apply_human_decisions(
    repo: DealRoomRepository,
    *,
    decisions: Sequence[HumanDecisionImport],
    deal_slug: str,
    transitioned_at: datetime | None = None,
) -> HumanDecisionApplyResult:
    """Apply each decision to the deal-room.

    Always records a `human_decisions` row first so audit history is
    preserved even when a transition refuses. The applier never mutates
    `claim_attempts.payload_json` — corrections create new attempts
    via `repo.create_correction`.
    """
    transitioned_at = transitioned_at or datetime.now(timezone.utc)
    applied: list[AppliedDecision] = []

    for decision in decisions:
        original_attempt = _fetch_attempt(repo, decision.attempt_id)
        decision_id = _new_id("decision")
        # Always record the decision before any transition attempt.
        repo.insert_human_decision(
            HumanDecision(
                decision_id=decision_id,
                attempt_id=decision.attempt_id,
                decision=decision.decision,
                correction_json=decision.correction_json,
                reviewer=decision.reviewer,
                reviewed_at=decision.reviewed_at,
                notes=decision.notes,
            )
        )

        if decision.decision == "defer":
            applied.append(
                AppliedDecision(
                    decision_id=decision_id,
                    attempt_id=decision.attempt_id,
                    decision=decision.decision,
                    new_attempt_id=None,
                    final_status=original_attempt["status"],
                    note="deferred — no transition",
                )
            )
            continue

        if decision.decision == "correct":
            if not (decision.correction_json and decision.correction_json.strip()):
                applied.append(
                    AppliedDecision(
                        decision_id=decision_id,
                        attempt_id=decision.attempt_id,
                        decision=decision.decision,
                        new_attempt_id=None,
                        final_status=original_attempt["status"],
                        note="notes-only correction; no new attempt created",
                    )
                )
                continue
            new_id = repo.create_correction(
                original_attempt_id=decision.attempt_id,
                corrected_payload_json=decision.correction_json,
                claim_fingerprint=f"{original_attempt['claim_fingerprint']}:human",
                deal_slug=deal_slug,
                claim_type=original_attempt["claim_type"],
                origin_agent_role="human:correction",
                origin_agent_run_id=f"human:{decision.reviewer}",
                model="human",
                prompt_hash="human:correction_v1",
                created_sequence=int(original_attempt["created_sequence"]) + 100_000,
                created_at_run_clock=transitioned_at,
                reason="human_correct",
            )
            applied.append(
                AppliedDecision(
                    decision_id=decision_id,
                    attempt_id=decision.attempt_id,
                    decision=decision.decision,
                    new_attempt_id=new_id,
                    final_status="superseded",
                    note="correction created new attempt; original superseded",
                )
            )
            continue

        if decision.decision == "accept":
            path = _resolve_path(_ACCEPT_PATHS, original_attempt["status"], "accept")
            for intermediate in path:
                repo.transition_attempt(
                    decision.attempt_id,
                    to_status=intermediate,
                    reason=f"human_accept:{decision.reviewer}",
                    transitioned_at=transitioned_at,
                )
            applied.append(
                AppliedDecision(
                    decision_id=decision_id,
                    attempt_id=decision.attempt_id,
                    decision=decision.decision,
                    new_attempt_id=None,
                    final_status="accepted" if path else original_attempt["status"],
                    note=f"path={list(path)}",
                )
            )
            continue

        if decision.decision == "reject":
            path = _resolve_path(_REJECT_PATHS, original_attempt["status"], "reject")
            for intermediate in path:
                repo.transition_attempt(
                    decision.attempt_id,
                    to_status=intermediate,
                    reason=f"human_reject:{decision.reviewer}",
                    transitioned_at=transitioned_at,
                )
            applied.append(
                AppliedDecision(
                    decision_id=decision_id,
                    attempt_id=decision.attempt_id,
                    decision=decision.decision,
                    new_attempt_id=None,
                    final_status="superseded",
                    note=f"path={list(path)}",
                )
            )

    return HumanDecisionApplyResult(applied=tuple(applied))


def _resolve_path(
    table: dict[str, tuple[str, ...]],
    from_status: str,
    decision_kind: str,
) -> tuple[str, ...]:
    if from_status not in table:
        raise IllegalTransitionError(
            f"human {decision_kind} decision cannot be applied to attempt in "
            f"state {from_status!r}"
        )
    return table[from_status]


def _fetch_attempt(
    repo: DealRoomRepository, attempt_id: str
) -> dict[str, object]:
    row = repo._conn.execute(  # type: ignore[attr-defined]
        """
        SELECT attempt_id, claim_fingerprint, claim_type, status,
               created_sequence
        FROM claim_attempts
        WHERE attempt_id = ?
        """,
        (attempt_id,),
    ).fetchone()
    if row is None:
        raise HumanDecisionImportError(
            f"unknown attempt_id in human decision import: {attempt_id!r}"
        )
    return {
        "attempt_id": row[0],
        "claim_fingerprint": row[1],
        "claim_type": row[2],
        "status": row[3],
        "created_sequence": row[4],
    }
