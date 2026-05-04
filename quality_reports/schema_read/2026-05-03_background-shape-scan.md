# Background Section Shape Scan For Robust Schema

**Date:** 2026-05-03
**Branch:** `schema-robustness-readfirst-20260503`
**Scope:** Read-first schema reconnaissance for a 400+ deal pipeline.
**Mode:** Local EDGAR fetches plus read-only parallel agent scan. No pipeline code
was changed for this note.

## Why This Scan Exists

The extraction schema must survive hundreds of merger filings, not only the
three-deal acceptance set. The central question was whether the schema should
force fields like buyer group, final round, go-shop, special committee, or
auction, or whether those should be conditional facts/judgments derived from a
generic graph.

The scan supports the second design. The robust core should preserve:

- source-backed process cycles and phases;
- actors and actor relations;
- events and event-actor links;
- bids/proposals/revisions;
- participation counts by stage;
- deal-protection and conflict facts;
- judgments such as formality, initiation, final-round status, and bidder type
  as evidence-backed projections, not universal required fields.

## Sample And Fetch Result

Reference deals already present locally and marked in `seeds.csv`:

```text
providence-worcester
medivation
imprivata
zep
petsmart-inc
penford
mac-gray
saks
stec
```

Deterministic random sample seed: `20260503`.

Initial 30 random candidates:

```text
robbins-myers-inc
commscope-inc
mead-johnson-nutrition-co
cafepress-inc
l-c-a-vision-inc
vectren-corp
perspecta-inc
syntel-inc
life-time-fitness-inc
polypore-international-inc
snyders-lance-inc
b-m-c-software-inc
acacia-communications-inc
barry-r-g-corp-ohio
standard-microsystems-corp
immucor-inc
young-innovations-inc
habit-restaurants-inc
presstek-inc
press-ganey-holdings-inc
international-rectifier-corp
blackboard-inc
true-religion-apparel-inc
sanderson-farms-inc
cephalon-inc
ancestry-com-inc
iparty-corp
micronetics-inc
pepco-holdings-inc
bioclinica-inc
```

Fetch failure and replacement:

- `cafepress-inc` failed loudly with `MissingOfferToPurchaseError`: the
  `SC TO-T` filing had no selected `EX-99.(A)(1)(A)` Offer to Purchase exhibit.
  This is the correct no-fallback behavior.
- Replacement used: `advent-software-inc`.

Final 30 successfully fetched sample deals:

```text
robbins-myers-inc
commscope-inc
mead-johnson-nutrition-co
l-c-a-vision-inc
vectren-corp
perspecta-inc
syntel-inc
life-time-fitness-inc
polypore-international-inc
snyders-lance-inc
b-m-c-software-inc
acacia-communications-inc
barry-r-g-corp-ohio
standard-microsystems-corp
immucor-inc
young-innovations-inc
habit-restaurants-inc
presstek-inc
press-ganey-holdings-inc
international-rectifier-corp
blackboard-inc
true-religion-apparel-inc
sanderson-farms-inc
cephalon-inc
ancestry-com-inc
iparty-corp
micronetics-inc
pepco-holdings-inc
bioclinica-inc
advent-software-inc
```

## Section Selection Finding

The temporary section excerpts under `tmp/schema_read/background_sections/` are
not reliable as standalone navigation aids. The QA lane found that only three of
39 were complete enough to trust:

- `providence-worcester`: `raw.md` 961-1048.
- `commscope-inc`: `raw.md` 913-986.
- `sanderson-farms-inc`: `raw.md` 1067-1170.

Many false windows were caused by table-of-contents lines, cross-references in
`Reasons`, `Interests`, `Projections`, or merger-agreement summaries, and
converter noise around headings.

Pipeline implication: the evidence map must validate that a selected region is a
chronological sale-process narrative before sending it to Linkflow. It should
fail loudly or mark the region ambiguous when it has only cross-references,
recommendation bullets, projections, litigation, or covenant summaries.

### Raw Ranges To Use

Wrong-section or cross-reference hits; use these raw ranges:

| Deal | Raw range and heading |
|---|---|
| `petsmart-inc` | 1113-1194, `Background of the Merger` |
| `saks` | 848-981, `Background of the Merger` |
| `zep` | 744-911, `Background of the Merger` |
| `l-c-a-vision-inc` | 931-1040, `Background of the Merger` |
| `syntel-inc` | 915-1032, `Background of the Merger` |
| `young-innovations-inc` | 908-1053, `Background of the Merger` |
| `bioclinica-inc` | 465-586, `Background of the Merger` |
| `imprivata` | 901-1114, `Background of the Merger` |
| `mead-johnson-nutrition-co` | 668-818 under `THE MERGER`; explicit heading appears omitted in markdown |
| `penford` | 968-1169, `Background of the Merger` |
| `standard-microsystems-corp` | 933-1056, `Background of the Merger` |
| `barry-r-g-corp-ohio` | 932-1440, `Background of the Merger` |
| `b-m-c-software-inc` | 886-1139, `Background of the Merger` |
| `blackboard-inc` | 1320-1769, `Background of the Merger` |
| `true-religion-apparel-inc` | 767-1136, `Background of the Merger` |
| `press-ganey-holdings-inc` | 1009-1359, `Background of the Merger` |
| `ancestry-com-inc` | 693-946, `Background of the Merger` |
| `snyders-lance-inc` | 1216-1419, `Background of the Merger` |
| `perspecta-inc` | 732-995, `Anchor Background of the Merger` |
| `life-time-fitness-inc` | 1149-1378, `Background of the Merger` |
| `micronetics-inc` | 801-892, `Background of the Merger` |

Correct start but cut off early; use the full raw section:

| Deal | Raw range and heading |
|---|---|
| `medivation` | 554-628, `Background of the Offer`; also inspect 630, `Past Contacts, Transactions, Negotiations and Agreements` |
| `mac-gray` | 726-995, `Background of the Merger` |
| `stec` | 993-1218, `Background of the Merger` |
| `robbins-myers-inc` | 848-953, `Background of the Merger` |
| `vectren-corp` | 857-1072, `Background of the Merger` |
| `polypore-international-inc` | 1002-1175, `Background of the Merger` |
| `immucor-inc` | 823-986, `Background of the Merger` |
| `habit-restaurants-inc` | 980-1275, `Background of the Merger` |
| `presstek-inc` | 827-1028, `Background of the Merger` |
| `international-rectifier-corp` | 764-891, `Background of the Merger` |
| `cephalon-inc` | 858-1021, `Background of the Merger` |
| `iparty-corp` | 628-851, `Background of the Merger` |
| `pepco-holdings-inc` | 1520-1667, `Background of the Merger` |
| `advent-software-inc` | 894-1015, `COMMAND=STYLE_ADDED... Background of the Merger` |
| `acacia-communications-inc` | 1095-1364, `Background of the Merger` |

Heading variants the evidence map must support:

- `Background of the Merger`;
- bold, italic, and plain markdown variants;
- `COMMAND=STYLE_ADDED... Background of the Merger`;
- `Anchor Background of the Merger`;
- `Background of the Merger Agreement`;
- wrappers such as `THE MERGER`, `THE MERGER (PROPOSAL 1)`,
  `PROPOSAL ONE: THE MERGER`, and `SPECIAL FACTORS`;
- tender headings such as `Background of the Offer`,
  `Background of the Offer and Merger`, and
  `Past Contacts, Transactions, Negotiations and Agreements`.

## Deal Shape Notes

### Reference Deals

`providence-worcester`

- DEFM14A. Informal commercial/JV interest became a target-run formal process.
- GHF contacted 11 strategic and 18 financial buyers; mixed population.
- Explicit stage counts: 25 confidentiality agreements, 9 IOIs, 7 management
  presentations, 6 LOIs.
- Finalists were G&W and Party B. Need narrowed-finalist cycles, not only
  literal "final round" labels.
- Committee, late interlopers, recusal/conflict, advisor conflict, non-cash/CVR
  proposal terms.

`medivation`

- Selected document is `EX-99.(A)(1)(A)` Offer to Purchase, not a proxy.
- Buyer-side source points to Schedule 14D-9 for fuller target-side reasons.
- Sanofi hostile/unsolicited pressure, consent solicitation, then Pfizer joins
  process.
- Final revisions visible: Pfizer $65, then $77, then best/final $81.50.
- Schema needs source-perspective/document-perspective fields and a way to say
  target-side full background is elsewhere.

`imprivata`

- DEFM14A. Thoma Bravo inbound interest became target-directed process.
- Contacts: 15 initially listed parties, 11 S and 4 F; later 16 total.
- Preliminary written bids came from financial sponsors only; final bidder F.
- Special committee due management-conflict risk; no go-shop found.
- Need stage-specific bidder type and counts; do not infer strategic bids from
  strategic contacts.

`zep`

- DEFM14A. Two cycles: failed target-led 2014 auction, then 2015 unsolicited New
  Mountain approach.
- Cycle 1: 50 contacted, 28 S and 22 F; five initial bids from four F and one S.
- Cycle 2: single-bidder exclusivity; New Mountain repeatedly best/final at
  $20.05; post-signing go-shop contacted 58 parties, no proposal.
- This is the cleanest warning against one flat sale-process field.

`petsmart-inc`

- DEFM14A. Formal public sale process after activism/market pressure.
- Mixed outreach: 27 potential participants, three strategic and 24 financial;
  active process became financial-heavy.
- Final round explicit, four bidders at/above $80 advanced.
- Buyer Group includes financial sponsors plus Longview rollover/support role.
- Need activist/shareholder pressure separate from bidder initiation and
  rollover separate from management-only categories.

`penford`

- DEFM14A. Bidder-initiated strategic approach by Ingredion plus target-controlled
  targeted market check.
- Deutsche Bank contacted six strategic counterparties; several declined or did
  not respond.
- No broad auction and no explicit final round.
- Executive Committee is not a special committee. SEACOR activism/support is not
  a buyer group.

`mac-gray`

- DEFM14A. Formal target-led sale process after strategic review.
- 50 contacted: 15 S and 35 F; 20 NDAs: 2 S and 18 F.
- Final indications requested; CSC/Pamplona wins as mixed S/F group.
- Special committee formed because MacDonald/Moab conflicts and possible
  rollover were live.
- Need buyer group as process bidder plus underlying actor relations.

`saks`

- DEFM14A. Informal/unsolicited sponsor and Hudson's Bay approaches became
  broader strategic alternatives review.
- Mixed population; shifting losing buyer groups among sponsors.
- No clean best/final final round; focused negotiation to $16.
- Go-shop explicit: 58 contacted, 6 interested, 1 NDA/diligence, 0 proposals.
- Company B was an alternative acquisition target for Saks, not a bidder for
  Saks.

`stec`

- DEFM14A. Target-initiated strategic alternatives after underperformance and
  activism.
- 18 acquirers contacted: 17 tech companies and one financial sponsor.
- Full-company bids and asset-only interests both appear; final round letters to
  WDC and Company D.
- Special committee, don't-ask-don't-waive standstills, activist pressure, and
  Moshayedi ancillary agreements.
- Need full-company vs asset-only proposal typing.

### Random Sample Deals

`robbins-myers-inc`

- DEFM14A. Target/Citi limited strategic outreach, not broad auction.
- Strategic-only bidder population; NOV became only remaining bidder.
- Final negotiation by revisions with one bidder, not a formal final round.

`commscope-inc`

- DEFM14A. Carlyle-initiated mostly bilateral pre-signing process.
- Post-signing go-shop is central: 71 contacted, 30 S and 41 F; consortium
  "Bidder A" formed; no proposal.
- Negative management rollover fact appears and should be recordable.

`mead-johnson-nutrition-co`

- DEFM14A. Explicit Background heading appears omitted in markdown; narrative
  starts under `THE MERGER`.
- Strategic/bilateral Reckitt process; Reckitt resisted auction for leak risk.
- No formal final round; Reckitt held at $90.
- Go-shop was proposed and rejected for lower termination-fee terms.

`l-c-a-vision-inc`

- DEFM14A. Strategic bilateral process after long acquisition-search history.
- Final best/final $5.37 from PhotoMedex.
- Post-signing go-shop contacted 48 strategic buyers, 2 CAs/diligence, no
  alternative proposal.
- Consideration included contingent warrants/special-dividend mechanics; do not
  assume simple cash-only bid fields.

`vectren-corp`

- DEFM14A. Target-initiated formal limited market assessment.
- Seven counterparties: six utilities and one infrastructure fund; mixed
  population, final buyer S.
- Round structure and best/final present; no go-shop or special committee.
- Bid terms include cash/stock mix, collars, regulatory commitments, termination
  fees, employee/community commitments, and board seats.

`perspecta-inc`

- DEFM14A, Special Factors / `Anchor Background of the Merger`.
- Activist pressure, PE inbound, standstill-waiver issue, then board-directed
  outreach.
- Mixed population; Veritas final buyer F; final round cash-vs-stock comparison.
- Sponsor/entity/board-affiliation relations and Rule 13E-3 posture matter.

`syntel-inc`

- DEFM14A. Atos initiated by unsolicited email/call; target ran limited process.
- Active bidders mainly S; one PE inbound did not produce indication.
- Special committee; Atos best/final $41.
- Founder voting agreement separate from bidder process.

`life-time-fitness-inc`

- DEFM14A. PE Party A unsolicited offers led to formal sale process.
- Mixed outreach but final bidders F; special committee due Akradi rollover and
  management-discussion concerns.
- Final round explicit; go-shop appeared as negotiated/draft term, not executed
  in the scanned background.

`polypore-international-inc`

- DEFM14A. Strategic, nonstandard two-buyer structure.
- Asahi merger plus 3M separations-media sale are cross-conditional.
- Buyer population S; no broad auction despite many alternatives considered.
- Need business-line proposal and whole-company proposal distinction.

`snyders-lance-inc`

- DEFM14A. Campbell strategic CEO outreach; target not actively seeking sale.
- Target then contacted strategic Companies A-D.
- Special committee due Warehime family/large-shareholder conflict, not
  management rollover.
- Final round collapses to one bidder; Company E non-actionable inquiry.

`b-m-c-software-inc`

- DEFM14A. Activist Elliott pressure; two sale-process cycles.
- 2012 process discontinued; 2013 process reinitiated.
- Final buyer F consortium expanded with GICSI and Insight.
- 30-day go-shop: 7 sponsors and 9 strategics contacted, no alternative.
- Must separate go-shop counts from pre-signing auction counts.

`acacia-communications-inc`

- DEFM14A. Multiple informal strategic contacts over 2017-2019.
- Cisco/Parent initiated as customer; no broad auction.
- Higher nonbinding Party C offer lost to Parent due timing/diligence/certainty.
- Need strategic partnership/customer relationship separate from acquisition bid.

`barry-r-g-corp-ohio`

- DEFM14A. Repeated unsolicited Mill Road approaches from 5-10% holder.
- No pre-signing auction; post-signing 30-day go-shop.
- Party A made nominally higher $21 offer but rejected over antitrust/certainty.
- Need shareholder-bidder status, regulatory-certainty judgment, and excluded
  party/go-shop state.

`standard-microsystems-corp`

- DEFM14A. Strategic Microchip CEO contact led to bilateral negotiation and
  limited market check.
- S-only active process; Company A surfaced during exclusivity but not contacted.
- Need limited-market-check category separate from auction.

`immucor-inc`

- PREM14A. Multi-year narrative with several cycles.
- Early strategic contacts and later formal strategic process, then TPG/PE entry.
- Final buyer F but overall population mixed over time.
- Regulatory/litigation diligence constraints and go-shop matter.

`young-innovations-inc`

- DEFM14A. Prior 2010 auction-like process, later Linden bilateral PE sale, then
  post-signing go-shop.
- Buyer type F for signed deal; population mixed across cycles.
- Need prior process separated from current sale process.

`habit-restaurants-inc`

- DEFM14A. Highly structured formal auction.
- 85 buyers contacted, 48 NDAs, 46 bid instructions, 10 initial bids.
- Special committee due TRA conflicts; final bids from Parent and Bidder X.
- Final price adjusted downward due cash estimates; TRA conflict is economic
  allocation, not management rollover.

`presstek-inc`

- PREM14A. Distress-driven formal process.
- 54 firms contacted: 31 S and 23 F; 11 presentations; 5 preliminary indications;
  2 final bids, one withdrew.
- Management-retention condition surfaced and was removed.
- Bidder participation is non-monotonic; do not assume a bidder only advances.

`press-ganey-holdings-inc`

- DEFM14A. Strategic inbounds, then management/board confidential sale review.
- 16 strategics and 5 sponsors identified; mixed population; EQT wins.
- Controller/support agreement, go-shop/no-shop, management rollover/equity pool.
- Need controller and deferred-consideration facts separate from bidder group.

`international-rectifier-corp`

- DEFM14A. Infineon informal contact and bidder-initiated proposal.
- Not a broad auction; six other strategic acquirers reviewed, only Company A/B
  contacted after Infineon best/final.
- Need reviewed-but-not-contacted status.

`blackboard-inc`

- DEFM14A. Sponsor-led initiation; board formed independent Transaction
  Committee and chose targeted market check, not formal auction.
- Mixed but heavily F population; buyer/financing partner constraints.
- Need distinction between proposed terms and executed deal terms.

`true-religion-apparel-inc`

- DEFM14A. Unsolicited strategic inquiry, then special committee and broad public
  strategic alternatives process.
- 91 contacted: 30 S and 61 F. Final path became one-surviving-bidder
  negotiation with TowerBrook.
- Rollover should allow negative/currently-no-arrangement states.

`sanderson-farms-inc`

- DEFM14A. Earlier paused process, unsolicited Durational proposal, then 2021
  formal process.
- CGC/Cargill joint Bidder Group approved; final bid/counter/revised price.
- Need actor relations for CGC, Cargill, Wayne Farms, CMSC, and Bidder Group.

`cephalon-inc`

- DEFM14A. Valeant unsolicited hostile proposal and consent solicitation.
- Board contacted 26 strategic parties and 5 sponsors; Teva later wins.
- Asset-only alternative proposal and financing alternatives appear; distinguish
  them from whole-company bids.

`ancestry-com-inc`

- DEFM14A. Party A inbound, then formal Qatalyst outreach to 4 S and 8 PE firms.
- Mixed population; final-bid invitation and actual received final bids diverge.
- Buyer group/rollover central: Permira, co-investors, Spectrum, management.

`iparty-corp`

- DEFM14A. Board review plus Party City/Lessin Estate approach, then special
  committee and Raymond James process.
- Mixed population and post-signing go-shop: 40 contacted, no proposals.
- Consideration included preferred stock; final round is repeated Party City
  revision, not clean multi-bid auction.

`micronetics-inc`

- DEFM14A. Informal multi-year management discussions became formal advisor
  process.
- Mercury strategic and Firm B unsolicited; final selection Mercury versus Firm B.
- Need oral indications, "on or about" dates, exclusivity, and voting agreements.

`pepco-holdings-inc`

- DEFM14A. CEO contacts from Exelon and Bidder A, then formal Phase I/Phase II.
- S-only utility holding-company population; final best/final offers.
- Need regulatory commitments, reverse termination/preferred-stock mechanics,
  DADW standstill waivers, and management retirement/extension facts.

`bioclinica-inc`

- PREM14A. Tender offer plus back-end merger in a proxy-style filing.
- Formal exploratory process; 17 PE funds and 4 strategic partners contacted.
- No clean final auction round; JLL confirms after exclusivity.
- Third-party PE diligence/synergy facts should not become buyer-group facts.

`advent-software-inc`

- DEFM14A. Prior strategic review plus current SS&C strategic approach.
- Current process is strategic bilateral, not broad current auction.
- Strategic Transaction Committee exists; no go-shop.
- Separate historical cycle from active cycle; final round not applicable.

## Cross-Deal Schema Conclusions

1. Use `process_cycles` as a real unit, not a decorative table.

Many filings contain multiple sale-process cycles: failed prior auction plus
later inbound approach (`zep`, `advent-software-inc`,
`young-innovations-inc`, `b-m-c-software-inc`, `immucor-inc`,
`sanderson-farms-inc`). Classifications such as formality, initiation, bidder
type, and final-round status must be cycle-scoped.

2. Keep S/F/mixed as a judgment over actor-cycle facts.

The user only cares about `S`, `F`, and `mixed`, but the evidence rarely lives
as a single deal-level truth. It can differ by stage:

- outreach mixed, active bidders F-heavy (`petsmart-inc`, `b-m-c-software-inc`);
- final winner S but process mixed (`vectren-corp`);
- final winner F but early contacts S (`immucor-inc`);
- buyer group mixed (`mac-gray`);
- unknown or partially inferable labels (`sanderson-farms-inc`).

Recommended projection states: `S`, `F`, `mixed`, `unknown`, with evidence and
cycle/stage scope. User-facing analysis can collapse away `unknown` later, but
the graph should not invent S/F labels.

3. Formal/informal is the most important but must be phase-aware.

Observed shapes:

- broad formal auction;
- limited strategic market check;
- targeted PE/sponsor process;
- bilateral inbound negotiation;
- failed prior process plus later bilateral deal;
- hostile/interloper pressure followed by board process;
- post-signing go-shop as market check.

Do not force a single `formal_bid` boolean. Use process-cycle judgments such as
`formal_auction`, `limited_market_check`, `bilateral_negotiation`,
`post_signing_go_shop`, `hostile_pressure`, and `no_supported_claim`, each with
evidence.

4. Initiation should allow mixed and staged answers.

Several deals begin with bidder/stockholder pressure but later become
target-controlled processes. Examples: `imprivata`, `petsmart-inc`, `saks`,
`syntel-inc`, `press-ganey-holdings-inc`, `cephalon-inc`. The schema should
record initiating events and then project a judgment, not ask GPT for one
global initiator.

5. Final round is important but not universal.

Some deals have clean final rounds (`mac-gray`, `stec`, `habit-restaurants-inc`,
`vectren-corp`, `pepco-holdings-inc`). Others are one-bidder negotiations or
exclusivity revisions (`penford`, `mead-johnson-nutrition-co`,
`advent-software-inc`, `bioclinica-inc`). The schema needs:

- final-round invitation events;
- final-bid received events;
- best-and-final statements;
- one-bidder final negotiation;
- explicit `not_applicable` or `no_supported_claim` when no final round exists.

6. Buyer group and consortium are actor relations, not deal-level fields.

Buyer groups can be winners (`mac-gray`, `petsmart-inc`,
`sanderson-farms-inc`, `b-m-c-software-inc`), losing bidders (`saks`,
`commscope-inc` go-shop), or financing/support relations. They also mutate over
time. Use actor relations with effective cycle/stage, not one static consortium
field.

7. Go-shop/no-shop should be event/protection facts with outcomes.

Go-shop is present in many but absent in many. When present, the important facts
are duration, parties contacted, NDAs, diligence, proposals, excluded-party
status, and termination/no alternative. Do not require go-shop as a deal field.

8. Committees require type distinctions.

Do not collapse all committees into `special_committee`. Observed variants:

- special committee;
- transaction committee;
- strategic transaction committee;
- executive committee;
- finance committee;
- independent/disinterested directors only;
- ad hoc committee for efficiency.

Committee authority and conflict rationale should be source-backed relation or
judgment facts.

9. Conflicts and rollover are broad relation/event facts.

Observed conflict facts include management rollover, no rollover, shareholder
rollover, controller/support agreements, voting agreements, founder/family
conflicts, director recusal, advisor conflict, employment agreements,
non-competes, consulting agreements, TRA/economic allocation issues, and
management-contact restrictions. This should not be a single `management_rollover`
boolean.

10. Proposal objects must be richer than price.

Bids may include ranges, oral indications, stock/cash mix, collars, preferred
stock, CVR/non-cash value, warrants, dividends, asset-only proposals, business
line carve-outs, cross-conditional transactions, financing certainty, regulatory
commitments, termination fees, board seats, employee/community commitments, and
expiration/contingencies.

11. Absence is not failure when a feature is inapplicable.

The prior static-obligation shape risks marking a deal suspicious because a
feature is absent. `buyer group composition` is wrong to require for a single
strategic buyer deal; `final round` is wrong to require for a bilateral
exclusivity deal; `go-shop` is wrong to require generally. Coverage must support
conditional applicability:

- `claims_emitted`;
- `no_supported_claim`;
- `ambiguous`;
- `missed`;
- recommended additional policy layer: obligation applicability such as
  `universal`, `conditional`, `calibration`, and `not_applicable`.

12. Evidence-map obligations should be generated from region facts, not static
deal templates.

Suggested obligation families:

- universal: process initiation events, main process chronology, signed-buyer
  actor, proposal/bid revisions, key count claims when present, deal-protection
  summary;
- conditional after scan triggers: go-shop, buyer group, special committee,
  management/conflict/rollover, hostile/interloper, asset-only proposal,
  support/voting agreement, financing, tender-offer source perspective;
- calibration-only: features useful for Alex but not required for `SOUND`.

## Proposed Robust Extraction Shape

The graph can stay generic as in `docs/spec.md`, but the schema/prompt should
ask for facts at the right granularity.

Recommended claim families:

- `actor_claims`: actor labels, anonymized labels, actor type if evidenced.
- `actor_relation_claims`: member-of, affiliate-of, acquisition vehicle,
  advisor, financier, support holder, rollover holder, voting/support party,
  committee member, recusal/conflict relation.
- `event_claims`: approach, board meeting, committee formation, contact,
  confidentiality agreement, diligence access, management presentation, bid
  deadline, final-bid request, exclusivity, signing, go-shop start/end,
  withdrawal, public/hostile proposal, consent solicitation.
- `bid_claims`: bidder, date, consideration, range/value, form, certainty,
  conditions, best/final status, revision, final/withdrawn/declined status.
- `participation_count_claims`: contacted, signed NDA/CA, management
  presentations, IOIs, preliminary bids, final bids, diligence participants,
  go-shop contacts and outcomes, all with stage/cycle and actor class.
- `judgment_claims` or canonical `judgments`: formal/informal formality,
  target/bidder/mixed initiation, final-round status, bidder-population S/F/mixed,
  process phase labels, and feature applicability.

Important: If there is no explicit `judgment_claims` family in the Linkflow
schema, these should still exist as canonical `judgments` derived from typed
facts and linked to the supporting claim evidence.

## Immediate Next Steps

1. Replace brittle heading extraction with a validated evidence-region builder.
   It must distinguish actual narrative regions from TOC/cross-reference hits
   and should emit ambiguous/fail-loud region results when validation fails.

2. Add applicability-aware coverage obligations. Do not require buyer group,
   go-shop, special committee, final round, or management rollover unless source
   triggers make the obligation applicable.

3. Update the LLM schema/prompt to ask for phase/cycle facts and typed claims,
   not global deal judgments. Let Python/projectors derive Alex-facing
   classifications.

4. Build deterministic projection rules for:
   - bidder type: `S`, `F`, `mixed`, `unknown`;
   - process formality by cycle;
   - initiation by cycle;
   - final-round status by cycle;
   - go-shop/no-shop outcome;
   - buyer group presence and membership.

5. Keep `Medivation` and tender-offer filings as a separate source-perspective
   test. The selected Offer to Purchase can be a valid source, but it is not the
   same document perspective as a target proxy statement.

6. Add a small regression set from this scan before trying 400+ deals:
   - `zep` for multiple cycles;
   - `medivation` for tender/source perspective;
   - `mead-johnson-nutrition-co` for omitted heading and bilateral strategic;
   - `petsmart-inc` for activism/buyer group;
   - `saks` for alternative target-acquisition lane and go-shop;
   - `polypore-international-inc` for business-line/cross-conditional deal;
   - `cephalon-inc` for hostile pressure and asset-only alternative;
   - `habit-restaurants-inc` for formal auction and rich counts.
