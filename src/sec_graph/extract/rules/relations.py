"""Obsolete actor-relation deterministic rules surface."""

from __future__ import annotations

_OBSOLETE_RULES_MESSAGE = (
    "obsolete deterministic extraction rules: actor-relation candidate rules "
    "were removed by the hard-reset typed-claim pipeline; use "
    "sec_graph.extract.pipeline"
)


def relation_aliases(*_args: object, **_kwargs: object) -> dict[str, str]:
    raise RuntimeError(_OBSOLETE_RULES_MESSAGE)


def relation_matches(*_args: object, **_kwargs: object) -> list[object]:
    raise RuntimeError(_OBSOLETE_RULES_MESSAGE)


def __getattr__(name: str) -> object:
    raise RuntimeError(f"{_OBSOLETE_RULES_MESSAGE}; requested {name!r}")


__all__ = ["relation_aliases", "relation_matches"]
