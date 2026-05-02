import hashlib
import json
from pathlib import Path

from sec_graph.cli.run_cmd import main as run_main
from sec_graph.extract.rules import run_rules
from sec_graph.ingest.pipeline import ingest_examples
from sec_graph.project.bidder_rows import bidder_rows
from sec_graph.reconcile.pipeline import reconcile_all
from sec_graph.schema import connect, init_schema
from sec_graph.validate.integrity import validate_database

GOLDEN_BIDDER_ROWS_PATH = Path("tests/fixtures/reconcile/real_bidder_rows_golden.json")


def _loaded_candidate_conn():
    conn = connect(":memory:")
    init_schema(conn)
    filings = ingest_examples(conn, examples_dir=Path("data/examples"))
    for filing in filings:
        run_rules(conn, filing_id=filing.filing_id)
    return conn


def _row_hashes(conn, table_name: str) -> list[str]:
    rows = conn.execute(f"SELECT * FROM {table_name} ORDER BY 1").fetchall()
    payloads = [json.dumps(row, sort_keys=True, default=str) for row in rows]
    return [hashlib.sha256(payload.encode("utf-8")).hexdigest() for payload in payloads]


def _projection_hash(rows: list[dict[str, object]]) -> str:
    payload = json.dumps(rows, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def test_real_reconcile_produces_valid_canonical_projection() -> None:
    conn = _loaded_candidate_conn()

    reconcile_all(conn, run_id="stage7-test")

    result = validate_database(conn)
    assert result.passed, result.hard_failures
    assert {
        row[0]
        for row in conn.execute("SELECT deal_slug FROM deals ORDER BY deal_slug").fetchall()
    } == {"petsmart-inc", "providence-worcester", "saks", "zep"}
    assert conn.execute("SELECT count(*) FROM process_cycles").fetchone()[0] >= 4

    rows = bidder_rows(conn)
    golden = json.loads(GOLDEN_BIDDER_ROWS_PATH.read_text(encoding="utf-8"))
    assert len(rows) == golden["row_count"]
    assert _projection_hash(rows) == golden["projection_sha256"]

    actual = {(row["deal_slug"], row["actor_label"]) for row in rows}
    assert {
        ("petsmart-inc", "Buyer Group"),
        ("petsmart-inc", "Bidder 2"),
        ("saks", "Hudson\u2019s Bay"),
        ("saks", "Sponsor A"),
        ("saks", "Sponsor E"),
        ("providence-worcester", "G&W"),
        ("providence-worcester", "Party B"),
        ("zep", "Party X"),
        ("zep", "New Mountain Capital"),
    } <= actual
    required_projection_rows = [
        {key: row[key] for key in required_row}
        for row in rows
        for required_row in golden["required_rows"]
        if row["deal_slug"] == required_row["deal_slug"] and row["actor_label"] == required_row["actor_label"]
    ]
    for required_row in golden["required_rows"]:
        assert required_row in required_projection_rows
    assert all(row["cycle_visibility"] is not None for row in rows)


def test_real_reconcile_is_deterministic() -> None:
    first = _loaded_candidate_conn()
    second = _loaded_candidate_conn()
    for conn in (first, second):
        reconcile_all(conn, run_id="stage7-test")

    for table_name in (
        "deals",
        "process_cycles",
        "actors",
        "events",
        "event_actor_links",
        "judgments",
        "participation_counts",
    ):
        assert _row_hashes(first, table_name) == _row_hashes(second, table_name)


def test_run_cli_executes_ingest_extract_reconcile_validate_project(tmp_path) -> None:
    db_path = tmp_path / "pipeline.duckdb"
    run_dir = tmp_path / "run"

    assert run_main(["--all", "--db", str(db_path), "--run-dir", str(run_dir)]) == 0

    report = json.loads((run_dir / "validation_report.json").read_text(encoding="utf-8"))
    assert report["passed"] is True
    assert (run_dir / "bidder_rows.jsonl").read_text(encoding="utf-8").strip()
    assert (run_dir / "run_memo.md").read_text(encoding="utf-8").startswith("# sec_graph Run Memo")
