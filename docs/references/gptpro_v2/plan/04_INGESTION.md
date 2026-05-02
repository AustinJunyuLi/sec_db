# Ingestion: Filing to Clean Text and Provenance Map

Ingestion converts each markdown filing extract into a normalized document plus a precise source map. It does not decide what a bidder, bid, or formal boundary is. Its purpose is to make later extraction auditable and reproducible.

The input is one filing file and optional metadata. The file is read as UTF-8 and assigned `filing_id` and `deal_slug` from the filename unless supplied metadata overrides them. The system stores `raw_text_hash` before any edits. The raw file is never modified in place. The cleaned text, paragraph index, page index, and section index are separate artifacts.

Cleaning is conservative. Preserve substantive text, quotation marks, dollar signs, ranges, dates, party labels, and page markers. Remove or mark repeated navigational artifacts such as `Table of Contents`, printer command strings, and isolated folio numbers only when they can be classified as non-substantive. When such text is removed, record a normalization note with the raw character span. If classification is uncertain, keep the text and let extraction ignore it.

Page markers are parsed from strings such as `<!-- PAGE 35 -->`. Each marker becomes a record with `page_number`, `raw_marker_text`, `raw_char_offset`, and `clean_char_offset`. The page marker is also retained in the clean text unless it disrupts sentence parsing; if removed, its clean offset is attached to the following paragraph. Page hints are not treated as exact legal citations because the extracts include original pagination and operational trimming. They are a helpful provenance label, not the only source reference.

Sections are identified from headings such as `Background of the Merger`, `Reasons for the Merger`, `Opinion of the Financial Advisor`, `Financing`, and `Interests of Directors and Executive Officers`. The ingestion layer assigns section spans even when headings contain command prefixes or bold markers. If a heading cannot be confidently detected, the text remains in an `unknown_section` span and is still available for extraction.

Paragraph segmentation is deterministic. Split on blank lines after cleaning while preserving original offsets. Very long paragraphs remain single paragraphs, because merger proxies often encode multiple dated events in one paragraph; sentence splitting is performed later as an extraction aid, not as the provenance unit. Each paragraph gets `paragraph_id`, section, page hint, raw offsets, clean offsets, and a short hash.

The ingestion output includes a source-span seed for every paragraph. Later extraction can create narrower spans for sentences or clauses, but those narrower spans must remain within a paragraph seed. This prevents floating evidence spans that cannot be traced back to the original file.

The ingestion layer also records document-level warnings. Examples are missing page markers, non-monotonic page markers, command-text density above a threshold, unusually long paragraphs, headings not found, and large deleted spans. These are not extraction errors. They are audit cues that help reviewers understand whether a filing was unusually noisy.

For the four reference filings, ingestion must preserve the original page markers in PetSmart pages 29 through 33, Providence and Worcester pages 35 through 43, Zep pages 35 through 42 with printer command noise, and Saks pages 31 through 36. It must also preserve in-text aliases such as `Industry Participant`, `Party A`, `G&W`, `Party X`, `Sponsor A`, and `Company H`, because alias resolution depends on exact wording.

Acceptance for ingestion is mechanical: re-running on unchanged files produces identical document hashes, paragraph IDs, section spans, page-marker records, and clean text hashes. Later changes to cleaning rules must change `parser_version` and keep both old and new artifacts available for audit.

The source map must support two lookup directions. Given a paragraph or evidence ID, the reviewer can recover raw text, clean text, page hint, and section. Given a raw character offset or page marker, the system can identify the clean paragraph that contains the same material. This bidirectional map is essential when a validation flag points to an object and the reviewer wants to inspect surrounding context rather than only the quoted snippet.

Ingestion also records file-level deal hints. From filenames such as `filing_zep.md`, it proposes a slug, but it does not infer target names from filenames when the text gives a better name. Any such inferred value is marked as a metadata hint until extraction or supplied metadata confirms it.
