import datetime as dt
import json
from pathlib import Path

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
    validate_quote,
)
from sec_graph.schema.judgments import latest_judgments
from sec_graph.schema import versions


def _table_names(conn) -> set[str]:
    return {
        row[0]
        for row in conn.execute(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'main'
            ORDER BY table_name
            """
        ).fetchall()
    }


def _insert_smoke_evidence(conn) -> None:
    text = Path("tests/fixtures/smoke_filing.md").read_text(encoding="utf-8")
    filing = CleanFiling(
        filing_id="smoke_filing",
        deal_slug="smoke",
        source_path="tests/fixtures/smoke_filing.md",
        raw_sha256=quote_hash(text),
        parser_version=versions.PARSER_VERSION,
        page_count=2,
        section_count=1,
    )
    metadata = RunMetadata(
        run_id="stage1b-smoke",
        schema_version=versions.SCHEMA_VERSION,
        parser_version=versions.PARSER_VERSION,
        ingest_version=versions.INGEST_VERSION,
        extract_version=versions.EXTRACT_VERSION,
        reconcile_version=versions.RECONCILE_VERSION,
        validate_version=versions.VALIDATE_VERSION,
        project_version=versions.PROJECT_VERSION,
        input_hashes={"smoke_filing.md": filing.raw_sha256},
        created_at=dt.datetime(2026, 5, 2, 13, 0, tzinfo=dt.UTC),
    )
    conn.execute("INSERT INTO filings VALUES (?, ?, ?, ?, ?, ?, ?)", tuple(filing.model_dump().values()))
    paragraph_texts = [
        "On January 5, 2024, Party A submitted an indication of interest.",
        "On January 12, 2024, Party B proposed $12.50 per share in cash.",
        "The board also contacted 15 financial buyers during the process.",
    ]
    cursor = 0
    for idx, paragraph_text in enumerate(paragraph_texts, start=1):
        char_start = text.index(paragraph_text, cursor)
        char_end = char_start + len(paragraph_text)
        cursor = char_end
        paragraph = Paragraph(
            paragraph_id=make_id("smoke", "para", idx),
            filing_id=filing.filing_id,
            section="Background of the Merger",
            page_hint=1 if idx < 3 else 2,
            char_start=char_start,
            char_end=char_end,
            paragraph_text=paragraph_text,
            paragraph_hash=quote_hash(paragraph_text),
        )
        span = SourceSpan(
            evidence_id=make_id("smoke", "evidence", idx),
            filing_id=filing.filing_id,
            paragraph_id=paragraph.paragraph_id,
            span_basis="raw_md",
            span_kind="paragraph_seed",
            parent_evidence_id=None,
            created_by_stage="ingest",
            char_start=char_start,
            char_end=char_end,
            quote_text=paragraph_text,
            quote_hash=quote_hash(paragraph_text),
        )
        conn.execute("INSERT INTO paragraphs VALUES (?, ?, ?, ?, ?, ?, ?, ?)", tuple(paragraph.model_dump().values()))
        conn.execute("INSERT INTO spans VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", tuple(span.model_dump().values()))
    metadata_row = metadata.model_dump()
    metadata_row["input_hashes"] = json.dumps(metadata_row["input_hashes"], sort_keys=True)
    metadata_row["created_at"] = metadata_row["created_at"].isoformat()
    conn.execute("INSERT INTO run_metadata VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", tuple(metadata_row.values()))


def _load_smoke_fixture() -> dict[str, list[object]]:
    payload = json.loads(Path("tests/fixtures/smoke_canonical.json").read_text(encoding="utf-8"))
    return {
        "deals": [Deal.model_validate(row) for row in payload["deals"]],
        "process_cycles": [ProcessCycle.model_validate(row) for row in payload["process_cycles"]],
        "actors": [Actor.model_validate(row) for row in payload["actors"]],
        "events": [Event.model_validate(row) for row in payload["events"]],
        "event_actor_links": [EventActorLink.model_validate(row) for row in payload["event_actor_links"]],
        "judgments": [Judgment.model_validate(row) for row in payload["judgments"]],
        "participation_counts": [
            ParticipationCount.model_validate(row) for row in payload["participation_counts"]
        ],
    }


def _row_values(model) -> tuple[object, ...]:
    payload = model.model_dump(mode="json")
    if "bidder_subtype_split" in payload and payload["bidder_subtype_split"] is not None:
        payload["bidder_subtype_split"] = json.dumps(payload["bidder_subtype_split"], sort_keys=True)
    return tuple(payload.values())


def _insert_canonical_fixture(conn, fixture: dict[str, list[object]]) -> None:
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
        conn.execute(
            "INSERT INTO participation_counts VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            _row_values(count),
        )


def test_init_schema_creates_stage1b_table_subset() -> None:
    conn = connect(":memory:")
    init_schema(conn)

    assert {
        "filings",
        "paragraphs",
        "spans",
        "run_metadata",
        "deals",
        "process_cycles",
        "actors",
        "events",
        "event_actor_links",
        "judgments",
        "participation_counts",
    } <= _table_names(conn)


def test_smoke_canonical_fixture_is_fk_clean_and_evidence_bound() -> None:
    conn = connect(":memory:")
    init_schema(conn)
    _insert_smoke_evidence(conn)
    fixture = _load_smoke_fixture()
    _insert_canonical_fixture(conn, fixture)

    actors = {row[0] for row in conn.execute("SELECT actor_id FROM actors").fetchall()}
    cycles = {row[0] for row in conn.execute("SELECT cycle_id FROM process_cycles").fetchall()}
    events = {row[0] for row in conn.execute("SELECT event_id FROM events").fetchall()}
    spans = {
        row[0]: row
        for row in conn.execute(
            "SELECT evidence_id, char_start, char_end, quote_hash FROM spans"
        ).fetchall()
    }
    smoke_text = Path("tests/fixtures/smoke_filing.md").read_text(encoding="utf-8")

    for deal in fixture["deals"]:
        assert deal.target_actor_id in actors
    for event in fixture["events"]:
        assert event.cycle_id in cycles
    for link in fixture["event_actor_links"]:
        assert link.event_id in events
        assert link.actor_id in actors
    for count in fixture["participation_counts"]:
        assert count.cycle_id in cycles
        assert count.actor_creation_required == "deferred"

    for rows in fixture.values():
        for row in rows:
            for evidence_id in row.evidence_ids:
                assert evidence_id in spans
                _, start, end, expected_hash = spans[evidence_id]
                assert validate_quote(smoke_text, start, end, expected_hash)


def test_each_stage1b_model_round_trips_through_duckdb_rows() -> None:
    conn = connect(":memory:")
    init_schema(conn)
    _insert_smoke_evidence(conn)
    fixture = _load_smoke_fixture()
    _insert_canonical_fixture(conn, fixture)

    deal_row = conn.execute("SELECT * FROM deals WHERE deal_id = 'smoke_deal_1'").fetchone()
    assert Deal.model_validate(dict(zip(Deal.model_fields, deal_row, strict=True))) == fixture["deals"][0]

    actor_row = conn.execute("SELECT * FROM actors WHERE actor_id = 'smoke_actor_2'").fetchone()
    assert Actor.model_validate(dict(zip(Actor.model_fields, actor_row, strict=True))) == fixture["actors"][1]

    cycle_row = conn.execute("SELECT * FROM process_cycles WHERE cycle_id = 'smoke_cycle_1'").fetchone()
    assert ProcessCycle.model_validate(dict(zip(ProcessCycle.model_fields, cycle_row, strict=True))) == fixture[
        "process_cycles"
    ][0]

    event_row = conn.execute("SELECT * FROM events WHERE event_id = 'smoke_event_2'").fetchone()
    assert Event.model_validate(dict(zip(Event.model_fields, event_row, strict=True))) == fixture["events"][1]

    link_row = conn.execute("SELECT * FROM event_actor_links WHERE link_id = 'smoke_link_1'").fetchone()
    assert EventActorLink.model_validate(dict(zip(EventActorLink.model_fields, link_row, strict=True))) == fixture[
        "event_actor_links"
    ][0]

    judgment_row = conn.execute("SELECT * FROM judgments WHERE judgment_id = 'smoke_judgment_1'").fetchone()
    assert Judgment.model_validate(dict(zip(Judgment.model_fields, judgment_row, strict=True))) == fixture[
        "judgments"
    ][0]

    count_row = conn.execute(
        "SELECT * FROM participation_counts WHERE participation_count_id = 'smoke_count_1'"
    ).fetchone()
    count_payload = dict(zip(ParticipationCount.model_fields, count_row, strict=True))
    count_payload["bidder_subtype_split"] = json.loads(count_payload["bidder_subtype_split"])
    assert ParticipationCount.model_validate(count_payload) == fixture["participation_counts"][0]


def test_latest_judgment_resolution_returns_non_superseded_chain_tip() -> None:
    chain = [
        Judgment(
            judgment_id="j1",
            run_id="r1",
            deal_id="d1",
            cycle_id="c1",
            actor_id=None,
            event_id=None,
            judgment_type="formal_boundary",
            judgment_value="none_observed",
            confidence="low",
            alternative_value=None,
            supersedes_judgment_id=None,
            evidence_ids=["smoke_evidence_1"],
        ),
        Judgment(
            judgment_id="j2",
            run_id="r1",
            deal_id="d1",
            cycle_id="c1",
            actor_id=None,
            event_id=None,
            judgment_type="formal_boundary",
            judgment_value="board_meeting",
            confidence="medium",
            alternative_value=None,
            supersedes_judgment_id="j1",
            evidence_ids=["smoke_evidence_1"],
        ),
        Judgment(
            judgment_id="j3",
            run_id="r1",
            deal_id="d1",
            cycle_id="c1",
            actor_id=None,
            event_id=None,
            judgment_type="formal_boundary",
            judgment_value="final_round_invitation",
            confidence="high",
            alternative_value=None,
            supersedes_judgment_id="j2",
            evidence_ids=["smoke_evidence_2"],
        ),
    ]

    assert latest_judgments(chain) == [chain[2]]


def test_docs_declare_module_table_ownership_policy() -> None:
    spec_text = Path("docs/spec.md").read_text(encoding="utf-8")
    claude_text = Path("CLAUDE.md").read_text(encoding="utf-8")

    assert "Module Table Ownership" in spec_text
    assert "`ingest`" in spec_text and "`filings`, `paragraphs`, `spans`" in spec_text
    assert "`extract`" in spec_text and "`candidates`" in spec_text
    assert "`reconcile`" in spec_text and "`judgments`, `participation_counts`" in spec_text
    assert "module-table ownership policy" in claude_text
