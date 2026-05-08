"""Orchestrator + offline rule-based confidentiality extractor.

The orchestrator is plain Python (no agent framework). For US-007 the
offline path uses a deterministic rule-based extractor that finds
"confidentiality agreement" mentions. The live path (out of scope for
this story) will inject a Linkflow-driven extractor instead.

Doctrine guardrails enforced here:
- agents emit only structured proposals (`ExtractedClaim`); the
  orchestrator validates and writes;
- the run clock comes from `RunId.started_at`, not a wall clock, so
  exports are reproducible;
- partial verdicts always create new attempts (`create_correction`);
  the original attempt's payload is never mutated;
- canonical eligibility (`accepted`) is reached only via the lifecycle
  state machine — rejections cannot slip through.
"""

from __future__ import annotations

import csv
import hashlib
import json
import secrets
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Iterable, Protocol, Sequence

import duckdb

from ..filing.atlas import build_atlas
from ..filing.package import FilingPackage, build_filing_package
from ..retrieval.index import RetrievalIndex
from ..retrieval.tools import verify_quote
from ..run.ids import RunClock, RunId
from ..run.io import atomic_write_json, atomic_write_text
from ..store.lifecycle import (
    AggregatedVerdict,
    aggregate_verdicts,
    can_publish_trusted,
)
from ..store.migrations import apply_schema
from ..store.repository import (
    ClaimAttempt,
    DealRoomRepository,
    EvidenceBinding,
    Verdict,
)
from .consistency import NoOpConsistencyChecker
from .coverage import compute_initial_coverage_for_slice
from .recorders import ProviderCallRecorder, ToolCallRecorder
from .verifier import OfflineFakeVerifier, Verifier, VerifierProposal


TOOL_VERSION = "deterministic_binder_v1"


@dataclass(frozen=True, slots=True)
class ExtractedClaim:
    """An extractor's proposal — never written to DuckDB by the agent."""

    claim_type: str
    claim_fingerprint: str
    payload_json: str
    cited_quotes: tuple[str, ...]
    cited_paragraph_ids: tuple[str, ...]


class Extractor(Protocol):
    def extract(self, *, package: FilingPackage, index: RetrievalIndex) -> list[ExtractedClaim]: ...  # pragma: no cover


# ---------------------------------------------------------------- offline extractor

_NDA_PATTERN = "confidentiality agreement"


class OfflineConfidentialityExtractor:
    """Rule-based extractor used when no Linkflow client is available.

    Finds paragraphs that mention a confidentiality agreement and emits
    one `ExtractedClaim` per such paragraph. This is *not* a fallback
    for the live Linkflow extractor — it is the explicit dev/offline
    path called out by the US-007 acceptance criterion.
    """

    def extract(
        self, *, package: FilingPackage, index: RetrievalIndex
    ) -> list[ExtractedClaim]:
        claims: list[ExtractedClaim] = []
        for paragraph in package.paragraphs:
            lowered = paragraph.text.lower()
            if _NDA_PATTERN not in lowered:
                continue
            verification = verify_quote(index, paragraph.text)
            if not verification.verbatim_present:
                continue
            payload = {
                "event_type": "confidentiality_agreement",
                "paragraph_id": paragraph.paragraph_id,
            }
            payload_json = json.dumps(payload, sort_keys=True, separators=(",", ":"))
            fingerprint = hashlib.sha256(
                f"confidentiality_agreement|{paragraph.paragraph_id}".encode("utf-8")
            ).hexdigest()
            claims.append(
                ExtractedClaim(
                    claim_type="timeline_event",
                    claim_fingerprint=f"fp:{fingerprint[:16]}",
                    payload_json=payload_json,
                    cited_quotes=(paragraph.text,),
                    cited_paragraph_ids=(paragraph.paragraph_id,),
                )
            )
        return claims


# ---------------------------------------------------------------- result types

@dataclass(frozen=True, slots=True)
class SliceArtifact:
    name: str
    path: Path


@dataclass(frozen=True, slots=True)
class SliceResult:
    run_id: str
    deal_dir: Path
    db_path: Path
    artifacts: tuple[SliceArtifact, ...]
    accepted_attempt_ids: tuple[str, ...]
    rejected_attempt_ids: tuple[str, ...]
    superseded_attempt_ids: tuple[str, ...]
    correction_attempt_ids: tuple[str, ...]
    can_publish_trusted: bool


# ---------------------------------------------------------------- orchestrator

class Orchestrator:
    def __init__(
        self,
        *,
        deal_slug: str,
        extractor: Extractor,
        verifier: Verifier,
        consistency_checker: NoOpConsistencyChecker | None = None,
        provider_recorder: ProviderCallRecorder | None = None,
        tool_recorder: ToolCallRecorder | None = None,
    ) -> None:
        self._deal_slug = deal_slug
        self._extractor = extractor
        self._verifier = verifier
        self._consistency = consistency_checker or NoOpConsistencyChecker()
        self._provider_recorder = provider_recorder
        self._tool_recorder = tool_recorder

    @property
    def deal_slug(self) -> str:
        return self._deal_slug

    # ------------------------------------------------------ entry point

    def run_synthetic_vertical_slice(
        self,
        run_dir: Path,
        filing_path: Path,
        *,
        run_id: RunId | None = None,
        filing_id: str = "synthetic-demo:0001",
        filing_type: str = "8-K",
    ) -> SliceResult:
        run_dir = Path(run_dir)
        filing_path = Path(filing_path)
        deal_dir = run_dir / self._deal_slug
        exports_dir = deal_dir / "exports"
        deal_dir.mkdir(parents=True, exist_ok=True)
        exports_dir.mkdir(parents=True, exist_ok=True)

        if run_id is None:
            # Derive a run id from the run_dir name when present.
            try:
                run_id = RunId.parse(run_dir.name)
            except Exception:
                run_id = RunId.new(self._deal_slug)
        clock = RunClock.from_run_id(run_id)
        now = clock.now()

        # ---------------- Build filing + atlas + retrieval ----------------
        raw_text = filing_path.read_text(encoding="utf-8")
        package = build_filing_package(
            filing_id=filing_id, filing_type=filing_type, raw_text=raw_text
        )
        atlas = build_atlas(package)
        index = RetrievalIndex.from_atlas(atlas, raw_text=raw_text, filing_id=filing_id)

        # Bind index into live verifier if supported (duck-typed).
        if hasattr(self._verifier, "bind_index"):
            self._verifier.bind_index(index)  # type: ignore[attr-defined]

        # Persist the filing package manifest (small, deterministic).
        atomic_write_json(
            deal_dir / "filing_package_manifest.json",
            {
                "filing_id": package.filing_id,
                "filing_type": package.filing_type,
                "raw_sha256": package.raw_sha256,
                "normalized_sha256": package.normalized_sha256,
                "paragraph_count": len(package.paragraphs),
                "exhibit_count": len(package.exhibits),
                "run_id": str(run_id),
            },
        )

        # ---------------- Open deal-room DB + run pipeline ----------------
        db_path = deal_dir / "deal_room.duckdb"
        if db_path.exists():
            db_path.unlink()
        connection = duckdb.connect(str(db_path))
        try:
            apply_schema(connection)
            repo = DealRoomRepository(connection)

            extracted = self._extractor.extract(package=package, index=index)
            attempts: list[tuple[ClaimAttempt, ExtractedClaim]] = []
            for ordinal, claim in enumerate(extracted):
                attempt = ClaimAttempt(
                    attempt_id=_new_id("attempt"),
                    claim_fingerprint=claim.claim_fingerprint,
                    deal_slug=self._deal_slug,
                    claim_type=claim.claim_type,
                    payload_json=claim.payload_json,
                    origin_agent_role="extractor:offline_confidentiality",
                    origin_agent_run_id=f"offline:{run_id}",
                    model="offline-rule",
                    prompt_hash="rule:nda_v1",
                    created_sequence=ordinal,
                    created_at_run_clock=now,
                    status="proposed",
                )
                repo.insert_claim_attempt(attempt)
                attempts.append((attempt, claim))

            # Bind evidence deterministically.
            bound_attempts: list[tuple[ClaimAttempt, ExtractedClaim]] = []
            for attempt, claim in attempts:
                all_bound = True
                for quote, paragraph_id in zip(
                    claim.cited_quotes, claim.cited_paragraph_ids
                ):
                    verification = verify_quote(index, quote)
                    if (
                        not verification.verbatim_present
                        or verification.ambiguity == "ambiguous_multiple"
                    ):
                        all_bound = False
                        binding_status = "rejected"
                        binding_error_code = (
                            "absent" if not verification.verbatim_present else "ambiguous"
                        )
                        char_start, char_end = (0, 0)
                    else:
                        char_start, char_end = verification.positions[0]
                        binding_status = "accepted"
                        binding_error_code = None
                    binding = EvidenceBinding(
                        binding_id=_new_id("binding"),
                        attempt_id=attempt.attempt_id,
                        evidence_id=_evidence_id(
                            filing_id=filing_id,
                            char_start=char_start,
                            char_end=char_end,
                            quote_text=quote,
                        ),
                        filing_id=filing_id,
                        paragraph_id=paragraph_id,
                        char_start=char_start,
                        char_end=char_end,
                        quote_text=quote,
                        quote_text_hash=hashlib.sha256(quote.encode("utf-8")).hexdigest(),
                        binding_status=binding_status,
                        binding_error_code=binding_error_code,
                        tool_version=TOOL_VERSION,
                        created_at_run_clock=now,
                    )
                    repo.insert_evidence_binding(binding)
                if all_bound:
                    repo.transition_attempt(
                        attempt.attempt_id,
                        to_status="bound",
                        reason="binder_accepted_all_evidence",
                        transitioned_at=now,
                    )
                    bound_attempts.append((attempt, claim))
                else:
                    repo.transition_attempt(
                        attempt.attempt_id,
                        to_status="binding_failed",
                        reason="binder_rejected_one_or_more_quotes",
                        transitioned_at=now,
                    )

            # Verify each bound attempt and aggregate.
            rejected_ids: list[str] = []
            superseded_ids: list[str] = []
            correction_ids: list[str] = []
            confirmed_ids: list[str] = []
            for attempt, claim in bound_attempts:
                proposal = self._verifier.verify(
                    attempt_id=attempt.attempt_id,
                    cited_quotes=claim.cited_quotes,
                    cited_paragraph_ids=claim.cited_paragraph_ids,
                    raw_text=raw_text,
                )
                self._record_verdict(repo, attempt.attempt_id, proposal, now)
                aggregated = repo.aggregate_attempt(
                    attempt.attempt_id, decided_at_run_clock=now
                )
                self._apply_aggregate_to_lifecycle(
                    repo,
                    attempt=attempt,
                    claim=claim,
                    proposal=proposal,
                    aggregated=aggregated,
                    now=now,
                    confirmed_ids=confirmed_ids,
                    rejected_ids=rejected_ids,
                    superseded_ids=superseded_ids,
                    correction_ids=correction_ids,
                )

            # Consistency stub — no findings for the slice.
            self._consistency.check(
                [a for a, _ in attempts]  # original attempts only
            )

            # Promote confirmed attempts through consistent → accepted.
            accepted_ids: list[str] = []
            for attempt_id in confirmed_ids:
                if repo.get_attempt_status(attempt_id) != "verified_confirmed":
                    continue
                repo.transition_attempt(
                    attempt_id,
                    to_status="consistent",
                    reason="consistency_stub_no_findings",
                    transitioned_at=now,
                )
                repo.transition_attempt(
                    attempt_id,
                    to_status="accepted",
                    reason="slice_accepted",
                    transitioned_at=now,
                )
                accepted_ids.append(attempt_id)

            # Compute coverage records.
            for cov in compute_initial_coverage_for_slice(
                deal_slug=self._deal_slug,
                package=package,
                accepted_attempt_ids=accepted_ids,
                created_at_run_clock=now,
                atlas=atlas,
            ):
                repo.insert_coverage_check(cov)
            decision = can_publish_trusted(
                repo.list_coverage_checks(self._deal_slug)
            )

            # Emit exports.
            from ..exports.review import (
                export_claim_cards,
                export_human_decisions_template,
                export_provider_calls,
                export_review_queue,
                export_tool_calls,
            )

            artifacts: list[SliceArtifact] = [
                SliceArtifact(
                    name="claim_cards.csv",
                    path=export_claim_cards(repo, exports_dir, deal_slug=self._deal_slug),
                ),
                SliceArtifact(
                    name="review_queue.csv",
                    path=export_review_queue(repo, exports_dir, deal_slug=self._deal_slug),
                ),
                SliceArtifact(
                    name="human_decisions_template.csv",
                    path=export_human_decisions_template(repo, exports_dir, deal_slug=self._deal_slug),
                ),
                SliceArtifact(
                    name="provider_calls.jsonl",
                    path=export_provider_calls(
                        deal_dir,
                        self._provider_recorder.records if self._provider_recorder else [],
                    ),
                ),
                SliceArtifact(
                    name="tool_calls.jsonl",
                    path=export_tool_calls(
                        deal_dir,
                        self._tool_recorder.records if self._tool_recorder else [],
                    ),
                ),
            ]
        finally:
            connection.close()

        return SliceResult(
            run_id=str(run_id),
            deal_dir=deal_dir,
            db_path=db_path,
            artifacts=tuple(artifacts),
            accepted_attempt_ids=tuple(accepted_ids),
            rejected_attempt_ids=tuple(rejected_ids),
            superseded_attempt_ids=tuple(superseded_ids),
            correction_attempt_ids=tuple(correction_ids),
            can_publish_trusted=decision.can_publish_trusted,
        )

    # ------------------------------------------------------ helpers

    def _record_verdict(
        self,
        repo: DealRoomRepository,
        attempt_id: str,
        proposal: VerifierProposal,
        now: datetime,
    ) -> None:
        verdict = Verdict(
            verdict_id=_new_id("verdict"),
            attempt_id=attempt_id,
            verifier_agent_run_id=f"offline-verifier:{attempt_id}",
            model="offline-rule",
            prompt_hash="rule:verifier_v1",
            verdict=proposal.verdict,
            reasoning_summary=proposal.reasoning_summary,
            supporting_evidence_ids=proposal.supporting_evidence_paragraph_ids,
            proposed_correction_json=proposal.proposed_correction_json,
            confidence=proposal.confidence,
            created_at_run_clock=now,
        )
        repo.insert_verdict(verdict)

    def _apply_aggregate_to_lifecycle(
        self,
        repo: DealRoomRepository,
        *,
        attempt: ClaimAttempt,
        claim: ExtractedClaim,
        proposal: VerifierProposal,
        aggregated: AggregatedVerdict,
        now: datetime,
        confirmed_ids: list[str],
        rejected_ids: list[str],
        superseded_ids: list[str],
        correction_ids: list[str],
    ) -> None:
        if aggregated.outcome == "confirmed":
            repo.transition_attempt(
                attempt.attempt_id,
                to_status="verified_confirmed",
                reason=f"aggregate:{aggregated.outcome}",
                transitioned_at=now,
            )
            confirmed_ids.append(attempt.attempt_id)
            return

        if aggregated.outcome == "rejected":
            repo.transition_attempt(
                attempt.attempt_id,
                to_status="verified_rejected",
                reason=f"aggregate:{aggregated.outcome}",
                transitioned_at=now,
            )
            rejected_ids.append(attempt.attempt_id)
            return

        if aggregated.outcome == "correction_required":
            repo.transition_attempt(
                attempt.attempt_id,
                to_status="verified_partial",
                reason=f"aggregate:{aggregated.outcome}",
                transitioned_at=now,
            )
            correction_payload = (
                proposal.proposed_correction_json
                or json.dumps(
                    {"corrected": True, "from": attempt.attempt_id},
                    sort_keys=True,
                    separators=(",", ":"),
                )
            )
            new_id = repo.create_correction(
                original_attempt_id=attempt.attempt_id,
                corrected_payload_json=correction_payload,
                claim_fingerprint=f"{claim.claim_fingerprint}:c1",
                deal_slug=self._deal_slug,
                claim_type=claim.claim_type,
                origin_agent_role="orchestrator:correction",
                origin_agent_run_id=f"correction:{attempt.attempt_id}",
                model="offline-rule",
                prompt_hash="rule:correction_v1",
                created_sequence=attempt.created_sequence + 10_000,
                created_at_run_clock=now,
            )
            superseded_ids.append(attempt.attempt_id)
            correction_ids.append(new_id)
            return

        # escalated, no_verdicts, verifier_stage_failed → escalate.
        repo.transition_attempt(
            attempt.attempt_id,
            to_status="escalated",
            reason=f"aggregate:{aggregated.outcome}",
            transitioned_at=now,
        )
        rejected_ids.append(attempt.attempt_id)


def _new_id(prefix: str) -> str:
    return f"{prefix}:{secrets.token_hex(8)}"


def _evidence_id(
    *, filing_id: str, char_start: int, char_end: int, quote_text: str
) -> str:
    quote_hash = hashlib.sha256(quote_text.encode("utf-8")).hexdigest()
    payload = f"{filing_id}{char_start}{char_end}{quote_hash}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
