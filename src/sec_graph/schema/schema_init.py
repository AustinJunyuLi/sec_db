"""Schema initialization."""

from __future__ import annotations

import duckdb

from .db import apply_ddl
from .models import (
    CANONICAL_DDL,
    EXTRACTION_DDL,
    FILINGS_DDL,
    JUDGMENTS_DDL,
    PARTICIPATION_COUNTS_DDL,
    RUN_METADATA_DDL,
)


def init_schema(conn: duckdb.DuckDBPyConnection) -> None:
    apply_ddl(conn, FILINGS_DDL)
    apply_ddl(conn, RUN_METADATA_DDL)
    apply_ddl(conn, EXTRACTION_DDL)
    apply_ddl(conn, CANONICAL_DDL)
    apply_ddl(conn, JUDGMENTS_DDL)
    apply_ddl(conn, PARTICIPATION_COUNTS_DDL)
