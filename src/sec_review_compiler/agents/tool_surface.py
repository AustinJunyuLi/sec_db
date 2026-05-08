"""Per-role tool allowlist.

The orchestrator builds the `ToolRegistry` for each Linkflow call from
the role-specific allowlist below. Tools that compare against external
extraction systems or fetch reference answers are listed in
`FORBIDDEN_TOOL_NAMES` and must NEVER appear in any role's set —
verified at module import and again by `tests/test_agent_roles.py`.
"""

from __future__ import annotations

from .roles import AgentRole, ROLE_ORDER


# Read-only retrieval and parsing tools available across roles. The
# orchestrator wires concrete handlers; this list names the canonical
# tool surface only.
_READ_TOOLS: frozenset[str] = frozenset({
    "search_filing",
    "get_section",
    "get_paragraph",
    "get_neighborhood",
    "get_table",
    "verify_quote",
    "parse_date",
    "parse_money",
    "parse_count",
    "normalize_actor_label",
})

# Listing/discovery tools used by inspectors and consistency checks.
_LIST_TOOLS: frozenset[str] = frozenset({
    "list_claim_attempts",
    "list_coverage_checks",
    "list_conflicts",
})


# Tools that MUST NEVER be exposed to any role.
FORBIDDEN_TOOL_NAMES: frozenset[str] = frozenset({
    "compare_to_baseline",
    "compare_to_other_pipeline",
    "lookup_answer_key",
    "fetch_reference_answer",
    "internet_search",
    "external_search",
    "execute_sql",
    "write_database",
    "write_filesystem",
})


_ROLE_TOOLS: dict[AgentRole, frozenset[str]] = {
    AgentRole.SCOUT: _READ_TOOLS - {"normalize_actor_label"},
    AgentRole.PARTY_RELATION_EXTRACTOR: _READ_TOOLS,
    AgentRole.TIMELINE_BID_EXTRACTOR: _READ_TOOLS,
    AgentRole.COUNT_COVERAGE_EXTRACTOR: _READ_TOOLS,
    AgentRole.OMISSION_INSPECTOR: (
        (_READ_TOOLS - {"normalize_actor_label"}) | _LIST_TOOLS
    ),
    AgentRole.VERIFIER: frozenset({
        "get_paragraph",
        "get_neighborhood",
        "verify_quote",
        "parse_date",
        "parse_money",
        "parse_count",
    }),
    AgentRole.CONSISTENCY_CHECKER: (
        frozenset({"get_paragraph", "verify_quote"}) | _LIST_TOOLS
    ),
}


def tools_for_role(role: AgentRole) -> frozenset[str]:
    return _ROLE_TOOLS[role]


# Module-level invariant: forbidden names are nowhere in any role surface.
for _role in ROLE_ORDER:
    _allowed = _ROLE_TOOLS[_role]
    _bad = _allowed & FORBIDDEN_TOOL_NAMES
    assert not _bad, f"role {_role} exposes forbidden tools: {sorted(_bad)}"
