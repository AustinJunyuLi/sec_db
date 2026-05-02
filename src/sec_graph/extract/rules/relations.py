"""Actor-relation extraction rules.

The production rule surface only emits relation candidates from GENERIC
filing patterns: explicit `(“Parent”)` / `(“Merger Sub”)` alias clauses,
the source-defined `the “Buyer Group” refers to ...` clause, and generic
parent/merger-sub vehicle relations. No specific reference-deal members,
no hand-listed buyer-group rosters, no Longview-style support/rollover
patterns are encoded here. Deal-specific facts must come from source
evidence parsed by these generic patterns or from LLM/window extraction
fixtures — never from a hardcoded production constant.

Phase 6 of the cleanup plan removed the prior reference-deal member list
(BC Partners, La Caisse de dépôt et placement du Québec, GIC Special
Investments, StepStone Group, Longview Asset Management) and the
Longview-specific support/rollover/debt-financing patterns from this module.
The buyer-group member parser now derives members from the source-defined
clause itself.
"""

from __future__ import annotations

import json
import re

from .actors import Match

_BUYER_GROUP_RE = re.compile(
    r"the [“\"]Buyer Group[”\"] refers to (?P<text>.+?);",
    re.IGNORECASE | re.DOTALL,
)
_PARENT_MERGER_SUB_RE = re.compile(
    r"Parent and Merger Sub .*? owned by the Buyer Group",
    re.IGNORECASE | re.DOTALL,
)
_MERGER_SUB_OWNED_RE = re.compile(
    r"Merger Sub .*? wholly owned subsidiary of Parent",
    re.IGNORECASE | re.DOTALL,
)
_DEBT_FINANCING_RE = re.compile(
    r"firm commitments from a consortium of financial institutions to provide the debt financing",
    re.IGNORECASE,
)
_ALIAS_RE = re.compile(
    r"(?:^|[,;]\s+|and\s+)"
    r"(?P<label>[A-Z][A-Za-z0-9&.'’ \-]+?(?:Inc\.|Corp\.|Corporation|LLC|L\.P\.|LP|Ltd\.|Limited))"
    r"\s*,?\s*(?:a [^()]{0,160}?)?"
    r"\([\"“](?P<alias>Parent|Merger Sub)[\"”]\)",
    re.IGNORECASE,
)
# Buyer-group members are sourced from the filing-defined "Buyer Group refers
# to ..." clause. The pattern matches a comma- or "and"-separated list of
# proper-noun member labels that may include diacritics, ampersands, dots,
# and curly apostrophes. No specific names are hardcoded.
_BUYER_GROUP_MEMBER_RE = re.compile(
    r"(?:^|,\s+|and\s+)"
    r"(?P<label>[A-Z][A-Za-z0-9&.'’À-ſ \-]{2,}?)"
    r"(?=\s*(?:,|;|\sand\s|$))",
)


def _payload(
    *,
    subject_label: str,
    object_label: str,
    relation_type: str,
    role_detail: str | None = None,
    effective_date_first: str | None = None,
) -> str:
    return json.dumps(
        {
            "subject_label": subject_label,
            "object_label": object_label,
            "relation_type": relation_type,
            "role_detail": role_detail,
            "effective_date_first": effective_date_first,
        },
        sort_keys=True,
    )


def _relation_match(text: str, start: int, end: int, normalized_value: str) -> Match:
    raw_value = text[start:end].strip()
    return Match(
        candidate_type="actor_relation",
        raw_value=raw_value,
        normalized_value=normalized_value,
        confidence="high",
        start=start,
        end=end,
        span_kind="clause",
    )


def relation_aliases(text: str) -> dict[str, str]:
    labels: dict[str, str] = {}
    for match in _ALIAS_RE.finditer(text):
        alias = "Parent" if match.group("alias").casefold() == "parent" else "Merger Sub"
        label = match.group("label").strip(" ,")
        if label.casefold().startswith("and "):
            label = label[4:]
        labels[alias] = label
    return labels


def _buyer_group_members_from_text(text: str) -> list[str]:
    """Source-derived buyer-group members from a `the "Buyer Group" refers to ...` clause.

    Returns proper-noun labels in source order. Filters out generic role nouns
    that may appear in the clause but are not member identities (e.g.,
    `affiliates`, `Inc.`, `LLC` standalone). No reference-deal name list is
    consulted.
    """
    seen: set[str] = set()
    members: list[str] = []
    skip = {
        "affiliates",
        "the buyer group",
        "buyer group",
        "and",
    }
    for match in _BUYER_GROUP_MEMBER_RE.finditer(text):
        label = match.group("label").strip(" ,")
        if not label:
            continue
        folded = label.casefold()
        if folded in skip:
            continue
        if folded in seen:
            continue
        seen.add(folded)
        members.append(label)
    return members


def relation_matches(text: str, aliases: dict[str, str] | None = None) -> list[Match]:
    matches: list[Match] = []
    alias_labels = {"Parent": "Parent", "Merger Sub": "Merger Sub"}
    if aliases is not None:
        alias_labels.update(aliases)
    alias_labels.update(relation_aliases(text))
    parent_label = alias_labels["Parent"]
    merger_sub_label = alias_labels["Merger Sub"]
    buyer_group = _BUYER_GROUP_RE.search(text)
    if buyer_group:
        clause_text = buyer_group.group("text") or ""
        for label in _buyer_group_members_from_text(clause_text):
            matches.append(
                _relation_match(
                    text,
                    buyer_group.start(),
                    buyer_group.end(),
                    _payload(
                        subject_label=label,
                        object_label="Buyer Group",
                        relation_type="member_of",
                        role_detail="buyer group member",
                    ),
                )
            )
    for pattern, payload in (
        (
            _PARENT_MERGER_SUB_RE,
            _payload(
                subject_label=parent_label,
                object_label="Buyer Group",
                relation_type="acquisition_vehicle_of",
                role_detail="parent vehicle owned by buyer group",
            ),
        ),
        (
            _MERGER_SUB_OWNED_RE,
            _payload(
                subject_label=merger_sub_label,
                object_label=parent_label,
                relation_type="acquisition_vehicle_of",
                role_detail="merger subsidiary owned by parent",
            ),
        ),
        (
            _DEBT_FINANCING_RE,
            _payload(
                subject_label="consortium of financial institutions",
                object_label=parent_label,
                relation_type="finances",
                role_detail="debt financing commitments",
            ),
        ),
    ):
        match = pattern.search(text)
        if match:
            matches.append(_relation_match(text, match.start(), match.end(), payload))
    return matches
