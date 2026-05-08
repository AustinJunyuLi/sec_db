"""Canonical run identifiers and a deterministic run clock.

The shape `YYYYMMDDTHHMMSSZ_<slug>_<8hex>` is intentionally redundant: the
timestamp gives a human-readable run order, the slug names the deal under
review, and the 8-hex suffix prevents collisions when two runs of the same
deal start in the same UTC second.
"""

from __future__ import annotations

import re
import secrets
from dataclasses import dataclass
from datetime import datetime, timezone

from ..errors import InvalidRunIdError

TIMESTAMP_FMT = "%Y%m%dT%H%M%SZ"
SLUG_PATTERN = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,62})$")
RUN_ID_PATTERN = re.compile(
    r"^(?P<ts>\d{8}T\d{6}Z)"
    r"_(?P<slug>[a-z0-9](?:[a-z0-9-]{0,62}))"
    r"_(?P<hex>[0-9a-f]{8})$"
)


@dataclass(frozen=True, slots=True)
class RunId:
    """Immutable canonical run identifier."""

    timestamp: str
    slug: str
    short_hex: str

    def __str__(self) -> str:  # noqa: D401 — `str(rid)` is the canonical form
        return f"{self.timestamp}_{self.slug}_{self.short_hex}"

    @property
    def started_at(self) -> datetime:
        return datetime.strptime(self.timestamp, TIMESTAMP_FMT).replace(
            tzinfo=timezone.utc
        )

    @classmethod
    def parse(cls, value: str) -> "RunId":
        match = RUN_ID_PATTERN.fullmatch(value)
        if not match:
            raise InvalidRunIdError(
                f"run id does not match canonical shape: {value!r}"
            )
        try:
            datetime.strptime(match["ts"], TIMESTAMP_FMT)
        except ValueError as exc:
            raise InvalidRunIdError(
                f"run id timestamp not a real UTC datetime: {value!r}"
            ) from exc
        return cls(timestamp=match["ts"], slug=match["slug"], short_hex=match["hex"])

    @classmethod
    def new(cls, slug: str, *, now: datetime | None = None) -> "RunId":
        if not SLUG_PATTERN.fullmatch(slug):
            raise InvalidRunIdError(
                f"slug must be lowercase alnum/hyphen and start with alnum: {slug!r}"
            )
        when = now or datetime.now(timezone.utc)
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
        timestamp = when.astimezone(timezone.utc).strftime(TIMESTAMP_FMT)
        return cls(
            timestamp=timestamp,
            slug=slug,
            short_hex=secrets.token_hex(4),
        )


@dataclass(frozen=True, slots=True)
class RunClock:
    """Deterministic clock: tied to a run id, or live wall-clock."""

    run_id: RunId | None
    live: bool

    @classmethod
    def from_run_id(cls, run_id: RunId) -> "RunClock":
        return cls(run_id=run_id, live=False)

    @classmethod
    def live_clock(cls) -> "RunClock":
        return cls(run_id=None, live=True)

    def now(self) -> datetime:
        if self.live:
            return datetime.now(timezone.utc)
        # Deterministic mode is never reachable without a run_id.
        assert self.run_id is not None
        return self.run_id.started_at
