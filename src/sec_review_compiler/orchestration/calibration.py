"""Verifier calibration runner.

Sends each seed card through a Verifier and computes per-category
metrics. Designed to fail-closed: if every card receives `confirm`, the
report flags rubber-stamp behaviour so the operator does not trust
verifier output downstream.
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

from ..errors import CompilerError
from .verifier import Verifier, VerifierProposal


REQUIRED_CARD_KEYS = {
    "card_id",
    "category",
    "filing_id",
    "cited_quotes",
    "cited_paragraph_ids",
    "payload_json",
    "expected_verdict",
}

# Categories we expect at least once in a usable seed set.
EXPECTED_CATEGORIES: tuple[str, ...] = (
    "confirmed_correct",
    "single_field_error_date",
    "single_field_error_actor",
    "single_field_error_amount",
    "multi_field_error",
    "plausible_hallucination",
    "genuinely_ambiguous",
    "coverage_gap",
)


# ---------------------------------------------------------------- types

class CalibrationLoadError(CompilerError):
    """Raised when the seed JSONL fails schema validation."""


@dataclass(frozen=True, slots=True)
class CalibrationCard:
    card_id: str
    category: str
    filing_id: str
    cited_quotes: tuple[str, ...]
    cited_paragraph_ids: tuple[str, ...]
    payload_json: str
    expected_verdict: str
    notes: str = ""


@dataclass(frozen=True, slots=True)
class CardResult:
    card_id: str
    category: str
    expected_verdict: str
    actual_verdict: str
    match: bool


@dataclass(frozen=True, slots=True)
class CalibrationReport:
    card_results: tuple[CardResult, ...]
    per_category_counts: dict[str, dict[str, int]]
    match_rate: float
    fail_closed: bool
    fail_reason: str | None


# ---------------------------------------------------------------- loader

def load_calibration_cards(path: Path) -> list[CalibrationCard]:
    cards: list[CalibrationCard] = []
    seen_ids: set[str] = set()
    text = Path(path).read_text(encoding="utf-8")
    for line_no, line in enumerate(text.splitlines(), start=1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            data = json.loads(line)
        except json.JSONDecodeError as exc:
            raise CalibrationLoadError(
                f"line {line_no}: invalid JSON ({exc})"
            ) from exc
        missing = REQUIRED_CARD_KEYS - data.keys()
        if missing:
            raise CalibrationLoadError(
                f"line {line_no}: missing keys {sorted(missing)}"
            )
        if data["card_id"] in seen_ids:
            raise CalibrationLoadError(
                f"line {line_no}: duplicate card_id {data['card_id']!r}"
            )
        seen_ids.add(data["card_id"])
        cards.append(
            CalibrationCard(
                card_id=str(data["card_id"]),
                category=str(data["category"]),
                filing_id=str(data["filing_id"]),
                cited_quotes=tuple(str(q) for q in data["cited_quotes"]),
                cited_paragraph_ids=tuple(str(p) for p in data["cited_paragraph_ids"]),
                payload_json=str(data["payload_json"]),
                expected_verdict=str(data["expected_verdict"]),
                notes=str(data.get("notes", "")),
            )
        )
    if len(cards) < 12:
        raise CalibrationLoadError(
            f"seed file at {path} has only {len(cards)} cards; require >= 12"
        )
    return cards


# ---------------------------------------------------------------- runner

def run_calibration(
    cards: Sequence[CalibrationCard],
    *,
    verifier: Verifier,
    raw_text: str,
) -> CalibrationReport:
    if not cards:
        raise ValueError("cards must be non-empty")

    results: list[CardResult] = []
    for card in cards:
        proposal: VerifierProposal = verifier.verify(
            attempt_id=card.card_id,
            cited_quotes=list(card.cited_quotes),
            cited_paragraph_ids=list(card.cited_paragraph_ids),
            raw_text=raw_text,
        )
        results.append(
            CardResult(
                card_id=card.card_id,
                category=card.category,
                expected_verdict=card.expected_verdict,
                actual_verdict=proposal.verdict,
                match=proposal.verdict == card.expected_verdict,
            )
        )

    per_category: dict[str, dict[str, int]] = {}
    for r in results:
        bucket = per_category.setdefault(r.category, {})
        bucket[r.actual_verdict] = bucket.get(r.actual_verdict, 0) + 1

    matches = sum(1 for r in results if r.match)
    match_rate = matches / len(results)

    all_confirm = all(r.actual_verdict == "confirm" for r in results)
    if all_confirm:
        fail_closed = True
        fail_reason = (
            "every card received verdict=confirm — verifier appears to be "
            "rubber-stamping; refuse to trust downstream output"
        )
    else:
        # Additional fail-closed: confirmed-correct cards must dominate
        # confirms — if we see confirm verdicts on rejection-class
        # categories without any rejection elsewhere, that's also a
        # rubber-stamp tell.
        rejection_classes = {
            "single_field_error_date",
            "single_field_error_actor",
            "single_field_error_amount",
            "multi_field_error",
            "plausible_hallucination",
        }
        rejection_results = [r for r in results if r.category in rejection_classes]
        if rejection_results and all(r.actual_verdict == "confirm" for r in rejection_results):
            fail_closed = True
            fail_reason = (
                "every rejection-class card was confirmed by the verifier — "
                "rubber-stamping suspected"
            )
        else:
            fail_closed = False
            fail_reason = None

    return CalibrationReport(
        card_results=tuple(results),
        per_category_counts={k: dict(v) for k, v in per_category.items()},
        match_rate=match_rate,
        fail_closed=fail_closed,
        fail_reason=fail_reason,
    )


# ---------------------------------------------------------------- helpers

def planted_error_categories() -> tuple[str, ...]:
    return (
        "single_field_error_date",
        "single_field_error_actor",
        "single_field_error_amount",
        "multi_field_error",
        "plausible_hallucination",
    )
