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
APPLICABILITY_EXPECTATIONS_PATH = (
    REPO_ROOT / "tests" / "fixtures" / "reference9_applicability_expectations.json"
)
FACT_LEDGER_PATH = REPO_ROOT / "tests" / "fixtures" / "reference9_fact_ledger.json"
RUN_ID = "2026-05-04T000000Z_reference9-offline_offline0"
FETCH_COMMAND = "UV_CACHE_DIR=/private/tmp/uv-cache PYTHONDONTWRITEBYTECODE=1 uv run python scripts/fetch_filings.py --slug {slug}"

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


def _load_applicability_expectations() -> dict[str, dict]:
    return json.loads(APPLICABILITY_EXPECTATIONS_PATH.read_text(encoding="utf-8"))[
        "deals"
    ]


def _load_fact_ledger() -> dict[str, dict]:
    return json.loads(FACT_LEDGER_PATH.read_text(encoding="utf-8"))["deals"]


@pytest.fixture(scope="module")
def expectations() -> dict[str, dict]:
    return _load_expectations()


@pytest.fixture(scope="module")
def applicability_expectations() -> dict[str, dict]:
    return _load_applicability_expectations()


@pytest.fixture(scope="module")
def fact_ledger() -> dict[str, dict]:
    return _load_fact_ledger()


def _missing_filings() -> list[str]:
    return [slug for slug in REFERENCE9_SLUGS if not (FILINGS_DIR / slug / "raw.md").exists()]


def test_reference9_filings_are_present_locally() -> None:
    missing = _missing_filings()
    commands = [FETCH_COMMAND.format(slug=slug) for slug in missing]
    assert not missing, (
        "Reference-9 offline gate requires local filings under data/filings/. "
        "Missing slugs: "
        f"{missing}. Fetch commands: {commands}"
    )


@pytest.mark.parametrize("slug", REFERENCE9_SLUGS)
def test_reference9_slug_builds_validated_sale_process_regions(
    slug: str, expectations: dict[str, dict], applicability_expectations: dict[str, dict]
) -> None:
    if slug in _missing_filings():
        pytest.fail(
            f"Reference-9 slug {slug!r} has no data/filings/{slug}/raw.md; "
            f"fetch it with: {FETCH_COMMAND.format(slug=slug)}"
        )

    deal_expectation = expectations[slug]
    applicability_expectation = applicability_expectations[slug]
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
    assert filing.process_scope == applicability_expectation["process_scope"], (
        f"{slug}: applicability fixture expected "
        f"process_scope={applicability_expectation['process_scope']!r} "
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
        expected_region = expected_regions[index]
        expected_applicability = applicability_expectation["regions"][index]
        assert region_kind == expected_region["region_kind"], (
            f"{slug}[{index}]: expected {expected_region['region_kind']!r} kind, got {region_kind!r}"
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
        assert trigger == expected_applicability["section"], (
            f"{slug}[{index}]: applicability fixture section "
            f"{expected_applicability['section']!r} does not match selected "
            f"section {trigger!r}"
        )

        paragraph_ids = json.loads(paragraph_ids_json)
        expected_min = expected_region["min_paragraphs"]
        expected_max = expected_region["max_paragraphs"]
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
        actual_applicability = _applicability_summary(conn, index=index)
        assert actual_applicability == {
            "applicable_count": expected_applicability["applicable_count"],
            "applicable_kinds": expected_applicability["applicable_kinds"],
            "claim_types": expected_applicability["claim_types"],
            "important_or_required_kinds": expected_applicability[
                "important_or_required_kinds"
            ],
            "reason_codes": expected_applicability["reason_codes"],
            "trigger_basis": expected_applicability["trigger_basis"],
        }, f"{slug}[{index}]: applicability summary drifted"

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


def test_medivation_reference9_uses_offer_to_purchase_exhibit() -> None:
    manifest_path = FILINGS_DIR / "medivation" / "manifest.json"
    if not manifest_path.exists():
        pytest.fail(
            "Reference-9 slug 'medivation' has no data/filings/medivation/manifest.json; "
            f"fetch it with: {FETCH_COMMAND.format(slug='medivation')}"
        )

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    source = manifest["source"]
    selected_form_type = source.get("selected_document_form_type") or source.get("form_type")

    assert source["seed_url"].endswith("-index.htm")
    assert selected_form_type == "EX-99.(A)(1)(A)"
    assert source["primary_document_name"].lower().endswith("ex99a1a.htm")
    assert "dex99a1a" in source["primary_document_url"].lower()


@pytest.mark.parametrize("slug", ("penford", "zep", "saks"))
def test_reference9_negative_facts_do_not_become_applicable(
    slug: str, fact_ledger: dict[str, dict]
) -> None:
    if slug in _missing_filings():
        pytest.fail(
            f"Reference-9 slug {slug!r} has no data/filings/{slug}/raw.md; "
            f"fetch it with: {FETCH_COMMAND.format(slug=slug)}"
        )
    conn = connect(":memory:")
    init_schema(conn)
    [source] = filing_sources([slug], filings_dir=FILINGS_DIR)
    filing = ingest_source(conn, source)
    build_evidence_map(conn, filing_id=filing.filing_id, run_id=RUN_ID)

    rows = {
        kind: applicability
        for kind, applicability in conn.execute(
            """
            SELECT obligation_kind, applicability
            FROM coverage_obligations
            WHERE filing_id = ?
              AND current = true
            """,
            [filing.filing_id],
        ).fetchall()
    }
    for fact in fact_ledger[slug].get("negative_facts", []):
        assert rows[fact["kind"]] == fact["expected_applicability"], (
            f"{slug}: {fact['kind']} should be {fact['expected_applicability']} "
            f"because source snippet contains {fact['snippet_must_contain']!r}"
        )


def test_medivation_cross_reference_only_past_contacts_region_is_rejected(
    fact_ledger: dict[str, dict]
) -> None:
    slug = "medivation"
    if slug in _missing_filings():
        pytest.fail(
            f"Reference-9 slug {slug!r} has no data/filings/{slug}/raw.md; "
            f"fetch it with: {FETCH_COMMAND.format(slug=slug)}"
        )
    conn = connect(":memory:")
    init_schema(conn)
    [source] = filing_sources([slug], filings_dir=FILINGS_DIR)
    filing = ingest_source(conn, source)
    build_evidence_map(conn, filing_id=filing.filing_id, run_id=RUN_ID)

    selected_sections = [
        json.loads(row[0])[0]
        for row in conn.execute(
            """
            SELECT trigger_phrases_json
            FROM evidence_regions
            WHERE filing_id = ?
            ORDER BY priority
            """,
            [filing.filing_id],
        ).fetchall()
    ]
    rejected = fact_ledger[slug]["rejected_regions"][0]["section"]
    assert rejected not in selected_sections


def _applicability_summary(conn, *, index: int) -> dict[str, object]:
    region_id = conn.execute(
        """
        SELECT region_id
        FROM evidence_regions
        ORDER BY priority
        LIMIT 1 OFFSET ?
        """,
        [index],
    ).fetchone()[0]
    app_rows = conn.execute(
        """
        SELECT obligation_kind, expected_claim_type, importance,
               applicability_reason_code, applicability_basis_json
        FROM coverage_obligations
        WHERE region_id = ?
          AND current = true
          AND applicability = 'applicable'
        ORDER BY CAST(regexp_extract(obligation_id, '_(\\d+)$', 1) AS INTEGER),
                 obligation_id
        """,
        [region_id],
    ).fetchall()
    return {
        "applicable_count": len(app_rows),
        "applicable_kinds": [row[0] for row in app_rows],
        "claim_types": sorted({row[1] for row in app_rows}),
        "important_or_required_kinds": [
            row[0] for row in app_rows if row[2] in {"required", "important"}
        ],
        "reason_codes": sorted({row[3] for row in app_rows}),
        "trigger_basis": sorted(
            {
                item
                for row in app_rows
                for item in json.loads(row[4])
                if row[3] == "trigger_phrase_match"
            }
        ),
    }


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
