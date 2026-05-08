"""Phase 11 (US-012) — verifier calibration seed."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from sec_review_compiler.filing.examples import SYNTHETIC_FILING_PATH
from sec_review_compiler.orchestration import (
    CalibrationLoadError,
    OfflineFakeVerifier,
    load_calibration_cards,
    run_calibration,
)
from sec_review_compiler.orchestration.calibration import (
    EXPECTED_CATEGORIES,
    planted_error_categories,
)
from sec_review_compiler.orchestration.verifier import VerifierProposal


SEED_PATH = Path(__file__).resolve().parent.parent / "calibration" / "verifier_seed.jsonl"


# ---------------------------------------------------------------- shape

class TestSeedShape:
    def test_seed_file_exists_and_loads(self) -> None:
        cards = load_calibration_cards(SEED_PATH)
        assert len(cards) >= 12

    def test_seed_includes_each_required_category_at_least_once(self) -> None:
        cards = load_calibration_cards(SEED_PATH)
        present = {c.category for c in cards}
        missing = set(EXPECTED_CATEGORIES) - present
        assert not missing, f"missing categories in seed: {sorted(missing)}"

    def test_breakdown_matches_phase_11_quotas(self) -> None:
        # 3 confirmed_correct, 3 single-field errors, 2 multi-field errors,
        # 2 plausible hallucinations, 1 ambiguous, 1 coverage gap.
        cards = load_calibration_cards(SEED_PATH)
        from collections import Counter

        per_cat = Counter(c.category for c in cards)
        assert per_cat["confirmed_correct"] >= 3
        single_field = (
            per_cat["single_field_error_date"]
            + per_cat["single_field_error_actor"]
            + per_cat["single_field_error_amount"]
        )
        assert single_field >= 3
        assert per_cat["multi_field_error"] >= 2
        assert per_cat["plausible_hallucination"] >= 2
        assert per_cat["genuinely_ambiguous"] >= 1
        assert per_cat["coverage_gap"] >= 1

    def test_invalid_seed_rejected(self, tmp_path: Path) -> None:
        bad = tmp_path / "bad.jsonl"
        bad.write_text(
            json.dumps({"card_id": "x"}) + "\n",
            encoding="utf-8",
        )
        with pytest.raises(CalibrationLoadError):
            load_calibration_cards(bad)


# ---------------------------------------------------------------- planted errors

class TestPlantedErrors:
    @pytest.fixture()
    def report(self):
        cards = load_calibration_cards(SEED_PATH)
        raw_text = SYNTHETIC_FILING_PATH.read_text(encoding="utf-8")
        return run_calibration(cards, verifier=OfflineFakeVerifier(), raw_text=raw_text)

    def test_wrong_dates_and_actors_not_confirmed(self, report) -> None:
        # OfflineFakeVerifier rejects altered quotes (they are no longer
        # verbatim), so single-field date/actor errors must NOT receive
        # verdict=confirm.
        for r in report.card_results:
            if r.category in {
                "single_field_error_date",
                "single_field_error_actor",
                "single_field_error_amount",
                "multi_field_error",
                "plausible_hallucination",
            }:
                assert r.actual_verdict != "confirm", (
                    f"{r.card_id} ({r.category}) was rubber-stamped: {r.actual_verdict!r}"
                )

    def test_per_category_counts_present(self, report) -> None:
        for category in planted_error_categories():
            assert category in report.per_category_counts
            counts = report.per_category_counts[category]
            assert sum(counts.values()) >= 1

    def test_match_rate_below_one_for_offline_verifier(self, report) -> None:
        # The offline verifier cannot diagnose ambiguous duplicates or
        # coverage gaps, so match_rate is necessarily < 1.
        assert 0.0 < report.match_rate < 1.0


# ---------------------------------------------------------------- fail-closed

class _AlwaysConfirmVerifier:
    def verify(self, **kwargs):
        return VerifierProposal(
            verdict="confirm",
            reasoning_summary="rubber stamp",
            supporting_evidence_paragraph_ids=(),
            proposed_correction_json=None,
            confidence=1.0,
        )


class TestFailClosed:
    def test_all_confirm_triggers_fail_closed(self) -> None:
        cards = load_calibration_cards(SEED_PATH)
        raw_text = SYNTHETIC_FILING_PATH.read_text(encoding="utf-8")
        report = run_calibration(
            cards, verifier=_AlwaysConfirmVerifier(), raw_text=raw_text
        )
        assert report.fail_closed is True
        assert report.fail_reason is not None

    def test_offline_verifier_does_not_fail_closed(self) -> None:
        cards = load_calibration_cards(SEED_PATH)
        raw_text = SYNTHETIC_FILING_PATH.read_text(encoding="utf-8")
        report = run_calibration(cards, verifier=OfflineFakeVerifier(), raw_text=raw_text)
        # Offline verifier rejects altered-quote cards, so it does not look
        # like a rubber stamp.
        assert report.fail_closed is False
