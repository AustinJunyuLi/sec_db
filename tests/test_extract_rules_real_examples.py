import hashlib
import json
from pathlib import Path

from sec_graph.extract.rules import run_rules
from sec_graph.extract.rules.actors import actor_matches
from sec_graph.extract.rules.bids import bid_matches
from sec_graph.extract.rules.events import dated_event_matches
from sec_graph.extract.rules.relations import relation_matches
from sec_graph.ingest.pipeline import ingest_examples
from sec_graph.schema import connect, init_schema, validate_quote

GOLDEN_PATH = Path("tests/fixtures/extract/real_candidate_golden.json")


def test_actor_rules_cover_real_example_alias_forms() -> None:
    text = (
        "Industry Participant contacted J.P. Morgan before the Buyer Group and Bidder 2 submitted bids. "
        "Hudson\u2019s Bay, Sponsor A, Sponsor E, Sponsor G and Company B remained active."
    )

    assert [match.raw_value for match in actor_matches(text)] == [
        "Industry Participant",
        "Buyer Group",
        "Bidder 2",
        "Hudson\u2019s Bay",
        "Sponsor A",
        "Sponsor E",
        "Sponsor G",
        "Company B",
    ]


def test_dated_event_rules_stop_at_sentence_boundaries_with_initialisms() -> None:
    text = (
        "On August 13, 2014, the board met with J.P. Morgan. "
        "As a result of this meeting, the board determined to explore strategic alternatives. "
        "On August 19, 2014, the Company issued a press release."
    )

    assert [(match.raw_value, match.normalized_value) for match in dated_event_matches(text)] == [
        ("On August 13, 2014, the board met with J.P. Morgan.", "2014-08-13"),
        ("On August 19, 2014, the Company issued a press release.", "2014-08-19"),
    ]


def test_bid_rules_capture_ranges_without_duplicate_upper_endpoint() -> None:
    text = (
        "Hudson\u2019s Bay\u2019s proposal included a price of $15.25 per share. "
        "The joint proposal included an indicative price range of $14.50\u2013$15.50 per share. "
        "Another bidder ranged from $80.00 per share to $85.00 per share."
    )

    assert [(match.raw_value, match.normalized_value) for match in bid_matches(text)] == [
        ("$15.25 per share", "15.25"),
        ("$14.50\u2013$15.50 per share", "14.5-15.5"),
        ("$80.00 per share to $85.00 per share", "80.0-85.0"),
    ]


def test_generic_merger_sub_relations_do_not_manufacture_petsmart_vehicle_labels() -> None:
    text = (
        "Merger Sub will merge with and into the Company, with the Company "
        "surviving the merger as a wholly owned subsidiary of Parent."
    )

    payloads = [json.loads(match.normalized_value) for match in relation_matches(text)]

    assert payloads == [
        {
            "effective_date_first": None,
            "object_label": "Parent",
            "relation_type": "acquisition_vehicle_of",
            "role_detail": "merger subsidiary owned by parent",
            "subject_label": "Merger Sub",
        }
    ]


def test_defined_parent_and_merger_sub_aliases_use_clean_company_labels() -> None:
    text = (
        "The merger agreement was entered into by and among the Company, Argos Holdings Inc., "
        "a Delaware corporation (\u201cParent\u201d), and Argos Merger Sub Inc., a Delaware corporation "
        "and wholly owned subsidiary of Parent (\u201cMerger Sub\u201d). Merger Sub is a wholly owned "
        "subsidiary of Parent."
    )

    payloads = [json.loads(match.normalized_value) for match in relation_matches(text)]

    assert {
        "effective_date_first": None,
        "object_label": "Argos Holdings Inc.",
        "relation_type": "acquisition_vehicle_of",
        "role_detail": "merger subsidiary owned by parent",
        "subject_label": "Argos Merger Sub Inc.",
    } in payloads


def test_document_level_aliases_apply_to_later_generic_vehicle_clauses() -> None:
    text = "Merger Sub is a wholly owned subsidiary of Parent."

    payloads = [
        json.loads(match.normalized_value)
        for match in relation_matches(text, {"Parent": "Argos Holdings Inc.", "Merger Sub": "Argos Merger Sub Inc."})
    ]

    assert payloads == [
        {
            "effective_date_first": None,
            "object_label": "Argos Holdings Inc.",
            "relation_type": "acquisition_vehicle_of",
            "role_detail": "merger subsidiary owned by parent",
            "subject_label": "Argos Merger Sub Inc.",
        }
    ]


def test_real_extraction_candidate_sequence_follows_source_order() -> None:
    conn = connect(":memory:")
    init_schema(conn)
    ingest_examples(conn, examples_dir=Path("data/examples"))
    filing_id = conn.execute("SELECT filing_id FROM filings WHERE deal_slug = 'petsmart-inc'").fetchone()[0]

    run_rules(conn, filing_id=filing_id)

    first_dated_event = conn.execute(
        """
        SELECT normalized_value
        FROM candidates
        WHERE candidate_type = 'dated_event'
        ORDER BY CAST(regexp_extract(candidate_id, 'candidate_(\\d+)$', 1) AS INTEGER)
        LIMIT 1
        """
    ).fetchone()[0]
    assert first_dated_event == "2014-05-21"


def _loaded_real_conn():
    conn = connect(":memory:")
    init_schema(conn)
    filings = ingest_examples(conn, examples_dir=Path("data/examples"))
    for filing in filings:
        run_rules(conn, filing_id=filing.filing_id)
    return conn


def _candidate_projection(conn, slug: str) -> list[dict[str, object]]:
    rows = conn.execute(
        """
        SELECT candidate_id, candidate_type, raw_value, normalized_value, confidence, status
        FROM candidates
        JOIN filings USING (filing_id)
        WHERE deal_slug = ?
        ORDER BY CAST(regexp_extract(candidate_id, 'candidate_(\\d+)$', 1) AS INTEGER)
        """,
        [slug],
    ).fetchall()
    return [
        {
            "candidate_id": row[0],
            "candidate_type": row[1],
            "raw_value": row[2],
            "normalized_value": row[3],
            "confidence": row[4],
            "status": row[5],
        }
        for row in rows
    ]


def _projection_hash(projection: list[dict[str, object]]) -> str:
    payload = json.dumps(projection, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def test_real_petsmart_and_saks_candidates_match_golden_projection() -> None:
    conn = _loaded_real_conn()
    golden = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))

    for slug, expected in golden.items():
        projection = _candidate_projection(conn, slug)
        assert len(projection) == expected["row_count"]
        assert _projection_hash(projection) == expected["projection_sha256"]

        actual_required_rows = [
            {
                "candidate_type": row["candidate_type"],
                "raw_value": row["raw_value"],
                "normalized_value": row["normalized_value"],
            }
            for row in projection
        ]
        for required_row in expected["required_rows"]:
            assert required_row in actual_required_rows


def test_real_candidates_are_evidence_bound_to_extract_spans() -> None:
    conn = _loaded_real_conn()
    golden = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))

    for slug in golden:
        source_path = conn.execute("SELECT source_path FROM filings WHERE deal_slug = ?", [slug]).fetchone()[0]
        filing_text = Path(source_path).read_text(encoding="utf-8")
        candidate_rows = conn.execute(
            """
            SELECT candidate_id, evidence_ids
            FROM candidates
            JOIN filings USING (filing_id)
            WHERE deal_slug = ?
            ORDER BY candidate_id
            """,
            [slug],
        ).fetchall()
        assert candidate_rows
        for candidate_id, evidence_ids in candidate_rows:
            assert evidence_ids, candidate_id
            for evidence_id in evidence_ids:
                span = conn.execute(
                    """
                    SELECT child.char_start, child.char_end, child.quote_hash, child.parent_evidence_id,
                           parent.char_start, parent.char_end
                    FROM spans AS child
                    JOIN spans AS parent ON child.parent_evidence_id = parent.evidence_id
                    WHERE child.evidence_id = ?
                    """,
                    [evidence_id],
                ).fetchone()
                assert span is not None, (candidate_id, evidence_id)
                child_start, child_end, quote_hash_value, parent_id, parent_start, parent_end = span
                assert parent_id is not None
                assert parent_start <= child_start <= child_end <= parent_end
                assert validate_quote(filing_text, child_start, child_end, quote_hash_value)


def test_real_candidate_extraction_is_deterministic_for_golden_slugs() -> None:
    first = _loaded_real_conn()
    second = _loaded_real_conn()
    golden = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))

    for slug in golden:
        assert _candidate_projection(first, slug) == _candidate_projection(second, slug)
