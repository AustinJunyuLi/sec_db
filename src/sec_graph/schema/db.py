"""DuckDB connection and DDL helpers."""

from __future__ import annotations

from pathlib import Path

import duckdb

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_DB_PATH = REPO_ROOT / "data" / "pipeline.duckdb"


def connect(path: str | Path | None = None) -> duckdb.DuckDBPyConnection:
    db_path = DEFAULT_DB_PATH if path is None else path
    return duckdb.connect(str(db_path))


def apply_ddl(conn: duckdb.DuckDBPyConnection, ddl_text: str) -> None:
    conn.execute(ddl_text)
