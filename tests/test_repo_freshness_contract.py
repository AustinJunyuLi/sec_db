"""Repository freshness contract.

Phase 3 of the stale-scaffold hard-cleanse repair plan. These checks lock in
the cleanse so the repo cannot silently drift back into stale execution
authority, fallback language, tracked generated outputs, or registered stale
worktrees.

Design notes:

- All scans use stdlib only (`pathlib`, `re`, `subprocess`).
- Tracked-file checks (caches, generated outputs) use `git ls-files` rather
  than filesystem walks. The filesystem walk would be tautologically failing
  because pytest itself materializes `__pycache__` while collecting this very
  module.
- Doc-content checks read files line by line and skip lines whose immediate
  context (line plus 2-line window around it) explicitly disclaims the
  forbidden authority claim. The disclaimer markers below match the natural
  language used by the current active docs to retire references to deleted
  plans.
- The allowlist of files exempt from the doc/code scans is narrow on
  purpose: `docs/prior-pipeline-lessons.md` (failure history),
  retained session logs (point-in-time proof), tests that NAME forbidden
  phrases as part of an assertion, and the executing repair plan itself
  (which quotes its own forbidden phrases as requirements). The active
  authority docs (`AGENTS.md`, `CLAUDE.md`, `README.md`, `docs/spec.md`,
  `docs/llm-interface.md`) are NEVER allowlisted — they must be clean.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

ACTIVE_AUTHORITY_DOCS: tuple[Path, ...] = (
    REPO_ROOT / "AGENTS.md",
    REPO_ROOT / "CLAUDE.md",
    REPO_ROOT / "README.md",
    REPO_ROOT / "docs" / "spec.md",
    REPO_ROOT / "docs" / "llm-interface.md",
)

# Files allowed to mention forbidden phrases. These are point-in-time proof,
# failure history, the executing plan itself (which must quote its own
# requirements), or tests that assert the phrase is rejected.
ALLOWED_PATHS: tuple[Path, ...] = (
    REPO_ROOT / "docs" / "prior-pipeline-lessons.md",
    REPO_ROOT
    / "quality_reports"
    / "plans"
    / "2026-05-02_stale-scaffold-hard-cleanse-repair-plan.md",
    REPO_ROOT / "tests" / "test_repo_freshness_contract.py",
    REPO_ROOT / "tests" / "test_no_deal_specific_scaffolds.py",
)

ALLOWED_PATH_PREFIXES: tuple[Path, ...] = (
    REPO_ROOT / "quality_reports" / "session_logs",
)

# Disclaimer markers retire a stale reference. If any marker appears in the
# 2-line window around a forbidden-pattern hit, the line is treated as a
# disclaimer rather than an active claim. The current active docs use
# "no longer execution authority" / "is being deleted" / "not execution
# authority" in addition to the literal "rejected" / "superseded" markers
# called out by the Phase 3 spec.
DISCLAIMER_MARKERS: tuple[str, ...] = (
    "rejected",
    "superseded",
    "no longer",
    "not execution authority",
    "do not execute",
    "is being deleted",
    "being deleted",
    "deleted as part",
    "obsolete",
)

# The single plan name that may be called the executing plan.
CURRENT_EXECUTING_PLAN_NAME = (
    "2026-05-02_stale-scaffold-hard-cleanse-repair-plan.md"
)

# Generated-output directories that must not contain tracked files.
GENERATED_OUTPUT_DIRS: tuple[str, ...] = ("artifacts", "runs", "tmp")

# Empty for now. If a future plan force-adds sanitized proof files by exact
# repo-relative path, list them here. Keep tight: any addition is a deliberate
# escape hatch, not a wildcard.
GENERATED_OUTPUT_TRACKED_ALLOWLIST: frozenset[str] = frozenset()


def _is_allowed_path(path: Path) -> bool:
    if path in ALLOWED_PATHS:
        return True
    for prefix in ALLOWED_PATH_PREFIXES:
        try:
            path.relative_to(prefix)
        except ValueError:
            continue
        return True
    return False


def _read_lines(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8").splitlines()


def _disclaimed(lines: list[str], idx: int) -> bool:
    """Return True if the disclaimer markers appear within +/-2 lines of idx."""
    lo = max(0, idx - 2)
    hi = min(len(lines), idx + 3)
    window = " ".join(lines[lo:hi]).lower()
    return any(marker in window for marker in DISCLAIMER_MARKERS)


def _scan_active_docs(
    pattern: re.Pattern[str],
    *,
    allow_disclaimed: bool,
) -> list[tuple[Path, int, str]]:
    violations: list[tuple[Path, int, str]] = []
    for path in ACTIVE_AUTHORITY_DOCS:
        assert path.exists(), f"active authority doc missing: {path}"
        if _is_allowed_path(path):  # active docs must NEVER be allowlisted
            raise AssertionError(
                f"active authority doc is in the allowlist: {path}"
            )
        lines = _read_lines(path)
        for idx, line in enumerate(lines):
            if not pattern.search(line):
                continue
            if allow_disclaimed and _disclaimed(lines, idx):
                continue
            violations.append((path, idx + 1, line))
    return violations


def _format_violations(violations: list[tuple[Path, int, str]]) -> str:
    return "\n".join(
        f"  {path.relative_to(REPO_ROOT)}:{lineno}: {line.strip()}"
        for path, lineno, line in violations
    )


def test_active_docs_do_not_name_superseded_plans_as_execution_authority() -> None:
    superseded_filename_pattern = re.compile(
        r"(parallel-execution-plan\.md|stage-8-llm-linkflow-plan\.md)",
        re.IGNORECASE,
    )
    sole_source_pattern = re.compile(
        r"sole source of truth for execution",
        re.IGNORECASE,
    )
    # "THE executing plan" must only ever refer to the current hard-cleanse
    # repair plan. Match the phrase and require the same line OR the next
    # line to name the current plan; otherwise it is a violation.
    executing_plan_pattern = re.compile(r"THE executing plan", re.IGNORECASE)

    violations: list[tuple[Path, int, str]] = []

    violations.extend(
        _scan_active_docs(superseded_filename_pattern, allow_disclaimed=True)
    )
    violations.extend(
        _scan_active_docs(sole_source_pattern, allow_disclaimed=False)
    )

    for path in ACTIVE_AUTHORITY_DOCS:
        lines = _read_lines(path)
        for idx, line in enumerate(lines):
            if not executing_plan_pattern.search(line):
                continue
            if _disclaimed(lines, idx):
                continue
            window = " ".join(
                lines[max(0, idx - 2) : min(len(lines), idx + 3)]
            )
            if CURRENT_EXECUTING_PLAN_NAME in window:
                continue
            violations.append((path, idx + 1, line))

    assert not violations, (
        "Active authority docs must not name superseded plans as "
        "execution authority. Violations:\n"
        + _format_violations(violations)
    )


def test_active_docs_do_not_contain_stale_kickoff_phrases() -> None:
    pattern = re.compile(r"Begin Phase \d+", re.IGNORECASE)
    violations = _scan_active_docs(pattern, allow_disclaimed=True)
    assert not violations, (
        "Active authority docs must not contain stale kickoff phrases such "
        "as 'Begin Phase N' that reference the deleted parallel-execution "
        "plan. Violations:\n" + _format_violations(violations)
    )


def test_source_files_do_not_contain_compatibility_shim_language() -> None:
    pattern = re.compile(r"compatibility shim", re.IGNORECASE)
    violations: list[tuple[Path, int, str]] = []
    for sub in ("src", "scripts"):
        root = REPO_ROOT / sub
        if not root.exists():
            continue
        for path in root.rglob("*.py"):
            if _is_allowed_path(path):
                continue
            try:
                lines = _read_lines(path)
            except UnicodeDecodeError:
                continue
            for idx, line in enumerate(lines):
                if pattern.search(line):
                    violations.append((path, idx + 1, line))
    assert not violations, (
        "Source files under src/ and scripts/ must not contain "
        "'compatibility shim' language. Violations:\n"
        + _format_violations(violations)
    )


def test_generated_output_directories_have_no_tracked_files() -> None:
    result = subprocess.run(
        ["git", "ls-files", *GENERATED_OUTPUT_DIRS],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    tracked = [line for line in result.stdout.splitlines() if line.strip()]
    unexpected = [
        path for path in tracked if path not in GENERATED_OUTPUT_TRACKED_ALLOWLIST
    ]
    assert not unexpected, (
        "Generated-output directories (artifacts/, runs/, tmp/) must not "
        "contain tracked files. To intentionally retain a sanitized proof "
        "file, add its exact repo-relative path to "
        "GENERATED_OUTPUT_TRACKED_ALLOWLIST in this test. Tracked files:\n  "
        + "\n  ".join(unexpected)
    )


def test_top_level_source_and_tests_have_no_python_caches_or_dsstore() -> None:
    """Tracked Python caches and .DS_Store files must not exist anywhere
    under src/, tests/, or the repo root.

    We intentionally check tracked files via `git ls-files` instead of
    walking the filesystem: pytest itself materializes
    `tests/__pycache__/...pyc` while collecting this module, so a literal
    filesystem walk would be tautologically failing. The contract we care
    about is that none of these files are committed.
    """
    result = subprocess.run(
        ["git", "ls-files"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    tracked = result.stdout.splitlines()
    forbidden_suffixes = (".pyc", "/.DS_Store")
    forbidden_dir_segment = "/__pycache__/"
    violations: list[str] = []
    for path in tracked:
        if not (
            path.startswith("src/")
            or path.startswith("tests/")
            or "/" not in path  # repo root files
        ):
            continue
        if path.endswith(".pyc"):
            violations.append(path)
            continue
        if path == ".DS_Store" or path.endswith("/.DS_Store"):
            violations.append(path)
            continue
        if forbidden_dir_segment in f"/{path}":
            violations.append(path)
    assert not violations, (
        "Repository must not track Python caches or .DS_Store files under "
        "src/, tests/, or the repo root. Violations:\n  "
        + "\n  ".join(violations)
    )


def test_quality_reports_session_logs_readme_lists_retained_logs() -> None:
    readme = REPO_ROOT / "quality_reports" / "session_logs" / "README.md"
    assert readme.exists(), f"missing session-logs README: {readme}"
    text = readme.read_text(encoding="utf-8")
    assert "|" in text and "---" in text, (
        "session-logs README must contain a markdown table"
    )

    required_log_filenames = (
        "2026-05-02_g0-stage-1a.md",
        "2026-05-02_g1-stage-1b.md",
        "2026-05-02_g2-phase-2-merge.md",
        "2026-05-02_g3-track-c2-real-extraction.md",
        "2026-05-02_g4-stage-7-reconcile-real.md",
        "2026-05-02_g5-stage-8-linkflow.md",
        "2026-05-02_reference9_offline-proof.md",
    )
    missing = [name for name in required_log_filenames if name not in text]
    assert not missing, (
        "session-logs README must reference each retained log. Missing:\n  "
        + "\n  ".join(missing)
    )

    required_authority_refs = (
        "docs/spec.md",
        "2026-05-02_stale-scaffold-hard-cleanse-repair-plan.md",
    )
    missing_auth = [ref for ref in required_authority_refs if ref not in text]
    assert not missing_auth, (
        "session-logs README must name docs/spec.md and the hard-cleanse "
        "repair plan as current authority. Missing:\n  "
        + "\n  ".join(missing_auth)
    )


def test_superseded_plans_and_specs_are_deleted() -> None:
    must_be_absent = (
        REPO_ROOT
        / "quality_reports"
        / "plans"
        / "2026-05-02_parallel-execution-plan.md",
        REPO_ROOT
        / "quality_reports"
        / "plans"
        / "2026-05-02_stage-8-llm-linkflow-plan.md",
        REPO_ROOT
        / "quality_reports"
        / "session_logs"
        / "2026-05-02_parallel-execution-plan.md",
        REPO_ROOT
        / "quality_reports"
        / "specs"
        / "2026-05-02_pipeline-gaps-and-buyer-group-atomization.md",
        REPO_ROOT
        / "quality_reports"
        / "specs"
        / "2026-05-02_schema-direction-overfit-and-overengineering.md",
        REPO_ROOT
        / "quality_reports"
        / "session_logs"
        / "2026-05-02_reference-deal-development-note.md",
    )
    still_present = [
        str(path.relative_to(REPO_ROOT)) for path in must_be_absent if path.exists()
    ]
    assert not still_present, (
        "Superseded plans, specs, and session-log notes must be deleted. "
        "Still present:\n  " + "\n  ".join(still_present)
    )


def test_no_registered_stale_worktrees() -> None:
    result = subprocess.run(
        ["git", "worktree", "list", "--porcelain"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    worktrees: list[str] = []
    for line in result.stdout.splitlines():
        if line.startswith("worktree "):
            worktrees.append(line[len("worktree ") :])
    assert len(worktrees) == 1, (
        "Exactly one worktree (the main repo) must be registered. Found:\n  "
        + "\n  ".join(worktrees)
    )
    assert worktrees[0] == str(REPO_ROOT), (
        f"sole worktree must be the repo root {REPO_ROOT}; got {worktrees[0]}"
    )
