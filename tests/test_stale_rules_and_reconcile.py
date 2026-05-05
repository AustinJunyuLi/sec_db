import importlib
from pathlib import Path

import pytest

from sec_graph.extract.disposition import dispose_claims_for_filing
from sec_graph.reconcile.pipeline import reconcile_all
from sec_graph.schema import (
    ActorClaim,
    Claim,
    CleanFiling,
    EvidenceRegion,
    Paragraph,
    SourceSpan,
    connect,
    evidence_fingerprint,
    init_schema,
    make_id,
    quote_hash,
)


RUN_ID = "2026-05-03T020304Z_rules-reconcile_deadbeef"


def test_obsolete_rules_surface_imports_and_fails_loudly() -> None:
    rules = importlib.import_module("sec_graph.extract.rules")
    relations = importlib.import_module("sec_graph.extract.rules.relations")

    with pytest.raises(RuntimeError, match="obsolete deterministic extraction rules"):
        rules.run_rules(None, filing_id="stale_filing_1", run_id=RUN_ID)
    with pytest.raises(RuntimeError, match="obsolete deterministic extraction rules"):
        relations.relation_matches("Parent owned Merger Sub")


def test_reconcile_all_is_idempotent_after_claims_are_disposed(tmp_path: Path) -> None:
    conn = connect(":memory:")
    init_schema(conn)
    _insert_single_actor_claim(conn, tmp_path)
    filing_id = make_id("smoke-deal", "filing", 1)
    dispose_claims_for_filing(conn, filing_id=filing_id, run_id=RUN_ID)

    reconcile_all(conn, run_id=RUN_ID)
    first_rows = _canonical_snapshot(conn)
    assert conn.execute("SELECT status FROM claims").fetchall() == [("disposed",)]

    reconcile_all(conn, run_id=RUN_ID)
    second_rows = _canonical_snapshot(conn)

    assert second_rows == first_rows
    assert conn.execute("SELECT status FROM claims").fetchall() == [("disposed",)]
    assert conn.execute("SELECT count(*) FROM claim_dispositions").fetchone()[0] == 1


def _insert_single_actor_claim(conn, tmp_path: Path) -> None:
    slug = "smoke-deal"
    filing_id = make_id(slug, "filing", 1)
    paragraph_id = make_id(slug, "para", 1)
    evidence_id = make_id(slug, "evidence", 1)
    region_id = make_id(slug, "region", 1)
    claim_id = make_id(slug, "claim", 1)
    text = "Smoke Deal, Inc. entered into a merger agreement."
    source_path = tmp_path / "smoke-deal.md"
    source_path.write_text(text, encoding="utf-8")
    text_hash = quote_hash(text)

    filing = CleanFiling(
        filing_id=filing_id,
        deal_slug=slug,
        source_path=str(source_path),
        raw_sha256=text_hash,
        parser_version=1,
        page_count=None,
        section_count=1,
        process_scope="target_full_proxy",
    )
    paragraph = Paragraph(
        paragraph_id=paragraph_id,
        filing_id=filing_id,
        section="Background of the Merger",
        page_hint=None,
        char_start=0,
        char_end=len(text),
        paragraph_text=text,
        paragraph_hash=text_hash,
    )
    span = SourceSpan(
        evidence_id=evidence_id,
        filing_id=filing_id,
        paragraph_id=paragraph_id,
        span_basis="raw_md",
        span_kind="paragraph_seed",
        parent_evidence_id=None,
        created_by_stage="ingest",
        char_start=0,
        char_end=len(text),
        quote_text=text,
        quote_text_hash=text_hash,
        evidence_fingerprint=evidence_fingerprint(filing_id, 0, len(text), text_hash),
    )
    region = EvidenceRegion(
        region_id=region_id,
        run_id=RUN_ID,
        filing_id=filing_id,
        deal_slug=slug,
        region_kind="sale_process_narrative",
        priority=1,
        start_paragraph_id=paragraph_id,
        end_paragraph_id=paragraph_id,
        paragraph_ids_json=f'["{paragraph_id}"]',
        trigger_phrases_json='["Background of the Merger"]',
        expected_claim_types_json='["actor"]',
    )
    claim = Claim(
        claim_id=claim_id,
        run_id=RUN_ID,
        filing_id=filing_id,
        deal_slug=slug,
        region_id=region_id,
        provider_source_stage="linkflow",
        claim_type="actor",
        confidence="high",
        raw_value="Smoke Deal, Inc.",
        normalized_value="Smoke Deal, Inc.",
        quote_text="Smoke Deal, Inc.",
        quote_text_hash=quote_hash("Smoke Deal, Inc."),
        status="validated",
        claim_sequence=1,
    )
    actor_claim = ActorClaim(
        claim_id=claim_id,
        actor_label="Smoke Deal, Inc.",
        actor_kind="organization",
        observability="named",
    )

    conn.execute("INSERT INTO filings VALUES (?, ?, ?, ?, ?, ?, ?, ?)", tuple(filing.model_dump().values()))
    conn.execute("INSERT INTO paragraphs VALUES (?, ?, ?, ?, ?, ?, ?, ?)", tuple(paragraph.model_dump().values()))
    conn.execute("INSERT INTO spans VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", tuple(span.model_dump().values()))
    conn.execute("INSERT INTO evidence_regions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", tuple(region.model_dump().values()))
    conn.execute("INSERT INTO claims VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", tuple(claim.model_dump().values()))
    conn.execute("INSERT INTO actor_claims VALUES (?, ?, ?, ?)", tuple(actor_claim.model_dump().values()))
    conn.execute("INSERT INTO claim_evidence VALUES (?, ?, ?)", [claim_id, evidence_id, 1])


def _canonical_snapshot(conn) -> dict[str, list[tuple[object, ...]]]:
    return {
        table: conn.execute(f"SELECT * FROM {table} ORDER BY 1").fetchall()
        for table in ("deals", "actors", "row_evidence", "claim_dispositions")
    }
