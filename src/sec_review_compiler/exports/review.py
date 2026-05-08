"""Per-deal review exports — CSV and JSONL.

CSVs are deterministic: rows are sorted by `attempt_id` and the column
order is fixed. JSONLs are written line-by-line with newline at end.
All writes are atomic via temp+replace.
"""

from __future__ import annotations

import csv
import io
import json
from pathlib import Path
from typing import Iterable, Sequence

from ..run.io import atomic_write_text
from ..store.repository import DealRoomRepository

CLAIM_CARD_COLUMNS: tuple[str, ...] = (
    "attempt_id",
    "deal_slug",
    "claim_type",
    "claim_fingerprint",
    "status",
    "supersedes_attempt_id",
    "origin_agent_role",
    "evidence_paragraph_ids",
    "evidence_quote_count",
    "payload_json",
)

REVIEW_QUEUE_COLUMNS: tuple[str, ...] = (
    "attempt_id",
    "deal_slug",
    "claim_type",
    "status",
    "reason",
    "evidence_paragraph_ids",
)

HUMAN_DECISIONS_COLUMNS: tuple[str, ...] = (
    "attempt_id",
    "decision",
    "correction_json",
    "reviewer",
    "reviewed_at",
    "notes",
)

REVIEW_QUEUE_STATUSES: frozenset[str] = frozenset(
    {"verified_rejected", "escalated", "binding_failed"}
)


def _csv_text(columns: Sequence[str], rows: Iterable[dict]) -> str:
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=list(columns), extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow(row)
    return buf.getvalue()


def _attempts(repo: DealRoomRepository, deal_slug: str) -> list[tuple]:
    return repo._conn.execute(  # type: ignore[attr-defined]
        """
        SELECT attempt_id, deal_slug, claim_type, claim_fingerprint, status,
               supersedes_attempt_id, origin_agent_role, payload_json
        FROM claim_attempts
        WHERE deal_slug = ?
        ORDER BY created_sequence, attempt_id
        """,
        (deal_slug,),
    ).fetchall()


def _bindings_by_attempt(
    repo: DealRoomRepository, attempt_ids: Sequence[str]
) -> dict[str, list[tuple]]:
    if not attempt_ids:
        return {}
    placeholders = ",".join("?" for _ in attempt_ids)
    rows = repo._conn.execute(  # type: ignore[attr-defined]
        f"""
        SELECT attempt_id, paragraph_id, quote_text, binding_status, binding_error_code
        FROM evidence_bindings
        WHERE attempt_id IN ({placeholders})
        ORDER BY attempt_id, binding_id
        """,
        list(attempt_ids),
    ).fetchall()
    out: dict[str, list[tuple]] = {}
    for r in rows:
        out.setdefault(r[0], []).append(r)
    return out


def _latest_status_reason(
    repo: DealRoomRepository, attempt_ids: Sequence[str]
) -> dict[str, str]:
    if not attempt_ids:
        return {}
    placeholders = ",".join("?" for _ in attempt_ids)
    rows = repo._conn.execute(  # type: ignore[attr-defined]
        f"""
        SELECT attempt_id, reason FROM claim_attempt_status_history
        WHERE attempt_id IN ({placeholders})
        ORDER BY transitioned_at DESC
        """,
        list(attempt_ids),
    ).fetchall()
    latest: dict[str, str] = {}
    for r in rows:
        latest.setdefault(r[0], r[1] or "")
    return latest


# ====================================================== claim_cards.csv

def export_claim_cards(
    repo: DealRoomRepository,
    exports_dir: Path,
    *,
    deal_slug: str,
) -> Path:
    rows: list[dict] = []
    attempts = _attempts(repo, deal_slug)
    bindings = _bindings_by_attempt(repo, [a[0] for a in attempts])
    for (
        attempt_id,
        d_slug,
        claim_type,
        fingerprint,
        status,
        supersedes,
        role,
        payload_json,
    ) in attempts:
        bs = bindings.get(attempt_id, [])
        rows.append(
            {
                "attempt_id": attempt_id,
                "deal_slug": d_slug,
                "claim_type": claim_type,
                "claim_fingerprint": fingerprint,
                "status": status,
                "supersedes_attempt_id": supersedes or "",
                "origin_agent_role": role,
                "evidence_paragraph_ids": "|".join(b[1] or "" for b in bs),
                "evidence_quote_count": len(bs),
                "payload_json": payload_json,
            }
        )
    target = exports_dir / "claim_cards.csv"
    atomic_write_text(target, _csv_text(CLAIM_CARD_COLUMNS, rows))
    return target


# ====================================================== review_queue.csv

def export_review_queue(
    repo: DealRoomRepository,
    exports_dir: Path,
    *,
    deal_slug: str,
) -> Path:
    rows: list[dict] = []
    attempts = _attempts(repo, deal_slug)
    queue_attempts = [a for a in attempts if a[4] in REVIEW_QUEUE_STATUSES]
    bindings = _bindings_by_attempt(repo, [a[0] for a in queue_attempts])
    reasons = _latest_status_reason(repo, [a[0] for a in queue_attempts])
    for attempt_id, d_slug, claim_type, _fingerprint, status, *_rest in queue_attempts:
        bs = bindings.get(attempt_id, [])
        rows.append(
            {
                "attempt_id": attempt_id,
                "deal_slug": d_slug,
                "claim_type": claim_type,
                "status": status,
                "reason": reasons.get(attempt_id, ""),
                "evidence_paragraph_ids": "|".join(b[1] or "" for b in bs),
            }
        )
    target = exports_dir / "review_queue.csv"
    atomic_write_text(target, _csv_text(REVIEW_QUEUE_COLUMNS, rows))
    return target


# ====================================================== human_decisions_template.csv

def export_human_decisions_template(
    repo: DealRoomRepository,
    exports_dir: Path,
    *,
    deal_slug: str,
) -> Path:
    """Empty CSV with the human-decision header columns.

    Reviewers fill in `decision`, optional `correction_json`, etc., and
    re-import via the human_decisions ingestion path (US-009).
    """
    target = exports_dir / "human_decisions_template.csv"
    atomic_write_text(target, _csv_text(HUMAN_DECISIONS_COLUMNS, []))
    return target


# ====================================================== provider_calls.jsonl

def export_provider_calls(
    deal_dir: Path,
    records: Iterable[dict],
) -> Path:
    target = deal_dir / "provider_calls.jsonl"
    body = "".join(json.dumps(r, sort_keys=True, default=str) + "\n" for r in records)
    atomic_write_text(target, body)
    return target


# ====================================================== tool_calls.jsonl

def export_tool_calls(
    deal_dir: Path,
    records: Iterable[dict],
) -> Path:
    target = deal_dir / "tool_calls.jsonl"
    body = "".join(json.dumps(r, sort_keys=True, default=str) + "\n" for r in records)
    atomic_write_text(target, body)
    return target
