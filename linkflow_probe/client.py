"""Thin Linkflow SDK client wrapper."""

from __future__ import annotations

import os
from dataclasses import dataclass

from openai import AsyncOpenAI

DEFAULT_BASE_URL = "https://www.linkflow.run/v1"
DEFAULT_MODEL = "gpt-5.5"


@dataclass(frozen=True)
class LinkflowEnv:
    api_key_present: bool
    base_url: str
    model: str


def load_env() -> LinkflowEnv:
    api_key = os.environ.get("LINKFLOW_API_KEY")
    if not api_key:
        raise RuntimeError("LINKFLOW_API_KEY is required")
    return LinkflowEnv(
        api_key_present=True,
        base_url=os.environ.get("LINKFLOW_BASE_URL", DEFAULT_BASE_URL),
        model=os.environ.get("LINKFLOW_MODEL", DEFAULT_MODEL),
    )


def build_client(timeout: float | None = None) -> AsyncOpenAI:
    env = load_env()
    kwargs = {
        "api_key": os.environ["LINKFLOW_API_KEY"],
        "base_url": env.base_url,
    }
    if timeout is not None:
        kwargs["timeout"] = timeout
    return AsyncOpenAI(**kwargs)
