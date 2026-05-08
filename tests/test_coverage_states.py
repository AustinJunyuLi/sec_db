"""Phase 8 (US-009) — full coverage state ledger and review visibility."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import duckdb
import pytest

from sec_review_compiler.canonical import CanonicalCompiler
from sec_review_compiler.filing.atlas import build_atlas
from sec_review_compiler.filing.examples import load_synthetic_filing
from sec_review_compiler.filing.package import build_filing_package
from sec_review_compiler.orchestration.coverage import (
    compute_initial_coverage_for_slice,
)
from sec_review_compiler.store.lifecycle import can_publish_trusted
from sec_review_compiler.store.repository import CoverageCheck, DealRoomRepository
from sec_review_compiler.store.migrations import apply_schema


def _ts() -> datetime:
    return datetime(2026, 5, 8, 14, 0, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------- state shape

class TestCoverageStateShape:
    def test_synthetic_8k_produces_expected_categories(self) -> None:
        package = load_synthetic_filing()
        atlas = build_atlas(package)
        checks = compute_initial_coverage_for_slice(
            deal_slug="synthetic-demo",
            package=package,
            accepted_attempt_ids=("attempt:demo",),
            created_at_run_clock=_ts(),
            atlas=atlas,
        )
        categories = {c.category for c in checks}
        assert categories == {
            "timeline_events",
            "exhibit_substantive_offer",
            "section_label_resolution",
        }

    def test_non_tender_offer_marks_substantive_exhibit_not_applicable(self) -> None:
        package = load_synthetic_filing()  # 8-K
        atlas = build_atlas(package)
        checks = compute_initial_coverage_for_slice(
            deal_slug="synthetic-demo",
            package=package,
            accepted_attempt_ids=(),
            created_at_run_clock=_ts(),
            atlas=atlas,
        )
        exhibit = next(c for c in checks if c.category == "exhibit_substantive_offer")
        assert exhibit.check_state == "not_applicable"
        assert exhibit.required is False

    def test_ambiguous_section_label_emits_ambiguous_state(self) -> None:
        package = load_synthetic_filing()  # has duplicate "Background of the Merger"
        atlas = build_atlas(package)
        checks = compute_initial_coverage_for_slice(
            deal_slug="synthetic-demo",
            package=package,
            accepted_attempt_ids=("a:1",),
            created_at_run_clock=_ts(),
            atlas=atlas,
        )
        section_check = next(c for c in checks if c.category == "section_label_resolution")
        assert section_check.check_state == "ambiguous"

    def test_tender_offer_with_substantive_exhibit_required(self) -> None:
        # Build a tender-offer package whose exhibit IS substantive.
        text = (
            "SC TO-T cover.\n\n"
            "Exhibit (a)(1)(A)\n"
            "Offer to Purchase dated April 1, 2026.\n\n"
            "All shares of Target Co. ...\n"
        )
        package = build_filing_package(
            filing_id="t:1", filing_type="SC TO-T", raw_text=text,
        )
        checks = compute_initial_coverage_for_slice(
            deal_slug="t1",
            package=package,
            accepted_attempt_ids=("a:1",),
            created_at_run_clock=_ts(),
        )
        exhibit = next(c for c in checks if c.category == "exhibit_substantive_offer")
        assert exhibit.check_state == "checked_found"
        assert exhibit.required is True


# ---------------------------------------------------------------- gate behavior

class TestPublicationGate:
    def test_failed_to_check_required_blocks(self) -> None:
        decision = can_publish_trusted([
            CoverageCheck(
                coverage_id="c:1", deal_slug="d", category="bids", subcategory=None,
                check_state="failed_to_check", evidence_id=None, attempt_id=None,
                required=True, notes=None, created_at_run_clock=_ts(),
            ),
        ])
        assert decision.can_publish_trusted is False

    def test_checked_absent_does_not_block(self) -> None:
        decision = can_publish_trusted([
            CoverageCheck(
                coverage_id="c:1", deal_slug="d", category="bids", subcategory=None,
                check_state="checked_absent", evidence_id=None, attempt_id=None,
                required=True, notes=None, created_at_run_clock=_ts(),
            ),
        ])
        assert decision.can_publish_trusted is True

    def test_ambiguous_does_not_block(self) -> None:
        decision = can_publish_trusted([
            CoverageCheck(
                coverage_id="c:1", deal_slug="d", category="section_label_resolution",
                subcategory=None, check_state="ambiguous",
                evidence_id=None, attempt_id=None, required=True,
                notes=None, created_at_run_clock=_ts(),
            ),
        ])
        assert decision.can_publish_trusted is True

    def test_not_applicable_does_not_block(self) -> None:
        decision = can_publish_trusted([
            CoverageCheck(
                coverage_id="c:1", deal_slug="d", category="exhibit_substantive_offer",
                subcategory=None, check_state="not_applicable",
                evidence_id=None, attempt_id=None, required=False,
                notes=None, created_at_run_clock=_ts(),
            ),
        ])
        assert decision.can_publish_trusted is True


# ---------------------------------------------------------------- compile + checked_absent

class TestCompileWithCheckedAbsent:
    def test_checked_absent_does_not_invent_a_fact(self, tmp_path: Path) -> None:
        # Build a tiny deal-room with one accepted attempt, then add a
        # checked_absent coverage row. The compile should still publish
        # but no canonical row is invented for the absent category.
        from sec_review_compiler.orchestration import (
            OfflineConfidentialityExtractor,
            OfflineFakeVerifier,
            Orchestrator,
        )
        from sec_review_compiler.filing.examples import SYNTHETIC_FILING_PATH

        run_dir = tmp_path / "20260508T140000Z_synthetic-demo_deadbeef"
        run_dir.mkdir(parents=True, exist_ok=True)
        orch = Orchestrator(
            deal_slug="synthetic-demo",
            extractor=OfflineConfidentialityExtractor(),
            verifier=OfflineFakeVerifier(),
        )
        slice_result = orch.run_synthetic_vertical_slice(
            run_dir=run_dir, filing_path=SYNTHETIC_FILING_PATH,
        )
        conn = duckdb.connect(str(slice_result.db_path))
        repo = DealRoomRepository(conn)
        repo.insert_coverage_check(
            CoverageCheck(
                coverage_id="cov:bids:absent",
                deal_slug="synthetic-demo",
                category="bids",
                subcategory=None,
                check_state="checked_absent",
                evidence_id=None,
                attempt_id=None,
                required=True,
                notes="no bid claims found",
                created_at_run_clock=_ts(),
            )
        )
        compiler = CanonicalCompiler(
            repo,
            run_id=slice_result.run_id,
            deal_slug="synthetic-demo",
            compiled_at_run_clock=_ts(),
        )
        # Wipe prior canonical rows so the test isolates the rerun.
        conn.execute("DELETE FROM canonical_row_evidence")
        conn.execute("DELETE FROM canonical_rows")
        result = compiler.compile()
        assert result.published is True
        # No bid-canonical-rows: checked_absent is review-visible, not
        # an invented fact.
        bid_rows = conn.execute(
            "SELECT COUNT(*) FROM canonical_rows WHERE canonical_table='bid'"
        ).fetchone()[0]
        conn.close()
        assert bid_rows == 0
