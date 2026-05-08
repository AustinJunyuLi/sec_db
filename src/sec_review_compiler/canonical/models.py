"""Canonical row entities.

Stored as `canonical_rows` rows tagged by `canonical_table`. Each entity
type keeps its structure-specific fields under `payload_json`. Row ids
are deterministic — see `compiler.canonical_row_id`.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class CanonicalDeal(_Base):
    canonical_table: Literal["deal"] = "deal"
    canonical_row_id: str
    deal_slug: str
    run_id: str


class CanonicalFiling(_Base):
    canonical_table: Literal["filing"] = "filing"
    canonical_row_id: str
    deal_slug: str
    filing_id: str
    raw_sha256: str
    normalized_sha256: str | None = None


class CanonicalSourceSpan(_Base):
    canonical_table: Literal["source_span"] = "source_span"
    canonical_row_id: str
    deal_slug: str
    filing_id: str
    char_start: int
    char_end: int
    quote_text_hash: str
    evidence_id: str
    paragraph_id: str | None


class CanonicalActor(_Base):
    canonical_table: Literal["actor"] = "actor"
    canonical_row_id: str
    deal_slug: str
    filing_id: str
    canonical_local: str


class CanonicalEvent(_Base):
    canonical_table: Literal["event"] = "event"
    canonical_row_id: str
    deal_slug: str
    event_type: str
    payload_json: str


class CanonicalEventActorLink(_Base):
    canonical_table: Literal["event_actor_link"] = "event_actor_link"
    canonical_row_id: str
    event_row_id: str
    actor_row_id: str
    role: str


class CanonicalRowEvidenceLink(_Base):
    canonical_row_id: str
    attempt_id: str
    evidence_id: str
    ordinal: int
