"""Soft ambiguity flags for reviewer triage."""

from __future__ import annotations

from dataclasses import dataclass

import duckdb


@dataclass(frozen=True)
class SoftFlag:
    flag_type: str
    table_name: str
    row_id: str
    detail: str


def soft_flags(conn: duckdb.DuckDBPyConnection) -> list[SoftFlag]:
    flags: list[SoftFlag] = []
    for row in conn.execute(
        """
        SELECT judgment_id, judgment_type, confidence, alternative_value, judgment_value
        FROM judgments
        ORDER BY judgment_id
        """
    ).fetchall():
        judgment_id, judgment_type, confidence, alternative_value, judgment_value = row
        if confidence == "low":
            flags.append(
                SoftFlag(
                    flag_type="low_confidence_judgment",
                    table_name="judgments",
                    row_id=judgment_id,
                    detail=f"{judgment_type} confidence is low",
                )
            )
        if alternative_value is not None:
            flags.append(
                SoftFlag(
                    flag_type="alternative_value",
                    table_name="judgments",
                    row_id=judgment_id,
                    detail=f"{judgment_type} alternative={alternative_value}",
                )
            )
        if judgment_type == "formal_boundary" and judgment_value in {"none_observed", "null", ""}:
            flags.append(
                SoftFlag(
                    flag_type="no_boundary_cycle",
                    table_name="judgments",
                    row_id=judgment_id,
                    detail="formal boundary is not observed",
                )
            )
    for row in conn.execute(
        """
        SELECT participation_count_id, actor_creation_required
        FROM participation_counts
        ORDER BY participation_count_id
        """
    ).fetchall():
        count_id, actor_creation_required = row
        if actor_creation_required != "required":
            flags.append(
                SoftFlag(
                    flag_type="hidden_individual_bids",
                    table_name="participation_counts",
                    row_id=count_id,
                    detail=f"actor creation is {actor_creation_required}",
                )
            )
    return flags
