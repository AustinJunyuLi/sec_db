"""Evidence-layer filing models and DDL."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class CleanFiling(BaseModel):
    model_config = ConfigDict(frozen=True)

    filing_id: str
    deal_slug: str
    source_path: str | None
    raw_sha256: str = Field(min_length=64, max_length=64)
    parser_version: int
    page_count: int | None
    section_count: int | None


class Section(BaseModel):
    model_config = ConfigDict(frozen=True)

    section_id: str
    filing_id: str
    section_name: str
    char_start: int = Field(ge=0)
    char_end: int = Field(ge=0)


class Paragraph(BaseModel):
    model_config = ConfigDict(frozen=True)

    paragraph_id: str
    filing_id: str
    section: str
    page_hint: int | None
    char_start: int = Field(ge=0)
    char_end: int = Field(ge=0)
    paragraph_text: str
    paragraph_hash: str = Field(min_length=64, max_length=64)


class SourceSpan(BaseModel):
    model_config = ConfigDict(frozen=True)

    evidence_id: str
    filing_id: str
    paragraph_id: str
    span_basis: Literal["raw_md", "clean_text"]
    span_kind: Literal["paragraph_seed", "sentence", "clause", "phrase"]
    parent_evidence_id: str | None
    created_by_stage: Literal["ingest", "extract"]
    char_start: int = Field(ge=0)
    char_end: int = Field(ge=0)
    quote_text: str
    quote_hash: str = Field(min_length=64, max_length=64)


FILINGS_DDL = """
CREATE TABLE filings (
  filing_id VARCHAR PRIMARY KEY,
  deal_slug VARCHAR NOT NULL,
  source_path VARCHAR,
  raw_sha256 VARCHAR NOT NULL,
  parser_version INTEGER NOT NULL,
  page_count INTEGER,
  section_count INTEGER
);

CREATE TABLE paragraphs (
  paragraph_id VARCHAR PRIMARY KEY,
  filing_id VARCHAR NOT NULL,
  section VARCHAR NOT NULL,
  page_hint INTEGER,
  char_start INTEGER NOT NULL,
  char_end INTEGER NOT NULL,
  paragraph_text VARCHAR NOT NULL,
  paragraph_hash VARCHAR NOT NULL,
  CHECK (char_end >= char_start),
  FOREIGN KEY (filing_id) REFERENCES filings(filing_id)
);

CREATE TABLE spans (
  evidence_id VARCHAR PRIMARY KEY,
  filing_id VARCHAR NOT NULL,
  paragraph_id VARCHAR NOT NULL,
  span_basis VARCHAR NOT NULL CHECK (span_basis IN ('raw_md', 'clean_text')),
  span_kind VARCHAR NOT NULL CHECK (span_kind IN ('paragraph_seed', 'sentence', 'clause', 'phrase')),
  parent_evidence_id VARCHAR,
  created_by_stage VARCHAR NOT NULL CHECK (created_by_stage IN ('ingest', 'extract')),
  char_start INTEGER NOT NULL,
  char_end INTEGER NOT NULL,
  quote_text VARCHAR NOT NULL,
  quote_hash VARCHAR NOT NULL,
  CHECK (char_end >= char_start),
  FOREIGN KEY (filing_id) REFERENCES filings(filing_id),
  FOREIGN KEY (paragraph_id) REFERENCES paragraphs(paragraph_id)
);
"""
