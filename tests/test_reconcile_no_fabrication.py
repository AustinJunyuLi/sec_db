"""Reconcile and projection contract: no fabricated admissions, counts, or judgment deletes."""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import pytest

from sec_graph.extract.rules import run_rules
from sec_graph.ingest.pipeline import ingest_examples
from sec_graph.project.bidder_rows import bidder_rows
from sec_graph.reconcile.pipeline import ReconcileError, reconcile_all, reconcile_filing
from sec_graph.schema import (
    CleanFiling,
    ExtractionCandidate,
    Judgment,
    Paragraph,
    SourceSpan,
    connect,
    init_schema,
    make_id,
    quote_hash,
)
from sec_graph.schema import versions


def _insert_filing(conn, filing: CleanFiling) -> None:
    conn.execute(
        "INSERT INTO filings VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        tuple(filing.model_dump().values()),
    )


def _insert_paragraph(conn, paragraph: Paragraph) -> None:
    conn.execute(
        "INSERT INTO paragraphs VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        tuple(paragraph.model_dump().values()),
    )


def _insert_span(conn, span: SourceSpan) -> None:
    conn.execute(
        "INSERT INTO spans VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        tuple(span.model_dump().values()),
    )


def _insert_candidate(conn, candidate: ExtractionCandidate) -> None:
    conn.execute(
        "INSERT INTO candidates VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        tuple(candidate.model_dump().values()),
    )


def _insert_judgment(conn, judgment: Judgment) -> None:
    payload = judgment.model_dump(mode="json")
    conn.execute(
        "INSERT INTO judgments VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        tuple(payload.values()),
    )


def _build_synthetic_filing(
    conn,
    *,
    slug: str,
    paragraphs: list[str],
) -> tuple[CleanFiling, list[Paragraph], list[SourceSpan]]:
    """Insert one filing with N paragraphs joined by blank lines and return the records."""
    text = "\n\n".join(paragraphs) + "\n"
    filing = CleanFiling(
        filing_id=make_id(slug, "filing", 1),
        deal_slug=slug,
        source_path=f"tests/synthetic/{slug}.md",
        raw_sha256=quote_hash(text),
        parser_version=versions.PARSER_VERSION,
        page_count=None,
        section_count=1,
        process_scope="target_full_proxy",
    )
    _insert_filing(conn, filing)
    paragraph_records: list[Paragraph] = []
    span_records: list[SourceSpan] = []
    cursor = 0
    for index, body in enumerate(paragraphs, start=1):
        start = text.index(body, cursor)
        end = start + len(body)
        cursor = end
        paragraph = Paragraph(
            paragraph_id=make_id(slug, "para", index),
            filing_id=filing.filing_id,
            section="Background of the Merger",
            page_hint=None,
            char_start=start,
            char_end=end,
            paragraph_text=body,
            paragraph_hash=quote_hash(body),
        )
        span = SourceSpan(
            evidence_id=make_id(slug, "evidence", index),
            filing_id=filing.filing_id,
            paragraph_id=paragraph.paragraph_id,
            span_basis="raw_md",
            span_kind="paragraph_seed",
            parent_evidence_id=None,
            created_by_stage="ingest",
            char_start=start,
            char_end=end,
            quote_text=body,
            quote_hash=quote_hash(body),
        )
        _insert_paragraph(conn, paragraph)
        _insert_span(conn, span)
        paragraph_records.append(paragraph)
        span_records.append(span)
    return filing, paragraph_records, span_records


def _make_dated_event_candidate(
    *,
    slug: str,
    sequence: int,
    filing_id: str,
    raw_value: str,
    iso_date: str,
    evidence_id: str,
) -> ExtractionCandidate:
    return ExtractionCandidate(
        candidate_id=make_id(slug, "candidate", sequence),
        run_id="test-run",
        filing_id=filing_id,
        candidate_type="dated_event",
        raw_value=raw_value,
        normalized_value=iso_date,
        confidence="medium",
        evidence_ids=[evidence_id],
        dependencies=[],
        status="active",
    )


def _loaded_real_conn():
    conn = connect(":memory:")
    init_schema(conn)
    filings = ingest_examples(conn, examples_dir=Path("data/examples"))
    for filing in filings:
        run_rules(conn, filing_id=filing.filing_id)
    return conn


# ----------------------------------------------------------------------
# Test 1: boundary event subtype must come from evidence-supported text
# ----------------------------------------------------------------------


def test_boundary_event_subtype_must_come_from_evidence_not_cycle_boundary_selection() -> None:
    """A dated event that says 'submitted a written proposal' must not become advancement_admitted.

    The reconcile boundary picker must classify the subtype from the source quote.
    A non-admissive proposal cannot be promoted to advancement_admitted simply
    because it sits at the boundary of a cycle window.
    """
    conn = connect(":memory:")
    init_schema(conn)
    slug = "syntheticproposal"
    filing, _, spans = _build_synthetic_filing(
        conn,
        slug=slug,
        paragraphs=[
            "On January 5, 2020, Party A submitted a written proposal of $40.00 per share to PetSmart.",
            "On February 10, 2020, Party A submitted a revised written proposal of $42.00 per share.",
        ],
    )
    _insert_candidate(
        conn,
        _make_dated_event_candidate(
            slug=slug,
            sequence=1,
            filing_id=filing.filing_id,
            raw_value="On January 5, 2020, Party A submitted a written proposal of $40.00 per share to PetSmart.",
            iso_date="2020-01-05",
            evidence_id=spans[0].evidence_id,
        ),
    )
    _insert_candidate(
        conn,
        _make_dated_event_candidate(
            slug=slug,
            sequence=2,
            filing_id=filing.filing_id,
            raw_value="On February 10, 2020, Party A submitted a revised written proposal of $42.00 per share.",
            iso_date="2020-02-10",
            evidence_id=spans[1].evidence_id,
        ),
    )

    reconcile_filing(conn, filing_id=filing.filing_id, run_id="test-run")

    subtypes = [
        row[0]
        for row in conn.execute(
            "SELECT event_subtype FROM events ORDER BY event_id"
        ).fetchall()
    ]
    assert "advancement_admitted" not in subtypes, (
        "boundary picker fabricated advancement_admitted from a non-admissive proposal: "
        f"subtypes={subtypes}"
    )


# ----------------------------------------------------------------------
# Test 2: post-boundary bid alone does not imply admission
# ----------------------------------------------------------------------


def test_post_boundary_bid_does_not_imply_projection_admission() -> None:
    """A bid landing after the boundary event but with no explicit projection_eligibility
    judgment must NOT yield a projection row marked admitted.

    Projection admission comes from the latest non-superseded
    projection_eligibility judgment, not from the SQL inference 'post-boundary
    proposal exists'.
    """
    conn = _loaded_real_conn()
    reconcile_all(conn, run_id="test-run")

    # Remove the projection_eligibility judgment for one bidder and rebuild only its
    # canonical bid event (preserving the boundary). Strip judgments that would otherwise
    # admit it. Then ensure projection refuses to fabricate admission.
    actor_id = conn.execute(
        """
        SELECT actors.actor_id
        FROM actors
        JOIN deals USING (deal_id)
        WHERE deals.deal_slug = 'petsmart-inc'
          AND actors.actor_label = 'Bidder 2'
        LIMIT 1
        """
    ).fetchone()[0]

    conn.execute(
        """
        DELETE FROM judgments
        WHERE judgment_kind = 'projection_eligibility'
          AND actor_id = ?
        """,
        [actor_id],
    )

    rows = bidder_rows(conn)
    matching = [row for row in rows if row["actor_id"] == actor_id]
    assert all(row["admitted"] is False for row in matching) or matching == [], (
        "projection admitted an actor without a current projection_eligibility judgment: "
        f"actor_id={actor_id} rows={matching}"
    )


# ----------------------------------------------------------------------
# Test 3: participation count preserves actor_class, stage, exact-vs-at-least
# ----------------------------------------------------------------------


def test_participation_count_preserves_actor_class_and_stage_semantics() -> None:
    """Source: 'five financial sponsors and three strategic acquirers expressed interest at the
    early-outreach stage; at least two anonymous parties remained in the second round.'

    Reconcile must produce participation_counts rows whose actor_class, process_stage,
    and exact-vs-at-least semantics derive from the source quote, not from a hardcoded
    'financial / contacted / exact' default.
    """
    conn = connect(":memory:")
    init_schema(conn)
    slug = "syntheticcounts"
    filing, _, spans = _build_synthetic_filing(
        conn,
        slug=slug,
        paragraphs=[
            (
                "On January 5, 2020, the Company commenced outreach. Five financial sponsors "
                "and three strategic acquirers expressed interest at the early-outreach stage."
            ),
            (
                "On April 12, 2020, the Company invited bidders into the next round; at least "
                "two anonymous parties remained in the second round."
            ),
        ],
    )
    # Dated event candidates so cycles can form.
    _insert_candidate(
        conn,
        _make_dated_event_candidate(
            slug=slug,
            sequence=1,
            filing_id=filing.filing_id,
            raw_value="On January 5, 2020, the Company commenced outreach.",
            iso_date="2020-01-05",
            evidence_id=spans[0].evidence_id,
        ),
    )
    _insert_candidate(
        conn,
        _make_dated_event_candidate(
            slug=slug,
            sequence=2,
            filing_id=filing.filing_id,
            raw_value="On April 12, 2020, the Company invited bidders into the next round.",
            iso_date="2020-04-12",
            evidence_id=spans[1].evidence_id,
        ),
    )
    # Participation-count candidates carrying the source language. Each
    # candidate is narrowed to one cohort observation so reconcile can
    # classify actor_class without conflating financial and strategic into
    # `mixed`. The extractor is responsible for emitting one narrow
    # candidate per atomic cohort claim.
    _insert_candidate(
        conn,
        ExtractionCandidate(
            candidate_id=make_id(slug, "candidate", 3),
            run_id="test-run",
            filing_id=filing.filing_id,
            candidate_type="participation_count",
            raw_value="five financial sponsors expressed interest at the early-outreach stage",
            normalized_value="5",
            confidence="high",
            evidence_ids=[spans[0].evidence_id],
            dependencies=[],
            status="active",
        ),
    )
    _insert_candidate(
        conn,
        ExtractionCandidate(
            candidate_id=make_id(slug, "candidate", 4),
            run_id="test-run",
            filing_id=filing.filing_id,
            candidate_type="participation_count",
            raw_value="three strategic acquirers expressed interest at the early-outreach stage",
            normalized_value="3",
            confidence="high",
            evidence_ids=[spans[0].evidence_id],
            dependencies=[],
            status="active",
        ),
    )
    _insert_candidate(
        conn,
        ExtractionCandidate(
            candidate_id=make_id(slug, "candidate", 5),
            run_id="test-run",
            filing_id=filing.filing_id,
            candidate_type="participation_count",
            raw_value="at least two anonymous parties remained in the second round",
            normalized_value="2",
            confidence="medium",
            evidence_ids=[spans[1].evidence_id],
            dependencies=[],
            status="active",
        ),
    )

    reconcile_filing(conn, filing_id=filing.filing_id, run_id="test-run")

    rows = conn.execute(
        """
        SELECT process_stage, actor_class, count_min, count_max, count_qualifier,
               anonymous_remainder_count
        FROM participation_counts
        ORDER BY participation_count_id
        """
    ).fetchall()
    triples = {(row[0], row[1], row[4]) for row in rows}

    assert ("contacted", "financial", "exact") in triples, (
        "expected 5 financial sponsors to land as financial/contacted/exact: " f"got {rows}"
    )
    assert ("contacted", "strategic", "exact") in triples, (
        "expected 3 strategic acquirers to land as strategic/contacted/exact: " f"got {rows}"
    )
    # The 'second round' anonymous remainder must be carried as a lower-bound observation,
    # NOT classified as financial-contacted-exact.
    assert any(
        row[0] in ("first_round", "ioi_submitted")
        and row[4] == "lower_bound"
        and row[5] >= 2
        for row in rows
    ), (
        "expected at-least-two anonymous remainder rendered with lower_bound qualifier "
        f"under a non-contacted stage: got {rows}"
    )

    # No row should treat the strategic-acquirer cohort as financial.
    strategic_rows = [row for row in rows if row[1] == "strategic"]
    assert strategic_rows, "strategic-cohort row missing entirely; reconcile fabricated financial-only rows"
    for stage, actor_class, count_min, count_max, qualifier, anon in strategic_rows:
        assert actor_class == "strategic"
        assert count_min == 3
        assert qualifier == "exact"


# ----------------------------------------------------------------------
# Test 4: reconcile must not delete pre-existing judgments
# ----------------------------------------------------------------------


def test_reconcile_refuses_to_delete_existing_judgments() -> None:
    """Append-only judgments must survive the default reconcile_all() pass.

    Reconcile may rebuild derived canonical tables, but the judgments table is
    append-only — reviewer overrides and prior rows must NOT be silently
    truncated.
    """
    conn = _loaded_real_conn()
    reconcile_all(conn, run_id="first-run")

    # Pick any existing actor for the seeded judgment FK.
    actor_id = conn.execute("SELECT actor_id FROM actors LIMIT 1").fetchone()[0]
    evidence_id = conn.execute("SELECT evidence_id FROM spans LIMIT 1").fetchone()[0]
    seeded = Judgment(
        judgment_id="seeded_reviewer_judgment_1",
        run_id="reviewer-session",
        judgment_kind="projection_eligibility",
        target_table=None,
        target_id=None,
        target_column=None,
        prior_value=None,
        new_value=None,
        projection_name="bidder_cycle_baseline_v1",
        actor_id=actor_id,
        included=False,
        rule_id="bidder_cycle_baseline_v1.admission",
        evidence_ids=[evidence_id],
        supersedes_judgment_id=None,
        created_at="2026-05-02T10:00:00+00:00",
        created_by="reviewer",
    )
    _insert_judgment(conn, seeded)

    # Default reconcile_all() must not destroy the seeded reviewer judgment.
    reconcile_all(conn, run_id="second-run")
    surviving = conn.execute(
        "SELECT count(*) FROM judgments WHERE judgment_id = ?",
        [seeded.judgment_id],
    ).fetchone()[0]
    assert surviving == 1, (
        "reconcile_all() destroyed an append-only reviewer judgment under its default code path"
    )


# ----------------------------------------------------------------------
# Test 5: unresolved actor relations fail loudly or get rejected judgments
# ----------------------------------------------------------------------


def test_unresolved_actor_relation_is_rejected_not_silently_skipped() -> None:
    """An actor_relation candidate whose subject or object cannot resolve to a
    canonical actor must produce a hard ReconcileError naming the candidate id,
    or an explicit rejection judgment with reason. It must NOT be silently
    `continue`-d so the candidate disappears without trace.
    """
    conn = connect(":memory:")
    init_schema(conn)
    slug = "syntheticunresolved"
    filing, _, spans = _build_synthetic_filing(
        conn,
        slug=slug,
        paragraphs=[
            "On March 1, 2020, Party A executed the merger agreement with the Company.",
            (
                "On March 5, 2020, Phantom Holdings LLC, a previously undisclosed entity, "
                "rolled over its stake into Mystery Vehicle Inc."
            ),
        ],
    )
    _insert_candidate(
        conn,
        _make_dated_event_candidate(
            slug=slug,
            sequence=1,
            filing_id=filing.filing_id,
            raw_value="On March 1, 2020, Party A executed the merger agreement with the Company.",
            iso_date="2020-03-01",
            evidence_id=spans[0].evidence_id,
        ),
    )
    _insert_candidate(
        conn,
        ExtractionCandidate(
            candidate_id=make_id(slug, "candidate", 2),
            run_id="test-run",
            filing_id=filing.filing_id,
            candidate_type="actor_mention",
            raw_value="Party A",
            normalized_value="Party A",
            confidence="high",
            evidence_ids=[spans[0].evidence_id],
            dependencies=[],
            status="active",
        ),
    )
    unresolved_candidate_id = make_id(slug, "candidate", 3)
    _insert_candidate(
        conn,
        ExtractionCandidate(
            candidate_id=unresolved_candidate_id,
            run_id="test-run",
            filing_id=filing.filing_id,
            candidate_type="actor_relation",
            raw_value=(
                "Phantom Holdings LLC rolled over its stake into Mystery Vehicle Inc."
            ),
            normalized_value=json.dumps(
                {
                    "subject_label": "Phantom Holdings LLC",
                    "object_label": "Mystery Vehicle Inc.",
                    "relation_type": "rollover_holder_of",
                    "role_detail": None,
                    "effective_date_first": "2020-03-05",
                },
                sort_keys=True,
            ),
            confidence="medium",
            evidence_ids=[spans[1].evidence_id],
            dependencies=[],
            status="active",
        ),
    )

    raised: ReconcileError | None = None
    try:
        reconcile_filing(conn, filing_id=filing.filing_id, run_id="test-run")
    except ReconcileError as exc:
        raised = exc

    if raised is not None:
        assert unresolved_candidate_id in str(raised), (
            "ReconcileError must name the unresolved candidate id: " f"{raised}"
        )
        return

    # Or: an explicit rejection record must exist for the candidate.
    rejected_rows = conn.execute(
        """
        SELECT count(*) FROM judgments
        WHERE judgment_kind = 'fact_correction'
          AND target_table = 'candidates'
          AND target_id = ?
          AND new_value LIKE '%unresolved_actor_relation%'
        """,
        [unresolved_candidate_id],
    ).fetchone()[0]
    assert rejected_rows >= 1, (
        "unresolved actor_relation must either raise ReconcileError naming the candidate "
        "or insert a rejection judgment row referencing the candidate; neither happened"
    )
