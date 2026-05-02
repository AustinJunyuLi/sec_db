"""Minimal canonical skeleton models and DDL."""

from __future__ import annotations

import datetime as dt
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Deal(BaseModel):
    model_config = ConfigDict(frozen=True)

    deal_id: str
    run_id: str
    deal_slug: str
    target_actor_id: str
    announcement_date: dt.date | None
    evidence_ids: list[str]


class ProcessCycle(BaseModel):
    model_config = ConfigDict(frozen=True)

    cycle_id: str
    run_id: str
    deal_id: str
    cycle_sequence: int = Field(ge=1)
    cycle_label: str
    start_date: dt.date | None
    end_date: dt.date | None
    evidence_ids: list[str]


class Actor(BaseModel):
    model_config = ConfigDict(frozen=True)

    actor_id: str
    run_id: str
    deal_id: str
    actor_label: str
    actor_type: Literal["target", "bidder", "advisor", "counsel", "board", "committee", "other"]
    bidder_subtype: Literal["strategic", "financial", "unknown"] | None
    is_anonymous: bool
    evidence_ids: list[str]


class Event(BaseModel):
    model_config = ConfigDict(frozen=True)

    event_id: str
    run_id: str
    deal_id: str
    cycle_id: str
    event_type: Literal["bid", "withdrawal", "meeting", "nda", "boundary", "signing", "other"]
    event_date: dt.date | None
    description: str
    bid_value: float | None
    bid_value_lower: float | None
    bid_value_upper: float | None
    bid_value_unit: str | None
    consideration_type: str | None
    evidence_ids: list[str]


class EventActorLink(BaseModel):
    model_config = ConfigDict(frozen=True)

    link_id: str
    run_id: str
    event_id: str
    actor_id: str
    role: Literal["target", "bidder", "advisor", "board", "counterparty", "other"]
    evidence_ids: list[str]


CANONICAL_DDL = """
CREATE TABLE deals (
  deal_id VARCHAR PRIMARY KEY,
  run_id VARCHAR NOT NULL,
  deal_slug VARCHAR NOT NULL,
  target_actor_id VARCHAR NOT NULL,
  announcement_date DATE,
  evidence_ids VARCHAR[] NOT NULL
);

CREATE TABLE actors (
  actor_id VARCHAR PRIMARY KEY,
  run_id VARCHAR NOT NULL,
  deal_id VARCHAR NOT NULL,
  actor_label VARCHAR NOT NULL,
  actor_type VARCHAR NOT NULL CHECK (actor_type IN ('target', 'bidder', 'advisor', 'counsel', 'board', 'committee', 'other')),
  bidder_subtype VARCHAR CHECK (bidder_subtype IS NULL OR bidder_subtype IN ('strategic', 'financial', 'unknown')),
  is_anonymous BOOLEAN NOT NULL,
  evidence_ids VARCHAR[] NOT NULL,
  FOREIGN KEY (deal_id) REFERENCES deals(deal_id)
);

CREATE TABLE process_cycles (
  cycle_id VARCHAR PRIMARY KEY,
  run_id VARCHAR NOT NULL,
  deal_id VARCHAR NOT NULL,
  cycle_sequence INTEGER NOT NULL,
  cycle_label VARCHAR NOT NULL,
  start_date DATE,
  end_date DATE,
  evidence_ids VARCHAR[] NOT NULL,
  CHECK (cycle_sequence >= 1),
  CHECK (end_date IS NULL OR start_date IS NULL OR end_date >= start_date),
  FOREIGN KEY (deal_id) REFERENCES deals(deal_id)
);

CREATE TABLE events (
  event_id VARCHAR PRIMARY KEY,
  run_id VARCHAR NOT NULL,
  deal_id VARCHAR NOT NULL,
  cycle_id VARCHAR NOT NULL,
  event_type VARCHAR NOT NULL CHECK (event_type IN ('bid', 'withdrawal', 'meeting', 'nda', 'boundary', 'signing', 'other')),
  event_date DATE,
  description VARCHAR NOT NULL,
  bid_value DOUBLE,
  bid_value_lower DOUBLE,
  bid_value_upper DOUBLE,
  bid_value_unit VARCHAR,
  consideration_type VARCHAR,
  evidence_ids VARCHAR[] NOT NULL,
  CHECK (bid_value_upper IS NULL OR bid_value_lower IS NULL OR bid_value_upper >= bid_value_lower),
  FOREIGN KEY (deal_id) REFERENCES deals(deal_id),
  FOREIGN KEY (cycle_id) REFERENCES process_cycles(cycle_id)
);

CREATE TABLE event_actor_links (
  link_id VARCHAR PRIMARY KEY,
  run_id VARCHAR NOT NULL,
  event_id VARCHAR NOT NULL,
  actor_id VARCHAR NOT NULL,
  role VARCHAR NOT NULL CHECK (role IN ('target', 'bidder', 'advisor', 'board', 'counterparty', 'other')),
  evidence_ids VARCHAR[] NOT NULL,
  FOREIGN KEY (event_id) REFERENCES events(event_id),
  FOREIGN KEY (actor_id) REFERENCES actors(actor_id)
);
"""
