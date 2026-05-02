"""Runtime metadata model and DDL."""

from __future__ import annotations

import datetime as dt

from pydantic import BaseModel, ConfigDict


class RunMetadata(BaseModel):
    model_config = ConfigDict(frozen=True)

    run_id: str
    schema_version: int
    parser_version: int
    ingest_version: int
    extract_version: int
    reconcile_version: int
    validate_version: int
    project_version: int
    input_hashes: dict[str, str]
    created_at: dt.datetime


RUN_METADATA_DDL = """
CREATE TABLE run_metadata (
  run_id VARCHAR PRIMARY KEY,
  schema_version INTEGER NOT NULL,
  parser_version INTEGER NOT NULL,
  ingest_version INTEGER NOT NULL,
  extract_version INTEGER NOT NULL,
  reconcile_version INTEGER NOT NULL,
  validate_version INTEGER NOT NULL,
  project_version INTEGER NOT NULL,
  input_hashes VARCHAR NOT NULL,
  created_at VARCHAR NOT NULL
);
"""
