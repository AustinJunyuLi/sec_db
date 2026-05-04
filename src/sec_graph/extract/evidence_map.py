"""Evidence-map construction for semantic claim windows."""

from __future__ import annotations

import json
from dataclasses import dataclass

import duckdb

from sec_graph.extract.applicability import (
    ApplicabilityDecision,
    decide_applicability,
)
from sec_graph.extract.source_support import is_substantive_sale_process_text
from sec_graph.ingest.section_vocabulary import SALE_PROCESS_SECTIONS
from sec_graph.schema import make_id

_SALE_PROCESS_REGION_KIND = "sale_process_narrative"


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
    """Create evidence regions and applicability-aware obligations.

    For every contiguous substantive sale-process run in the filing, emit one
    region in encounter order. Each region carries the full applicability
    ledger: universal obligations are always applicable, conditional
    obligations are applicable only when the region text supports the positive
    source fact, and scope-driven obligations apply only to the matching process
    scope.

    A filing with no sale-process paragraphs is a hard failure. A region with
    zero applicable obligations is a hard failure: the universal set ensures
    this is impossible in practice, and a region without any applicable
    obligation cannot produce a meaningful Linkflow request.
    """

    rows = _paragraph_rows(conn, filing_id)
    if not rows:
        raise ValueError(f"filing {filing_id} has no paragraphs")
    slug = rows[0].deal_slug
    process_scope = _filing_process_scope(conn, filing_id)

    conn.execute(
        "DELETE FROM coverage_results WHERE obligation_id IN ("
        " SELECT obligation_id FROM coverage_obligations WHERE filing_id = ?"
        ")",
        [filing_id],
    )
    conn.execute("DELETE FROM coverage_obligations WHERE filing_id = ?", [filing_id])
    conn.execute("DELETE FROM evidence_regions WHERE filing_id = ?", [filing_id])

    candidate_runs = _sale_process_runs(rows)
    if not candidate_runs:
        raise ValueError(
            f"filing {filing_id} has no sale-process paragraphs "
            f"(e.g., 'Background of the Merger', 'Background of the Offer', "
            f"or 'Past Contacts, Transactions, Negotiations and Agreements')"
        )
    substantive_runs: list[tuple[str, list[ParagraphRow]]] = []
    for section, paragraphs in candidate_runs:
        region_text = "\n".join(p.paragraph_text for p in paragraphs)
        if is_substantive_sale_process_text(region_text):
            substantive_runs.append((section, paragraphs))

    if not substantive_runs:
        raise ValueError(
            f"filing {filing_id} has no substantive sale-process paragraphs "
            "(recognized headings were absent or cross-reference-only)"
        )

    region_ids: list[str] = []
    obligation_counter = 0
    for region_index, (section, paragraphs) in enumerate(substantive_runs, start=1):
        region_text = "\n".join(p.paragraph_text for p in paragraphs)
        decisions = decide_applicability(
            region_text=region_text,
            process_scope=process_scope,
        )
        applicable_decisions = [d for d in decisions if d.applicability == "applicable"]
        if not applicable_decisions:
            raise ValueError(
                f"region for section {section!r} in filing {filing_id} has no "
                "applicable obligations; refusing to send empty window to Linkflow"
            )
        expected_types = _ordered_unique(
            d.obligation_kind.claim_type for d in applicable_decisions
        )
        region_id = make_id(slug, "region", region_index)
        conn.execute(
            "INSERT INTO evidence_regions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                region_id,
                run_id,
                filing_id,
                slug,
                _SALE_PROCESS_REGION_KIND,
                region_index,
                paragraphs[0].paragraph_id,
                paragraphs[-1].paragraph_id,
                json.dumps([row.paragraph_id for row in paragraphs]),
                json.dumps([section]),
                json.dumps(expected_types),
            ],
        )
        for decision in decisions:
            obligation_counter += 1
            obligation_id = make_id(slug, "obligation", obligation_counter)
            kind = decision.obligation_kind
            conn.execute(
                "INSERT INTO coverage_obligations VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    obligation_id,
                    run_id,
                    region_id,
                    filing_id,
                    slug,
                    kind.claim_type,
                    kind.kind,
                    kind.label,
                    kind.importance,
                    decision.applicability,
                    decision.reason_code,
                    json.dumps(list(decision.basis)),
                    True,
                ],
            )
        region_ids.append(region_id)
    return region_ids


def _sale_process_runs(rows: list[ParagraphRow]) -> list[tuple[str, list[ParagraphRow]]]:
    runs: list[tuple[str, list[ParagraphRow]]] = []
    current_section: str | None = None
    current_rows: list[ParagraphRow] = []
    for row in rows:
        if row.section not in SALE_PROCESS_SECTIONS:
            if current_rows and current_section is not None:
                runs.append((current_section, current_rows))
            current_section = None
            current_rows = []
            continue
        if row.section != current_section:
            if current_rows and current_section is not None:
                runs.append((current_section, current_rows))
            current_section = row.section
            current_rows = [row]
        else:
            current_rows.append(row)
    if current_rows and current_section is not None:
        runs.append((current_section, current_rows))
    return runs


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


def _filing_process_scope(conn: duckdb.DuckDBPyConnection, filing_id: str) -> str:
    row = conn.execute(
        "SELECT process_scope FROM filings WHERE filing_id = ?", [filing_id]
    ).fetchone()
    if row is None:
        raise ValueError(f"filing {filing_id} not found in filings table")
    return row[0]


def _ordered_unique(values) -> list[str]:
    seen: list[str] = []
    for value in values:
        if value not in seen:
            seen.append(value)
    return seen
