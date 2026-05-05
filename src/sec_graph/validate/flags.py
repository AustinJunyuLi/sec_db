"""Soft review flags for reviewer triage."""

from __future__ import annotations

import duckdb


def soft_flags(conn: duckdb.DuckDBPyConnection):
    return conn.execute(
        """
        SELECT flag_id, flag_type, severity, reason_code, reason
        FROM review_flags
        WHERE current = true
          AND severity IN ('review', 'info')
        ORDER BY flag_id
        """
    ).fetchall()
