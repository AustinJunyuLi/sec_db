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

from ..filing.atlas import Atlas
from ..filing.package import FilingPackage, TENDER_OFFER_FILING_TYPES
from ..store.repository import CoverageCheck


def _coverage_id(prefix: str) -> str:
    return f"coverage:{prefix}:{secrets.token_hex(4)}"


def compute_initial_coverage_for_slice(
    *,
    deal_slug: str,
    package: FilingPackage,
    accepted_attempt_ids: Sequence[str],
    created_at_run_clock: datetime,
    atlas: Atlas | None = None,
) -> list[CoverageCheck]:
    """Build the per-deal coverage ledger for the vertical slice.

    Produces records using the full coverage vocabulary (`checked_found`,
    `checked_absent`, `ambiguous`, `not_applicable`, `failed_to_check`).
    Required checks gate trusted publication; optional checks are
    review-visible only.
    """
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

    is_tender_offer = package.filing_type in TENDER_OFFER_FILING_TYPES
    has_substantive_exhibit = any(ex.substantive_offer for ex in package.exhibits)
    if not is_tender_offer:
        exhibit_state = "not_applicable"
        exhibit_notes = (
            f"filing_type={package.filing_type!r} is not a tender offer"
        )
    elif has_substantive_exhibit:
        exhibit_state = "checked_found"
        exhibit_notes = "substantive Offer to Purchase exhibit present"
    else:
        # Tender offer without a substantive offer should already have
        # been blocked by the package builder (US-003); if it slipped
        # through, surface it as a coverage failure rather than absence.
        exhibit_state = "failed_to_check"
        exhibit_notes = (
            "tender-offer filing reached coverage stage without a "
            "substantive Offer to Purchase exhibit — investigate"
        )
    exhibit_check = CoverageCheck(
        coverage_id=_coverage_id("exhibit_substantive_offer"),
        deal_slug=deal_slug,
        category="exhibit_substantive_offer",
        subcategory=None,
        check_state=exhibit_state,
        evidence_id=None,
        attempt_id=None,
        required=is_tender_offer,
        notes=exhibit_notes,
        created_at_run_clock=created_at_run_clock,
    )

    checks: list[CoverageCheck] = [timeline_check, exhibit_check]

    # Atlas-derived ambiguity check.
    if atlas is not None:
        ambiguous_warnings = [
            w for w in atlas.atlas_warnings if w.code == "ambiguous_section_label"
        ]
        if ambiguous_warnings:
            sections_state = "ambiguous"
            section_notes = (
                f"{len(ambiguous_warnings)} ambiguous section label(s) recorded"
            )
        else:
            sections_state = "checked_found"
            section_notes = "all section labels resolved confidently"
        checks.append(
            CoverageCheck(
                coverage_id=_coverage_id("section_label_resolution"),
                deal_slug=deal_slug,
                category="section_label_resolution",
                subcategory=None,
                check_state=sections_state,
                evidence_id=None,
                attempt_id=None,
                required=False,
                notes=section_notes,
                created_at_run_clock=created_at_run_clock,
            )
        )

    return checks
