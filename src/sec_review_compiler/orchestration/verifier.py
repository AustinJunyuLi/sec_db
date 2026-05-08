"""Verifier interfaces and the offline deterministic verifier.

The Verifier sees one bound claim attempt and its cited evidence, plus
the filing text. It does not see extractor reasoning. The offline
verifier confirms iff every cited quote is verbatim-present in the
filing text; otherwise it rejects. Test code can inject ad-hoc verifier
callables for partial / reject paths.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, Sequence


@dataclass(frozen=True, slots=True)
class VerifierProposal:
    verdict: str  # confirm | partial | reject | ambiguous
    reasoning_summary: str
    supporting_evidence_paragraph_ids: tuple[str, ...]
    proposed_correction_json: str | None
    confidence: float


class Verifier(Protocol):
    def verify(
        self,
        *,
        attempt_id: str,
        cited_quotes: Sequence[str],
        cited_paragraph_ids: Sequence[str],
        raw_text: str,
    ) -> VerifierProposal: ...  # pragma: no cover — protocol


class OfflineFakeVerifier:
    """Deterministic offline verifier — no network calls.

    The verdict is `confirm` iff every cited quote is verbatim in
    `raw_text`; otherwise `reject`. The verifier does not see the
    extractor's reasoning; it only sees the bound evidence. This
    matches the design's verifier-isolation contract.
    """

    def verify(
        self,
        *,
        attempt_id: str,
        cited_quotes: Sequence[str],
        cited_paragraph_ids: Sequence[str],
        raw_text: str,
    ) -> VerifierProposal:
        missing = [q for q in cited_quotes if q not in raw_text]
        if missing:
            return VerifierProposal(
                verdict="reject",
                reasoning_summary=(
                    f"{len(missing)} cited quote(s) not verbatim in filing text"
                ),
                supporting_evidence_paragraph_ids=(),
                proposed_correction_json=None,
                confidence=0.95,
            )
        return VerifierProposal(
            verdict="confirm",
            reasoning_summary="all cited quotes are verbatim in the filing text",
            supporting_evidence_paragraph_ids=tuple(cited_paragraph_ids),
            proposed_correction_json=None,
            confidence=0.95,
        )
