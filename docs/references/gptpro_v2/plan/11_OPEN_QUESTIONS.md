# Open Questions and Known Limits

Several fields in the current view or auxiliary design cannot always be extracted from the trimmed filings alone. `filing_url`, `filing_type`, `filing_date`, and often `date_effective` require EDGAR metadata or the untrimmed proxy. The pipeline should accept those as external filing metadata and keep them null when not supplied.

Individual bid values are sometimes hidden behind aggregate descriptions. Providence and Worcester reports nine IOIs with an aggregate range before naming later LOI parties. Zep reports five initial bids with only an aggregate range. In those cases the pipeline can preserve counts, named later values, aggregate ranges, and anonymous actors, but it cannot assign exact individual `bI`, `bI_lo`, or `bI_hi` to every bidder without inventing data.

Bidder type `T` can be unknown for anonymous or partially described parties. The filings sometimes provide aggregate strategic/financial splits, but not labels for every participant. The row should carry `T = null`, `bidder_subtype = unknown`, and a scope flag unless the text supports a strategic or financial classification.

Some `dropout_mechanism` values are fundamentally ambiguous. Silence after a process letter, failure to submit a later bid, or disappearance after a fire or market shock may reflect bidder withdrawal, target screening, or mutual loss of interest. The pipeline should record `ambiguous` with alternatives rather than choose a false binary label.

Formal-boundary placement may need reviewer policy in multi-step processes. Providence and Worcester has IOIs, management presentations, LOIs, reengagement attempts, and a final two-party negotiation. The proposed default is to treat the July 27 shortlist to G&W and Party B as the formal boundary and to store later Party D and Party E submissions as reengagement proposals unless readmission is evidenced. A reviewer may want a stricter or looser boundary policy for the estimator.

External characteristics needed for adjacent research are not fully present. Advisor “strength,” recent advisor track record, bidder domicile, bidder public/private status, exact industry codes, and law-firm rankings require external datasets. The canonical model has fields for them, but this packet’s filings do not supply enough evidence to populate them reliably.

Alias resolution is limited by the filings. `Sponsor A`, `Party B`, `Company H`, and similar labels should not be resolved to real entities unless the filing defines them or external metadata is deliberately introduced. The default is to preserve the alias as the actor label.

Non-cash or mixed consideration requires projection policy. CVRs, stock consideration, enterprise values, and verbal ceilings can be stored faithfully, but converting them into a per-share cash bid for `r_23` or likelihood inputs may require assumptions outside the filing. Such rows should carry valuation-comparability flags until the estimator’s inclusion rule is specified.

The current `derive_views.py` treats `admitted` as the existence of a post-boundary eligible proposal. If the research team needs to distinguish “admitted but withdrew before submitting a formal bid,” the canonical store supports it through admission events, but the current view would need a separate projection field.
