"""Offline gate: every Reference-9 local filing produces validated regions.

This test exercises the full ingest -> evidence-map path against the local
``data/filings`` artifacts without any Linkflow credentials. It is the offline
proof that region selection works on real deal text before we authorize live
spend.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from sec_graph.extract.evidence_map import build_evidence_map
from sec_graph.extract.llm.requests import build_llm_windows
from sec_graph.ingest.pipeline import filing_sources, ingest_source
from sec_graph.ingest.section_vocabulary import SALE_PROCESS_SECTIONS
from sec_graph.schema import connect, init_schema

REPO_ROOT = Path(__file__).resolve().parents[1]
FILINGS_DIR = REPO_ROOT / "data" / "filings"
EXPECTATIONS_PATH = (
    REPO_ROOT / "tests" / "fixtures" / "reference9_region_expectations.json"
)
RUN_ID = "2026-05-04T000000Z_reference9-offline_offline0"

REFERENCE9_SLUGS = (
    "providence-worcester",
    "medivation",
    "imprivata",
    "zep",
    "petsmart-inc",
    "penford",
    "mac-gray",
    "saks",
    "stec",
)


def _load_expectations() -> dict[str, dict]:
    return json.loads(EXPECTATIONS_PATH.read_text(encoding="utf-8"))["deals"]


@pytest.fixture(scope="module")
def expectations() -> dict[str, dict]:
    return _load_expectations()


def _missing_filings() -> list[str]:
    return [slug for slug in REFERENCE9_SLUGS if not (FILINGS_DIR / slug / "raw.md").exists()]


def test_reference9_filings_are_present_locally() -> None:
    missing = _missing_filings()
    assert not missing, (
        "Reference-9 offline gate requires local filings under data/filings/. "
        "Missing slugs: "
        f"{missing}. Re-run the EDGAR fetcher for these slugs (see scripts/fetch_filings.py)."
    )


@pytest.mark.parametrize("slug", REFERENCE9_SLUGS)
def test_reference9_slug_builds_validated_sale_process_regions(
    slug: str, expectations: dict[str, dict]
) -> None:
    if slug in _missing_filings():
        pytest.fail(
            f"Reference-9 slug {slug!r} has no data/filings/{slug}/raw.md; "
            "fetch the filing before running the offline gate."
        )

    deal_expectation = expectations[slug]
    expected_regions = deal_expectation["regions"]
    expected_sections = [region["section"] for region in expected_regions]

    conn = connect(":memory:")
    init_schema(conn)
    [source] = filing_sources([slug], filings_dir=FILINGS_DIR)
    filing = ingest_source(conn, source)
    assert filing.process_scope == deal_expectation["process_scope"], (
        f"{slug}: expected process_scope={deal_expectation['process_scope']!r} "
        f"but ingest produced {filing.process_scope!r}"
    )

    region_ids = build_evidence_map(conn, filing_id=filing.filing_id, run_id=RUN_ID)
    assert region_ids, f"{slug}: build_evidence_map returned no regions"

    rows = conn.execute(
        """
        SELECT region_kind, priority, paragraph_ids_json, trigger_phrases_json,
               expected_claim_types_json, start_paragraph_id, end_paragraph_id
        FROM evidence_regions
        WHERE filing_id = ?
        ORDER BY priority
        """,
        [filing.filing_id],
    ).fetchall()

    assert len(rows) == len(expected_regions), (
        f"{slug}: expected {len(expected_regions)} sale-process region(s) but "
        f"got {len(rows)} (sections={[json.loads(r[3])[0] for r in rows]})"
    )

    actual_sections: list[str] = []
    for index, row in enumerate(rows):
        region_kind, priority, paragraph_ids_json, trigger_json, claim_types_json, _start, _end = row
        assert region_kind == "sale_process_narrative", (
            f"{slug}[{index}]: expected sale_process_narrative kind, got {region_kind!r}"
        )
        assert priority == index + 1, f"{slug}[{index}]: priority {priority} != {index + 1}"

        trigger_phrases = json.loads(trigger_json)
        assert len(trigger_phrases) == 1, (
            f"{slug}[{index}]: expected one trigger phrase per region, got {trigger_phrases}"
        )
        trigger = trigger_phrases[0]
        assert trigger in SALE_PROCESS_SECTIONS, (
            f"{slug}[{index}]: trigger phrase {trigger!r} is not a recognized "
            "sale-process section heading"
        )
        actual_sections.append(trigger)

        paragraph_ids = json.loads(paragraph_ids_json)
        expected_min = expected_regions[index]["min_paragraphs"]
        expected_max = expected_regions[index]["max_paragraphs"]
        assert expected_min <= len(paragraph_ids) <= expected_max, (
            f"{slug}[{index}] section={trigger!r}: paragraph count "
            f"{len(paragraph_ids)} outside expected band [{expected_min}, "
            f"{expected_max}] -- region selection may have broken (heading "
            "spilled over or under-selected)."
        )

        # Each paragraph in the region must actually be tagged with this section.
        placeholders = ", ".join("?" for _ in paragraph_ids)
        section_set = {
            row_section
            for (row_section,) in conn.execute(
                f"SELECT DISTINCT section FROM paragraphs WHERE paragraph_id IN ({placeholders})",
                paragraph_ids,
            ).fetchall()
        }
        assert section_set == {trigger}, (
            f"{slug}[{index}] section={trigger!r}: paragraphs in region carry "
            f"unexpected section labels {section_set - {trigger}}"
        )

        valid_claim_types = {
            "event",
            "participation_count",
            "actor",
            "bid",
            "actor_relation",
        }
        actual_claim_types = json.loads(claim_types_json)
        assert actual_claim_types, f"{slug}[{index}]: expected_claim_types_json is empty"
        assert set(actual_claim_types) <= valid_claim_types, (
            f"{slug}[{index}]: expected_claim_types_json {actual_claim_types} "
            "contains unknown claim types"
        )
        # Universal obligations cover event/actor/bid in every region.
        assert {"event", "actor", "bid"} <= set(actual_claim_types), (
            f"{slug}[{index}]: expected_claim_types_json {actual_claim_types} "
            "is missing universal sale-process claim types"
        )

    assert actual_sections == expected_sections, (
        f"{slug}: expected sections {expected_sections} in order but got "
        f"{actual_sections}"
    )

    # Each region must produce exactly one Linkflow window with current
    # obligations -- the production request mode reads from these tables.
    windows = build_llm_windows(conn, filing_id=filing.filing_id)
    assert len(windows) == len(rows), (
        f"{slug}: expected {len(rows)} LLM window(s) but got {len(windows)}"
    )
    for window in windows:
        assert window.coverage_obligations, (
            f"{slug}: window {window.window_id} has no current obligations"
        )
        allowed = set(window.allowed_claim_types)
        assert allowed <= valid_claim_types, (
            f"{slug}: window {window.window_id} allows unknown claim types "
            f"{allowed - valid_claim_types}"
        )
        assert {"event", "actor", "bid"} <= allowed, (
            f"{slug}: window {window.window_id} is missing universal claim types"
        )


def test_reference9_filing_without_sale_process_section_fails_loudly(tmp_path: Path) -> None:
    """An ingested filing with no sale-process paragraphs must fail loudly."""
    from sec_graph.ingest.pipeline import IngestSource, ingest_source

    raw = "Some Other Section\n\nThe board considered options.\n"
    source_path = tmp_path / "no-sale" / "raw.md"
    manifest_path = tmp_path / "no-sale" / "manifest.json"
    source_path.parent.mkdir(parents=True)
    source_path.write_text(raw, encoding="utf-8")
    manifest_path.write_text(
        json.dumps({"source": {"form_type": "DEFM14A"}}),
        encoding="utf-8",
    )

    conn = connect(":memory:")
    init_schema(conn)
    source = IngestSource(slug="no-sale", source_path=source_path, manifest_path=manifest_path)
    filing = ingest_source(conn, source)

    with pytest.raises(ValueError) as excinfo:
        build_evidence_map(conn, filing_id=filing.filing_id, run_id=RUN_ID)
    assert "sale-process" in str(excinfo.value)
