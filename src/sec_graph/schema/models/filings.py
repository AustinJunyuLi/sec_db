"""Evidence-layer filing models and DDL."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from sec_graph.schema.evidence import evidence_fingerprint, quote_hash


_NON_PARAGRAPH_SPAN_KINDS: frozenset[str] = frozenset(
    {"sentence", "clause", "phrase", "llm_extract"}
)


class CleanFiling(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    filing_id: str
    deal_slug: str
    source_path: str | None
    raw_sha256: str = Field(min_length=64, max_length=64)
    parser_version: int
    page_count: int | None
    section_count: int | None
    process_scope: Literal[
        "target_full_proxy",
        "bidder_partial_schedule_to",
        "amendment_only",
        "go_shop_only",
    ]


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
    span_basis: Literal["raw_md", "cleaned_paragraph", "clean_text"]
    span_kind: Literal[
        "paragraph_seed", "sentence", "clause", "phrase", "llm_extract"
    ]
    parent_evidence_id: str | None
    created_by_stage: Literal["ingest", "extract"]
    char_start: int = Field(ge=0)
    char_end: int = Field(ge=0)
    quote_text: str
    quote_text_hash: str = Field(min_length=64, max_length=64)
    evidence_fingerprint: str = Field(min_length=64, max_length=64)

    @property
    def quote_hash(self) -> str:
        return self.quote_text_hash

    @model_validator(mode="after")
    def _source_span_contract(self) -> "SourceSpan":
        if (
            self.span_kind in _NON_PARAGRAPH_SPAN_KINDS
            and self.parent_evidence_id is None
        ):
            raise ValueError(
                "parent_evidence_id is required when span_kind is one of "
                f"{sorted(_NON_PARAGRAPH_SPAN_KINDS)}; "
                f"got span_kind={self.span_kind!r} for evidence_id={self.evidence_id!r}"
            )
        expected_hash = quote_hash(self.quote_text)
        if self.quote_text_hash != expected_hash:
            raise ValueError(
                f"quote_text_hash mismatch for evidence_id={self.evidence_id!r}"
            )
        expected_fingerprint = evidence_fingerprint(
            self.filing_id,
            self.char_start,
            self.char_end,
            self.quote_text_hash,
        )
        if self.evidence_fingerprint != expected_fingerprint:
            raise ValueError(
                f"evidence_fingerprint mismatch for evidence_id={self.evidence_id!r}"
            )
        return self


FILINGS_DDL = """
CREATE TABLE filings (
  filing_id VARCHAR PRIMARY KEY,
  deal_slug VARCHAR NOT NULL,
  source_path VARCHAR,
  raw_sha256 VARCHAR NOT NULL,
  parser_version INTEGER NOT NULL,
  page_count INTEGER,
  section_count INTEGER,
  process_scope VARCHAR NOT NULL CHECK (process_scope IN ('target_full_proxy', 'bidder_partial_schedule_to', 'amendment_only', 'go_shop_only'))
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
  span_basis VARCHAR NOT NULL CHECK (span_basis IN ('raw_md', 'cleaned_paragraph', 'clean_text')),
  span_kind VARCHAR NOT NULL CHECK (span_kind IN ('paragraph_seed', 'sentence', 'clause', 'phrase', 'llm_extract')),
  parent_evidence_id VARCHAR,
  created_by_stage VARCHAR NOT NULL CHECK (created_by_stage IN ('ingest', 'extract')),
  char_start INTEGER NOT NULL,
  char_end INTEGER NOT NULL,
  quote_text VARCHAR NOT NULL,
  quote_text_hash VARCHAR NOT NULL,
  evidence_fingerprint VARCHAR NOT NULL,
  CHECK (char_end >= char_start),
  CHECK (
    span_kind = 'paragraph_seed'
    OR parent_evidence_id IS NOT NULL
  ),
  FOREIGN KEY (filing_id) REFERENCES filings(filing_id),
  FOREIGN KEY (paragraph_id) REFERENCES paragraphs(paragraph_id)
);
"""
