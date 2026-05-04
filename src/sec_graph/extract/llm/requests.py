"""Build semantic Linkflow windows from evidence regions."""

from __future__ import annotations

import json

import duckdb

from sec_graph.extract.llm.models import DEFAULT_REQUEST_MODE, LLMWindowRequest, WindowObligation, WindowParagraph
from sec_graph.schema import versions


def build_llm_windows(
    conn: duckdb.DuckDBPyConnection,
    *,
    filing_id: str,
    request_mode: str = DEFAULT_REQUEST_MODE,
) -> list[LLMWindowRequest]:
    if request_mode != DEFAULT_REQUEST_MODE:
        raise ValueError(f"unsupported LLM request_mode {request_mode!r}; expected {DEFAULT_REQUEST_MODE!r}")
    rows = conn.execute(
        """
        SELECT region_id, run_id, deal_slug, region_kind, paragraph_ids_json,
               expected_claim_types_json
        FROM evidence_regions
        WHERE filing_id = ?
        ORDER BY priority, region_id
        """,
        [filing_id],
    ).fetchall()
    windows: list[LLMWindowRequest] = []
    for sequence, (region_id, _run_id, deal_slug, region_kind, paragraph_ids_json, expected_claim_types_json) in enumerate(rows, start=1):
        paragraph_ids = json.loads(paragraph_ids_json)
        paragraphs = _window_paragraphs(conn, paragraph_ids)
        obligations = _window_obligations(conn, region_id)
        allowed_claim_types = json.loads(expected_claim_types_json)
        windows.append(
            LLMWindowRequest(
                request_id=f"{deal_slug}_llmrequest_{sequence}",
                deal_slug=deal_slug,
                deal_id=deal_slug,
                filing_id=filing_id,
                region_id=region_id,
                window_id=f"{deal_slug}_window_{sequence}",
                region_kind=region_kind,
                ordered_paragraphs=paragraphs,
                coverage_obligations=obligations,
                allowed_claim_types=allowed_claim_types,
                schema_version=versions.SCHEMA_VERSION,
                extract_version=versions.EXTRACT_VERSION,
                request_mode=request_mode,
            )
        )
    return windows


def _window_paragraphs(
    conn: duckdb.DuckDBPyConnection,
    paragraph_ids: list[str],
) -> list[WindowParagraph]:
    if not paragraph_ids:
        raise ValueError("evidence region has no paragraph ids")
    placeholders = ", ".join("?" for _ in paragraph_ids)
    order_expr = " ".join(f"WHEN ? THEN {index}" for index, _ in enumerate(paragraph_ids))
    params = [*paragraph_ids, *paragraph_ids]
    rows = conn.execute(
        f"""
        SELECT paragraphs.paragraph_id, spans.evidence_id, paragraphs.char_start,
               paragraphs.char_end, paragraphs.paragraph_text
        FROM paragraphs
        JOIN spans
          ON spans.paragraph_id = paragraphs.paragraph_id
         AND spans.span_kind = 'paragraph_seed'
        WHERE paragraphs.paragraph_id IN ({placeholders})
        ORDER BY CASE paragraphs.paragraph_id {order_expr} END
        """,
        params,
    ).fetchall()
    if len(rows) != len(paragraph_ids):
        raise ValueError("evidence region references missing paragraph ids")
    return [WindowParagraph.model_validate(dict(zip(("paragraph_id", "source_span_id", "char_start", "char_end", "paragraph_text"), row, strict=True))) for row in rows]


def _window_obligations(
    conn: duckdb.DuckDBPyConnection,
    region_id: str,
) -> list[WindowObligation]:
    rows = conn.execute(
        """
        SELECT obligation_id, expected_claim_type, obligation_label, importance
        FROM coverage_obligations
        WHERE region_id = ? AND current = true
        ORDER BY CAST(regexp_extract(obligation_id, '_(\\d+)$', 1) AS INTEGER), obligation_id
        """,
        [region_id],
    ).fetchall()
    if not rows:
        raise ValueError(f"region {region_id} has no coverage obligations")
    return [
        WindowObligation.model_validate(
            dict(zip(("obligation_id", "expected_claim_type", "obligation_label", "importance"), row, strict=True))
        )
        for row in rows
    ]
