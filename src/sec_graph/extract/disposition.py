"""Pre-reconcile claim support dispositions.

This module is the single semantic gate. Disposition decides whether a
claim's `quote_text` supports its typed fields. The post-canonical
semantic checks in `validate/integrity.py` were deleted in this refactor.
Coverage is finalized once, after disposition, by
`finalize_coverage_after_disposition`.
"""

from __future__ import annotations

import datetime as dt
from typing import Iterable

import duckdb

from sec_graph.extract.quote_support import (
    any_term_in_text,
    bid_context_supported_by_quote,
    contains_phrase,
    date_supported_by_quote,
    normalize_text,
    number_supported_by_quote,
    numeric_tokens,
    relation_supported_by_quote,
)
from sec_graph.schema import make_id

_RUN_TIMESTAMP_FALLBACK = "2026-05-07T00:00:00Z"


# --------------------------------------------------------------------------- #
# Public API                                                                  #
# --------------------------------------------------------------------------- #


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
        claim_id, claim_type, deal_slug, region_id, quote_text, _raw_value = row
        disposition, reason_code, reason = _classify_claim(
            conn, claim_id, claim_type, quote_text
        )
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
            review_type = "claim_disposition"
            severity = "review"
            _insert_review_row(
                conn,
                deal_slug=deal_slug,
                run_id=run_id,
                claim_id=claim_id,
                review_type=review_type,
                severity=severity,
                reason_code=reason_code,
                message=reason,
                review_question=(
                    "Review whether this claim is supported by the quoted "
                    "source text."
                ),
                source_table="claims",
                source_id=claim_id,
                evidence_json=quote_text,
            )


def finalize_coverage_after_disposition(
    conn: duckdb.DuckDBPyConnection,
    *,
    run_id: str,
    filing_id: str,
) -> None:
    """Recompute coverage_results for ``filing_id`` from disposed claims.

    Coverage is the post-disposition count of supported (or merged
    duplicate) claims linked to each applicable+current obligation.
    Pre-existing coverage rows for those obligations are deleted before
    insertion so this function is idempotent.
    """

    conn.execute(
        """
        DELETE FROM coverage_results
        WHERE obligation_id IN (
            SELECT obligation_id
            FROM coverage_obligations
            WHERE filing_id = ?
              AND applicability = 'applicable'
              AND current = true
        )
        """,
        [filing_id],
    )
    obligations = conn.execute(
        """
        SELECT obligation_id, importance, applicability_reason_code
        FROM coverage_obligations
        WHERE filing_id = ?
          AND applicability = 'applicable'
          AND current = true
        ORDER BY obligation_id
        """,
        [filing_id],
    ).fetchall()
    _refresh_current_coverage_links(conn, filing_id=filing_id)
    deal_slug = _filing_deal_slug(conn, filing_id)
    coverage_sequence = _next_sequence(
        conn, "coverage_results", "coverage_result_id", deal_slug, "coverage"
    )
    for obligation_id, importance, applicability_reason_code in obligations:
        supported_count = int(
            conn.execute(
                """
                SELECT count(*)
                FROM claim_coverage_links
                WHERE claim_coverage_links.obligation_id = ?
                  AND claim_coverage_links.current = true
                """,
                [obligation_id],
            ).fetchone()[0]
        )
        result, reason_code, reason = _classify_obligation(
            obligation_id,
            supported_count,
            applicability_reason_code,
            importance,
            conn,
        )
        coverage_result_id = make_id(deal_slug, "coverage", coverage_sequence)
        coverage_sequence += 1
        conn.execute(
            "INSERT INTO coverage_results VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [
                coverage_result_id,
                run_id,
                obligation_id,
                result,
                reason_code,
                reason,
                supported_count,
                True,
            ],
        )


# --------------------------------------------------------------------------- #
# Classification                                                              #
# --------------------------------------------------------------------------- #


def _classify_claim(
    conn: duckdb.DuckDBPyConnection,
    claim_id: str,
    claim_type: str,
    quote_text: str,
) -> tuple[str, str, str]:
    if claim_type == "bid":
        return _classify_bid_claim(conn, claim_id, quote_text)
    if claim_type == "actor_relation":
        return _classify_actor_relation_claim(conn, claim_id, quote_text)
    if claim_type == "participation_count":
        return _classify_participation_count_claim(conn, claim_id, quote_text)
    if claim_type == "event":
        return _classify_event_claim(conn, claim_id, quote_text)
    if claim_type == "actor":
        return _classify_actor_claim(conn, claim_id, quote_text)
    return (
        "rejected_unsupported",
        "unknown_claim_type",
        f"unsupported claim_type={claim_type}",
    )


def _classify_bid_claim(
    conn: duckdb.DuckDBPyConnection, claim_id: str, quote_text: str
) -> tuple[str, str, str]:
    row = conn.execute(
        """
        SELECT bidder_label, bid_date, bid_value, bid_value_lower, bid_value_upper, bid_stage
        FROM bid_claims
        WHERE claim_id = ?
        """,
        [claim_id],
    ).fetchone()
    if row is None:
        return (
            "rejected_unsupported",
            "missing_bid_claim",
            "Bid claim has no typed bid row.",
        )
    bidder_label, bid_date, bid_value, bid_value_lower, bid_value_upper, bid_stage = row
    missing: list[str] = []
    if not contains_phrase(quote_text, str(bidder_label)):
        missing.append("bidder")
    if not bid_context_supported_by_quote(str(bid_stage) if bid_stage else None, quote_text):
        missing.append("bid_context")
    values = [
        value
        for value in (bid_value, bid_value_lower, bid_value_upper)
        if value is not None
    ]
    if values and not any(number_supported_by_quote(float(value), quote_text) for value in values):
        missing.append("value")
    if bid_date is not None and not date_supported_by_quote(bid_date, quote_text):
        missing.append("date")
    if missing:
        ordered = sorted(set(missing))
        return (
            "rejected_unsupported",
            "bid_quote_missing_" + "_or_".join(ordered),
            "Bid claim quote_text does not support: " + ", ".join(ordered),
        )
    return (
        "supported",
        "bid_quote_supported",
        "Bid claim quote_text supports typed fields.",
    )


def _classify_actor_relation_claim(
    conn: duckdb.DuckDBPyConnection, claim_id: str, quote_text: str
) -> tuple[str, str, str]:
    row = conn.execute(
        """
        SELECT subject_label, object_label, relation_type, role_detail
        FROM actor_relation_claims
        WHERE claim_id = ?
        """,
        [claim_id],
    ).fetchone()
    if row is None:
        return (
            "rejected_unsupported",
            "missing_actor_relation_claim",
            "Actor-relation claim has no typed row.",
        )
    subject_label, object_label, relation_type, role_detail = row
    missing: list[str] = []
    if not contains_phrase(quote_text, str(subject_label)):
        missing.append("subject_label")
    if not contains_phrase(quote_text, str(object_label)):
        missing.append("object_label")
    if not relation_supported_by_quote(str(relation_type), role_detail, quote_text):
        missing.append("relation_meaning")
    if relation_type == "member_of" and _looks_like_proposal_description(str(object_label)):
        missing.append("member_of_object_must_be_actor_or_group")
    if missing:
        ordered = sorted(set(missing))
        return (
            "rejected_unsupported",
            "relation_quote_missing_" + "_or_".join(ordered),
            "Actor-relation claim quote_text does not support: "
            + ", ".join(ordered),
        )
    return (
        "supported",
        "relation_quote_supported",
        "Actor-relation claim quote_text supports typed fields.",
    )


def _classify_participation_count_claim(
    conn: duckdb.DuckDBPyConnection, claim_id: str, quote_text: str
) -> tuple[str, str, str]:
    row = conn.execute(
        """
        SELECT process_stage, actor_class, count_min, count_max, count_qualifier
        FROM participation_count_claims
        WHERE claim_id = ?
        """,
        [claim_id],
    ).fetchone()
    if row is None:
        return (
            "rejected_unsupported",
            "missing_participation_count_claim",
            "Participation-count claim has no typed row.",
        )
    process_stage, actor_class, count_min, count_max, _qualifier = row
    missing: list[str] = []
    if not _quote_has_count_language(quote_text):
        missing.append("count_language")
    if not _quote_supports_participation_scope(process_stage, actor_class, quote_text):
        missing.append("class_or_scope")
    values = [value for value in (count_min, count_max) if value is not None]
    if values and not any(
        _count_value_supported_by_quote(int(value), quote_text) for value in values
    ):
        missing.append("count_number")
    if missing:
        ordered = sorted(set(missing))
        return (
            "rejected_unsupported",
            "count_quote_missing_" + "_or_".join(ordered),
            "Participation-count claim quote_text does not support: "
            + ", ".join(ordered),
        )
    return (
        "supported",
        "count_quote_supported",
        "Participation-count claim quote_text supports typed fields.",
    )


def _classify_event_claim(
    conn: duckdb.DuckDBPyConnection, claim_id: str, quote_text: str
) -> tuple[str, str, str]:
    row = conn.execute(
        """
        SELECT event_type, event_subtype, event_date, description
        FROM event_claims
        WHERE claim_id = ?
        """,
        [claim_id],
    ).fetchone()
    if row is None:
        return (
            "rejected_unsupported",
            "missing_event_claim",
            "Event claim has no typed row.",
        )
    event_type, event_subtype, event_date, _description = row
    missing: list[str] = []
    if not _event_subtype_supported_by_quote(str(event_type), str(event_subtype), quote_text):
        missing.append("event_subtype")
    if event_date is not None and not date_supported_by_quote(event_date, quote_text):
        missing.append("event_date")
    if missing:
        ordered = sorted(set(missing))
        return (
            "rejected_unsupported",
            "event_quote_missing_" + "_or_".join(ordered),
            "Event claim quote_text does not support: " + ", ".join(ordered),
        )
    return (
        "supported",
        "event_quote_supported",
        "Event claim quote_text supports typed fields.",
    )


def _classify_actor_claim(
    conn: duckdb.DuckDBPyConnection, claim_id: str, quote_text: str
) -> tuple[str, str, str]:
    row = conn.execute(
        "SELECT actor_label FROM actor_claims WHERE claim_id = ?",
        [claim_id],
    ).fetchone()
    if row is None:
        return (
            "rejected_unsupported",
            "missing_actor_claim",
            "Actor claim has no typed row.",
        )
    actor_label = row[0]
    if not contains_phrase(quote_text, str(actor_label)):
        return (
            "rejected_unsupported",
            "actor_quote_missing_label",
            "Actor claim quote_text does not name the actor.",
        )
    return (
        "supported",
        "actor_quote_supported",
        "Actor claim quote_text names the actor.",
    )


# --------------------------------------------------------------------------- #
# Coverage classification                                                     #
# --------------------------------------------------------------------------- #


def _classify_obligation(
    obligation_id: str,
    supported_count: int,
    applicability_reason_code: str | None,
    importance: str,
    conn: duckdb.DuckDBPyConnection,
) -> tuple[str, str, str]:
    if supported_count >= 1:
        return (
            "claims_emitted",
            "claims_emitted",
            "Obligation has at least one supported claim.",
        )
    link_count = int(
        conn.execute(
            """
            SELECT count(*)
            FROM claim_coverage_links
            WHERE obligation_id = ?
            """,
            [obligation_id],
        ).fetchone()[0]
    )
    if link_count > 0:
        return (
            "no_supported_claim",
            "links_present_no_supported_claim",
            (
                "Obligation has claim_coverage_links but no linked claim was "
                "disposed supported."
            ),
        )
    if importance in {"required", "important"}:
        return (
            "missed_supported_obligation",
            "missed_required_or_important_obligation",
            (
                "Obligation is required/important but has no claim_coverage_links "
                "and no supported claim."
            ),
        )
    return (
        "ambiguous_support",
        applicability_reason_code or "ambiguous_no_links_no_supported",
        "Obligation has no claim_coverage_links and no supported claim.",
    )


# --------------------------------------------------------------------------- #
# Inserts and helpers                                                         #
# --------------------------------------------------------------------------- #


def _refresh_current_coverage_links(
    conn: duckdb.DuckDBPyConnection,
    *,
    filing_id: str,
) -> None:
    """Mark current coverage links as the supported proof links for a filing."""

    conn.execute(
        """
        UPDATE claim_coverage_links
        SET current = false
        WHERE obligation_id IN (
            SELECT obligation_id
            FROM coverage_obligations
            WHERE filing_id = ?
              AND applicability = 'applicable'
              AND current = true
        )
        """,
        [filing_id],
    )
    conn.execute(
        """
        UPDATE claim_coverage_links
        SET current = true
        WHERE claim_id IN (
            SELECT claims.claim_id
            FROM claims
            JOIN claim_dispositions
              ON claim_dispositions.claim_id = claims.claim_id
             AND claim_dispositions.current = true
            WHERE claims.filing_id = ?
              AND claim_dispositions.disposition IN ('supported', 'merged_duplicate')
        )
          AND obligation_id IN (
            SELECT obligation_id
            FROM coverage_obligations
            WHERE filing_id = ?
              AND applicability = 'applicable'
              AND current = true
          )
        """,
        [filing_id, filing_id],
    )


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


def _insert_review_row(
    conn: duckdb.DuckDBPyConnection,
    *,
    deal_slug: str,
    run_id: str,
    claim_id: str | None,
    review_type: str,
    severity: str,
    reason_code: str,
    message: str,
    review_question: str,
    source_table: str,
    source_id: str,
    obligation_id: str | None = None,
    judgment_id: str | None = None,
    canonical_table: str | None = None,
    canonical_id: str | None = None,
    evidence_json: str | None = None,
) -> None:
    sequence = _next_review_row_sequence(conn, deal_slug)
    conn.execute(
        "INSERT INTO review_rows VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            make_id(deal_slug, "reviewrow", sequence),
            run_id,
            deal_slug,
            "open",
            review_type,
            source_table,
            source_id,
            severity,
            reason_code,
            message,
            review_question,
            claim_id,
            obligation_id,
            judgment_id,
            canonical_table,
            canonical_id,
            evidence_json,
            None,
            None,
            None,
            _now_iso(),
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


def _next_review_row_sequence(conn: duckdb.DuckDBPyConnection, deal_slug: str) -> int:
    prefix = f"{deal_slug}_reviewrow_"
    rows = conn.execute(
        "SELECT review_row_id FROM review_rows WHERE review_row_id LIKE ?",
        [f"{prefix}%"],
    ).fetchall()
    if not rows:
        return 1
    return max(int(row[0].rsplit("_", maxsplit=1)[1]) for row in rows) + 1


def _next_sequence(
    conn: duckdb.DuckDBPyConnection,
    table_name: str,
    id_col: str,
    slug: str,
    type_name: str,
) -> int:
    prefix = f"{slug}_{type_name}_"
    rows = conn.execute(
        f"SELECT {id_col} FROM {table_name} WHERE {id_col} LIKE ?",
        [f"{prefix}%"],
    ).fetchall()
    if not rows:
        return 1
    return max(int(row[0].rsplit("_", maxsplit=1)[1]) for row in rows) + 1


def _filing_deal_slug(conn: duckdb.DuckDBPyConnection, filing_id: str) -> str:
    row = conn.execute(
        "SELECT deal_slug FROM filings WHERE filing_id = ?",
        [filing_id],
    ).fetchone()
    if row is None:
        raise ValueError(f"unknown filing_id={filing_id}")
    return row[0]


def _now_iso() -> str:
    try:
        return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except Exception:  # pragma: no cover - defensive
        return _RUN_TIMESTAMP_FALLBACK


# --------------------------------------------------------------------------- #
# Quote-level predicates                                                      #
# --------------------------------------------------------------------------- #


_PARTICIPATION_NOUNS = (
    "buyer",
    "buyers",
    "bidder",
    "bidders",
    "party",
    "parties",
    "purchaser",
    "purchasers",
    "sponsor",
    "sponsors",
    "participant",
    "participants",
    "firm",
    "firms",
    "acquiror",
    "acquirors",
    "company",
    "companies",
)


_COUNT_WORDS = (
    "one",
    "two",
    "three",
    "four",
    "five",
    "six",
    "seven",
    "eight",
    "nine",
    "ten",
    "eleven",
    "twelve",
    "thirteen",
    "fourteen",
    "fifteen",
    "sixteen",
    "seventeen",
    "eighteen",
    "nineteen",
    "twenty",
)


_COUNT_WORD_VALUES = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
    "thirteen": 13,
    "fourteen": 14,
    "fifteen": 15,
    "sixteen": 16,
    "seventeen": 17,
    "eighteen": 18,
    "nineteen": 19,
    "twenty": 20,
}


def _count_value_supported_by_quote(value: int, quote_text: str | None) -> bool:
    """Recognize digits and spelled-out small integers in the quote."""

    if not quote_text:
        return False
    if number_supported_by_quote(float(value), quote_text):
        return True
    folded = normalize_text(quote_text)
    tokens = folded.split()
    for token in tokens:
        if _COUNT_WORD_VALUES.get(token) == value:
            return True
    return False


def _quote_has_count_language(quote_text: str | None) -> bool:
    if not quote_text:
        return False
    folded = normalize_text(quote_text)
    if any(token.isdigit() for token in numeric_tokens(folded)):
        if any_term_in_text(_PARTICIPATION_NOUNS, folded):
            return True
    if any(word in folded.split() for word in _COUNT_WORDS):
        if any_term_in_text(_PARTICIPATION_NOUNS, folded):
            return True
    return False


def _quote_supports_participation_scope(
    process_stage: str | None,
    actor_class: str | None,
    quote_text: str | None,
) -> bool:
    """Require the quote to support the claimed process_stage.

    ``actor_class`` is allowed to be ``unknown`` (per plan Task 5). When
    a specific class is claimed, the quote should ideally mention class
    cues, but Task 3's gate requires only stage and participation noun
    support to keep claim canonicalization usable for filings that say
    "parties" without naming financial/strategic/mixed. Task 5 tightens
    class support once the ``unknown`` value is allowed end-to-end.
    """

    if not quote_text:
        return False
    folded = normalize_text(quote_text)
    if process_stage:
        stage_terms = _stage_terms(process_stage)
        if not any(normalize_text(term) in folded for term in stage_terms):
            return False
    if not (any_term_in_text(_PARTICIPATION_NOUNS, folded) or "potential" in folded):
        return False
    return True


def _stage_terms(process_stage: str) -> Iterable[str]:
    table = {
        "contacted": ("contacted", "outreach", "approached"),
        "ioi": (
            "indication of interest",
            "ioi",
            "preliminary proposal",
            "interested parties",
            "interested party",
            "submitted revised",
            "submitted a revised",
            "submitted proposals",
        ),
        "ioi_submitted": (
            "indication of interest",
            "ioi",
            "preliminary proposal",
            "interested parties",
            "interested party",
            "submitted revised",
            "submitted a revised",
            "submitted proposals",
        ),
        "nda_signed": ("nda", "non-disclosure", "confidentiality agreement"),
        "first_round": (
            "first round",
            "first-round",
            "first phase",
            "preliminary proposal",
            "preliminary proposals",
        ),
        "final_round": (
            "final round",
            "final-round",
            "best and final",
            "best-and-final",
        ),
        "exclusivity": ("exclusivity", "exclusive negotiations"),
        "process": ("process", "sale process"),
    }
    return table.get(process_stage, (process_stage.replace("_", " "),))


def _class_terms(actor_class: str) -> Iterable[str]:
    table = {
        "financial": ("financial", "private equity", "sponsor"),
        "strategic": ("strategic",),
        "mixed": ("financial", "strategic"),
    }
    return table.get(actor_class, (actor_class,))


def _event_subtype_supported_by_quote(
    event_type: str, event_subtype: str, quote_text: str | None
) -> bool:
    if not quote_text:
        return False
    folded = normalize_text(quote_text)
    direct = normalize_text(event_subtype.replace("_", " "))
    if direct and direct in folded:
        return True
    synonyms = {
        "merger_agreement_executed": (
            "executed the merger agreement",
            "signed the merger agreement",
            "entered into the merger agreement",
        ),
        "ioi_submitted": (
            "indication of interest",
            "preliminary proposal",
            "non-binding proposal",
        ),
        "first_round_bid": ("first round", "first-round", "first phase"),
        "final_round_bid": ("final round", "best and final", "best-and-final"),
        "go_shop_period": ("go-shop", "go shop"),
        "amendment": ("amendment", "amended"),
        "withdrawn_by_bidder": ("withdrew", "withdrawn", "withdrew its proposal"),
        "excluded_by_target": ("excluded", "exclude"),
        "non_responsive": ("non-responsive", "did not respond"),
    }
    candidates = synonyms.get(event_subtype, ())
    if any(normalize_text(term) in folded for term in candidates):
        return True
    # Fall back to event_type words being present.
    return normalize_text(event_type.replace("_", " ")) in folded


def _looks_like_proposal_description(label: str) -> bool:
    folded = normalize_text(label)
    bad_terms = (
        "joint acquisition proposal",
        "joint proposal",
        "acquisition proposal",
        "non-binding proposal",
    )
    return any(term in folded for term in bad_terms)
