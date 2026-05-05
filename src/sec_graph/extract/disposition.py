"""Pre-reconcile claim support dispositions."""

from __future__ import annotations

import re

import duckdb

from sec_graph.schema import make_id


def dispose_claims_for_filing(
    conn: duckdb.DuckDBPyConnection,
    *,
    filing_id: str,
    run_id: str,
) -> None:
    rows = conn.execute(
        """
        SELECT claim_id, claim_type, deal_slug, region_id, quote_text, raw_value
        FROM claims
        WHERE filing_id = ? AND status = 'validated'
        ORDER BY claim_sequence, claim_id
        """,
        [filing_id],
    ).fetchall()
    start_sequence = _next_disposition_sequence(conn, filing_id)
    for offset, row in enumerate(rows):
        sequence = start_sequence + offset
        claim_id, claim_type, deal_slug, region_id, quote_text, raw_value = row
        del raw_value
        disposition, reason_code, reason = _classify_claim(conn, claim_id, claim_type, quote_text)
        _insert_disposition(
            conn,
            deal_slug=deal_slug,
            run_id=run_id,
            sequence=sequence,
            claim_id=claim_id,
            disposition=disposition,
            reason_code=reason_code,
            reason=reason,
        )
        if disposition in {"rejected_unsupported", "queued_ambiguity"}:
            _insert_review_flag(
                conn,
                deal_slug=deal_slug,
                run_id=run_id,
                filing_id=filing_id,
                region_id=region_id,
                claim_id=claim_id,
                sequence=sequence,
                flag_type="unsupported_claim" if disposition == "rejected_unsupported" else "ambiguous_support",
                severity="blocking" if disposition == "rejected_unsupported" else "review",
                reason_code=reason_code,
                reason=reason,
                quote_text=quote_text,
            )


def _classify_claim(
    conn: duckdb.DuckDBPyConnection,
    claim_id: str,
    claim_type: str,
    quote_text: str,
) -> tuple[str, str, str]:
    if claim_type == "bid":
        row = conn.execute(
            """
            SELECT bidder_label, bid_date, bid_value, bid_value_lower, bid_value_upper
            FROM bid_claims
            WHERE claim_id = ?
            """,
            [claim_id],
        ).fetchone()
        if row is None:
            return "rejected_unsupported", "missing_bid_claim", "Bid claim has no typed bid row."
        bidder_label, bid_date, bid_value, bid_value_lower, bid_value_upper = row
        missing = []
        if not _contains_phrase(quote_text, str(bidder_label)):
            missing.append("bidder")
        if bid_date is not None and str(bid_date)[:4] not in quote_text:
            missing.append("date")
        values = [value for value in (bid_value, bid_value_lower, bid_value_upper) if value is not None]
        if values and not any(_number_appears(quote_text, float(value)) for value in values):
            missing.append("value")
        if missing:
            return (
                "rejected_unsupported",
                "bid_quote_missing_" + "_or_".join(missing),
                "Bid claim quote_text does not support: " + ", ".join(missing),
            )
        return "supported", "bid_quote_supported", "Bid claim quote_text supports typed fields."
    return "supported", f"{claim_type}_support_not_yet_specialized", "Claim passed generic support gate."


def _insert_disposition(
    conn: duckdb.DuckDBPyConnection,
    *,
    deal_slug: str,
    run_id: str,
    sequence: int,
    claim_id: str,
    disposition: str,
    reason_code: str,
    reason: str,
) -> None:
    conn.execute(
        "DELETE FROM claim_dispositions WHERE claim_id = ? AND current = true",
        [claim_id],
    )
    conn.execute(
        "INSERT INTO claim_dispositions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            make_id(deal_slug, "disposition", sequence),
            claim_id,
            run_id,
            disposition,
            reason_code,
            reason,
            None,
            None,
            None,
            "dispose",
            True,
        ],
    )


def _insert_review_flag(
    conn: duckdb.DuckDBPyConnection,
    *,
    deal_slug: str,
    run_id: str,
    filing_id: str,
    region_id: str,
    claim_id: str,
    sequence: int,
    flag_type: str,
    severity: str,
    reason_code: str,
    reason: str,
    quote_text: str,
) -> None:
    flag_sequence = _next_review_flag_sequence(conn, deal_slug)
    conn.execute(
        "INSERT INTO review_flags VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            make_id(deal_slug, "reviewflag", flag_sequence),
            run_id,
            deal_slug,
            filing_id,
            region_id,
            None,
            claim_id,
            None,
            None,
            None,
            flag_type,
            severity,
            reason_code,
            reason,
            quote_text,
            None,
            quote_text[:240],
            "Review whether this claim is supported by the quoted source text.",
            True,
        ],
    )


def _next_disposition_sequence(conn: duckdb.DuckDBPyConnection, filing_id: str) -> int:
    row = conn.execute(
        """
        SELECT count(*)
        FROM claim_dispositions
        JOIN claims USING (claim_id)
        WHERE claims.filing_id = ?
        """,
        [filing_id],
    ).fetchone()
    return int(row[0]) + 1


def _next_review_flag_sequence(conn: duckdb.DuckDBPyConnection, deal_slug: str) -> int:
    prefix = f"{deal_slug}_reviewflag_"
    rows = conn.execute(
        "SELECT flag_id FROM review_flags WHERE flag_id LIKE ?",
        [f"{prefix}%"],
    ).fetchall()
    if not rows:
        return 1
    return max(int(row[0].rsplit("_", maxsplit=1)[1]) for row in rows) + 1


def _contains_phrase(text: str, phrase: str) -> bool:
    return phrase.casefold() in text.casefold()


def _number_appears(text: str, value: float) -> bool:
    candidates = {
        f"{value:g}",
        f"{value:.1f}".rstrip("0").rstrip("."),
        f"{value:.2f}",
    }
    folded = re.sub(r"[$,]", " ", text.casefold())
    return any(candidate in folded for candidate in candidates)
