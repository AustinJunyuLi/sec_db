"""Evidence-map construction for semantic claim windows."""

from __future__ import annotations

import json
from dataclasses import dataclass

import duckdb

from sec_graph.schema import make_id

_BACKGROUND_SECTION = "Background of the Merger"
_BACKGROUND_REGION_KIND = "sale_process_narrative"
_BACKGROUND_OBLIGATIONS = (
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
)


@dataclass(frozen=True)
class ParagraphRow:
    paragraph_id: str
    filing_id: str
    deal_slug: str
    section: str
    char_start: int
    char_end: int
    paragraph_text: str
    source_span_id: str


def build_evidence_map(
    conn: duckdb.DuckDBPyConnection,
    *,
    filing_id: str,
    run_id: str,
) -> list[str]:
    """Create evidence regions and obligations for one filing.

    The production LLM path receives the full Background of the Merger section.
    Missing section assignment is a hard ingest failure, not a routing choice.
    """

    rows = _paragraph_rows(conn, filing_id)
    if not rows:
        raise ValueError(f"filing {filing_id} has no paragraphs")
    slug = rows[0].deal_slug
    conn.execute("DELETE FROM coverage_results WHERE obligation_id IN (SELECT obligation_id FROM coverage_obligations WHERE filing_id = ?)", [filing_id])
    conn.execute("DELETE FROM coverage_obligations WHERE filing_id = ?", [filing_id])
    conn.execute("DELETE FROM evidence_regions WHERE filing_id = ?", [filing_id])

    selected = [row for row in rows if row.section == _BACKGROUND_SECTION]
    if not selected:
        raise ValueError(f"filing {filing_id} has no {_BACKGROUND_SECTION!r} paragraphs")

    expected_types = _unique_claim_types(_BACKGROUND_OBLIGATIONS)
    region_id = make_id(slug, "region", 1)
    conn.execute(
        "INSERT INTO evidence_regions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            region_id,
            run_id,
            filing_id,
            slug,
            _BACKGROUND_REGION_KIND,
            1,
            selected[0].paragraph_id,
            selected[-1].paragraph_id,
            json.dumps([row.paragraph_id for row in selected]),
            json.dumps([_BACKGROUND_SECTION]),
            json.dumps(expected_types),
        ],
    )
    for sequence, (claim_type, label, importance) in enumerate(_BACKGROUND_OBLIGATIONS, start=1):
        obligation_id = make_id(slug, "obligation", sequence)
        conn.execute(
            "INSERT INTO coverage_obligations VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                obligation_id,
                run_id,
                region_id,
                filing_id,
                slug,
                claim_type,
                label,
                importance,
                True,
            ],
        )
    return [region_id]


def _paragraph_rows(conn: duckdb.DuckDBPyConnection, filing_id: str) -> list[ParagraphRow]:
    rows = conn.execute(
        """
        SELECT paragraphs.paragraph_id, paragraphs.filing_id, filings.deal_slug,
               paragraphs.section, paragraphs.char_start, paragraphs.char_end,
               paragraphs.paragraph_text, spans.evidence_id
        FROM paragraphs
        JOIN filings USING (filing_id)
        JOIN spans
          ON spans.paragraph_id = paragraphs.paragraph_id
         AND spans.span_kind = 'paragraph_seed'
        WHERE paragraphs.filing_id = ?
        ORDER BY paragraphs.char_start, paragraphs.paragraph_id
        """,
        [filing_id],
    ).fetchall()
    return [ParagraphRow(*row) for row in rows]


def _unique_claim_types(obligations: tuple[tuple[str, str, str], ...]) -> list[str]:
    claim_types: list[str] = []
    for claim_type, _label, _importance in obligations:
        if claim_type not in claim_types:
            claim_types.append(claim_type)
    return claim_types
