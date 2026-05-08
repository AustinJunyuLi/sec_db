"""Deal-room schema constants: lifecycle, verdicts, coverage, and DuckDB DDL.

The schema is intentionally append-oriented: corrections create new rows
in `claim_attempts` (with `supersedes_attempt_id` set) rather than
mutating accepted claims, and verifier verdicts are insert-only (multiple
verdicts per attempt are normal). Aggregation is recorded as fresh rows
in `verdict_aggregates` so the policy can be re-derived from the inputs.
"""

from __future__ import annotations

# ---------------------------------------------------------------- lifecycle

# The full set of lifecycle states a `claim_attempt` can occupy.
LIFECYCLE_STATES: tuple[str, ...] = (
    "proposed",
    "binding_failed",
    "bound",
    "verified_confirmed",
    "verified_partial",
    "verified_rejected",
    "escalated",
    "consistent",
    "accepted",
    "superseded",
)

# Allowed transitions. A state with an empty allowed set is terminal.
TRANSITIONS: dict[str, frozenset[str]] = {
    "proposed": frozenset({"bound", "binding_failed"}),
    "binding_failed": frozenset(),
    "bound": frozenset(
        {"verified_confirmed", "verified_partial", "verified_rejected", "escalated"}
    ),
    "verified_confirmed": frozenset({"consistent", "escalated", "superseded"}),
    "verified_partial": frozenset({"superseded", "escalated"}),
    "verified_rejected": frozenset({"escalated", "superseded"}),
    "escalated": frozenset({"consistent", "accepted", "superseded"}),
    "consistent": frozenset({"accepted", "escalated"}),
    "accepted": frozenset({"superseded"}),
    "superseded": frozenset(),
}

TERMINAL_STATES: frozenset[str] = frozenset(
    state for state, nexts in TRANSITIONS.items() if not nexts
)


# ---------------------------------------------------------------- verdicts

# The verdict vocabulary an independent verifier may emit (design spec §10.5).
VERDICT_TYPES: tuple[str, ...] = (
    "confirm",
    "partial",
    "reject",
    "ambiguous",
    "malformed",
)


# ---------------------------------------------------------------- coverage

# Coverage check states (design spec §10.7). `failed_to_check` blocks trusted
# canonical publication; `ambiguous` and `checked_absent` are review-visible
# but do not block source-backed rows from being published.
COVERAGE_STATES: tuple[str, ...] = (
    "checked_found",
    "checked_absent",
    "ambiguous",
    "not_applicable",
    "failed_to_check",
)


# ---------------------------------------------------------------- DDL

DDL_STATEMENTS: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS source_records (
        source_record_id TEXT PRIMARY KEY,
        record_type      TEXT NOT NULL,
        filing_id        TEXT NOT NULL,
        payload_json     TEXT NOT NULL,
        char_start       BIGINT,
        char_end         BIGINT,
        created_at       TIMESTAMP NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS claim_attempts (
        attempt_id              TEXT PRIMARY KEY,
        claim_fingerprint       TEXT NOT NULL,
        deal_slug               TEXT NOT NULL,
        claim_type              TEXT NOT NULL,
        payload_json            TEXT NOT NULL,
        origin_agent_role       TEXT NOT NULL,
        origin_agent_run_id     TEXT NOT NULL,
        model                   TEXT NOT NULL,
        prompt_hash             TEXT NOT NULL,
        created_sequence        BIGINT NOT NULL,
        created_at_run_clock    TIMESTAMP NOT NULL,
        status                  TEXT NOT NULL,
        supersedes_attempt_id   TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS claim_attempt_status_history (
        history_id              TEXT PRIMARY KEY,
        attempt_id              TEXT NOT NULL,
        from_status             TEXT,
        to_status               TEXT NOT NULL,
        reason                  TEXT,
        transitioned_at         TIMESTAMP NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS evidence_bindings (
        binding_id              TEXT PRIMARY KEY,
        attempt_id              TEXT NOT NULL,
        evidence_id             TEXT NOT NULL,
        filing_id               TEXT NOT NULL,
        paragraph_id            TEXT,
        char_start              BIGINT NOT NULL,
        char_end                BIGINT NOT NULL,
        quote_text              TEXT NOT NULL,
        quote_text_hash         TEXT NOT NULL,
        binding_status          TEXT NOT NULL,
        binding_error_code      TEXT,
        tool_version            TEXT NOT NULL,
        created_at_run_clock    TIMESTAMP NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS normalized_values (
        normalized_id           TEXT PRIMARY KEY,
        attempt_id              TEXT NOT NULL,
        field_name              TEXT NOT NULL,
        raw_value               TEXT NOT NULL,
        normalized_value        TEXT,
        normalization_state     TEXT NOT NULL,
        created_at_run_clock    TIMESTAMP NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS verifier_verdicts (
        verdict_id              TEXT PRIMARY KEY,
        attempt_id              TEXT NOT NULL,
        verifier_agent_run_id   TEXT NOT NULL,
        model                   TEXT NOT NULL,
        prompt_hash             TEXT NOT NULL,
        verdict                 TEXT NOT NULL,
        reasoning_summary       TEXT,
        supporting_evidence_ids_json TEXT NOT NULL,
        proposed_correction_json TEXT,
        confidence              DOUBLE,
        created_at_run_clock    TIMESTAMP NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS verdict_aggregates (
        aggregate_id            TEXT PRIMARY KEY,
        attempt_id              TEXT NOT NULL,
        aggregated_verdict      TEXT NOT NULL,
        aggregation_policy_version TEXT NOT NULL,
        input_verdict_ids_json  TEXT NOT NULL,
        decided_at_run_clock    TIMESTAMP NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS coverage_checks (
        coverage_id             TEXT PRIMARY KEY,
        deal_slug               TEXT NOT NULL,
        category                TEXT NOT NULL,
        subcategory             TEXT,
        check_state             TEXT NOT NULL,
        evidence_id             TEXT,
        attempt_id              TEXT,
        required                BOOLEAN NOT NULL,
        notes                   TEXT,
        created_at_run_clock    TIMESTAMP NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS conflicts (
        conflict_id             TEXT PRIMARY KEY,
        deal_slug               TEXT NOT NULL,
        conflict_type           TEXT NOT NULL,
        attempt_ids_json        TEXT NOT NULL,
        description             TEXT,
        resolution_state        TEXT NOT NULL,
        created_at_run_clock    TIMESTAMP NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS human_decisions (
        decision_id             TEXT PRIMARY KEY,
        attempt_id              TEXT,
        decision                TEXT NOT NULL,
        correction_json         TEXT,
        reviewer                TEXT NOT NULL,
        reviewed_at             TIMESTAMP NOT NULL,
        notes                   TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS canonical_rows (
        canonical_row_id        TEXT PRIMARY KEY,
        canonical_table         TEXT NOT NULL,
        payload_json            TEXT NOT NULL,
        compiled_at_run_clock   TIMESTAMP NOT NULL,
        compiled_run_id         TEXT NOT NULL,
        requires_human_review   BOOLEAN NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS canonical_row_evidence (
        canonical_row_id        TEXT NOT NULL,
        attempt_id              TEXT NOT NULL,
        evidence_id             TEXT NOT NULL,
        ordinal                 BIGINT NOT NULL,
        PRIMARY KEY (canonical_row_id, attempt_id, evidence_id)
    )
    """,
)

# Tables that must exist after migration (used by tests + sanity checks).
EXPECTED_TABLE_NAMES: tuple[str, ...] = (
    "source_records",
    "claim_attempts",
    "claim_attempt_status_history",
    "evidence_bindings",
    "normalized_values",
    "verifier_verdicts",
    "verdict_aggregates",
    "coverage_checks",
    "conflicts",
    "human_decisions",
    "canonical_rows",
    "canonical_row_evidence",
)
