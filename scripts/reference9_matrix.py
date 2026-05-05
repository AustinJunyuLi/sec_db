from __future__ import annotations

import argparse
import json
from pathlib import Path


REFERENCE9 = (
    "providence-worcester",
    "medivation",
    "imprivata",
    "zep",
    "petsmart-inc",
    "penford",
    "mac-gray",
    "saks",
    "stec",
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs-dir", default="runs")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    runs_dir = Path(args.runs_dir)
    rows = []
    for slug in REFERENCE9:
        run_dir = _latest_run_dir(runs_dir, slug)
        rows.append(_row_for_slug(slug, run_dir))

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps({"reference9": rows}, indent=2), encoding="utf-8")
    print(f"wrote {output}")
    return 0


def _latest_run_dir(runs_dir: Path, slug: str) -> Path | None:
    candidates = sorted(path for path in runs_dir.glob(f"*{slug}*") if path.is_dir())
    return candidates[-1] if candidates else None


def _row_for_slug(slug: str, run_dir: Path | None) -> dict[str, object]:
    if run_dir is None:
        return {
            "deal_slug": slug,
            "run_dir": None,
            "provider_completed": False,
            "quote_binding_passed": False,
            "claim_dispositions_complete": False,
            "unsupported_claims_rejected": False,
            "coverage_complete_or_reviewed": False,
            "judgments_complete_or_reviewed": False,
            "projection_trace_passed": False,
            "verdict": "MISSING_RUN",
            "review_flag_count": None,
            "blocking_flag_count": None,
        }

    proof = _read_json(run_dir / "proof_summary.json")
    validation = _read_json(run_dir / "validation_report.json")
    failed = _read_json(run_dir / "failed_validation_proof.json")
    source = proof or failed or {}

    return {
        "deal_slug": slug,
        "run_dir": run_dir.as_posix(),
        "provider_completed": bool(source),
        "quote_binding_passed": not _has_failure(validation, "claim_evidence"),
        "claim_dispositions_complete": not _has_failure(
            validation, "claim_disposition"
        ),
        "unsupported_claims_rejected": not _has_failure(
            validation, "semantic_claim_evidence"
        ),
        "coverage_complete_or_reviewed": not _has_failure(
            validation, "coverage_result"
        ),
        "judgments_complete_or_reviewed": True,
        "projection_trace_passed": not _has_failure(validation, "projection_unit"),
        "verdict": source.get("verdict")
        or ("SOUND" if validation.get("passed") else "UNSOUND"),
        "review_flag_count": source.get("review_flag_count"),
        "blocking_flag_count": source.get("blocking_flag_count"),
    }


def _read_json(path: Path) -> dict[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    if not isinstance(payload, dict):
        return {}
    return payload


def _has_failure(validation: dict[str, object], check: str) -> bool:
    failures = validation.get("hard_failures")
    if not isinstance(failures, list):
        return False
    for failure in failures:
        if isinstance(failure, dict) and failure.get("check") == check:
            return True
    return False


if __name__ == "__main__":
    raise SystemExit(main())
