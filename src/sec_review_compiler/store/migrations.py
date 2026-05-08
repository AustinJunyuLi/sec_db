"""Apply the deal-room schema to a DuckDB connection."""

from __future__ import annotations

from typing import Any

from .schema import DDL_STATEMENTS, EXPECTED_TABLE_NAMES


def apply_schema(connection: Any) -> None:
    """Create deal-room tables on `connection` (idempotent).

    `connection` is a `duckdb.DuckDBPyConnection`. We accept `Any` to keep
    this module import-light: tests and the wider package may import
    schema-only without pulling in DuckDB if duckdb is unused at runtime.
    """
    for ddl in DDL_STATEMENTS:
        connection.execute(ddl)
    # Sanity check: every expected table must be present after apply.
    rows = connection.execute(
        "SELECT lower(table_name) FROM information_schema.tables "
        "WHERE lower(table_schema) IN ('main', 'temp')"
    ).fetchall()
    present = {r[0] for r in rows}
    missing = [name for name in EXPECTED_TABLE_NAMES if name not in present]
    if missing:
        raise RuntimeError(f"schema migration left tables missing: {missing!r}")
