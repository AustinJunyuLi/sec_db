"""Hard-reset freshness contract."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

ACTIVE_AUTHORITY_DOCS = (
    REPO_ROOT / "AGENTS.md",
    REPO_ROOT / "README.md",
    REPO_ROOT / "docs" / "spec.md",
    REPO_ROOT / "docs" / "llm-interface.md",
    REPO_ROOT / "docs" / "superpowers" / "specs" / "2026-05-03-pipeline-hard-reset-design.md",
    REPO_ROOT
    / "docs"
    / "superpowers"
    / "specs"
    / "2026-05-05-semantic-disposition-validity-design.md",
)

STALE_PLAN_NAMES = (
    "2026-05-02_stale-scaffold-hard-cleanse-repair-plan.md",
    "2026-05-02_deployable-canonical-pipeline-goal.md",
    "2026-05-02_deployable-canonical-pipeline-plan.md",
    "2026-05-02_parallel-execution-plan.md",
)


def test_may_3_hard_reset_is_the_only_execution_plan() -> None:
    for name in STALE_PLAN_NAMES:
        assert not (REPO_ROOT / "quality_reports" / "plans" / name).exists()
    assert (REPO_ROOT / "docs" / "superpowers" / "specs" / "2026-05-03-pipeline-hard-reset-design.md").exists()


def test_active_docs_do_not_preserve_deleted_pipeline_contracts() -> None:
    forbidden = re.compile(
        r"\bcandidates\b|relation_candidates|evidence_ids VARCHAR\[\]|paragraph-local|three-paragraph|actor-global",
        re.IGNORECASE,
    )
    violations: list[str] = []
    for path in ACTIVE_AUTHORITY_DOCS:
        if path.name == "2026-05-03-pipeline-hard-reset-design.md":
            continue
        if not path.exists():
            continue
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if forbidden.search(line) and "hard reset" not in line.casefold() and "replaces" not in line.casefold():
                violations.append(f"{path.relative_to(REPO_ROOT)}:{lineno}:{line.strip()}")
    assert not violations, "stale active-doc contract references:\n  " + "\n  ".join(violations)


def test_spec_coverage_result_invariant_is_applicability_aware() -> None:
    text = (REPO_ROOT / "docs" / "spec.md").read_text(encoding="utf-8")

    assert "Every current coverage obligation must have exactly one current result" not in text
    assert "Every current applicable coverage obligation must have exactly one current result" in text


def test_semantic_disposition_authority_chain_is_current() -> None:
    assert not (
        REPO_ROOT
        / "docs"
        / "superpowers"
        / "specs"
        / "2026-05-04-reference9-correctness-repair-design.md"
    ).exists()
    assert not (
        REPO_ROOT
        / "quality_reports"
        / "plans"
        / "2026-05-04_p8_region_applicability_ref9_plan.md"
    ).exists()
    assert not (
        REPO_ROOT
        / "quality_reports"
        / "plans"
        / "2026-05-04_reference9_correctness_repair_plan.md"
    ).exists()

    # The 2026-05-05 semantic-disposition design is moved to legacy/. The
    # 2026-05-07 plan is the binding authority for run status, review-row
    # publication, and parallel-region extraction.
    legacy_semantic_design = (
        REPO_ROOT
        / "docs"
        / "superpowers"
        / "specs"
        / "legacy"
        / "2026-05-05-semantic-disposition-validity-design.md"
    )
    assert legacy_semantic_design.exists(), "moved to legacy/, must be preserved"
    live_semantic_design = (
        REPO_ROOT
        / "docs"
        / "superpowers"
        / "specs"
        / "2026-05-05-semantic-disposition-validity-design.md"
    )
    assert not live_semantic_design.exists(), "must not exist outside legacy/"

    plan = (
        REPO_ROOT
        / "quality_reports"
        / "plans"
        / "2026-05-07_validation_review_status_parallel_regions_plan.md"
    )
    assert plan.exists()

    spec_text = (REPO_ROOT / "docs" / "spec.md").read_text(encoding="utf-8")
    llm_text = (REPO_ROOT / "docs" / "llm-interface.md").read_text(
        encoding="utf-8"
    )
    plan_authority = plan.relative_to(REPO_ROOT).as_posix()
    assert plan_authority in spec_text
    assert plan_authority in llm_text


def test_session_logs_do_not_reference_missing_spec_section() -> None:
    text = (REPO_ROOT / "quality_reports" / "session_logs" / "README.md").read_text(encoding="utf-8")
    assert "§1A" not in text


def test_tracked_existing_files_do_not_contain_secrets_or_raw_provider_payloads() -> None:
    result = subprocess.run(["git", "ls-files"], cwd=REPO_ROOT, capture_output=True, text=True, check=True)
    patterns = {
        "openai_style_secret": re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
        "bearer_token": re.compile(r"Authorization\s*:\s*Bearer\s+\S+", re.IGNORECASE),
        "raw_response_field": re.compile(r'"raw_response"\s*:'),
        "provider_body_field": re.compile(r'"provider_body"\s*:'),
    }
    violations: list[str] = []
    for rel_path in result.stdout.splitlines():
        path = REPO_ROOT / rel_path
        if not path.exists() or path.is_dir():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for line_number, line in enumerate(text.splitlines(), start=1):
            for label, pattern in patterns.items():
                if pattern.search(line):
                    violations.append(f"{rel_path}:{line_number}: {label}")
    assert not violations, "secret/raw provider payload violations:\n  " + "\n  ".join(violations)


def test_generated_output_directories_have_no_tracked_files() -> None:
    result = subprocess.run(["git", "ls-files", "artifacts", "runs", "tmp"], cwd=REPO_ROOT, capture_output=True, text=True, check=True)
    tracked_existing = [path for path in result.stdout.splitlines() if (REPO_ROOT / path).exists()]
    assert not tracked_existing, "generated output files are tracked:\n  " + "\n  ".join(tracked_existing)


def test_no_registered_stale_worktrees() -> None:
    result = subprocess.run(["git", "worktree", "list", "--porcelain"], cwd=REPO_ROOT, capture_output=True, text=True, check=True)
    worktrees = [line.removeprefix("worktree ") for line in result.stdout.splitlines() if line.startswith("worktree ")]
    assert worktrees == [str(REPO_ROOT)]
