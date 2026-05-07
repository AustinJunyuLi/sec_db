"""Quote-level source-support helpers.

These helpers answer narrow yes/no questions about whether a quote contains
the surface cues required for specific claim shapes. They are intentionally
conservative: they refuse anything that does not look like the targeted shape
rather than guessing.

Scope (Task 5 — buyer-group rules):

- ``member_of`` relation objects must be a named actor or actor group, not a
  proposal description such as "joint acquisition proposal" or "transaction".
- A relation quote that omits the subject actor cannot support a relation
  claim about that actor.

This module is the single home for these checks. Other modules import from
here rather than reimplementing the regular expressions.
"""

from __future__ import annotations

import re

# Words that disqualify an object label from being a valid ``member_of`` peer.
# A buyer group's members must be actors or actor groups, never abstract
# proposals, transactions, processes, or stage names.
_PROPOSAL_LIKE_TOKENS = (
    "proposal",
    "proposals",
    "transaction",
    "transactions",
    "offer",
    "offers",
    "bid",
    "bids",
    "process",
    "round",
    "rounds",
    "agreement",
    "consortium proposal",
    "joint proposal",
    "joint acquisition proposal",
    "acquisition proposal",
)

_PROPOSAL_LIKE_PATTERN = "|".join(
    sorted((re.escape(token) for token in _PROPOSAL_LIKE_TOKENS), key=len, reverse=True)
)
PROPOSAL_LIKE_RE = re.compile(rf"\b(?:{_PROPOSAL_LIKE_PATTERN})\b", re.IGNORECASE)


def is_proposal_like_label(label: str) -> bool:
    """Return ``True`` when ``label`` reads as a proposal/transaction phrase.

    Used to reject ``member_of`` relations whose object is a proposal
    description rather than an actor or actor group.
    """

    if not label:
        return False
    return bool(PROPOSAL_LIKE_RE.search(label))


def member_of_object_is_actor_like(object_label: str) -> bool:
    """Return ``True`` when an object label is acceptable as a ``member_of`` peer.

    Acceptable peers are *actor-shaped*: a named organization, person, or
    actor group. We approximate this by rejecting empty labels and labels
    that contain proposal-like tokens.
    """

    label = (object_label or "").strip()
    if not label:
        return False
    if is_proposal_like_label(label):
        return False
    return True


def relation_quote_names_subject(subject_label: str, quote_text: str) -> bool:
    """Return ``True`` when ``quote_text`` mentions ``subject_label`` literally.

    A relation claim cannot be supported by a quote that does not actually
    name the subject. The check is case-insensitive, whitespace-tolerant, and
    skips trailing punctuation.
    """

    subject = (subject_label or "").strip().casefold()
    quote = (quote_text or "").casefold()
    if not subject or not quote:
        return False
    return subject in quote


def member_of_quote_supports_pair(
    subject_label: str,
    object_label: str,
    quote_text: str,
) -> bool:
    """Return ``True`` when a ``member_of`` quote names both peers and is actor-shaped.

    ``member_of`` is the most common buyer-group relation. The quote must:

    - name the subject actor literally,
    - have a non-proposal object label (the object must be an actor/group),
    - and name the object literally so the relation is anchored in the text.
    """

    if not member_of_object_is_actor_like(object_label):
        return False
    if not relation_quote_names_subject(subject_label, quote_text):
        return False
    return relation_quote_names_subject(object_label, quote_text)


__all__ = [
    "PROPOSAL_LIKE_RE",
    "is_proposal_like_label",
    "member_of_object_is_actor_like",
    "member_of_quote_supports_pair",
    "relation_quote_names_subject",
]
