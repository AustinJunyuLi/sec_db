# Architecture Decisions

Decision 1: use a canonical representation rather than direct bidder-row extraction. The alternative was to extract `estimation_bidder_rows` directly from text. Direct extraction is shorter, but it would discard advisors, counsel, committees, go-shops, process restarts, and ambiguous events that future views need. The chosen design stores deals, cycles, actors, events, links, terms, and judgments, then derives bidder rows deterministically.

Decision 2: separate events from judgments. The alternative was to encode boundary, dropout, and comparability decisions as event attributes. That makes review difficult because a filing event and an analyst interpretation are different objects. The chosen design keeps events as dated narrative facts and judgments as scoped interpretations with confidence, basis, alternatives, and evidence.

Decision 3: require evidence spans for every canonical object. The alternative was table-level provenance, such as one citation per row group or filing-level references. That is too weak for audit. The chosen design uses `SourceSpan` objects with section, page hint, paragraph, character offsets, quote, and hash. Every object points to evidence, allowing row-level review.

Decision 4: make formal boundaries nullable. The alternative was to force the nearest diligence or signing event into a boundary field for every cycle. That would destroy variation in whether a formal/informal split exists. The chosen design creates a null `formal_boundary` judgment plus a boundary-absence marker event, so no-boundary cycles remain valid and informal bids can still be ranked before the marker.

Decision 5: reserve `proposal_submitted` for estimator-eligible proposals. The alternative was to label every offer-like statement as `proposal_submitted` and rely on later filters. Because `derive_views.py` uses event type and date, that would misclassify incomplete unsolicited letters or post-rejection reengagements as formal bids. The chosen design stores those facts under separate proposal event types while preserving their values for future analyses.

Decision 6: represent aggregate unnamed bidders explicitly. The alternative was to ignore unnamed parties because their individual values are hidden. Ignoring them would understate `J` and process intensity. The chosen design stores aggregate count evidence and, when needed for cycle counts, deterministic anonymous actors with null bid values and incomplete-scope flags. This preserves count information without inventing individual bids.

Decision 7: model go-shops as process segments with configurable cycle relation. The alternative was to always merge go-shops into the primary cycle or always create a second auction cycle. Both are defensible for different research questions. The chosen design records go-shop start, end, outreach, proposals, and terms, then stores `cycle_relation` so a projection can merge or split later.

Decision 8: classify dropout through evidence-linked competing mechanisms. The alternative was to infer dropout from absence from the formal stage. That would conflate target screening with voluntary withdrawal. The chosen design uses explicit rejection, withdrawal, inability-to-proceed, no-response, and silence evidence. It emits `ambiguous` where causal order is not recoverable.

Decision 9: keep bid units and comparability judgments instead of aggressive conversion. The alternative was to convert every value to a per-share cash equivalent. The filings contain CVRs, enterprise values, aggregate equity values, verbal floors, and incomplete offers. The chosen design stores original unit, normalized numeric fields where safe, and `valuation_comparability` judgments. Conversion beyond the filing evidence is deferred.

Decision 10: use deterministic IDs. The alternative was random IDs or database autoincrement keys. Those make regression tests and audit diffs noisy. The chosen design constructs IDs from deal slug, object type, cycle sequence, actor alias, and sequence number after reconciliation. Rule-version changes are allowed to change IDs, but unchanged inputs and rules should not.

Decision 11: keep auxiliary deal terms in typed tables rather than raw notes. The alternative was to put breakup fees, go-shop lengths, and financing conditions into event notes only. That would block future projections. The chosen design stores `deal_terms` with term type, value, unit, date, and evidence, while linked events preserve when the term was disclosed or negotiated.

Decision 12: treat validation as export control. The alternative was to export all rows and let the estimator discover problems. That is unsafe because invalid boundaries, unsupported dropout labels, or impossible bid ranges can change inference. The chosen design blocks hard integrity failures and exports soft ambiguities with explicit flags and review artifacts.

Decision 13: store participation counts separately from actor rows. The alternative was to rely only on actors, including anonymous actors, to represent counts. That makes aggregate statements hard to audit and can confuse named-bidder counts with process-intensity counts. The chosen design stores count facts in `participation_counts` and creates anonymous actors only when a projection needs row-level completeness.

Decision 14: make bid normalization an auditable object. The alternative was to place normalized values directly on proposal events and trust the number. Because ranges, floors, ceilings, CVRs, and aggregate values are common, the chosen design records the raw amount text, center rule, operator, and conversion basis. This makes the reason for every `bI`, `bI_lo`, and `bI_hi` inspectable.

Decision 15: keep admission decisions even though the current view computes admission from `bF`. The alternative was to omit explicit admission events because `derive_views.py` does not consume them. That would prevent future analysis of bidders admitted to diligence who never submitted a formal bid. The chosen design stores admission decisions canonically and lets the current view continue to use its existing definition.
