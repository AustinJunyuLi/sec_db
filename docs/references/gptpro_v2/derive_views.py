"""Layer 3: Derive estimation views + Alex-facing tables from canonical DuckDB."""
from __future__ import annotations

import csv
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import duckdb

from scripts.data_pipeline.io import write_jsonl

_BIDDER_ROWS_SQL = """
WITH
bidder_cycles AS (
    SELECT DISTINCT
        a.deal_slug,
        a.actor_id,
        a.actor_label,
        a.bidder_subtype,
        e.cycle_id
    FROM actors a
    JOIN event_actor_links eal ON a.actor_id = eal.actor_id
    JOIN events e ON eal.event_id = e.event_id
    WHERE a.actor_type = 'bidder'
),
boundaries AS (
    SELECT
        cycle_id,
        event_id AS boundary_event_id,
        value AS formal_boundary,
        confidence AS boundary_quality
    FROM judgments
    WHERE judgment_type = 'formal_boundary'
),
boundary_dates AS (
    SELECT
        b.cycle_id,
        b.boundary_event_id,
        b.formal_boundary,
        b.boundary_quality,
        e.event_date_start AS boundary_date
    FROM boundaries b
    LEFT JOIN events e ON b.boundary_event_id = e.event_id
),
actor_proposals AS (
    SELECT
        eal.actor_id,
        e.event_id,
        e.cycle_id,
        e.event_date_start,
        e.bid_value,
        e.bid_value_lower,
        e.bid_value_upper,
        e.bid_value_unit,
        e.consideration_type
    FROM events e
    JOIN event_actor_links eal ON e.event_id = eal.event_id
    WHERE e.event_type = 'proposal_submitted'
      AND e.bid_value IS NOT NULL
),
bI_ranked AS (
    SELECT
        ap.*,
        bd.boundary_date,
        ROW_NUMBER() OVER (
            PARTITION BY ap.actor_id, ap.cycle_id
            ORDER BY ap.event_date_start DESC
        ) AS rn
    FROM actor_proposals ap
    JOIN boundary_dates bd ON ap.cycle_id = bd.cycle_id
    WHERE bd.boundary_date IS NOT NULL
      AND ap.event_date_start < bd.boundary_date
),
bF_ranked AS (
    SELECT
        ap.*,
        ROW_NUMBER() OVER (
            PARTITION BY ap.actor_id, ap.cycle_id
            ORDER BY ap.bid_value DESC
        ) AS rn
    FROM actor_proposals ap
    JOIN boundary_dates bd ON ap.cycle_id = bd.cycle_id
    WHERE bd.boundary_date IS NOT NULL
      AND ap.event_date_start >= bd.boundary_date
)
SELECT
    bc.deal_slug,
    bc.cycle_id,
    bc.actor_id,
    bc.actor_label,
    bc.bidder_subtype,
    bi.bid_value AS bI,
    bi.bid_value_lower AS bI_lo,
    bi.bid_value_upper AS bI_hi,
    bi.bid_value_unit,
    bi.consideration_type,
    bi.event_id AS bI_event_id,
    bf.bid_value AS bF,
    CASE WHEN bf.event_id IS NOT NULL THEN TRUE ELSE FALSE END AS admitted,
    CASE bc.bidder_subtype
        WHEN 'financial' THEN 0
        WHEN 'strategic' THEN 1
        ELSE NULL
    END AS T,
    bd.boundary_event_id,
    bd.formal_boundary,
    bd.boundary_quality,
    sv.value AS scope_validity,
    dm.value AS dropout_mechanism,
    dm.alternative_value IS NOT NULL AS dropout_has_alternative,
    dm.confidence AS dropout_confidence,
    cv.value AS cycle_visibility,
    vc.value AS valuation_comparability,
    vc.confidence AS vc_confidence,
    sv.confidence AS sv_confidence
FROM bidder_cycles bc
LEFT JOIN boundary_dates bd ON bc.cycle_id = bd.cycle_id
LEFT JOIN bI_ranked bi
    ON bc.actor_id = bi.actor_id AND bc.cycle_id = bi.cycle_id AND bi.rn = 1
LEFT JOIN bF_ranked bf
    ON bc.actor_id = bf.actor_id AND bc.cycle_id = bf.cycle_id AND bf.rn = 1
LEFT JOIN judgments sv
    ON sv.judgment_type = 'scope_validity' AND sv.actor_id = bc.actor_id
LEFT JOIN judgments dm
    ON dm.judgment_type = 'dropout_mechanism'
    AND dm.actor_id = bc.actor_id AND dm.cycle_id = bc.cycle_id
LEFT JOIN judgments cv
    ON cv.judgment_type = 'cycle_visibility' AND cv.cycle_id = bc.cycle_id
LEFT JOIN judgments vc
    ON vc.judgment_type = 'valuation_comparability'
    AND vc.event_id = bi.event_id
"""

_AUCTIONS_SQL = """
SELECT
    d.deal_slug,
    pc.cycle_id,
    pc.cycle_sequence,
    cr.value AS cycle_regime,
    cv.value AS cycle_visibility,
    crel.value AS cycle_relation,
    fb.value AS formal_boundary,
    fb.event_id AS boundary_event_id
FROM process_cycles pc
JOIN deals d ON pc.deal_slug = d.deal_slug
LEFT JOIN judgments cr
    ON cr.judgment_type = 'cycle_regime' AND cr.cycle_id = pc.cycle_id
LEFT JOIN judgments cv
    ON cv.judgment_type = 'cycle_visibility' AND cv.cycle_id = pc.cycle_id
LEFT JOIN judgments crel
    ON crel.judgment_type = 'cycle_relation' AND crel.cycle_id = pc.cycle_id
LEFT JOIN judgments fb
    ON fb.judgment_type = 'formal_boundary' AND fb.cycle_id = pc.cycle_id
"""

_CONF_RANK = {"low": 1, "medium": 2, "high": 3}
_RANK_CONF = {1: "low", 2: "medium", 3: "high"}


def _min_confidence(*confs: str | None) -> str | None:
    """Return the lowest confidence level as a string."""
    nums = [_CONF_RANK[conf] for conf in confs if conf in _CONF_RANK]
    if not nums:
        return None
    return _RANK_CONF[min(nums)]


def _build_estimation_bidder_rows(
    con: duckdb.DuckDBPyConnection,
) -> list[dict[str, Any]]:
    """Build estimation_bidder_rows from canonical DuckDB."""
    raw = con.execute(_BIDDER_ROWS_SQL).fetchall()
    columns = [desc[0] for desc in con.description]

    rows: list[dict[str, Any]] = []
    for record in raw:
        data = dict(zip(columns, record))
        bI_hi = data.get("bI_hi")
        bI_lo = data.get("bI_lo")
        w_logwidth = None
        if bI_hi is not None and bI_lo is not None and bI_lo > 0:
            w_logwidth = math.log(bI_hi / bI_lo)

        conf_min = _min_confidence(
            data.get("sv_confidence"),
            data.get("boundary_quality"),
            data.get("dropout_confidence"),
            data.get("vc_confidence"),
        )

        rows.append(
            {
                "deal_slug": data["deal_slug"],
                "cycle_id": data["cycle_id"],
                "actor_id": data["actor_id"],
                "actor_label": data.get("actor_label"),
                "bI": data.get("bI"),
                "bI_lo": bI_lo,
                "bI_hi": bI_hi,
                "w_logwidth": w_logwidth,
                "bF": data.get("bF"),
                "admitted": bool(data.get("admitted", False)),
                "T": data.get("T"),
                "bid_value_unit": data.get("bid_value_unit"),
                "consideration_type": data.get("consideration_type"),
                "boundary_event_id": data.get("boundary_event_id"),
                "boundary_quality": data.get("boundary_quality"),
                "formal_boundary": data.get("formal_boundary"),
                "dropout_mechanism": data.get("dropout_mechanism"),
                "dropout_has_alternative": bool(
                    data.get("dropout_has_alternative", False)
                ),
                "cycle_visibility": data.get("cycle_visibility"),
                "scope_validity": data.get("scope_validity"),
                "valuation_comparability": data.get("valuation_comparability"),
                "confidence_min": conf_min,
            }
        )
    return rows


def _build_estimation_auctions(
    con: duckdb.DuckDBPyConnection,
) -> list[dict[str, Any]]:
    """Build estimation_auctions (cycle-level metadata, no pre-computed counts)."""
    raw = con.execute(_AUCTIONS_SQL).fetchall()
    columns = [desc[0] for desc in con.description]
    return [dict(zip(columns, record)) for record in raw]


def _write_csv(rows: list[dict[str, Any]], path: Path) -> None:
    """Write a list of dicts to a CSV file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fieldnames = list(rows[0].keys())
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _build_review_master(con: duckdb.DuckDBPyConnection) -> list[dict[str, Any]]:
    """One row per event-actor observation across all deals."""
    sql = """
    SELECT
        e.deal_slug, e.cycle_id, e.event_id,
        e.event_date_start, e.event_date_end, e.date_precision,
        eal.actor_id, a.actor_label, a.actor_type,
        e.event_type, e.event_subtype,
        eal.role,
        e.bid_value, e.bid_value_lower, e.bid_value_upper,
        e.bid_value_unit, e.consideration_type,
        e.source_text, e.source_page_hint, e.raw_note
    FROM events e
    JOIN event_actor_links eal ON e.event_id = eal.event_id
    JOIN actors a ON eal.actor_id = a.actor_id
    ORDER BY e.deal_slug, e.cycle_id, e.event_date_start
    """
    raw = con.execute(sql).fetchall()
    columns = [desc[0] for desc in con.description]
    return [dict(zip(columns, record)) for record in raw]


def _build_ambiguity_queue(con: duckdb.DuckDBPyConnection) -> list[dict[str, Any]]:
    """Judgments where confidence is low or alternative_value is non-null."""
    sql = """
    SELECT
        j.deal_slug, j.judgment_id, j.judgment_type, j.scope,
        j.cycle_id, j.actor_id, j.event_id,
        j.value, j.confidence,
        j.basis, j.source_snippet,
        j.alternative_value, j.alternative_basis
    FROM judgments j
    WHERE j.confidence = 'low'
       OR j.alternative_value IS NOT NULL
    ORDER BY j.deal_slug, j.judgment_type
    """
    raw = con.execute(sql).fetchall()
    columns = [desc[0] for desc in con.description]
    return [dict(zip(columns, record)) for record in raw]


def _build_deal_index(con: duckdb.DuckDBPyConnection) -> list[dict[str, Any]]:
    """One row per deal."""
    sql = """
    SELECT
        deal_slug, target_name, filing_url, filing_type,
        filing_date, deal_outcome, winning_acquirer,
        date_announced, date_effective
    FROM deals
    ORDER BY deal_slug
    """
    raw = con.execute(sql).fetchall()
    columns = [desc[0] for desc in con.description]
    return [dict(zip(columns, record)) for record in raw]


def _build_bidder_summary(con: duckdb.DuckDBPyConnection) -> list[dict[str, Any]]:
    """One row per bidder-like actor."""
    sql = """
    SELECT
        a.deal_slug, a.actor_id, a.actor_label,
        a.actor_type, a.bidder_subtype,
        a.is_grouped, a.group_size_if_known,
        sv.value AS scope_validity
    FROM actors a
    LEFT JOIN judgments sv
        ON sv.judgment_type = 'scope_validity' AND sv.actor_id = a.actor_id
    WHERE a.actor_type = 'bidder'
    ORDER BY a.deal_slug, a.actor_id
    """
    raw = con.execute(sql).fetchall()
    columns = [desc[0] for desc in con.description]
    return [dict(zip(columns, record)) for record in raw]


def _build_cycle_summary(con: duckdb.DuckDBPyConnection) -> list[dict[str, Any]]:
    """One row per cycle."""
    sql = """
    SELECT
        pc.deal_slug, pc.cycle_id, pc.cycle_sequence,
        pc.cycle_start_date, pc.cycle_end_date,
        pc.segmentation_basis,
        cr.value AS cycle_regime,
        cv.value AS cycle_visibility,
        crel.value AS cycle_relation,
        fb.value AS formal_boundary
    FROM process_cycles pc
    LEFT JOIN judgments cr
        ON cr.judgment_type = 'cycle_regime' AND cr.cycle_id = pc.cycle_id
    LEFT JOIN judgments cv
        ON cv.judgment_type = 'cycle_visibility' AND cv.cycle_id = pc.cycle_id
    LEFT JOIN judgments crel
        ON crel.judgment_type = 'cycle_relation' AND crel.cycle_id = pc.cycle_id
    LEFT JOIN judgments fb
        ON fb.judgment_type = 'formal_boundary' AND fb.cycle_id = pc.cycle_id
    ORDER BY pc.deal_slug, pc.cycle_sequence
    """
    raw = con.execute(sql).fetchall()
    columns = [desc[0] for desc in con.description]
    return [dict(zip(columns, record)) for record in raw]


def _write_run_memo(
    views_dir: Path,
    deal_index: list[dict[str, Any]],
    ambiguity_queue: list[dict[str, Any]],
) -> None:
    """Write a markdown run memo for Alex."""
    n_deals = len(deal_index)
    n_ambiguous = len(ambiguity_queue)
    slugs = [deal["deal_slug"] for deal in deal_index]
    memo = f"""# Run Memo

**Generated:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}

## Deals Included ({n_deals})

{chr(10).join(f'- {slug}' for slug in slugs)}

## Ambiguity Queue

{n_ambiguous} judgment(s) flagged for review (low confidence or competing readings).

## Caveats

Review `ambiguity_queue.csv` for judgments requiring human review.
"""
    views_dir.mkdir(parents=True, exist_ok=True)
    (views_dir / "run_memo.md").write_text(memo, encoding="utf-8")


def build_all_views(
    db_path: Path,
    views_dir: Path,
    reference_dir: Path,
) -> dict[str, Any]:
    """Build all Layer 3 outputs: estimation views + Alex-facing tables."""
    db_path = Path(db_path)
    views_dir = Path(views_dir)
    views_dir.mkdir(parents=True, exist_ok=True)

    con = duckdb.connect(str(db_path), read_only=True)
    try:
        bidder_rows = _build_estimation_bidder_rows(con)
        write_jsonl(bidder_rows, views_dir / "estimation_bidder_rows.jsonl")

        auctions = _build_estimation_auctions(con)
        write_jsonl(auctions, views_dir / "estimation_auctions.jsonl")

        review_master = _build_review_master(con)
        _write_csv(review_master, views_dir / "review_master.csv")

        ambiguity_queue = _build_ambiguity_queue(con)
        _write_csv(ambiguity_queue, views_dir / "ambiguity_queue.csv")

        deal_index = _build_deal_index(con)
        _write_csv(deal_index, views_dir / "deal_index.csv")

        bidder_summary = _build_bidder_summary(con)
        _write_csv(bidder_summary, views_dir / "bidder_summary.csv")

        cycle_summary = _build_cycle_summary(con)
        _write_csv(cycle_summary, views_dir / "cycle_summary.csv")

        _write_run_memo(views_dir, deal_index, ambiguity_queue)
    finally:
        con.close()

    return {
        "views_dir": str(views_dir),
        "bidder_rows_count": len(bidder_rows),
        "auctions_count": len(auctions),
        "reference_dir": str(reference_dir),
    }
