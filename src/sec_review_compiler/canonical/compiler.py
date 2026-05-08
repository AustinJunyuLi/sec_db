"""Deterministic canonical compiler.

Reads the deal-room store, applies refusal gates, and writes canonical
rows + row evidence. The compile is atomic in the doctrine sense: if any
refusal fires, no canonical rows are written.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Sequence

from ..errors import CompilerError
from ..store.lifecycle import can_publish_trusted
from ..store.repository import DealRoomRepository
from .models import (
    CanonicalDeal,
    CanonicalEvent,
    CanonicalFiling,
    CanonicalRowEvidenceLink,
    CanonicalSourceSpan,
)


_BLOCKING_RESOLUTION_STATES = frozenset({"open", "escalated"})


# ---------------------------------------------------------------- ids

def canonical_row_id(
    *,
    table: str,
    run_id: str,
    deal_slug: str,
    source_ids: Sequence[str],
    payload_keys: Sequence[str],
) -> str:
    """Deterministic canonical row id from public inputs only.

    Inputs are sorted before hashing so callers can pass them in any order.
    """
    payload = "||".join([
        table,
        run_id,
        deal_slug,
        ",".join(sorted(source_ids)),
        ",".join(sorted(payload_keys)),
    ])
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return f"canonical:{table}:{digest[:32]}"


# ---------------------------------------------------------------- result

@dataclass(frozen=True, slots=True)
class CompileRefusalReason:
    code: str
    description: str
    payload: tuple[tuple[str, str], ...]


@dataclass(frozen=True, slots=True)
class CompileResult:
    published: bool
    run_id: str
    deal_slug: str
    refusals: tuple[CompileRefusalReason, ...]
    canonical_row_counts: dict[str, int]
    canonical_row_ids: dict[str, tuple[str, ...]]


class CompileError(CompilerError):
    """Raised when callers ask for strict compile and refusals fire."""


# ---------------------------------------------------------------- compiler

class CanonicalCompiler:
    """Read-only against attempts; write-only against canonical_rows."""

    def __init__(
        self,
        repo: DealRoomRepository,
        *,
        run_id: str,
        deal_slug: str,
        compiled_at_run_clock: datetime,
    ) -> None:
        self._repo = repo
        self._run_id = run_id
        self._deal_slug = deal_slug
        self._compiled_at = compiled_at_run_clock
        self._conn = repo._conn  # type: ignore[attr-defined]

    # ------------------------------------------------------ public

    def compile(self) -> CompileResult:
        refusals = self._gather_refusals()
        if refusals:
            return CompileResult(
                published=False,
                run_id=self._run_id,
                deal_slug=self._deal_slug,
                refusals=tuple(refusals),
                canonical_row_counts={},
                canonical_row_ids={},
            )

        # Wipe any prior compile output for this deal so recompile is exact.
        self._wipe_canonical()

        rows_by_table: dict[str, list[dict[str, Any]]] = {}
        evidence_links: list[CanonicalRowEvidenceLink] = []
        attempts = self._fetch_accepted_attempts()
        bindings_by_attempt = self._fetch_accepted_bindings(
            [a["attempt_id"] for a in attempts]
        )

        # Deal row.
        deal = self._build_deal()
        rows_by_table.setdefault("deal", []).append(deal.model_dump(mode="json"))

        # Filing rows — one per distinct filing in accepted bindings.
        filings_seen: dict[str, CanonicalFiling] = {}

        # Source span rows — one per accepted evidence binding.
        spans: list[CanonicalSourceSpan] = []

        # Event rows — one per accepted attempt with claim_type 'timeline_event'.
        for attempt in attempts:
            attempt_id = attempt["attempt_id"]
            attempt_bindings = bindings_by_attempt.get(attempt_id, [])
            if not attempt_bindings:
                # Acceptance gate already requires bindings, but defend in depth.
                refusals.append(
                    CompileRefusalReason(
                        code="accepted_without_binding",
                        description=(
                            f"attempt {attempt_id} is accepted but has no accepted "
                            "evidence bindings"
                        ),
                        payload=(("attempt_id", attempt_id),),
                    )
                )
                continue
            for binding in attempt_bindings:
                if binding["char_start"] is None or binding["char_end"] is None:
                    refusals.append(
                        CompileRefusalReason(
                            code="missing_evidence_coordinates",
                            description=(
                                f"binding {binding['binding_id']} on attempt "
                                f"{attempt_id} has null char offsets"
                            ),
                            payload=(("binding_id", binding["binding_id"]),),
                        )
                    )
                    continue
                # Filing row (idempotent).
                if binding["filing_id"] not in filings_seen:
                    filing_row = self._build_filing(filing_id=binding["filing_id"], raw_sha256=binding["quote_text_hash"])
                    filings_seen[binding["filing_id"]] = filing_row
                # Source span row.
                span = self._build_source_span(
                    filing_id=binding["filing_id"],
                    char_start=int(binding["char_start"]),
                    char_end=int(binding["char_end"]),
                    quote_text_hash=binding["quote_text_hash"],
                    evidence_id=binding["evidence_id"],
                    paragraph_id=binding["paragraph_id"],
                )
                spans.append(span)
                # Provisional event-evidence link is added below per attempt.

        if refusals:
            return CompileResult(
                published=False,
                run_id=self._run_id,
                deal_slug=self._deal_slug,
                refusals=tuple(refusals),
                canonical_row_counts={},
                canonical_row_ids={},
            )

        for filing_row in filings_seen.values():
            rows_by_table.setdefault("filing", []).append(filing_row.model_dump(mode="json"))
        for span in spans:
            rows_by_table.setdefault("source_span", []).append(span.model_dump(mode="json"))

        # Build event rows now (we already validated bindings).
        # Every accepted attempt with bindings yields a canonical event row;
        # the event_type comes from the payload (or the attempt's claim_type
        # as a fallback) so the compiler does not gate on fixture-specific
        # claim_type strings.
        for attempt in attempts:
            attempt_id = attempt["attempt_id"]
            attempt_bindings = bindings_by_attempt.get(attempt_id, [])
            try:
                payload = json.loads(attempt["payload_json"])
            except json.JSONDecodeError:
                payload = {}
            if "event_type" not in payload:
                payload["event_type"] = attempt["claim_type"]
            event = self._build_event(
                payload=payload,
                evidence_ids=tuple(b["evidence_id"] for b in attempt_bindings),
            )
            rows_by_table.setdefault("event", []).append(event.model_dump(mode="json"))
            for ordinal, binding in enumerate(attempt_bindings):
                evidence_links.append(
                    CanonicalRowEvidenceLink(
                        canonical_row_id=event.canonical_row_id,
                        attempt_id=attempt_id,
                        evidence_id=binding["evidence_id"],
                        ordinal=ordinal,
                    )
                )

        # Persist.
        canonical_row_ids: dict[str, list[str]] = {}
        for table, rows in rows_by_table.items():
            for row in rows:
                row_id = row["canonical_row_id"]
                self._conn.execute(
                    """
                    INSERT INTO canonical_rows
                        (canonical_row_id, canonical_table, payload_json,
                         compiled_at_run_clock, compiled_run_id, requires_human_review)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        row_id,
                        table,
                        json.dumps(row, sort_keys=True, separators=(",", ":")),
                        self._compiled_at,
                        self._run_id,
                        False,
                    ),
                )
                canonical_row_ids.setdefault(table, []).append(row_id)

        for link in evidence_links:
            self._conn.execute(
                """
                INSERT INTO canonical_row_evidence
                    (canonical_row_id, attempt_id, evidence_id, ordinal)
                VALUES (?, ?, ?, ?)
                """,
                (link.canonical_row_id, link.attempt_id, link.evidence_id, link.ordinal),
            )

        counts = {t: len(ids) for t, ids in canonical_row_ids.items()}
        return CompileResult(
            published=True,
            run_id=self._run_id,
            deal_slug=self._deal_slug,
            refusals=(),
            canonical_row_counts=counts,
            canonical_row_ids={t: tuple(ids) for t, ids in canonical_row_ids.items()},
        )

    # ------------------------------------------------------ refusal gates

    def _gather_refusals(self) -> list[CompileRefusalReason]:
        refusals: list[CompileRefusalReason] = []

        # Coverage gate.
        coverage = self._repo.list_coverage_checks(self._deal_slug)
        decision = can_publish_trusted(coverage)
        if not decision.can_publish_trusted:
            refusals.append(
                CompileRefusalReason(
                    code="coverage_failed_to_check",
                    description=decision.rationale,
                    payload=tuple(
                        ("blocking_category", c) for c in decision.blocking_categories
                    ),
                )
            )

        # Blocking conflicts.
        conflict_rows = self._conn.execute(
            "SELECT conflict_id, conflict_type, resolution_state FROM conflicts "
            "WHERE deal_slug = ? AND resolution_state IN ('open', 'escalated')",
            (self._deal_slug,),
        ).fetchall()
        for cid, ctype, state in conflict_rows:
            refusals.append(
                CompileRefusalReason(
                    code="blocking_conflict",
                    description=(
                        f"conflict {cid} of type {ctype!r} in state {state!r} blocks "
                        "canonical publication"
                    ),
                    payload=(("conflict_id", cid), ("resolution_state", state)),
                )
            )
        return refusals

    # ------------------------------------------------------ fetches

    def _fetch_accepted_attempts(self) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            """
            SELECT attempt_id, deal_slug, claim_type, payload_json
            FROM claim_attempts
            WHERE deal_slug = ? AND status = 'accepted'
            ORDER BY created_sequence, attempt_id
            """,
            (self._deal_slug,),
        ).fetchall()
        return [
            {
                "attempt_id": r[0],
                "deal_slug": r[1],
                "claim_type": r[2],
                "payload_json": r[3],
            }
            for r in rows
        ]

    def _fetch_accepted_bindings(
        self, attempt_ids: Sequence[str]
    ) -> dict[str, list[dict[str, Any]]]:
        if not attempt_ids:
            return {}
        placeholders = ",".join("?" for _ in attempt_ids)
        rows = self._conn.execute(
            f"""
            SELECT binding_id, attempt_id, evidence_id, filing_id, paragraph_id,
                   char_start, char_end, quote_text, quote_text_hash
            FROM evidence_bindings
            WHERE attempt_id IN ({placeholders})
              AND binding_status = 'accepted'
            ORDER BY attempt_id, created_at_run_clock, binding_id
            """,
            list(attempt_ids),
        ).fetchall()
        out: dict[str, list[dict[str, Any]]] = {}
        for r in rows:
            out.setdefault(r[1], []).append({
                "binding_id": r[0],
                "attempt_id": r[1],
                "evidence_id": r[2],
                "filing_id": r[3],
                "paragraph_id": r[4],
                "char_start": r[5],
                "char_end": r[6],
                "quote_text": r[7],
                "quote_text_hash": r[8],
            })
        return out

    def _wipe_canonical(self) -> None:
        # We delete only rows compiled by the current run id. Other runs'
        # canonical output (none in single-deal mode) is preserved.
        self._conn.execute(
            "DELETE FROM canonical_row_evidence WHERE canonical_row_id IN ("
            "  SELECT canonical_row_id FROM canonical_rows WHERE compiled_run_id = ?"
            ")",
            (self._run_id,),
        )
        self._conn.execute(
            "DELETE FROM canonical_rows WHERE compiled_run_id = ?",
            (self._run_id,),
        )

    # ------------------------------------------------------ row builders

    def _build_deal(self) -> CanonicalDeal:
        row_id = canonical_row_id(
            table="deal",
            run_id=self._run_id,
            deal_slug=self._deal_slug,
            source_ids=[],
            payload_keys=["deal_slug"],
        )
        return CanonicalDeal(
            canonical_row_id=row_id,
            deal_slug=self._deal_slug,
            run_id=self._run_id,
        )

    def _build_filing(
        self, *, filing_id: str, raw_sha256: str
    ) -> CanonicalFiling:
        row_id = canonical_row_id(
            table="filing",
            run_id=self._run_id,
            deal_slug=self._deal_slug,
            source_ids=[filing_id],
            payload_keys=["raw_sha256"],
        )
        return CanonicalFiling(
            canonical_row_id=row_id,
            deal_slug=self._deal_slug,
            filing_id=filing_id,
            raw_sha256=raw_sha256,
        )

    def _build_source_span(
        self,
        *,
        filing_id: str,
        char_start: int,
        char_end: int,
        quote_text_hash: str,
        evidence_id: str,
        paragraph_id: str | None,
    ) -> CanonicalSourceSpan:
        row_id = canonical_row_id(
            table="source_span",
            run_id=self._run_id,
            deal_slug=self._deal_slug,
            source_ids=[evidence_id],
            payload_keys=[
                f"filing_id={filing_id}",
                f"char_start={char_start}",
                f"char_end={char_end}",
                f"quote_text_hash={quote_text_hash}",
            ],
        )
        return CanonicalSourceSpan(
            canonical_row_id=row_id,
            deal_slug=self._deal_slug,
            filing_id=filing_id,
            char_start=char_start,
            char_end=char_end,
            quote_text_hash=quote_text_hash,
            evidence_id=evidence_id,
            paragraph_id=paragraph_id,
        )

    def _build_event(
        self,
        *,
        payload: dict[str, Any],
        evidence_ids: tuple[str, ...],
    ) -> CanonicalEvent:
        event_type = str(payload.get("event_type", "unknown"))
        payload_canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        row_id = canonical_row_id(
            table="event",
            run_id=self._run_id,
            deal_slug=self._deal_slug,
            source_ids=evidence_ids,
            payload_keys=[f"event_type={event_type}", f"payload={payload_canonical}"],
        )
        return CanonicalEvent(
            canonical_row_id=row_id,
            deal_slug=self._deal_slug,
            event_type=event_type,
            payload_json=payload_canonical,
        )
