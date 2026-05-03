"""Run-kernel metadata and cost/runtime schema."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

ProgressState = Literal[
    "queued",
    "ingested",
    "evidence_mapped",
    "llm_artifacts_written",
    "claims_imported",
    "reconciled",
    "validated",
    "projected",
    "blocked",
]


class RunManifest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    run_id: str
    run_type: Literal["proof", "corpus", "developer"]
    source_manifest_hash: str
    schema_version: int
    extract_version: int
    reconcile_version: int
    validate_version: int
    project_version: int
    provider: str | None
    model: str | None
    reasoning_effort: str | None
    request_modes_json: str
    started_at: str
    code_identity: str | None
    input_hashes_json: str
    config_hash: str


class ProgressLedgerEntry(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    progress_id: str
    run_id: str
    deal_slug: str
    stage: str
    attempt: int = Field(ge=1)
    state: ProgressState
    artifact_digest: str | None
    failure_reason: str | None
    recorded_at: str


class StageArtifact(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    artifact_id: str
    run_id: str
    artifact_path: str
    artifact_kind: str
    owning_stage: str
    deal_slug: str | None
    digest: str
    created_by: str
    finalized: bool


class CostRuntimeRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    record_id: str
    run_id: str
    deal_slug: str | None
    window_id: str | None
    provider: str | None
    model: str | None
    reasoning_effort: str | None
    input_tokens: int | None
    output_tokens: int | None
    token_source: Literal["actual", "estimated", "mixed"]
    latency_ms: int | None
    retry_count: int = Field(ge=0)
    provider_failure: str | None


RUN_METADATA_DDL = """
CREATE TABLE run_manifest (
  run_id VARCHAR PRIMARY KEY,
  run_type VARCHAR NOT NULL CHECK (run_type IN ('proof', 'corpus', 'developer')),
  source_manifest_hash VARCHAR NOT NULL,
  schema_version INTEGER NOT NULL,
  extract_version INTEGER NOT NULL,
  reconcile_version INTEGER NOT NULL,
  validate_version INTEGER NOT NULL,
  project_version INTEGER NOT NULL,
  provider VARCHAR,
  model VARCHAR,
  reasoning_effort VARCHAR,
  request_modes_json VARCHAR NOT NULL,
  started_at VARCHAR NOT NULL,
  code_identity VARCHAR,
  input_hashes_json VARCHAR NOT NULL,
  config_hash VARCHAR NOT NULL
);

CREATE TABLE run_lock (
  run_id VARCHAR PRIMARY KEY,
  lock_path VARCHAR NOT NULL,
  owner_pid INTEGER NOT NULL,
  acquired_at VARCHAR NOT NULL
);

CREATE TABLE progress_ledger (
  progress_id VARCHAR PRIMARY KEY,
  run_id VARCHAR NOT NULL,
  deal_slug VARCHAR NOT NULL,
  stage VARCHAR NOT NULL,
  attempt INTEGER NOT NULL,
  state VARCHAR NOT NULL CHECK (state IN ('queued', 'ingested', 'evidence_mapped', 'llm_artifacts_written', 'claims_imported', 'reconciled', 'validated', 'projected', 'blocked')),
  artifact_digest VARCHAR,
  failure_reason VARCHAR,
  recorded_at VARCHAR NOT NULL,
  CHECK (attempt >= 1)
);

CREATE TABLE stage_artifacts (
  artifact_id VARCHAR PRIMARY KEY,
  run_id VARCHAR NOT NULL,
  artifact_path VARCHAR NOT NULL,
  artifact_kind VARCHAR NOT NULL,
  owning_stage VARCHAR NOT NULL,
  deal_slug VARCHAR,
  digest VARCHAR NOT NULL,
  created_by VARCHAR NOT NULL,
  finalized BOOLEAN NOT NULL
);

CREATE TABLE resume_report (
  resume_report_id VARCHAR PRIMARY KEY,
  run_id VARCHAR NOT NULL,
  reused_json VARCHAR NOT NULL,
  recomputed_json VARCHAR NOT NULL,
  refused_json VARCHAR NOT NULL,
  created_at VARCHAR NOT NULL
);

CREATE TABLE cost_runtime_records (
  record_id VARCHAR PRIMARY KEY,
  run_id VARCHAR NOT NULL,
  deal_slug VARCHAR,
  window_id VARCHAR,
  provider VARCHAR,
  model VARCHAR,
  reasoning_effort VARCHAR,
  input_tokens INTEGER,
  output_tokens INTEGER,
  token_source VARCHAR NOT NULL CHECK (token_source IN ('actual', 'estimated', 'mixed')),
  latency_ms INTEGER,
  retry_count INTEGER NOT NULL,
  provider_failure VARCHAR,
  CHECK (retry_count >= 0)
);
"""
