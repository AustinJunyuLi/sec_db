"""Reviewer-facing review_rows projection."""

from __future__ import annotations

import duckdb


def soft_flags(conn: duckdb.DuckDBPyConnection):
    """Return the open review rows in deterministic order."""

    return conn.execute(
        """
        SELECT review_row_id, review_type, severity, reason_code, message
        FROM review_rows
        WHERE review_status = 'open'
        ORDER BY review_row_id
        """
    ).fetchall()
