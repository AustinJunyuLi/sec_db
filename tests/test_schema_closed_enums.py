import pytest
from pydantic import ValidationError

from sec_graph.schema import CleanFiling


def test_clean_filing_has_process_scope() -> None:
    filing = CleanFiling(
        filing_id="medivation_filing_1",
        deal_slug="medivation",
        source_path="data/filings/medivation/raw.md",
        raw_sha256="a" * 64,
        parser_version=1,
        page_count=10,
        section_count=3,
        process_scope="bidder_partial_schedule_to",
    )

    assert filing.process_scope == "bidder_partial_schedule_to"


def test_clean_filing_rejects_unknown_scope() -> None:
    with pytest.raises(ValidationError):
        CleanFiling(
            filing_id="bad_filing_1",
            deal_slug="bad",
            source_path=None,
            raw_sha256="a" * 64,
            parser_version=1,
            page_count=None,
            section_count=None,
            process_scope="un" + "known",
        )
