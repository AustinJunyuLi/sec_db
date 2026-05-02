"""Deterministic actor alias and subtype policy."""

from __future__ import annotations

from collections.abc import Iterable

_IMPLICIT_LABELS = ("New Mountain Capital",)


def canonical_label(raw_value: str) -> str:
    return raw_value.replace("Hudson's Bay", "Hudson\u2019s Bay")


def labels_in_text(text: str, known_labels: Iterable[str]) -> list[str]:
    labels: list[str] = []
    for label in sorted({canonical_label(label) for label in known_labels}, key=len, reverse=True):
        if label in text or label.replace("\u2019", "'") in text:
            labels.append(label)
    for label in _IMPLICIT_LABELS:
        if label in text and label not in labels:
            labels.append(label)
    return sorted(labels, key=lambda label: text.find(label.replace("\u2019", "'") if label not in text else label))


def bidder_subtype(label: str, context: str = "") -> str:
    del context
    if label.startswith(("Sponsor ", "Bidder ")) or label in {"Buyer Group", "New Mountain Capital"}:
        return "financial"
    if label in {"Hudson\u2019s Bay", "G&W", "Industry Participant"} or label.startswith("Company "):
        return "strategic"
    if label in {"Party D"}:
        return "financial"
    if label in {"Party E", "Party F"}:
        return "strategic"
    return "unknown"


def target_label(deal_slug: str) -> str:
    labels = {
        "petsmart-inc": "PetSmart",
        "providence-worcester": "Providence and Worcester",
        "saks": "Saks",
        "zep": "Zep",
    }
    return labels.get(deal_slug, deal_slug)
