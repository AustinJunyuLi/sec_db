# Data Model

The data model has three layers: ingested text, extraction candidates, and canonical records. The canonical layer is the contract for projections. It must contain the tables referenced by `derive_views.py`, plus auxiliary tables that retain deal, process, participant, and term data.

`CleanFiling` is the document object. Fields are `filing_id`, `deal_slug`, `source_filename`, `document_hash`, `raw_text_hash`, `clean_text_hash`, `created_at`, `parser_version`, `section_index`, `page_marker_index`, and `paragraph_index`. `section_index` stores section names with start and end character offsets. `page_marker_index` stores original `<!-- PAGE n -->` markers and their offsets. `paragraph_index` assigns deterministic paragraph IDs after cleaning. Provenance for document-level fields is the whole file hash.

`SourceSpan` is the evidence primitive used everywhere else. Fields are `evidence_id`, `filing_id`, `section`, `page_hint`, `paragraph_id`, `char_start`, `char_end`, `quote`, `quote_hash`, and `normalization_note`. Page hints are optional because page markers can be missing or duplicated; character offsets are mandatory. A span may cover a sentence, table row, bullet, or short paragraph. Every canonical object except run metadata must reference at least one `evidence_id`.

`ExtractionCandidate` is an intermediate object. It stores `candidate_id`, `candidate_type`, `raw_value`, `normalized_value`, `confidence`, `evidence_ids`, `dependencies`, and `status`. Candidates may be conflicting. They are not canonical until aggregation resolves them or emits a judgment with alternatives. Candidate types include `actor_mention`, `alias_definition`, `bid`, `date`, `board_action`, `advisor_engagement`, `deal_term`, `process_boundary`, `withdrawal`, `rejection`, `group_membership`, and `prior_relationship`.

Canonical `deals` fields are `deal_slug`, `target_name`, `filing_url`, `filing_type`, `filing_date`, `deal_outcome`, `winning_acquirer`, `date_announced`, `date_signed`, `date_effective`, `consideration_type`, `consideration_value`, `currency`, and `evidence_ids`. Only fields present in the filing or supplied by filing metadata are filled. Missing SEC metadata remains null with an open-question flag.

Canonical `process_cycles` fields are `deal_slug`, `cycle_id`, `cycle_sequence`, `cycle_start_date`, `cycle_end_date`, `date_precision_start`, `date_precision_end`, `segmentation_basis`, `cycle_label`, and `evidence_ids`. A cycle may be a broad sale process, a restarted process, a single-party negotiation, or a go-shop tail. `cycle_relation` is stored as a judgment rather than embedded, so alternative projections can treat go-shops as same-cycle tails or separate cycles.

Canonical `actors` fields are `deal_slug`, `actor_id`, `actor_label`, `actor_type`, `bidder_subtype`, `is_grouped`, `group_size_if_known`, `public_private_status`, `country`, `industry`, `alias_status`, and `evidence_ids`. `actor_type` includes `target`, `bidder`, `acquirer`, `advisor`, `legal_counsel`, `shareholder`, `board_committee`, `regulator`, and `other`. `bidder_subtype` is `strategic`, `financial`, `mixed_group`, or `unknown`. Unknown anonymous bidders may be represented as deterministic labels such as `anonymous_ioi_bidder_03` when an aggregate count requires row creation.

Canonical `events` fields are `deal_slug`, `cycle_id`, `event_id`, `event_date_start`, `event_date_end`, `date_precision`, `event_type`, `event_subtype`, `bid_value`, `bid_value_lower`, `bid_value_upper`, `bid_value_unit`, `consideration_type`, `source_text`, `source_page_hint`, `raw_note`, and `evidence_ids`. Dates use ISO strings when exact and normalized interval endpoints when rough. `date_precision` values include `exact`, `day_inferred`, `month`, `quarter`, `season`, `relative`, and `unknown`. Bid units include `per_share`, `equity_value`, `enterprise_value`, `total_transaction_value`, `asset_value`, and `verbal_non_numeric`.

The event vocabulary distinguishes estimator-eligible proposals from adjacent events. `proposal_submitted` is reserved for proposals that should be eligible for `bI` or `bF` in the current bidder-cycle view. `proposal_reengagement`, `proposal_incomplete_unsolicited`, and `proposal_out_of_scope` retain economically relevant bids that should not automatically create formal admission in `derive_views.py`. Other event types include `outreach`, `nda_signed`, `data_room_opened`, `management_presentation`, `process_letter_sent`, `draft_agreement_sent`, `admission_decision`, `rejection_notice`, `withdrawal`, `exclusivity_granted`, `agreement_signed`, `go_shop_started`, `go_shop_ended`, `process_terminated`, `advisor_engaged`, `board_meeting`, and `deal_term_disclosed`.

`event_actor_links` fields are `event_id`, `actor_id`, `role`, `link_confidence`, and `evidence_ids`. Roles include `submitter`, `recipient`, `target`, `advisor`, `counsel`, `committee`, `member`, `withdrawing_party`, `rejecting_party`, `financing_source`, and `counterparty`.

`judgments` fields are `deal_slug`, `judgment_id`, `judgment_type`, `scope`, `cycle_id`, `actor_id`, `event_id`, `value`, `confidence`, `basis`, `source_snippet`, `alternative_value`, `alternative_basis`, and `evidence_ids`. Required judgment types are `formal_boundary`, `cycle_regime`, `cycle_visibility`, `cycle_relation`, `scope_validity`, `valuation_comparability`, and `dropout_mechanism`. Additional judgment types include `actor_type_basis`, `alias_resolution`, `bid_normalization_basis`, and `no_formal_boundary_reason`.

Auxiliary canonical tables retain non-estimator data. `advisor_engagements` stores advisor actor, client actor, role, start date, end date, and evidence. `legal_counsel_engagements` is parallel. `board_committees` stores committee name, authority, member actors, independence status, and dates. `deal_terms` stores term type, value, unit, effective date, and evidence; examples are go-shop length, termination fee, reverse termination fee, voting agreement, financing condition, and regulatory condition. `group_memberships` stores grouped bidder actor, member actor, start date, end date, and evidence. `prior_relationships` stores bidder-target relationship type, description, date range, and evidence.

Illustrative canonical sketch:

```json
{
  "event_id": "petsmart_2014_evt_043",
  "cycle_id": "petsmart_2014_cycle_01",
  "event_type": "proposal_submitted",
  "event_subtype": "final_bid",
  "event_date_start": "2014-12-12",
  "date_precision": "exact",
  "bid_value": 83.00,
  "bid_value_lower": 83.00,
  "bid_value_upper": 83.00,
  "bid_value_unit": "per_share",
  "consideration_type": "cash",
  "evidence_ids": ["petsmart_span_077"]
}
```

All identifiers are deterministic within a filing: slug plus object type plus sequence. Re-runs over unchanged text must produce the same IDs unless the extraction rules change; rule-version changes are recorded in run metadata.

`participation_counts` is an auxiliary table used when the filing reports process counts without naming every party. Fields are `deal_slug`, `cycle_id`, `count_type`, `count_value`, `strategic_count`, `financial_count`, `unknown_count`, `process_stage`, `date_start`, `date_end`, and `evidence_ids`. Count types include `contacted`, `confidentiality_signed`, `ioi_submitted`, `loi_submitted`, `management_presentation`, `data_room_access`, `go_shop_contacted`, and `go_shop_interested`. This table preserves the exact count even when anonymous actors are also created for estimation-row completeness.

`bid_normalizations` records how raw bid language was converted into numeric fields. It stores `event_id`, `raw_amount_text`, `currency`, `operator`, `center_rule`, `unit_rule`, `lower_source`, `upper_source`, `conversion_applied`, `conversion_basis`, `confidence`, and `evidence_ids`. The default center rule for a closed range is midpoint. No center is created for a floor, ceiling, CVR-only value, or aggregate value unless the filing supplies a defensible center.

`cycle_phase_assignments` stores how events are interpreted relative to a boundary. Fields are `event_id`, `cycle_id`, `phase`, `phase_basis`, `eligible_for_estimation_view`, and `evidence_ids`. Phase values are `pre_boundary`, `formal`, `post_signing_go_shop`, `outside_process`, and `unknown`. The current `derive_views.py` projection relies mainly on event type and boundary date, but this auxiliary table makes the intended phase auditable and supports future projections that separate admission from formal bid submission.

A compact canonical bidder-cycle object can be materialized for review, although it is not the source of truth. It contains `deal_slug`, `cycle_id`, `actor_id`, `latest_informal_event_id`, `selected_formal_event_id`, `formal_boundary_judgment_id`, `dropout_judgment_id`, `scope_validity_judgment_id`, and `evidence_ids`. This materialization is useful for testing because it exposes exactly which canonical objects feed a row without replacing the underlying event and judgment tables.

`run_metadata` is outside the research schema but required for reproducibility. It stores `run_id`, `input_archive_hash`, `filing_ids`, `ingestion_version`, `extraction_config_version`, `reconciliation_version`, `validation_version`, `projection_version`, `started_at`, and `completed_at`. It has no source-span requirement because it describes the construction run rather than a filing fact.

Null semantics are standardized. A null factual field means absent from the filing, hidden by aggregation, not applicable under the cycle regime, or not yet supplied by external metadata. The reason is not inferred from null alone; it is stored in `scope_validity`, `valuation_comparability`, `cycle_visibility`, or a specific open metadata flag. This prevents analysts from confusing missing evidence with a zero value or negative fact.
