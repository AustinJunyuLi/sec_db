import json
from pathlib import Path

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

    reconcile_all(conn, run_id=RUN_ID)
    validation = validate_database(conn, raw_source_root=source_path.parent)
    assert validation.passed, validation.hard_failures

    proof = write_projection_outputs(
        conn,
        tmp_path / "run",
        run_id=RUN_ID,
        projection_name="bidder_cycle_baseline_v1",
    )
    run_dir = tmp_path / "run"

    assert proof["row_counts"]["claims"] >= 5
    assert proof["row_counts"]["claim_dispositions"] == proof["row_counts"]["claims"]
    assert proof["row_counts"]["coverage_results"] == proof["row_counts"]["coverage_obligations"]
    assert proof["row_counts"]["actor_relations"] >= 1
    assert proof["row_counts"]["participation_counts"] >= 1
    assert proof["row_counts"]["bidder_rows"] >= 1
    assert proof["canonical_rows_without_relational_evidence"] == 0
    assert proof["verdict"] in {"SOUND", "SUSPECT"}
    assert (run_dir / "cost_runtime_summary.json").exists()
    assert (run_dir / "cost_runtime_summary.csv").exists()
    assert (run_dir / "provider_usage_ledger.jsonl").exists()
    assert (run_dir / "latency_ledger.jsonl").exists()


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
        "coverage_results",
    }
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
            "coverage_results": [],
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


def test_llm_prompt_forbids_empty_string_dates(tmp_path: Path) -> None:
    conn = connect(":memory:")
    init_schema(conn)
    _insert_filing(conn, tmp_path)
    build_evidence_map(conn, filing_id="smoke-deal_filing_1", run_id=RUN_ID)
    window = build_llm_windows(conn, filing_id="smoke-deal_filing_1")[0]

    prompt = build_window_prompt(window)

    assert "otherwise return null" in prompt
    assert "Never return an empty string for a date" in prompt


def test_evidence_map_builds_one_full_background_sale_process_region() -> None:
    conn = connect(":memory:")
    init_schema(conn)
    filing_id = _insert_sectioned_filing(
        conn,
        [
            ("preamble", "Introductory proxy material."),
            ("Background of the Merger", "The board began a sale process."),
            ("Background of the Merger", "The Company contacted bidders."),
            ("Reasons for the Merger", "The board considered fairness."),
            ("Background of the Merger", "The parties granted exclusivity."),
        ],
    )

    region_ids = build_evidence_map(conn, filing_id=filing_id, run_id=RUN_ID)

    assert len(region_ids) == 1
    region = conn.execute(
        """
        SELECT region_kind, priority, start_paragraph_id, end_paragraph_id,
               paragraph_ids_json, expected_claim_types_json
        FROM evidence_regions
        WHERE filing_id = ?
        """,
        [filing_id],
    ).fetchone()
    assert region[:4] == ("sale_process_narrative", 1, "sectioned-deal_para_2", "sectioned-deal_para_5")
    assert json.loads(region[4]) == [
        "sectioned-deal_para_2",
        "sectioned-deal_para_3",
        "sectioned-deal_para_5",
    ]
    assert json.loads(region[5]) == ["event", "participation_count", "actor", "bid", "actor_relation"]

    obligations = conn.execute(
        """
        SELECT expected_claim_type, obligation_label, importance
        FROM coverage_obligations
        WHERE filing_id = ?
        ORDER BY CAST(regexp_extract(obligation_id, '_(\\d+)$', 1) AS INTEGER)
        """,
        [filing_id],
    ).fetchall()
    assert obligations == [
        ("event", "Sales process initiation", "required"),
        ("participation_count", "Bidder count at IOI stage", "required"),
        ("participation_count", "Bidder count at first round", "important"),
        ("event", "Final round bid receipt", "required"),
        ("event", "Exclusivity grant", "required"),
        ("actor", "Target board", "required"),
        ("actor", "Financial advisor for target", "required"),
        ("actor", "Legal advisor for target", "required"),
        ("bid", "Final bid price", "required"),
        ("actor_relation", "Buyer group composition", "important"),
    ]
    window = build_llm_windows(conn, filing_id=filing_id)[0]
    assert [obligation.obligation_label for obligation in window.coverage_obligations] == [
        label for _claim_type, label, _importance in obligations
    ]


def test_evidence_map_fails_loudly_without_background_section() -> None:
    conn = connect(":memory:")
    init_schema(conn)
    filing_id = _insert_sectioned_filing(conn, [("unknown_section", "No sale-process section here.")])

    try:
        build_evidence_map(conn, filing_id=filing_id, run_id=RUN_ID)
    except ValueError as exc:
        assert "Background of the Merger" in str(exc)
    else:
        raise AssertionError("expected missing Background section to fail loudly")


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
    allowed = set(window.allowed_claim_types)
    payload = SemanticClaimsPayload(
        actor_claims=[
            ActorClaimPayload(
                claim_type="actor",
                actor_label="Party A",
                actor_kind="organization",
                observability="named",
                confidence="high",
                quote_text="Party A submitted a final proposal",
            )
        ]
        if "actor" in allowed
        else [],
        event_claims=[
            EventClaimPayload(
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
        ]
        if "event" in allowed
        else [],
        bid_claims=[
            BidClaimPayload(
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
                quote_text="$10.00 per share",
            )
        ]
        if "bid" in allowed
        else [],
        participation_count_claims=[
            ParticipationCountClaimPayload(
                claim_type="participation_count",
                process_stage="contacted",
                actor_class="financial",
                count_min=10,
                count_max=None,
                count_qualifier="exact",
                confidence="high",
                quote_text="contacted 10 financial buyers",
            )
        ]
        if "participation_count" in allowed
        else [],
        actor_relation_claims=[
            ActorRelationClaimPayload(
                claim_type="actor_relation",
                subject_label="Parent",
                object_label="Buyer Group",
                relation_type="acquisition_vehicle_of",
                role_detail="acquisition vehicle",
                effective_date_first=None,
                confidence="high",
                quote_text="Parent was an acquisition vehicle of Buyer Group",
            )
        ]
        if "actor_relation" in allowed
        else [],
    )
    return LLMExtractionResponse(
        request_id=window.request_id,
        provider_name="linkflow",
        provider_model="gpt-5.5",
        reasoning_effort="high",
        payload=payload,
        raw_response_sha256=quote_hash(json.dumps(payload.model_dump(mode="json"), sort_keys=True)),
        finish_status="completed",
    )
