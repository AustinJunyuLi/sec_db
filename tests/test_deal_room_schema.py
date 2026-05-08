"""Phase 4 (US-005) — deal-room DuckDB schema."""

from __future__ import annotations

from datetime import datetime, timezone

import duckdb
import pytest

from sec_review_compiler.store import (
    COVERAGE_STATES,
    DDL_STATEMENTS,
    DealRoomRepository,
    LIFECYCLE_STATES,
    SourceRecord,
    VERDICT_TYPES,
    apply_schema,
)
from sec_review_compiler.store.schema import EXPECTED_TABLE_NAMES


@pytest.fixture()
def conn():
    c = duckdb.connect(":memory:")
    apply_schema(c)
    yield c
    c.close()


class TestSchemaShape:
    def test_all_expected_tables_exist(self, conn) -> None:
        rows = conn.execute(
            "SELECT lower(table_name) FROM information_schema.tables "
            "WHERE lower(table_schema) IN ('main', 'temp')"
        ).fetchall()
        names = {r[0] for r in rows}
        missing = [t for t in EXPECTED_TABLE_NAMES if t not in names]
        assert not missing, f"missing tables: {missing!r}"

    def test_apply_schema_is_idempotent(self, conn) -> None:
        # Re-apply should not raise.
        apply_schema(conn)

    def test_lifecycle_states_have_expected_members(self) -> None:
        # The full state set required by the design is present.
        required = {
            "proposed", "binding_failed", "bound",
            "verified_confirmed", "verified_partial", "verified_rejected",
            "escalated", "consistent", "accepted", "superseded",
        }
        assert required.issubset(set(LIFECYCLE_STATES))

    def test_verdict_types_have_expected_members(self) -> None:
        required = {"confirm", "partial", "reject", "ambiguous", "malformed"}
        assert required.issubset(set(VERDICT_TYPES))

    def test_coverage_states_have_failed_to_check(self) -> None:
        assert "failed_to_check" in COVERAGE_STATES

    def test_ddl_statements_count(self) -> None:
        # Sanity check: the number of DDL statements matches the expected
        # tables (with the status-history bookkeeping table included).
        assert len(DDL_STATEMENTS) == len(EXPECTED_TABLE_NAMES)


class TestSourceRecordInsert:
    def test_round_trip(self, conn) -> None:
        repo = DealRoomRepository(conn)
        ts = datetime(2026, 5, 8, 13, 0, 0, tzinfo=timezone.utc)
        record = SourceRecord(
            record_type="paragraph",
            record_id="rec:p0001",
            filing_id="f:1",
            payload_json='{"text":"x"}',
            char_start=0,
            char_end=10,
            created_at=ts,
        )
        repo.insert_source_record(record)
        rows = conn.execute(
            "SELECT source_record_id, record_type, char_start, char_end FROM source_records"
        ).fetchall()
        assert rows == [("rec:p0001", "paragraph", 0, 10)]

    def test_appendonly_rejects_duplicate_pk(self, conn) -> None:
        repo = DealRoomRepository(conn)
        ts = datetime(2026, 5, 8, 13, 0, 0, tzinfo=timezone.utc)
        record = SourceRecord(
            record_type="paragraph", record_id="rec:p0001", filing_id="f:1",
            payload_json="{}", char_start=0, char_end=1, created_at=ts,
        )
        repo.insert_source_record(record)
        with pytest.raises(Exception):
            repo.insert_source_record(record)
