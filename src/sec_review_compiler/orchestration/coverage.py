"""Coverage record generation for the orchestrator.

For the vertical slice the coverage ledger is intentionally minimal:
one required check (`timeline_events`) backed by the extractor's output
and one optional check (`exhibit_substantive_offer`) that records
whether the filing has a substantive offer-to-purchase exhibit. Real
coverage rules are added in Phase 8 (US-009).
"""

from __future__ import annotations

import secrets
from datetime import datetime
from typing import Sequence

from ..filing.package import FilingPackage
from ..store.repository import CoverageCheck


def _coverage_id(prefix: str) -> str:
    return f"coverage:{prefix}:{secrets.token_hex(4)}"


def compute_initial_coverage_for_slice(
    *,
    deal_slug: str,
    package: FilingPackage,
    accepted_attempt_ids: Sequence[str],
    created_at_run_clock: datetime,
) -> list[CoverageCheck]:
    timeline_state = (
        "checked_found" if accepted_attempt_ids else "checked_absent"
    )
    timeline_check = CoverageCheck(
        coverage_id=_coverage_id("timeline_events"),
        deal_slug=deal_slug,
        category="timeline_events",
        subcategory=None,
        check_state=timeline_state,
        evidence_id=None,
        attempt_id=accepted_attempt_ids[0] if accepted_attempt_ids else None,
        required=True,
        notes=(
            f"{len(accepted_attempt_ids)} accepted attempt(s) for the slice"
        ),
        created_at_run_clock=created_at_run_clock,
    )

    has_substantive_exhibit = any(
        ex.substantive_offer for ex in package.exhibits
    )
    exhibit_state = "checked_found" if has_substantive_exhibit else "checked_absent"
    exhibit_check = CoverageCheck(
        coverage_id=_coverage_id("exhibit_substantive_offer"),
        deal_slug=deal_slug,
        category="exhibit_substantive_offer",
        subcategory=None,
        check_state=exhibit_state,
        evidence_id=None,
        attempt_id=None,
        required=False,
        notes=None,
        created_at_run_clock=created_at_run_clock,
    )
    return [timeline_check, exhibit_check]
