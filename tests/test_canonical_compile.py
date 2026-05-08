"""Phase 7 (US-008) — deterministic canonical compiler."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import duckdb
import pytest

from sec_review_compiler.canonical import (
    CanonicalCompiler,
    CompileResult,
    canonical_row_id,
)
from sec_review_compiler.filing.examples import SYNTHETIC_FILING_PATH
from sec_review_compiler.orchestration import (
    OfflineConfidentialityExtractor,
    OfflineFakeVerifier,
    Orchestrator,
    SliceResult,
)
from sec_review_compiler.store.repository import (
    Conflict,
    CoverageCheck,
    DealRoomRepository,
)


# ---------------------------------------------------------------- fixtures

RUN_ID = "20260508T140000Z_synthetic-demo_deadbeef"


def _run_dir(tmp_path: Path) -> Path:
    p = tmp_path / RUN_ID
    p.mkdir(parents=True, exist_ok=True)
    return p


@pytest.fixture()
def compiled_slice(tmp_path: Path) -> tuple[SliceResult, CompileResult]:
    """Run the offline slice and compile canonical rows."""
    orch = Orchestrator(
        deal_slug="synthetic-demo",
        extractor=OfflineConfidentialityExtractor(),
        verifier=OfflineFakeVerifier(),
    )
    result = orch.run_synthetic_vertical_slice(
        run_dir=_run_dir(tmp_path),
        filing_path=SYNTHETIC_FILING_PATH,
    )
    conn = duckdb.connect(str(result.db_path))
    repo = DealRoomRepository(conn)
    compiler = CanonicalCompiler(
        repo,
        run_id=result.run_id,
        deal_slug="synthetic-demo",
        compiled_at_run_clock=datetime(2026, 5, 8, 14, 0, 0, tzinfo=timezone.utc),
    )
    compile_result = compiler.compile()
    yield result, compile_result
    conn.close()


# ---------------------------------------------------------------- happy path

class TestHappyCompile:
    def test_publication_succeeds(self, compiled_slice) -> None:
        _slice, result = compiled_slice
        assert result.published is True
        assert result.refusals == ()

    def test_canonical_rows_present(self, compiled_slice) -> None:
        slice_result, result = compiled_slice
        conn = duckdb.connect(str(slice_result.db_path))
        rows = conn.execute(
            "SELECT canonical_table, COUNT(*) FROM canonical_rows GROUP BY canonical_table"
        ).fetchall()
        conn.close()
        counts = dict(rows)
        # Deal, filing, source_span, event must all be present.
        assert counts.get("deal") == 1
        assert counts.get("filing") == 1
        assert counts.get("source_span", 0) >= 1
        assert counts.get("event", 0) >= 1

    def test_event_has_row_evidence(self, compiled_slice) -> None:
        slice_result, _ = compiled_slice
        conn = duckdb.connect(str(slice_result.db_path))
        rows = conn.execute(
            """
            SELECT cr.canonical_row_id, cre.attempt_id, cre.evidence_id, cre.ordinal
            FROM canonical_rows cr
            JOIN canonical_row_evidence cre USING (canonical_row_id)
            WHERE cr.canonical_table = 'event'
            ORDER BY cre.ordinal
            """
        ).fetchall()
        conn.close()
        assert rows, "compiled event must have row evidence"
        for _row_id, attempt_id, evidence_id, _ord in rows:
            assert attempt_id  # bound to an actual attempt
            assert evidence_id


# ---------------------------------------------------------------- determinism

class TestDeterministicCompile:
    def test_recompile_produces_identical_row_ids(self, tmp_path: Path) -> None:
        orch = Orchestrator(
            deal_slug="synthetic-demo",
            extractor=OfflineConfidentialityExtractor(),
            verifier=OfflineFakeVerifier(),
        )
        slice_result = orch.run_synthetic_vertical_slice(
            run_dir=_run_dir(tmp_path),
            filing_path=SYNTHETIC_FILING_PATH,
        )
        conn = duckdb.connect(str(slice_result.db_path))
        repo = DealRoomRepository(conn)
        compiler = CanonicalCompiler(
            repo,
            run_id=slice_result.run_id,
            deal_slug="synthetic-demo",
            compiled_at_run_clock=datetime(2026, 5, 8, 14, 0, 0, tzinfo=timezone.utc),
        )

        first = compiler.compile()
        first_ids = {t: tuple(sorted(ids)) for t, ids in first.canonical_row_ids.items()}

        # Delete the canonical rows entirely, then recompile.
        conn.execute("DELETE FROM canonical_row_evidence")
        conn.execute("DELETE FROM canonical_rows")

        second = compiler.compile()
        second_ids = {t: tuple(sorted(ids)) for t, ids in second.canonical_row_ids.items()}
        conn.close()

        assert second.published is True
        assert first_ids == second_ids

    def test_canonical_row_id_helper_is_pure(self) -> None:
        a = canonical_row_id(
            table="event",
            run_id="r1",
            deal_slug="d1",
            source_ids=["e2", "e1"],
            payload_keys=["k=v"],
        )
        b = canonical_row_id(
            table="event",
            run_id="r1",
            deal_slug="d1",
            source_ids=["e1", "e2"],  # reordered → still equal
            payload_keys=["k=v"],
        )
        assert a == b
        c = canonical_row_id(
            table="event",
            run_id="r2",  # different run id → different id
            deal_slug="d1",
            source_ids=["e1", "e2"],
            payload_keys=["k=v"],
        )
        assert a != c


# ---------------------------------------------------------------- unbound attempts never compile

class TestUnboundAttemptsNeverCompile:
    def test_unaccepted_attempts_excluded(self, tmp_path: Path) -> None:
        # Use an always-reject verifier so no attempt reaches 'accepted'.
        from tests.test_orchestrator_vertical_slice import _AlwaysRejectVerifier  # type: ignore  # noqa: E501

        orch = Orchestrator(
            deal_slug="synthetic-demo",
            extractor=OfflineConfidentialityExtractor(),
            verifier=_AlwaysRejectVerifier(),
        )
        slice_result = orch.run_synthetic_vertical_slice(
            run_dir=_run_dir(tmp_path),
            filing_path=SYNTHETIC_FILING_PATH,
        )
        assert slice_result.accepted_attempt_ids == ()
        conn = duckdb.connect(str(slice_result.db_path))
        repo = DealRoomRepository(conn)
        compiler = CanonicalCompiler(
            repo,
            run_id=slice_result.run_id,
            deal_slug="synthetic-demo",
            compiled_at_run_clock=datetime(2026, 5, 8, 14, 0, 0, tzinfo=timezone.utc),
        )
        result = compiler.compile()
        # No attempts → publish succeeds with only the deal row.
        # The compiler does not emit events from rejected/escalated attempts.
        events = conn.execute(
            "SELECT COUNT(*) FROM canonical_rows WHERE canonical_table='event'"
        ).fetchone()[0]
        conn.close()
        assert result.published is True
        assert events == 0


# ---------------------------------------------------------------- payload offsets ignored

class TestModelOwnedOffsetsImpossible:
    def test_payload_offsets_are_ignored_by_compiler(self, compiled_slice) -> None:
        slice_result, _ = compiled_slice
        conn = duckdb.connect(str(slice_result.db_path))
        # Tamper each accepted attempt's payload_json with fake offsets:
        # parse → inject → re-serialize, so the JSON stays valid.
        accepted = conn.execute(
            "SELECT attempt_id, payload_json FROM claim_attempts WHERE status='accepted'"
        ).fetchall()
        for attempt_id, payload_json in accepted:
            payload = json.loads(payload_json)
            payload["char_start"] = 999999
            payload["char_end"] = 999999
            conn.execute(
                "UPDATE claim_attempts SET payload_json = ? WHERE attempt_id = ?",
                (json.dumps(payload, sort_keys=True), attempt_id),
            )
        repo = DealRoomRepository(conn)
        compiler = CanonicalCompiler(
            repo,
            run_id=slice_result.run_id,
            deal_slug="synthetic-demo",
            compiled_at_run_clock=datetime(2026, 5, 8, 14, 0, 0, tzinfo=timezone.utc),
        )
        result = compiler.compile()
        assert result.published is True

        # Read back the canonical source_span: char_start/char_end come from
        # evidence_bindings, not the tampered payload.
        rows = conn.execute(
            "SELECT payload_json FROM canonical_rows WHERE canonical_table='source_span'"
        ).fetchall()
        conn.close()
        assert rows
        for (payload,) in rows:
            data = json.loads(payload)
            assert data["char_start"] != 999999
            assert data["char_end"] != 999999


# ---------------------------------------------------------------- refusal gates

class TestRefusalGates:
    def test_failed_to_check_coverage_blocks_publication(self, compiled_slice, tmp_path: Path) -> None:
        slice_result, _ = compiled_slice
        # Inject a failed_to_check coverage row, then re-run the compiler.
        conn = duckdb.connect(str(slice_result.db_path))
        repo = DealRoomRepository(conn)
        repo.insert_coverage_check(
            CoverageCheck(
                coverage_id="cov:bids:failed",
                deal_slug="synthetic-demo",
                category="bids",
                subcategory=None,
                check_state="failed_to_check",
                evidence_id=None,
                attempt_id=None,
                required=True,
                notes=None,
                created_at_run_clock=datetime(2026, 5, 8, 14, 0, 0, tzinfo=timezone.utc),
            )
        )
        compiler = CanonicalCompiler(
            repo,
            run_id=slice_result.run_id,
            deal_slug="synthetic-demo",
            compiled_at_run_clock=datetime(2026, 5, 8, 14, 0, 0, tzinfo=timezone.utc),
        )
        # Wipe prior canonical rows so the test isolates the refusal.
        conn.execute("DELETE FROM canonical_row_evidence")
        conn.execute("DELETE FROM canonical_rows")
        result = compiler.compile()
        conn.close()
        assert result.published is False
        codes = {r.code for r in result.refusals}
        assert "coverage_failed_to_check" in codes

    def test_open_conflict_blocks_publication(self, compiled_slice) -> None:
        slice_result, _ = compiled_slice
        conn = duckdb.connect(str(slice_result.db_path))
        repo = DealRoomRepository(conn)
        repo.insert_conflict(
            Conflict(
                conflict_id="conflict:1",
                deal_slug="synthetic-demo",
                conflict_type="contradictory_dates",
                attempt_ids=("a", "b"),
                description="test conflict",
                resolution_state="open",
                created_at_run_clock=datetime(2026, 5, 8, 14, 0, 0, tzinfo=timezone.utc),
            )
        )
        compiler = CanonicalCompiler(
            repo,
            run_id=slice_result.run_id,
            deal_slug="synthetic-demo",
            compiled_at_run_clock=datetime(2026, 5, 8, 14, 0, 0, tzinfo=timezone.utc),
        )
        conn.execute("DELETE FROM canonical_row_evidence")
        conn.execute("DELETE FROM canonical_rows")
        result = compiler.compile()
        conn.close()
        assert result.published is False
        codes = {r.code for r in result.refusals}
        assert "blocking_conflict" in codes
