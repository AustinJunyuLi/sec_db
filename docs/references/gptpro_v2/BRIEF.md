# Research Target Brief

## 1. The research domain

The downstream consumer of your pipeline is an empirical research project on **takeover auctions in U.S. M&A**. Specifically: when a public company is sold, the sale process often runs in two phases — an *informal* phase, where prospective acquirers submit non-binding indications of interest, and a *formal* phase, where a screened subset submits binding offers after due diligence.

The research is interested in what happens at the *informal* phase: how many bidders show up, how they bid, how the target screens them, and how this informal stage shapes the final outcome. There is a long literature on takeover auctions, but most of it studies the formal phase because formal bids are observable in announcement filings. The informal phase is harder to study because the data lives in narrative form inside the eventual merger proxy ("Background of the Merger" sections), and not all bidders survive into the formal stage.

The empirical work uses a structural model of this two-stage process. The model's parameters answer questions like:
- Are informal bids systematically biased relative to a benchmark of "fully informative" bidding? (Cheap-talk wedge.)
- Which features of an auction predict who the target lets into the formal round? (Screening rule.)
- Do strategic acquirers face systematically different treatment than financial sponsors? (Type effect.)
- Do imprecise bids (wide ranges) face a systematically higher hurdle? (Precision effect.)
- How much information does the target update on, between informal and formal stages? (Due-diligence noise.)

You do not need to know more about the model than this paragraph. The model exists. It is implemented. It is the consumer of your pipeline's output.

## 2. The data your pipeline must produce

This is an **ongoing research program**, not a one-shot estimation. Your pipeline produces a **structured representation** of each deal. The bidder-cycle table specified in `derive_views.py` is *one canonical view* of this representation, used by the current structural estimator. Adjacent research queries — present and future — will use other views over the same representation without re-extracting filings.

### 2.1 The primary view: bidder-cycle rows

The structural estimator consumes one row per (bidder × auction-cycle). The schema is defined precisely in `derive_views.py`. Read that file. The fields it consumes are:

**Per bidder-cycle:**

| Field | Meaning | Why the model needs it |
|---|---|---|
| `bI` | Informal bid value | Center of the informal-bid likelihood |
| `bI_lo`, `bI_hi` | Informal-bid range bounds | Range bids are common; both bounds carry information |
| `w_logwidth = log(bI_hi / bI_lo)` | Log-width of the bid interval | Identifies whether wider/imprecise bids face a higher screening hurdle |
| `bF` | Formal bid value (when admitted) | Center of the formal-bid likelihood |
| `admitted` | 0/1: did this bidder cross the formal-stage boundary? | The screening indicator |
| `T` | Bidder type: 1 = strategic (operating company), 0 = financial (PE/sponsor) | Identifies type-shift in screening |
| `formal_boundary` | The transition event/date that separates informal from formal phase for this cycle | Defines the partition that everything else hangs on |
| `dropout_mechanism` | Categorical: target-rejected, voluntarily-withdrew, ambiguous, n/a-admitted | Distinguishes "screened out by target" from "left of own accord" — see §3 |
| `cycle_id` | Identifier for the auction-cycle this bidder belongs to | A single deal can contain multiple cycles (terminated → restarted) |

**Per auction-cycle:**

| Field | Meaning |
|---|---|
| `J` | Number of bidders in this cycle (count of bidder rows) |
| `g^S` | Fraction of bidders that are strategic |
| `r_23` | Normalized spread between 2nd and 3rd-highest informal bids: `(b^I_(2) − b^I_(3)) / (½ \|b^I_(2) + b^I_(3)\|)` |
| `mean_w` | Auction-mean of `w_logwidth` |
| `S` | Selection indicator: did this cycle reach the formal stage at all? |

`derive_views.py` is the contract for this view. If a definition there conflicts with this brief, `derive_views.py` wins.

### 2.2 The richer representation

The bidder-cycle table is a *projection* of a richer structured representation. Adjacent research queries will run on the same representation without re-extracting filings. Examples of queries the pipeline must support — not produce, but support — without re-extraction:

- *Does the strength/identity of the target's legal counsel predict whether the deal exhibits a formal/informal boundary at all?* (i.e., is the boundary endogenous to deal-design choices?)
- *Do deals with longer go-shop windows attract more topping bids, conditional on initial deal premium?*
- *How does board-committee composition (independent vs. inside directors, special committee vs. full board) shape the screening rule the target applies?*
- *Do deals with breakup fees in the lower tail of the distribution see more aggressive informal bidding?*
- *Does prior bidder-target interaction (toehold, prior acquisition attempt, existing commercial relationship) predict admission probability?*
- *Do deals where the financial advisor has a recent track record on similar transactions show different screening behavior?*

These are illustrations, not the research target. Your pipeline does not produce these analyses. It produces data such that an analyst can write a new view function without going back to the filings.

### 2.3 Auxiliary data to retain

Illustrative, not exhaustive. Retain when the filing supports the field; do not invent.

**Deal-level:**
- Target and acquirer legal counsel (firm names, individual attorneys when prominent)
- Target and acquirer financial advisors (and any adviser changes during the process)
- Board committee structure: special committee, transaction committee, full board, independent directors
- Deal terms: consideration form (cash, stock, mixed, CVR), breakup fee, reverse breakup fee, go-shop window length, MAC clauses, regulatory contingencies, lock-up provisions
- Filing form (DEFM14A, PREM14A, S-4, SC-TO-T) and key dates (announcement, signing, closing)

**Process-level:**
- Advisor engagements (which advisor, what role, when engaged, when terminated)
- Process events that don't bear on bid extraction but show structure: data-room access dates, management presentations, exclusivity grants, standstill agreements, NDA signatories
- Process boundaries: termination events, restart events, go-shop transitions

**Participant-level:**
- Known aliases (the filing's "Sponsor A" and any later disambiguation to a real entity)
- Industry, public/private status, country of domicile
- Prior interactions with target (commercial relationship, prior bid, toehold)
- Group/consortium membership and the dates that membership was active
- Advisor associations (which financial advisor, which counsel)

**Event-level:**
- Source filing, section, page or paragraph, character span, verbatim quote
- Confidence/ambiguity tags when the filing is unclear
- Linked events (a revised bid linked to its prior; a withdrawal linked to its NDA; an admission decision linked to the bid it ruled on)

**Principle.** Do not discard data you can extract cheaply just because the current estimator does not consume it. Do not invent data you cannot extract. When a field is absent in a filing, mark it absent — do not impute.

## 3. The dropout-vs-screening identification problem

This is the hardest design problem your pipeline faces, and the central methodological concern for the downstream model.

**The problem.** When a bidder participates in the informal phase but does *not* appear in the formal phase, two scenarios are observationally similar:

- **Screened out:** The target reviewed the informal bid and declined to admit the bidder to formal due diligence.
- **Dropped out:** The bidder voluntarily withdrew before the target made an admission decision (changed strategic priorities, lost financing, found a better target, etc.).

Both produce the same surface fact: this bidder was in the informal phase but not the formal phase. But the implications for the structural model are completely different — screening is the parameter the model is trying to estimate; voluntary dropout is contamination that biases the estimate if mistaken for screening.

**What filings say.** SEC merger proxies sometimes describe explicitly which case applied ("the company informed Sponsor A that it would not be invited to the next round," vs. "Sponsor A withdrew citing changes in its investment strategy"). Often they do not. Often the language is deliberately ambiguous because both target and bidder have reasons to obscure who walked away first.

**What the pipeline must do.** Your `dropout_mechanism` field must distinguish these cases when the filing supports it, and explicitly mark ambiguity when it does not. A pipeline that silently labels every non-admission as "screened out" — or every non-admission as "dropped" — corrupts the estimator's input. A pipeline that produces a confidence-tagged judgment with explicit ambiguity is fine, even valuable.

**What you do not have to solve.** You do not have to *resolve* fundamental ambiguity. The downstream model has a robustness extension that handles unresolved dropout-vs-screening as a sensitivity parameter. Your pipeline's job is to give the estimator the cleanest signal the filings actually support, with calibrated uncertainty when they don't.

**The boundary itself may not exist.** Some deals are pure negotiations with one counterparty, with no informal/formal phase distinction. Some run informal-only processes with no formal round at all. Some have a process structure that genuinely resists a formal/informal split. **Do not force a boundary where the filing does not support one.** When a cycle has no formal boundary, mark it explicitly: `formal_boundary` is null, `admitted` is undefined for all bidders in that cycle, `bF` is undefined, and the cycle's `S` selection indicator is appropriately marked. Whether boundaries exist — and what predicts their existence — is itself an empirical question downstream researchers may want to study (see §2.2). The pipeline must not silently destroy that variation.

## 4. The auction-cycle concept

A single SEC merger filing can describe **multiple auction cycles** for the same target. The most common pattern: the target runs a sale process, terminates it (no satisfactory bid arrives, the market shifts, an event disrupts the process), then restarts a different process months or years later. Bidders who participated in the earlier process may or may not return.

For the structural model, a *cycle* is one observation — one auction. Bidders are scoped to the cycle they participated in. A bidder who appeared in the terminated 2014 process and again in the 2016 restarted process is two rows, with different `cycle_id` values and likely different bid values, types, and outcomes.

Your pipeline must identify cycles within filings. The boundary signals are typically:
- An explicit statement that the previous process is being terminated, suspended, or abandoned
- A long gap (many months) of no auction activity, followed by a new initiation event
- A change in advisor, board committee, or strategic posture
- An external event (a merger negotiation with a different counterparty, a major announcement, a market shock) that resets the process

Some filings describe one cycle. Some describe two. Some describe a primary cycle with a "go-shop" tail — a brief post-signing window where the target solicits topping bids. Whether the go-shop is "the same cycle" or a "new cycle" is a design decision; it depends on whether downstream queries treat go-shop activity as continuous with the primary process or as a structurally distinct second auction. Both views are reasonable; preserve enough metadata that either projection can be defined later.

A cycle may also lack a formal phase entirely (see §3). When this happens, the cycle still exists as a unit of observation — it just has no formal-stage events. The pipeline's representation must accommodate cycles with and without a formal boundary, without privileging the boundary-having case.

## 5. Out of scope (do not design)

- The structural estimator (selection-aware MH-within-Gibbs) and its likelihood. It exists and is the consumer of your output.
- The structural model class (two-stage screening with cheap-talk wedge). Treat as fixed.
- Other Informal_bids skills (boundary classification has its own skill spec; you don't need to redesign it, but you must produce a `formal_boundary` field consistent with what such a skill would consume).
- LLM provider binding. Your design is conceptual. Provider-specific operational concerns (rate limits, streaming, tool protocols) are deferred to a future packet.

## 6. References for optional depth

If you want more depth on the model, the following are available *outside* this packet (do not request them as part of your response — they exist; you are told they exist):

- The structural estimation report (Jan 2026), describing the two-stage model, identification, and Bayesian estimator
- The dropout-contamination report (Feb 2026), describing the competing-risks extension and Monte Carlo evidence on which parameters are robust to dropout misclassification
- The `Informal_bids` repository, containing `derive_views.py` (which you have), the estimator code, and supplementary skills

Your design must be self-contained against this packet. References above are context, not required reading.

## 7. Filing characteristics

The four attached files are extracts from SEC merger proxy statements (DEFM14A or similar forms). Each extract begins at the section titled "Background of the Merger" and ends at the start of the "Merger Agreement" boilerplate section. Sections included in each extract: Background of the Merger; Reasons for the Merger; Recommendation; Opinion of the Financial Advisor; Interests of Directors and Officers; in some cases Financing of the Merger, Voting Agreements, Material U.S. Federal Tax Consequences, and Litigation Related to the Merger. **Excluded:** the formal merger-agreement legal text, dissenters' rights notices, voting procedures, beneficial ownership tables, shareholder proposals, and SEC filing boilerplate.

The trimming was operational (full proxies are 4–6× over context budget). It does not pre-segment the auction narrative within each filing — the Background section is delivered as continuous text, with the original document's pagination markers (`<!-- PAGE n -->`) preserved as in-text annotations. Whether to use those markers, ignore them, or design a different provenance scheme is your decision.

Other characteristics common to these filings:

- Bidders are often referred to by anonymized aliases ("Sponsor A," "Bidder 2," "Buyer Group") with definitions sometimes elsewhere in the same document
- Bid values are quoted in mixed forms: per-share, total enterprise value, ranges, "at least X," "approximately X," "not above X," verbal-only valuations
- Dates appear in mixed forms: exact ("June 14, 2014"), rough ("early July"), relative ("over the next several weeks"), and milestone-anchored ("on the Friday following the board meeting")
- Filings vary in length, density, and the order in which information is presented
- Some bidders participate as consortia ("Buyer Group" being shorthand for several real entities); membership can change over time
- Some filings describe groups whose constituents are partially anonymous and partially named
- Filings include details adjacent to the auction narrative (financial-advisor identity and methodology, target/acquirer legal counsel, board-committee structure, deal terms summarized) — see §2.3 for what to retain

Each filing is one example of one deal. Together, they span enough variation that your pipeline can be designed to handle the patterns SEC merger filings actually present. They do not span all variation in the corpus the pipeline will eventually run on.
