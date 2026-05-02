"""Markdown ingestion into evidence-layer DuckDB tables."""

from .pipeline import IngestSource, ingest_examples, ingest_source

__all__ = ["IngestSource", "ingest_examples", "ingest_source"]
