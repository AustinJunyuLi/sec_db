"""Helpers to load synthetic filing fixtures shipped with the test suite."""

from __future__ import annotations

from pathlib import Path

from .package import FilingPackage, build_filing_package

FIXTURES_DIR = Path(__file__).resolve().parents[3] / "tests" / "fixtures"
SYNTHETIC_FILING_PATH = FIXTURES_DIR / "synthetic_filing.txt"


def load_synthetic_filing(
    filing_id: str = "synthetic-demo:0001",
    filing_type: str = "8-K",
) -> FilingPackage:
    """Build a `FilingPackage` from the canonical synthetic fixture."""
    raw_text = SYNTHETIC_FILING_PATH.read_text(encoding="utf-8")
    return build_filing_package(
        filing_id=filing_id,
        filing_type=filing_type,
        raw_text=raw_text,
    )
