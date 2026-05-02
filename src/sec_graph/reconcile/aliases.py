"""Deterministic actor alias policy.

Phase 6 contract: target labels for canonical `deals.target_actor_id` come
from filing metadata (the seed corpus or per-filing manifest), not from a
hand-coded `slug -> label` dict. An unknown slug FAILS LOUDLY with the
slug name in the error so the caller can decide to add metadata or raise
an explicit rejection — never a silent fallback to the slug string.
"""

from __future__ import annotations

import csv
from collections.abc import Iterable
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SEEDS_PATH = _REPO_ROOT / "seeds.csv"
_FILINGS_DIR = _REPO_ROOT / "data" / "filings"

_IMPLICIT_LABELS = ("New Mountain Capital",)


class UnknownTargetLabelError(KeyError):
    """Raised when no metadata source resolves a target label for a deal slug."""


def canonical_label(raw_value: str) -> str:
    return raw_value.replace("Hudson's Bay", "Hudson’s Bay")


def labels_in_text(text: str, known_labels: Iterable[str]) -> list[str]:
    labels: list[str] = []
    for label in sorted({canonical_label(label) for label in known_labels}, key=len, reverse=True):
        if label in text or label.replace("’", "'") in text:
            labels.append(label)
    for label in _IMPLICIT_LABELS:
        if label in text and label not in labels:
            labels.append(label)
    return sorted(labels, key=lambda label: text.find(label.replace("’", "'") if label not in text else label))


def _format_label(raw: str) -> str:
    """Title-case a SEC-uppercase target name (`PETSMART INC` -> `Petsmart Inc`).

    SEC EDGAR returns issuer names entirely uppercase. Title-casing them is
    a generic typography normalization, not a deal-specific lookup. The
    label is still source-derived (from the `target_name` column of
    seeds.csv or the `target_name` field of `manifest.json`).
    """
    cleaned = raw.strip()
    if not cleaned:
        return cleaned
    parts = cleaned.split()
    titled = []
    for part in parts:
        if "&" in part or "." in part:
            titled.append(part)
        else:
            titled.append(part.capitalize())
    return " ".join(titled)


def _seeds_target_name(slug: str) -> str | None:
    if not _SEEDS_PATH.exists():
        return None
    with _SEEDS_PATH.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            if row.get("deal_slug") == slug:
                target = row.get("target_name", "").strip()
                return target or None
    return None


def _manifest_target_name(slug: str) -> str | None:
    manifest_path = _FILINGS_DIR / slug / "manifest.json"
    if not manifest_path.exists():
        return None
    import json

    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    target = str(payload.get("target_name", "")).strip()
    return target or None


def target_label(deal_slug: str) -> str:
    """Return the canonical target label for a deal slug, sourced from metadata.

    Resolution order:
      1. `data/filings/{slug}/manifest.json` `target_name` (per-filing truth)
      2. `seeds.csv` `target_name` (corpus-wide seed truth)

    If neither source resolves, raises `UnknownTargetLabelError` whose
    message names the slug. The function MUST NOT silently fall back to
    the slug itself or any other guessed string. Callers that need to
    handle missing metadata explicitly should catch this error and emit
    an explicit rejection judgment.
    """
    raw = _manifest_target_name(deal_slug) or _seeds_target_name(deal_slug)
    if raw is None:
        raise UnknownTargetLabelError(
            f"no target_name available for deal_slug={deal_slug!r}: "
            "add a row to seeds.csv or fetch the filing manifest"
        )
    return _format_label(raw)
