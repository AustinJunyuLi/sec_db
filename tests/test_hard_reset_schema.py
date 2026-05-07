import csv
import json
from pathlib import Path

from sec_graph.extract.disposition import (
    dispose_claims_for_filing,
    finalize_coverage_after_disposition,
)
from sec_graph.extract.evidence_map import build_evidence_map
from sec_graph.extract.llm.convert import insert_llm_response
from sec_graph.extract.llm.linkflow import _parse_payload, _semantic_claim_schema
from sec_graph.extract.llm.models import (
    ActorClaimPayload,
    ActorRelationClaimPayload,
    BidClaimPayload,
    EventClaimPayload,
    LLMExtractionResponse,
    ParticipationCountClaimPayload,
    SemanticClaimsPayload,
)
from sec_graph.extract.llm.prompt import build_window_prompt
from sec_graph.extract.llm.requests import build_llm_windows
from sec_graph.project.summaries import write_projection_outputs
from sec_graph.reconcile.pipeline import reconcile_all
from sec_graph.schema import (
    CleanFiling,
    Paragraph,
    SourceSpan,
    connect,
    evidence_fingerprint,
    init_schema,
    make_id,
    quote_hash,
)
from sec_graph.validate.integrity import validate_database


RUN_ID = "2026-05-03T010203Z_smoke-deal_deadbeef"


def test_hard_reset_schema_replaces_candidates_and_array_evidence() -> None:
    conn = connect(":memory:")
    init_schema(conn)

    tables = {row[0] for row in conn.execute("SHOW TABLES").fetchall()}

    assert "candidates" not in tables
    assert "relation_candidates" not in tables
    assert {
        "claims",
        "actor_claims",
        "event_claims",
        "bid_claims",
        "participation_count_claims",
        "actor_relation_claims",
        "claim_evidence",
        "claim_dispositions",
        "row_evidence",
        "evidence_regions",
        "coverage_obligations",
        "coverage_results",
        "projection_units",
        "claim_coverage_links",
        "projection_judgments",
        "bidder_rows",
        "run_manifest",
        "progress_ledger",
        "stage_artifacts",
        "cost_runtime_records",
    } <= tables

    columns = {
        row[1]
        for table in ("deals", "actors", "events", "actor_relations", "event_actor_links", "participation_counts")
        for row in conn.execute(f"PRAGMA table_info({table})").fetchall()
    }
    assert "evidence_ids" not in columns


def test_claim_disposition_enum_uses_support_statuses() -> None:
    conn = connect(":memory:")
    init_schema(conn)
    rows = conn.execute(
        """
        SELECT constraint_text
        FROM duckdb_constraints()
        WHERE table_name = 'claim_dispositions'
        ORDER BY constraint_text
        """
    ).fetchall()
    text = "\n".join(row[0] for row in rows)
    assert "supported" in text
    assert "rejected_unsupported" in text
    assert "queued_ambiguity" in text
    assert "canonicalized" not in text


def test_judgments_and_review_rows_tables_exist() -> None:
    conn = connect(":memory:")
    init_schema(conn)
    table_names = {
        row[0]
        for row in conn.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'main'"
        ).fetchall()
    }
    assert "judgments" in table_names
    assert "review_rows" in table_names
    assert "review_flags" not in table_names

    judgment_columns = {
        row[1]
        for row in conn.execute("PRAGMA table_info('judgments')").fetchall()
    }
    for column in (
        "judgment_key",
        "judgment_value",
        "judgment_status",
        "rule_id",
        "basis_json",
        "current",
    ):
        assert column in judgment_columns

    review_row_columns = {
        row[1]
        for row in conn.execute("PRAGMA table_info('review_rows')").fetchall()
    }
    for column in (
        "review_row_id",
        "run_id",
        "deal_slug",
        "review_status",
        "review_type",
        "severity",
        "reason_code",
        "review_question",
    ):
        assert column in review_row_columns


def test_typed_claims_reconcile_to_source_backed_projection(tmp_path: Path) -> None:
    conn = connect(":memory:")
    init_schema(conn)
    source_path = _insert_filing(conn, tmp_path)

    build_evidence_map(conn, filing_id="smoke-deal_filing_1", run_id=RUN_ID)
    windows = build_llm_windows(conn, filing_id="smoke-deal_filing_1")
    assert windows
    for window in windows:
        response = _response_for_window(window)
        insert_llm_response(conn, window, response, run_id=RUN_ID)

    dispose_claims_for_filing(conn, filing_id="smoke-deal_filing_1", run_id=RUN_ID)
    finalize_coverage_after_disposition(
        conn, run_id=RUN_ID, filing_id="smoke-deal_filing_1"
    )
    reconcile_all(conn, run_id=RUN_ID)
    validation = validate_database(conn, raw_source_root=source_path.parent)
    assert validation.passed, validation.system_failures

    proof = write_projection_outputs(
        conn,
        tmp_path / "run",
        run_id=RUN_ID,
        projection_name="bidder_cycle_baseline_v1",
    )
    run_dir = tmp_path / "run"

    assert proof["row_counts"]["claims"] >= 5
    assert proof["row_counts"]["claim_dispositions"] == proof["row_counts"]["claims"]
    # coverage_results are written for applicable obligations only; the
    # inapplicable rows in coverage_obligations are audit-only.
    assert proof["row_counts"]["coverage_results"] == proof["row_counts"]["applicable_coverage_obligations"]
    assert proof["row_counts"]["coverage_results"] < proof["row_counts"]["coverage_obligations"]
    assert proof["row_counts"]["actor_relations"] >= 1
    assert proof["row_counts"]["participation_counts"] >= 1
    assert proof["row_counts"]["bidder_rows"] >= 1
    assert proof["canonical_rows_without_relational_evidence"] == 0
    assert proof["status"] in {"passed_clean", "needs_review", "high_burden"}
    assert (run_dir / "cost_runtime_summary.json").exists()
    assert (run_dir / "cost_runtime_summary.csv").exists()
    assert (run_dir / "provider_usage_ledger.jsonl").exists()
    assert (run_dir / "latency_ledger.jsonl").exists()
    with (run_dir / "coverage_results.csv").open(newline="", encoding="utf-8") as handle:
        coverage_header = next(csv.reader(handle))
    assert {
        "obligation_kind",
        "applicability",
        "applicability_reason_code",
        "applicability_basis_json",
    } <= set(coverage_header)


def test_generic_bid_claim_labels_do_not_project_as_named_bidders(tmp_path: Path) -> None:
    conn = connect(":memory:")
    init_schema(conn)
    _insert_generic_bidder_filing(conn, tmp_path)

    build_evidence_map(conn, filing_id="generic-bidder-deal_filing_1", run_id=RUN_ID)
    window = build_llm_windows(conn, filing_id="generic-bidder-deal_filing_1")[0]
    insert_llm_response(conn, window, _generic_bidder_response(window), run_id=RUN_ID)

    dispose_claims_for_filing(conn, filing_id="generic-bidder-deal_filing_1", run_id=RUN_ID)
    finalize_coverage_after_disposition(
        conn, run_id=RUN_ID, filing_id="generic-bidder-deal_filing_1"
    )
    reconcile_all(conn, run_id=RUN_ID)
    _insert_projection_leak_candidate(conn)
    proof = write_projection_outputs(
        conn,
        tmp_path / "run",
        run_id=RUN_ID,
        projection_name="bidder_cycle_baseline_v1",
    )

    projected_labels = {
        row[0]
        for row in conn.execute(
            "SELECT actor_label FROM bidder_rows WHERE deal_slug = ?",
            ["generic-bidder-deal"],
        ).fetchall()
    }
    assert projected_labels == {"Party A"}
    assert {
        "five parties",
        "six of the potentially interested parties",
        "potential bidders",
    }.isdisjoint(projected_labels)
    assert proof["row_counts"]["participation_counts"] >= 2

    disposed_generic_bids = conn.execute(
        """
        SELECT bid_claims.bidder_label, claim_dispositions.disposition,
               claim_dispositions.reason_code
        FROM bid_claims
        JOIN claim_dispositions USING (claim_id)
        WHERE bid_claims.bidder_label <> 'Party A'
        ORDER BY bid_claims.bidder_label
        """
    ).fetchall()
    assert disposed_generic_bids == [
        ("five parties", "rejected_unsupported", "generic_bidder_label_not_projectable"),
        ("potential bidders", "rejected_unsupported", "generic_bidder_label_not_projectable"),
        ("six of the potentially interested parties", "rejected_unsupported", "generic_bidder_label_not_projectable"),
    ]


def test_location_aware_fingerprint_distinguishes_repeated_text() -> None:
    quote = "same words"
    text_hash = quote_hash(quote)
    assert evidence_fingerprint("filing_a", 0, 10, text_hash) != evidence_fingerprint("filing_a", 20, 30, text_hash)
    assert evidence_fingerprint("filing_a", 0, 10, text_hash) != evidence_fingerprint("filing_b", 0, 10, text_hash)


def test_linkflow_strict_schema_is_typed_and_provider_safe() -> None:
    schema = _semantic_claim_schema()

    assert schema["type"] == "object"
    assert schema["additionalProperties"] is False
    assert set(schema["properties"]) == {
        "actor_claims",
        "event_claims",
        "bid_claims",
        "participation_count_claims",
        "actor_relation_claims",
    }
    assert "coverage_results" not in schema["properties"]
    assert schema["required"] == list(schema["properties"].keys())
    actor_item = schema["properties"]["actor_claims"]["items"]
    assert actor_item["additionalProperties"] is False
    assert "actor_label" in actor_item["properties"]

    unsupported = {
        "$defs",
        "allOf",
        "anyOf",
        "default",
        "examples",
        "format",
        "maximum",
        "maxLength",
        "minimum",
        "minItems",
        "minLength",
        "pattern",
        "title",
        "oneOf",
    }
    stack = [schema]
    while stack:
        node = stack.pop()
        if isinstance(node, dict):
            assert unsupported.isdisjoint(node)
            assert not isinstance(node.get("additionalProperties"), dict)
            stack.extend(node.values())
        elif isinstance(node, list):
            stack.extend(node)


def test_linkflow_payload_validation_error_is_sanitized_and_actionable() -> None:
    bad_payload = json.dumps(
        {
            "actor_claims": [
                {
                    "actor_label": "Party A",
                    "actor_kind": "organization",
                    "observability": "named",
                    "confidence": "high",
                    "quote_text": "Party A",
                }
            ],
            "event_claims": [],
            "bid_claims": [],
            "participation_count_claims": [],
            "actor_relation_claims": [],
        }
    )

    try:
        _parse_payload(bad_payload)
    except Exception as exc:
        message = str(exc)
    else:
        raise AssertionError("expected validation failure")

    assert "actor_claims.0.claim_type" in message
    assert "Party A" not in message


def test_new_actor_relation_labels_insert_reconcile_validate_and_canonicalize(tmp_path: Path) -> None:
    conn = connect(":memory:")
    init_schema(conn)
    source_path = _insert_relation_label_filing(conn, tmp_path)

    build_evidence_map(conn, filing_id="relation-label-deal_filing_1", run_id=RUN_ID)
    window = build_llm_windows(conn, filing_id="relation-label-deal_filing_1")[0]
    insert_llm_response(conn, window, _relation_label_response(window), run_id=RUN_ID)

    dispose_claims_for_filing(conn, filing_id="relation-label-deal_filing_1", run_id=RUN_ID)
    finalize_coverage_after_disposition(
        conn, run_id=RUN_ID, filing_id="relation-label-deal_filing_1"
    )
    reconcile_all(conn, run_id=RUN_ID)
    validation = validate_database(conn, raw_source_root=source_path.parent)

    assert validation.passed, validation.system_failures
    relation_rows = conn.execute(
        """
        SELECT relation_type
        FROM actor_relations
        ORDER BY relation_type
        """
    ).fetchall()
    assert relation_rows == [
        ("advises",),
        ("advises",),
        ("committee_member_of",),
        ("recused_from",),
        ("rollover_holder_for",),
        ("voting_support_for",),
    ]
    dispositions = conn.execute(
        """
        SELECT disposition, reason_code
        FROM claim_dispositions
        JOIN claims USING (claim_id)
        WHERE claims.claim_type = 'actor_relation'
        ORDER BY claim_id
        """
    ).fetchall()
    assert dispositions == [
        ("supported", "actor_relation_canonicalized"),
        ("supported", "actor_relation_canonicalized"),
        ("supported", "actor_relation_canonicalized"),
        ("supported", "actor_relation_canonicalized"),
        ("supported", "actor_relation_canonicalized"),
        ("supported", "actor_relation_canonicalized"),
    ]


def test_old_rollover_holder_relation_is_rejected() -> None:
    old_relation = "rollover_holder" + "_of"
    try:
        ActorRelationClaimPayload(
            coverage_obligation_id="obl_relation_1",
            claim_type="actor_relation",
            subject_label="Holder",
            object_label="Parent",
            relation_type=old_relation,
            role_detail=None,
            effective_date_first=None,
            confidence="high",
            quote_text="Holder rolled equity into Parent.",
        )
    except Exception as exc:
        assert old_relation in str(exc)
    else:
        raise AssertionError("old rollover holder relation must be rejected")


def test_llm_prompt_forbids_empty_string_dates(tmp_path: Path) -> None:
    conn = connect(":memory:")
    init_schema(conn)
    _insert_filing(conn, tmp_path)
    build_evidence_map(conn, filing_id="smoke-deal_filing_1", run_id=RUN_ID)
    window = build_llm_windows(conn, filing_id="smoke-deal_filing_1")[0]

    prompt = build_window_prompt(window)

    assert "otherwise return null" in prompt
    assert "Never return an empty string for a date" in prompt


def test_evidence_map_does_not_merge_repeated_headings_across_other_sections() -> None:
    conn = connect(":memory:")
    init_schema(conn)
    filing_id = _insert_sectioned_filing(
        conn,
        [
            ("unknown_section", "Cover."),
            ("Background of the Merger", "The Company contacted bidders."),
            ("Background of the Merger", "The Board reviewed a final proposal."),
            ("Reasons for the Merger", "The board considered fairness."),
            ("Background of the Merger", "The parties granted exclusivity."),
        ],
    )

    region_ids = build_evidence_map(conn, filing_id=filing_id, run_id=RUN_ID)

    rows = conn.execute(
        """
        SELECT paragraph_ids_json
        FROM evidence_regions
        WHERE filing_id = ?
        ORDER BY priority
        """,
        [filing_id],
    ).fetchall()
    paragraph_groups = [json.loads(row[0]) for row in rows]
    assert ["sectioned-deal_para_2", "sectioned-deal_para_3"] in paragraph_groups
    assert ["sectioned-deal_para_5"] in paragraph_groups
    assert [
        "sectioned-deal_para_2",
        "sectioned-deal_para_3",
        "sectioned-deal_para_5",
    ] not in paragraph_groups
    assert len(region_ids) == len(paragraph_groups)


def test_evidence_map_fails_loudly_without_background_section() -> None:
    conn = connect(":memory:")
    init_schema(conn)
    filing_id = _insert_sectioned_filing(conn, [("unknown_section", "No sale-process section here.")])

    try:
        build_evidence_map(conn, filing_id=filing_id, run_id=RUN_ID)
    except ValueError as exc:
        assert "sale-process" in str(exc)
        assert "Background of the Merger" in str(exc)
    else:
        raise AssertionError("expected missing sale-process section to fail loudly")


def _insert_filing(conn, tmp_path: Path) -> Path:
    text = (
        "Background of the Merger\n\n"
        "On January 1, 2020, Party A submitted a final proposal of $10.00 per share. "
        "The Company contacted 10 financial buyers. "
        "Parent was an acquisition vehicle of Buyer Group. "
        "The parties executed the merger agreement on January 5, 2020.\n"
    )
    source_path = tmp_path / "smoke-deal.md"
    source_path.write_text(text, encoding="utf-8")
    filing = CleanFiling(
        filing_id=make_id("smoke-deal", "filing", 1),
        deal_slug="smoke-deal",
        source_path=str(source_path),
        raw_sha256=quote_hash(text),
        parser_version=1,
        page_count=None,
        section_count=1,
        process_scope="target_full_proxy",
    )
    paragraph_text = text
    paragraph = Paragraph(
        paragraph_id=make_id("smoke-deal", "para", 1),
        filing_id=filing.filing_id,
        section="Background of the Merger",
        page_hint=None,
        char_start=0,
        char_end=len(paragraph_text),
        paragraph_text=paragraph_text,
        paragraph_hash=quote_hash(paragraph_text),
    )
    text_hash = quote_hash(paragraph_text)
    span = SourceSpan(
        evidence_id=make_id("smoke-deal", "evidence", 1),
        filing_id=filing.filing_id,
        paragraph_id=paragraph.paragraph_id,
        span_basis="raw_md",
        span_kind="paragraph_seed",
        parent_evidence_id=None,
        created_by_stage="ingest",
        char_start=0,
        char_end=len(paragraph_text),
        quote_text=paragraph_text,
        quote_text_hash=text_hash,
        evidence_fingerprint=evidence_fingerprint(filing.filing_id, 0, len(paragraph_text), text_hash),
    )
    conn.execute("INSERT INTO filings VALUES (?, ?, ?, ?, ?, ?, ?, ?)", tuple(filing.model_dump().values()))
    conn.execute("INSERT INTO paragraphs VALUES (?, ?, ?, ?, ?, ?, ?, ?)", tuple(paragraph.model_dump().values()))
    conn.execute("INSERT INTO spans VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", tuple(span.model_dump().values()))
    return source_path


def _insert_generic_bidder_filing(conn, tmp_path: Path) -> Path:
    text = (
        "Background of the Merger\n\n"
        "On January 1, 2020, Party A submitted a final proposal of $10.00 per share. "
        "On January 2, 2020, five parties submitted preliminary proposals. "
        "On January 3, 2020, six of the potentially interested parties submitted revised bids. "
        "Potential bidders were asked to improve proposals. "
        "The parties executed the merger agreement on January 5, 2020.\n"
    )
    source_path = tmp_path / "generic-bidder-deal.md"
    source_path.write_text(text, encoding="utf-8")
    filing = CleanFiling(
        filing_id=make_id("generic-bidder-deal", "filing", 1),
        deal_slug="generic-bidder-deal",
        source_path=str(source_path),
        raw_sha256=quote_hash(text),
        parser_version=1,
        page_count=None,
        section_count=1,
        process_scope="target_full_proxy",
    )
    paragraph = Paragraph(
        paragraph_id=make_id("generic-bidder-deal", "para", 1),
        filing_id=filing.filing_id,
        section="Background of the Merger",
        page_hint=None,
        char_start=0,
        char_end=len(text),
        paragraph_text=text,
        paragraph_hash=quote_hash(text),
    )
    text_hash = quote_hash(text)
    span = SourceSpan(
        evidence_id=make_id("generic-bidder-deal", "evidence", 1),
        filing_id=filing.filing_id,
        paragraph_id=paragraph.paragraph_id,
        span_basis="raw_md",
        span_kind="paragraph_seed",
        parent_evidence_id=None,
        created_by_stage="ingest",
        char_start=0,
        char_end=len(text),
        quote_text=text,
        quote_text_hash=text_hash,
        evidence_fingerprint=evidence_fingerprint(filing.filing_id, 0, len(text), text_hash),
    )
    conn.execute("INSERT INTO filings VALUES (?, ?, ?, ?, ?, ?, ?, ?)", tuple(filing.model_dump().values()))
    conn.execute("INSERT INTO paragraphs VALUES (?, ?, ?, ?, ?, ?, ?, ?)", tuple(paragraph.model_dump().values()))
    conn.execute("INSERT INTO spans VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", tuple(span.model_dump().values()))
    return source_path


def _insert_relation_label_filing(conn, tmp_path: Path) -> Path:
    text = (
        "Background of the Merger\n\n"
        "On January 1, 2020, Party A submitted a final proposal of $10.00 per share. "
        "The parties executed the merger agreement on January 5, 2020. "
        "Shareholder A entered into a voting agreement in support of Parent. "
        "Rollover Holder agreed to rollover equity into Parent. "
        "Director B was appointed to the special committee. "
        "Director C recused himself from the Board's evaluation. "
        "Evercore served as financial advisor to the Company. "
        "Kirkland served as legal advisor to the Company.\n"
    )
    source_path = tmp_path / "relation-label-deal.md"
    source_path.write_text(text, encoding="utf-8")
    filing = CleanFiling(
        filing_id=make_id("relation-label-deal", "filing", 1),
        deal_slug="relation-label-deal",
        source_path=str(source_path),
        raw_sha256=quote_hash(text),
        parser_version=1,
        page_count=None,
        section_count=1,
        process_scope="target_full_proxy",
    )
    paragraph = Paragraph(
        paragraph_id=make_id("relation-label-deal", "para", 1),
        filing_id=filing.filing_id,
        section="Background of the Merger",
        page_hint=None,
        char_start=0,
        char_end=len(text),
        paragraph_text=text,
        paragraph_hash=quote_hash(text),
    )
    text_hash = quote_hash(text)
    span = SourceSpan(
        evidence_id=make_id("relation-label-deal", "evidence", 1),
        filing_id=filing.filing_id,
        paragraph_id=paragraph.paragraph_id,
        span_basis="raw_md",
        span_kind="paragraph_seed",
        parent_evidence_id=None,
        created_by_stage="ingest",
        char_start=0,
        char_end=len(text),
        quote_text=text,
        quote_text_hash=text_hash,
        evidence_fingerprint=evidence_fingerprint(filing.filing_id, 0, len(text), text_hash),
    )
    conn.execute("INSERT INTO filings VALUES (?, ?, ?, ?, ?, ?, ?, ?)", tuple(filing.model_dump().values()))
    conn.execute("INSERT INTO paragraphs VALUES (?, ?, ?, ?, ?, ?, ?, ?)", tuple(paragraph.model_dump().values()))
    conn.execute("INSERT INTO spans VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", tuple(span.model_dump().values()))
    return source_path


def _insert_projection_leak_candidate(conn) -> None:
    deal_id, cycle_id = conn.execute(
        """
        SELECT deals.deal_id, process_cycles.cycle_id
        FROM deals
        JOIN process_cycles USING (deal_id)
        WHERE deals.deal_slug = ?
        """,
        ["generic-bidder-deal"],
    ).fetchone()
    evidence_id = conn.execute("SELECT evidence_id FROM claim_evidence ORDER BY claim_id LIMIT 1").fetchone()[0]
    actor_id = make_id("generic-bidder-deal", "actor", 90)
    event_id = make_id("generic-bidder-deal", "event", 90)
    link_id = make_id("generic-bidder-deal", "link", 90)
    conn.execute(
        "INSERT INTO actors VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [actor_id, RUN_ID, deal_id, "potential bidders", "organization", "named", None, None, None, None],
    )
    conn.execute(
        "INSERT INTO events VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [event_id, RUN_ID, deal_id, cycle_id, "bid", "first_round_bid", None, "generic cohort bid leak", None, None, None, None, None],
    )
    conn.execute("INSERT INTO event_actor_links VALUES (?, ?, ?, ?, ?, ?)", [link_id, RUN_ID, event_id, actor_id, "bid_submitter", None])
    conn.execute("INSERT INTO row_evidence VALUES (?, ?, ?, ?)", ["actors", actor_id, evidence_id, 1])
    conn.execute("INSERT INTO row_evidence VALUES (?, ?, ?, ?)", ["events", event_id, evidence_id, 1])
    conn.execute("INSERT INTO row_evidence VALUES (?, ?, ?, ?)", ["event_actor_links", link_id, evidence_id, 1])


def _insert_sectioned_filing(conn, sectioned_texts: list[tuple[str, str]]) -> str:
    slug = "sectioned-deal"
    filing_id = make_id(slug, "filing", 1)
    full_text = "\n\n".join(text for _, text in sectioned_texts)
    filing = CleanFiling(
        filing_id=filing_id,
        deal_slug=slug,
        source_path="sectioned-deal.md",
        raw_sha256=quote_hash(full_text),
        parser_version=1,
        page_count=None,
        section_count=len({section for section, _ in sectioned_texts if section != "unknown_section"}),
        process_scope="target_full_proxy",
    )
    conn.execute("INSERT INTO filings VALUES (?, ?, ?, ?, ?, ?, ?, ?)", tuple(filing.model_dump().values()))
    cursor = 0
    for sequence, (section, text) in enumerate(sectioned_texts, start=1):
        char_start = cursor
        char_end = char_start + len(text)
        paragraph = Paragraph(
            paragraph_id=make_id(slug, "para", sequence),
            filing_id=filing_id,
            section=section,
            page_hint=None,
            char_start=char_start,
            char_end=char_end,
            paragraph_text=text,
            paragraph_hash=quote_hash(text),
        )
        text_hash = quote_hash(text)
        span = SourceSpan(
            evidence_id=make_id(slug, "evidence", sequence),
            filing_id=filing_id,
            paragraph_id=paragraph.paragraph_id,
            span_basis="raw_md",
            span_kind="paragraph_seed",
            parent_evidence_id=None,
            created_by_stage="ingest",
            char_start=char_start,
            char_end=char_end,
            quote_text=text,
            quote_text_hash=text_hash,
            evidence_fingerprint=evidence_fingerprint(filing_id, char_start, char_end, text_hash),
        )
        conn.execute("INSERT INTO paragraphs VALUES (?, ?, ?, ?, ?, ?, ?, ?)", tuple(paragraph.model_dump().values()))
        conn.execute("INSERT INTO spans VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", tuple(span.model_dump().values()))
        cursor = char_end + 2
    return filing_id


def _response_for_window(window) -> LLMExtractionResponse:
    payload = SemanticClaimsPayload(
        actor_claims=[
            _actor_claim_for_obligation(obligation)
            for obligation in window.coverage_obligations
            if obligation.expected_claim_type == "actor"
        ],
        event_claims=[
            _event_claim_for_obligation(obligation)
            for obligation in window.coverage_obligations
            if obligation.expected_claim_type == "event"
        ],
        bid_claims=[
            _bid_claim_for_obligation(obligation)
            for obligation in window.coverage_obligations
            if obligation.expected_claim_type == "bid"
        ],
        participation_count_claims=[
            _participation_count_claim_for_obligation(obligation)
            for obligation in window.coverage_obligations
            if obligation.expected_claim_type == "participation_count"
        ],
        actor_relation_claims=[
            _buyer_group_relation_claim_for_obligation(obligation)
            for obligation in window.coverage_obligations
            if obligation.expected_claim_type == "actor_relation"
        ],
    )
    return LLMExtractionResponse(
        request_id=window.request_id,
        provider_name="linkflow",
        provider_model="gpt-5.5",
        reasoning_effort="medium",
        payload=payload,
        raw_response_sha256=quote_hash(json.dumps(payload.model_dump(mode="json"), sort_keys=True)),
        finish_status="completed",
    )


def _relation_label_response(window) -> LLMExtractionResponse:
    payload = SemanticClaimsPayload(
        actor_claims=[
            _actor_claim_for_obligation(obligation)
            for obligation in window.coverage_obligations
            if obligation.expected_claim_type == "actor"
        ],
        event_claims=[
            _event_claim_for_obligation(obligation)
            for obligation in window.coverage_obligations
            if obligation.expected_claim_type == "event"
        ],
        bid_claims=[
            _bid_claim_for_obligation(obligation)
            for obligation in window.coverage_obligations
            if obligation.expected_claim_type == "bid"
        ],
        actor_relation_claims=[
            ActorRelationClaimPayload(
                coverage_obligation_id=_obligation_id_by_label(window, "Voting support agreement"),
                claim_type="actor_relation",
                subject_label="Shareholder A",
                object_label="Parent",
                relation_type="voting_support_for",
                role_detail="voting agreement",
                effective_date_first=None,
                confidence="high",
                quote_text="Shareholder A entered into a voting agreement in support of Parent",
            ),
            ActorRelationClaimPayload(
                coverage_obligation_id=_obligation_id_by_label(window, "Rollover holder"),
                claim_type="actor_relation",
                subject_label="Rollover Holder",
                object_label="Parent",
                relation_type="rollover_holder_for",
                role_detail="rollover equity",
                effective_date_first=None,
                confidence="high",
                quote_text="Rollover Holder agreed to rollover equity into Parent",
            ),
            ActorRelationClaimPayload(
                coverage_obligation_id=_obligation_id_by_label(window, "Special committee membership"),
                claim_type="actor_relation",
                subject_label="Director B",
                object_label="special committee",
                relation_type="committee_member_of",
                role_detail="appointed",
                effective_date_first=None,
                confidence="high",
                quote_text="Director B was appointed to the special committee",
            ),
            ActorRelationClaimPayload(
                coverage_obligation_id=_obligation_id_by_label(window, "Recusal from sale process"),
                claim_type="actor_relation",
                subject_label="Director C",
                object_label="Board's evaluation",
                relation_type="recused_from",
                role_detail="recused",
                effective_date_first=None,
                confidence="high",
                quote_text="Director C recused himself from the Board's evaluation",
            ),
            ActorRelationClaimPayload(
                coverage_obligation_id=_obligation_id_by_label(window, "Financial advisor for target"),
                claim_type="actor_relation",
                subject_label="Evercore",
                object_label="Company",
                relation_type="advises",
                role_detail="financial advisor",
                effective_date_first=None,
                confidence="high",
                quote_text="Evercore served as financial advisor to the Company",
            ),
            ActorRelationClaimPayload(
                coverage_obligation_id=_obligation_id_by_label(window, "Legal advisor for target"),
                claim_type="actor_relation",
                subject_label="Kirkland",
                object_label="Company",
                relation_type="advises",
                role_detail="legal advisor",
                effective_date_first=None,
                confidence="high",
                quote_text="Kirkland served as legal advisor to the Company",
            ),
        ],
    )
    return LLMExtractionResponse(
        request_id=window.request_id,
        provider_name="linkflow",
        provider_model="gpt-5.5",
        reasoning_effort="medium",
        payload=payload,
        raw_response_sha256=quote_hash(json.dumps(payload.model_dump(mode="json"), sort_keys=True)),
        finish_status="completed",
    )


def _generic_bidder_response(window) -> LLMExtractionResponse:
    event_obligation_id = _first_obligation_id(window, "event")
    bid_obligation_id = _first_obligation_id(window, "bid")
    count_obligation_id = _first_obligation_id(window, "participation_count")
    payload = SemanticClaimsPayload(
        actor_claims=[],
        event_claims=[
            EventClaimPayload(
                coverage_obligation_id=event_obligation_id,
                claim_type="event",
                event_type="transaction",
                event_subtype="merger_agreement_executed",
                event_date="2020-01-05",
                description="The parties executed the merger agreement.",
                actor_label="Party A",
                actor_role="bid_submitter",
                confidence="high",
                quote_text="executed the merger agreement on January 5, 2020",
            )
        ],
        bid_claims=[
            BidClaimPayload(
                coverage_obligation_id=bid_obligation_id,
                claim_type="bid",
                bidder_label="Party A",
                bid_date="2020-01-01",
                bid_value=10.0,
                bid_value_lower=None,
                bid_value_upper=None,
                bid_value_unit="per_share",
                consideration_type="cash",
                bid_stage="final",
                confidence="high",
                quote_text="On January 1, 2020, Party A submitted a final proposal of $10.00 per share",
            ),
            BidClaimPayload(
                coverage_obligation_id=bid_obligation_id,
                claim_type="bid",
                bidder_label="five parties",
                bid_date="2020-01-02",
                bid_value=None,
                bid_value_lower=None,
                bid_value_upper=None,
                bid_value_unit=None,
                consideration_type=None,
                bid_stage="initial",
                confidence="high",
                quote_text="On January 2, 2020, five parties submitted preliminary proposals",
            ),
            BidClaimPayload(
                coverage_obligation_id=bid_obligation_id,
                claim_type="bid",
                bidder_label="six of the potentially interested parties",
                bid_date="2020-01-03",
                bid_value=None,
                bid_value_lower=None,
                bid_value_upper=None,
                bid_value_unit=None,
                consideration_type=None,
                bid_stage="revised",
                confidence="high",
                quote_text="On January 3, 2020, six of the potentially interested parties submitted revised bids",
            ),
            BidClaimPayload(
                coverage_obligation_id=bid_obligation_id,
                claim_type="bid",
                bidder_label="potential bidders",
                bid_date=None,
                bid_value=None,
                bid_value_lower=None,
                bid_value_upper=None,
                bid_value_unit=None,
                consideration_type=None,
                bid_stage="unspecified",
                confidence="medium",
                quote_text="Potential bidders were asked to improve proposals",
            ),
        ],
        participation_count_claims=[
            ParticipationCountClaimPayload(
                coverage_obligation_id=count_obligation_id,
                claim_type="participation_count",
                process_stage="first_round",
                actor_class="mixed",
                count_min=5,
                count_max=None,
                count_qualifier="exact",
                confidence="high",
                quote_text="five parties submitted preliminary proposals",
            ),
            ParticipationCountClaimPayload(
                coverage_obligation_id=count_obligation_id,
                claim_type="participation_count",
                process_stage="ioi_submitted",
                actor_class="financial",
                count_min=6,
                count_max=None,
                count_qualifier="exact",
                confidence="high",
                quote_text="six of the potentially interested parties submitted revised bids",
            ),
        ],
        actor_relation_claims=[],
    )
    return LLMExtractionResponse(
        request_id=window.request_id,
        provider_name="linkflow",
        provider_model="gpt-5.5",
        reasoning_effort="medium",
        payload=payload,
        raw_response_sha256=quote_hash(json.dumps(payload.model_dump(mode="json"), sort_keys=True)),
        finish_status="completed",
    )


def _first_obligation_id(window, claim_type: str) -> str:
    for obligation in window.coverage_obligations:
        if obligation.expected_claim_type == claim_type:
            return obligation.obligation_id
    raise AssertionError(f"window has no {claim_type} obligation")


def _obligation_id_by_label(window, label: str) -> str:
    for obligation in window.coverage_obligations:
        if obligation.obligation_label == label:
            return obligation.obligation_id
    raise AssertionError(f"window has no obligation label {label!r}")


def _actor_claim_for_obligation(obligation) -> ActorClaimPayload:
    return ActorClaimPayload(
        coverage_obligation_id=obligation.obligation_id,
        claim_type="actor",
        actor_label="Party A",
        actor_kind="organization",
        observability="named",
        confidence="high",
        quote_text="Party A submitted a final proposal",
    )


def _event_claim_for_obligation(obligation) -> EventClaimPayload:
    if obligation.obligation_label == "Final approval or signing event":
        return EventClaimPayload(
            coverage_obligation_id=obligation.obligation_id,
            claim_type="event",
            event_type="transaction",
            event_subtype="merger_agreement_executed",
            event_date="2020-01-05",
            description="The parties executed the merger agreement.",
            actor_label="Party A",
            actor_role="bid_submitter",
            confidence="high",
            quote_text="executed the merger agreement on January 5, 2020",
        )
    return EventClaimPayload(
        coverage_obligation_id=obligation.obligation_id,
        claim_type="event",
        event_type="process",
        event_subtype="contact_initial",
        event_date="2020-01-01",
        description="Party A submitted a final proposal.",
        actor_label="Party A",
        actor_role="bid_submitter",
        confidence="high",
        quote_text="Party A submitted a final proposal",
    )


def _bid_claim_for_obligation(obligation) -> BidClaimPayload:
    return BidClaimPayload(
        coverage_obligation_id=obligation.obligation_id,
        claim_type="bid",
        bidder_label="Party A",
        bid_date="2020-01-01",
        bid_value=10.0,
        bid_value_lower=None,
        bid_value_upper=None,
        bid_value_unit="per_share",
        consideration_type="cash",
        bid_stage="final",
        confidence="high",
        quote_text="On January 1, 2020, Party A submitted a final proposal of $10.00 per share",
    )


def _participation_count_claim_for_obligation(obligation) -> ParticipationCountClaimPayload:
    return ParticipationCountClaimPayload(
        coverage_obligation_id=obligation.obligation_id,
        claim_type="participation_count",
        process_stage="contacted",
        actor_class="financial",
        count_min=10,
        count_max=None,
        count_qualifier="exact",
        confidence="high",
        quote_text="contacted 10 financial buyers",
    )


def _buyer_group_relation_claim_for_obligation(obligation) -> ActorRelationClaimPayload:
    return ActorRelationClaimPayload(
        coverage_obligation_id=obligation.obligation_id,
        claim_type="actor_relation",
        subject_label="Parent",
        object_label="Buyer Group",
        relation_type="acquisition_vehicle_of",
        role_detail="acquisition vehicle",
        effective_date_first=None,
        confidence="high",
        quote_text="Parent was an acquisition vehicle of Buyer Group",
    )
