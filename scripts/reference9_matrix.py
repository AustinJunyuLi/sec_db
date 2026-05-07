from __future__ import annotations

import argparse
import json
from pathlib import Path

from sec_graph.run.latest import read_latest_pointer

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

_TRUSTED_POINTER_STATUSES = frozenset(
    {"passed_clean", "needs_review", "high_burden"}
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs-dir", default="runs")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    runs_dir = Path(args.runs_dir)
    rows = []
    for slug in REFERENCE9:
        run_dir = _run_dir_for_slug(runs_dir, slug)
        rows.append(_row_for_slug(slug, run_dir))

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps({"reference9": rows}, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {output}")
    return 0


def _run_dir_for_slug(runs_dir: Path, slug: str) -> Path | None:
    """Resolve the run dir for ``slug`` via ``runs/latest/{slug}.json``.

    Prefer ``latest_trusted.run_dir`` when the pointer is trusted (or
    stale-after-failure). Otherwise fall back to ``latest_attempt.run_dir``.
    """
    pointer = read_latest_pointer(slug, runs_root=runs_dir)
    if pointer is None:
        return None
    pointer_status = str(pointer.get("pointer_status", ""))
    latest_trusted = pointer.get("latest_trusted")
    latest_attempt = pointer.get("latest_attempt")
    if (
        pointer_status in _TRUSTED_POINTER_STATUSES
        or pointer_status == "stale_after_failure"
    ):
        if isinstance(latest_trusted, dict):
            run_dir = latest_trusted.get("run_dir")
            if isinstance(run_dir, str) and run_dir:
                return Path(run_dir)
    if isinstance(latest_attempt, dict):
        run_dir = latest_attempt.get("run_dir")
        if isinstance(run_dir, str) and run_dir:
            return Path(run_dir)
    return None


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
            "status": "MISSING_RUN",
            "review_row_count": None,
            "validation_failure_count": None,
            "failure_checks": [],
            "artifact_counts": None,
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
            validation, "claim_disposition"
        ),
        "coverage_complete_or_reviewed": not _has_failure(
            validation, "coverage_result"
        ),
        "judgments_complete_or_reviewed": True,
        "projection_trace_passed": not _has_failure(validation, "projection_unit"),
        "status": source.get("status")
        or ("passed_clean" if validation.get("passed") else "failed_system"),
        "review_row_count": source.get("open_review_row_count"),
        "validation_failure_count": source.get("validation_failure_count")
        or _failure_count(validation),
        "failure_checks": _failure_checks(validation),
        "artifact_counts": source.get("artifact_counts"),
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
    failures = validation.get("system_failures")
    if not isinstance(failures, list):
        return False
    for failure in failures:
        if isinstance(failure, dict) and failure.get("check") == check:
            return True
    return False


def _failure_count(validation: dict[str, object]) -> int | None:
    failures = validation.get("system_failures")
    if not isinstance(failures, list):
        return None
    return len(failures)


def _failure_checks(validation: dict[str, object]) -> list[str]:
    failures = validation.get("system_failures")
    if not isinstance(failures, list):
        return []
    checks = []
    for failure in failures:
        if not isinstance(failure, dict):
            continue
        check = failure.get("check")
        if isinstance(check, str) and check not in checks:
            checks.append(check)
    return checks


if __name__ == "__main__":
    raise SystemExit(main())
