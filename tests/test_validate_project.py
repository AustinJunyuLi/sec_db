import csv
import datetime as dt
import json
from pathlib import Path

from sec_graph.project.summaries import write_projection_outputs
from sec_graph.validate.flags import soft_flags
from sec_graph.validate.integrity import HardCheck, validate_database, write_validation_outputs
from sec_graph.schema import (
    Actor,
    CleanFiling,
    Deal,
    Event,
    EventActorLink,
    Judgment,
    Paragraph,
    ParticipationCount,
    ProcessCycle,
    RunMetadata,
    SourceSpan,
    connect,
    init_schema,
    make_id,
    quote_hash,
)
from sec_graph.schema import versions


def _load_fixture(path: Path = Path("tests/fixtures/canonical/petsmart.json")) -> dict[str, list[object]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {
        "deals": [Deal.model_validate(row) for row in payload["deals"]],
        "process_cycles": [ProcessCycle.model_validate(row) for row in payload["process_cycles"]],
        "actors": [Actor.model_validate(row) for row in payload["actors"]],
        "events": [Event.model_validate(row) for row in payload["events"]],
        "event_actor_links": [EventActorLink.model_validate(row) for row in payload["event_actor_links"]],
        "judgments": [Judgment.model_validate(row) for row in payload["judgments"]],
        "participation_counts": [ParticipationCount.model_validate(row) for row in payload["participation_counts"]],
    }


def _row_values(model) -> tuple[object, ...]:
    payload = model.model_dump(mode="json")
    if "bidder_subtype_split" in payload and payload["bidder_subtype_split"] is not None:
        payload["bidder_subtype_split"] = json.dumps(payload["bidder_subtype_split"], sort_keys=True)
    return tuple(payload.values())


def _insert_evidence(conn) -> None:
    text = (
        "The board allowed bidders at or above $80.00 to proceed to the final round.\n\n"
        "Buyer Group indicated a range of $81.00 to $83.00 per share and later offered $83.00.\n\n"
        "Bidder 2 submitted an offer of $81.50 per share.\n"
    )
    filing = CleanFiling(
        filing_id="petsmart_filing_1",
        deal_slug="petsmart",
        source_path="tests/fixtures/canonical/petsmart_evidence.md",
        raw_sha256=quote_hash(text),
        parser_version=versions.PARSER_VERSION,
        page_count=None,
        section_count=1,
    )
    metadata = RunMetadata(
        run_id="track-b-petsmart",
        schema_version=versions.SCHEMA_VERSION,
        parser_version=versions.PARSER_VERSION,
        ingest_version=versions.INGEST_VERSION,
        extract_version=versions.EXTRACT_VERSION,
        reconcile_version=versions.RECONCILE_VERSION,
        validate_version=versions.VALIDATE_VERSION,
        project_version=versions.PROJECT_VERSION,
        input_hashes={"petsmart": filing.raw_sha256},
        created_at=dt.datetime(2026, 5, 2, 14, 0, tzinfo=dt.UTC),
    )
    conn.execute("INSERT INTO filings VALUES (?, ?, ?, ?, ?, ?, ?)", tuple(filing.model_dump().values()))
    offset = 0
    for idx, paragraph_text in enumerate(text.split("\n\n"), start=1):
        if not paragraph_text:
            continue
        start = text.index(paragraph_text, offset)
        end = start + len(paragraph_text)
        offset = end
        paragraph = Paragraph(
            paragraph_id=make_id("petsmart", "para", idx),
            filing_id=filing.filing_id,
            section="Background of the Merger",
            page_hint=None,
            char_start=start,
            char_end=end,
            paragraph_text=paragraph_text,
            paragraph_hash=quote_hash(paragraph_text),
        )
        span = SourceSpan(
            evidence_id=make_id("petsmart", "evidence", idx),
            filing_id=filing.filing_id,
            paragraph_id=paragraph.paragraph_id,
            span_basis="raw_md",
            span_kind="paragraph_seed",
            parent_evidence_id=None,
            created_by_stage="ingest",
            char_start=start,
            char_end=end,
            quote_text=paragraph_text,
            quote_hash=quote_hash(paragraph_text),
        )
        conn.execute("INSERT INTO paragraphs VALUES (?, ?, ?, ?, ?, ?, ?, ?)", tuple(paragraph.model_dump().values()))
        conn.execute("INSERT INTO spans VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", tuple(span.model_dump().values()))
    payload = metadata.model_dump()
    payload["input_hashes"] = json.dumps(payload["input_hashes"], sort_keys=True)
    payload["created_at"] = payload["created_at"].isoformat()
    conn.execute("INSERT INTO run_metadata VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", tuple(payload.values()))


def _insert_fixture(conn, fixture: dict[str, list[object]]) -> None:
    for deal in fixture["deals"]:
        conn.execute("INSERT INTO deals VALUES (?, ?, ?, ?, ?, ?)", _row_values(deal))
    for actor in fixture["actors"]:
        conn.execute("INSERT INTO actors VALUES (?, ?, ?, ?, ?, ?, ?, ?)", _row_values(actor))
    for cycle in fixture["process_cycles"]:
        conn.execute("INSERT INTO process_cycles VALUES (?, ?, ?, ?, ?, ?, ?, ?)", _row_values(cycle))
    for event in fixture["events"]:
        conn.execute("INSERT INTO events VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", _row_values(event))
    for link in fixture["event_actor_links"]:
        conn.execute("INSERT INTO event_actor_links VALUES (?, ?, ?, ?, ?, ?)", _row_values(link))
    for judgment in fixture["judgments"]:
        conn.execute("INSERT INTO judgments VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", _row_values(judgment))
    for count in fixture["participation_counts"]:
        conn.execute("INSERT INTO participation_counts VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", _row_values(count))


def _loaded_conn() -> object:
    conn = connect(":memory:")
    init_schema(conn)
    _insert_evidence(conn)
    _insert_fixture(conn, _load_fixture())
    return conn


def test_hand_authored_petsmart_fixture_passes_hard_validation() -> None:
    result = validate_database(_loaded_conn())

    assert result.passed
    assert result.hard_failures == []


def test_broken_fixture_reports_specific_hard_check_classes() -> None:
    conn = _loaded_conn()
    conn.execute("UPDATE spans SET quote_hash = ? WHERE evidence_id = ?", ["0" * 64, "petsmart_evidence_1"])
    conn.execute("UPDATE events SET event_date = ? WHERE event_id = ?", ["2014-01-01", "petsmart_event_1"])
    conn.execute("UPDATE events SET bid_value = 100 WHERE event_id = ?", ["petsmart_event_1"])
    conn.execute("DELETE FROM judgments WHERE judgment_type = ?", ["cycle_relation"])

    result = validate_database(conn)
    checks = {failure.check for failure in result.hard_failures}

    assert HardCheck.EVIDENCE_HASH in checks
    assert HardCheck.DATE_SANITY in checks
    assert HardCheck.BID_BOUNDS in checks
    assert HardCheck.REQUIRED_JUDGMENTS in checks


def test_soft_flags_and_validation_outputs_are_written(tmp_path) -> None:
    conn = _loaded_conn()
    flags = soft_flags(conn)

    assert any(flag.flag_type == "low_confidence_judgment" for flag in flags)
    assert any(flag.flag_type == "alternative_value" for flag in flags)

    report = write_validation_outputs(conn, tmp_path)
    assert report["passed"] is True
    report_path = tmp_path / "validation_report.json"
    queue_path = tmp_path / "ambiguity_queue.csv"
    assert json.loads(report_path.read_text(encoding="utf-8"))["passed"] is True
    with queue_path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert {row["flag_type"] for row in rows} >= {"low_confidence_judgment", "alternative_value"}


def test_projection_outputs_match_golden_bidder_rows(tmp_path) -> None:
    conn = _loaded_conn()
    write_projection_outputs(conn, tmp_path)

    actual = (tmp_path / "bidder_rows.jsonl").read_text(encoding="utf-8").splitlines()
    expected = Path("tests/fixtures/canonical/petsmart_bidder_rows.jsonl").read_text(encoding="utf-8").splitlines()
    assert actual == expected
    assert (tmp_path / "run_memo.md").read_text(encoding="utf-8").startswith("# sec_graph Run Memo")
    for name in ("auctions.jsonl", "cycle_summary.csv", "bidder_summary.csv", "deal_index.csv", "review_master.csv"):
        assert (tmp_path / name).exists()
