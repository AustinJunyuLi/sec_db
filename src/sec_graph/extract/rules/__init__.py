"""Obsolete deterministic extraction rules surface.

The hard-reset pipeline imports typed semantic claims through
``sec_graph.extract.pipeline`` and does not produce candidate rows. This module
is intentionally importable so stale callers receive a precise runtime error
instead of an unrelated missing-model import failure.
"""

from __future__ import annotations

_OBSOLETE_RULES_MESSAGE = (
    "obsolete deterministic extraction rules: candidate-row rules were removed "
    "by the hard-reset typed-claim pipeline; use sec_graph.extract.pipeline"
)


def run_rules(*_args: object, **_kwargs: object) -> list[object]:
    raise RuntimeError(_OBSOLETE_RULES_MESSAGE)


def __getattr__(name: str) -> object:
    raise RuntimeError(f"{_OBSOLETE_RULES_MESSAGE}; requested {name!r}")


__all__ = ["run_rules"]
