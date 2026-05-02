"""Write projection files for a run directory."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import duckdb

from .bidder_rows import bidder_rows


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.write_text(
        "\n".join(json.dumps(row, separators=(",", ":")) for row in rows) + "\n",
        encoding="utf-8",
    )


def _write_csv(path: Path, rows: list[dict[str, object]], fieldnames: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field) for field in fieldnames})


def write_projection_outputs(conn: duckdb.DuckDBPyConnection, run_dir: Path) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    rows = bidder_rows(conn)
    _write_jsonl(run_dir / "bidder_rows.jsonl", rows)
    cycles = [
        {"cycle_id": row[0], "deal_id": row[1], "cycle_label": row[2]}
        for row in conn.execute(
            "SELECT cycle_id, deal_id, cycle_label FROM process_cycles ORDER BY cycle_id"
        ).fetchall()
    ]
    deals = [
        {"deal_id": row[0], "deal_slug": row[1], "announcement_date": row[2]}
        for row in conn.execute("SELECT deal_id, deal_slug, announcement_date FROM deals ORDER BY deal_id").fetchall()
    ]
    _write_jsonl(run_dir / "auctions.jsonl", cycles)
    _write_csv(run_dir / "cycle_summary.csv", cycles, ["cycle_id", "deal_id", "cycle_label"])
    _write_csv(run_dir / "bidder_summary.csv", rows, ["deal_slug", "cycle_id", "actor_id", "actor_label", "admitted"])
    _write_csv(run_dir / "deal_index.csv", deals, ["deal_id", "deal_slug", "announcement_date"])
    _write_csv(run_dir / "review_master.csv", rows, ["deal_slug", "cycle_id", "actor_id", "confidence_min"])
    (run_dir / "run_memo.md").write_text(
        "# sec_graph Run Memo\n\n"
        f"- Deals: {len(deals)}\n"
        f"- Cycles: {len(cycles)}\n"
        f"- Bidder rows: {len(rows)}\n",
        encoding="utf-8",
    )
