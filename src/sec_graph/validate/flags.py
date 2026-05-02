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
    for judgment_id, projection_name, actor_id, included in conn.execute(
        """
        SELECT judgment_id, projection_name, actor_id, included
        FROM judgments
        WHERE judgment_kind = 'projection_eligibility'
        ORDER BY judgment_id
        """
    ).fetchall():
        if included is False:
            flags.append(
                SoftFlag(
                    flag_type="projection_exclusion",
                    table_name="judgments",
                    row_id=judgment_id,
                    detail=f"{projection_name} excludes actor_id={actor_id}",
                )
            )
    for count_id, anonymous_remainder_count in conn.execute(
        """
        SELECT participation_count_id, anonymous_remainder_count
        FROM participation_counts
        ORDER BY participation_count_id
        """
    ).fetchall():
        if anonymous_remainder_count:
            flags.append(
                SoftFlag(
                    flag_type="count_only_cohort",
                    table_name="participation_counts",
                    row_id=count_id,
                    detail=f"{anonymous_remainder_count} anonymous participant(s) remain aggregate only",
                )
            )
    return flags
