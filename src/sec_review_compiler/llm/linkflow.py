"""Linkflow client config and credential checks.

Every Linkflow call originates here. The probe at
`runs/linkflow-probe/20260508T123815Z/` proved that direct OpenAI SDK
calls against `https://www.linkflow.run/v1` work for our needs; this
adapter pins those values from environment variables and refuses to
build a network client when required credentials are absent.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from ..errors import (
    InvalidLinkflowConfigError,
    MissingLinkflowCredentialsError,
)

DEFAULT_BASE_URL = "https://www.linkflow.run/v1"
DEFAULT_MODEL = "gpt-5.5"
DEFAULT_REASONING_EFFORT = "medium"
DEFAULT_MAX_CONCURRENCY = 4
SUPPORTED_REASONING_EFFORTS: frozenset[str] = frozenset({"low", "medium", "high"})


@dataclass(frozen=True, slots=True)
class LinkflowClientConfig:
    """Resolved Linkflow configuration. Never carries the API key."""

    base_url: str
    model: str
    reasoning_effort: str
    max_concurrency: int
    api_key_present: bool

    @classmethod
    def from_env(
        cls,
        env: dict[str, str] | None = None,
    ) -> "LinkflowClientConfig":
        env = os.environ if env is None else env

        base_url = env.get("LINKFLOW_BASE_URL", DEFAULT_BASE_URL).strip()
        if not base_url:
            raise InvalidLinkflowConfigError("LINKFLOW_BASE_URL must be non-empty")

        model = env.get("LINKFLOW_MODEL", DEFAULT_MODEL).strip()
        if not model:
            raise InvalidLinkflowConfigError("LINKFLOW_MODEL must be non-empty")

        reasoning = env.get(
            "LINKFLOW_REASONING_EFFORT",
            env.get("LINKFLOW_DEFAULT_REASONING", DEFAULT_REASONING_EFFORT),
        ).strip().lower()
        if reasoning not in SUPPORTED_REASONING_EFFORTS:
            raise InvalidLinkflowConfigError(
                f"LINKFLOW_REASONING_EFFORT={reasoning!r} is not in the probe-validated "
                f"set {sorted(SUPPORTED_REASONING_EFFORTS)}"
            )

        raw_concurrency = env.get("LINKFLOW_MAX_CONCURRENCY", str(DEFAULT_MAX_CONCURRENCY))
        try:
            concurrency = int(raw_concurrency)
        except ValueError as exc:
            raise InvalidLinkflowConfigError(
                f"LINKFLOW_MAX_CONCURRENCY={raw_concurrency!r} is not an integer"
            ) from exc
        if concurrency < 1 or concurrency > 8:
            raise InvalidLinkflowConfigError(
                f"LINKFLOW_MAX_CONCURRENCY={concurrency} outside probe-validated range [1, 8]"
            )

        api_key_present = bool(env.get("LINKFLOW_API_KEY"))

        return cls(
            base_url=base_url,
            model=model,
            reasoning_effort=reasoning,
            max_concurrency=concurrency,
            api_key_present=api_key_present,
        )

    def require_credentials(self) -> None:
        """Pre-network credential gate.

        Call this before constructing any Linkflow client. If the API key
        is absent, raise MissingLinkflowCredentialsError without ever
        attempting a network connection.
        """
        if not self.api_key_present:
            raise MissingLinkflowCredentialsError(
                "LINKFLOW_API_KEY is not set; refusing to construct a network "
                "client (live mode requires the key in the environment)"
            )


def build_responses_client(
    config: LinkflowClientConfig,
    *,
    env: dict[str, str] | None = None,
    timeout: float | None = None,
) -> Any:
    """Construct a sync OpenAI client pointed at Linkflow.

    Returns a `responses.create`-capable client (the OpenAI Python SDK
    `OpenAI` instance). The credential gate is enforced first; missing
    `LINKFLOW_API_KEY` raises before any client is instantiated.
    """
    config.require_credentials()
    env = os.environ if env is None else env
    api_key = env.get("LINKFLOW_API_KEY")
    if not api_key:  # pragma: no cover — covered by require_credentials
        raise MissingLinkflowCredentialsError("LINKFLOW_API_KEY missing at client build")

    # Imported lazily so unit tests that never need a live client don't
    # pay the import cost.
    from openai import OpenAI

    kwargs: dict[str, Any] = {"api_key": api_key, "base_url": config.base_url}
    if timeout is not None:
        kwargs["timeout"] = timeout
    return OpenAI(**kwargs)
