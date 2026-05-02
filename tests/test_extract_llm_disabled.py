import hashlib
import json
from pathlib import Path

import pytest

from sec_graph.extract.pipeline import run_extract
from sec_graph.ingest.pipeline import ingest_examples
from sec_graph.schema import connect, init_schema

GOLDEN_PATH = Path("tests/fixtures/extract/real_candidate_golden.json")


def _projection_hash(conn, slug: str) -> tuple[int, str]:
    rows = conn.execute(
        """
        SELECT candidate_id, candidate_type, raw_value, normalized_value, confidence, status
        FROM candidates
        JOIN filings USING (filing_id)
        WHERE deal_slug = ?
        ORDER BY CAST(regexp_extract(candidate_id, 'candidate_(\\d+)$', 1) AS INTEGER)
        """,
        [slug],
    ).fetchall()
    projection = [
        {
            "candidate_id": row[0],
            "candidate_type": row[1],
            "raw_value": row[2],
            "normalized_value": row[3],
            "confidence": row[4],
            "status": row[5],
        }
        for row in rows
    ]
    payload = json.dumps(projection, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return len(projection), hashlib.sha256(payload.encode("utf-8")).hexdigest()


def test_llm_disabled_run_extract_matches_rules_only_golden() -> None:
    conn = connect(":memory:")
    init_schema(conn)
    filings = ingest_examples(conn, examples_dir=Path("data/examples"))
    for filing in filings:
        run_extract(conn, filing_id=filing.filing_id)

    golden = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))
    for slug, expected in golden.items():
        row_count, digest = _projection_hash(conn, slug)
        assert row_count == expected["row_count"]
        assert digest == expected["projection_sha256"]


def test_extract_help_exposes_opt_in_llm_flags(capsys) -> None:
    from sec_graph.cli.extract_cmd import build_parser

    with pytest.raises(SystemExit) as raised:
        build_parser().parse_args(["--help"])

    assert raised.value.code == 0
    help_text = capsys.readouterr().out
    assert "--llm-provider" in help_text
    assert "--llm-model" in help_text
    assert "--llm-reasoning-effort" in help_text
    assert "--llm-limit" in help_text
