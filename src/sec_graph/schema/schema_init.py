"""Schema initialization."""

from __future__ import annotations

import duckdb

from .db import apply_ddl
from .models import FILINGS_DDL, RUN_METADATA_DDL


def init_schema(conn: duckdb.DuckDBPyConnection) -> None:
    apply_ddl(conn, FILINGS_DDL)
    apply_ddl(conn, RUN_METADATA_DDL)
