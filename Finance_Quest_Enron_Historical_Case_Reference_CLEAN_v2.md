---
title: "Finance Quest — Enron Corporation: Historical Case Reference"
case_id: FQ-AV-001
version: "2.2"
prepared_on: "2026-11-20"
language: en
historic_entity: "Enron Corporation"
fictional_campaign: "The Golden Guild's Secret"
market_data_file: "Enron_ENE_Historical_OHLCV_2001-08_to_2001-12.csv"
---

# Finance Quest — Enron Corporation
## Historical Case Reference

**Campaign:** *The Golden Guild's Secret*  
**Company:** Enron Corporation (`ENE`, NYSE; historical listing)  
**Research date:** November 20, 2026  
**Coverage:** Company background, contemporaneous financial statements, historical events, public information chronology, fantasy adaptation, and linked source documents.  
**Companion market dataset:** [Enron_ENE_Historical_OHLCV_2001-08_to_2001-12.csv](Enron_ENE_Historical_OHLCV_2001-08_to_2001-12.csv), 102 dated OHLCV records from August 1 to December 31, 2001.

**Reading the evidence.** Values are identified as originally **reported by Enron** or as **later findings and retrospective accounts**. Original reported values may differ from subsequently restated information. A historical event's occurrence date and the date it became public can differ. All prices in the companion CSV are sourced from the [UMKC Enron stock-price archive](https://law2.umkc.edu/faculty/projects/ftrials/enron/enronstockchart.pdf), a secondary historical compilation; corporate-action, delisting-return and currency-conversion validation remain separate matters.

---

## 1. Purpose, scope, and learner objective

This case supplies a historical basis for a fictionalized, open-ended financial investigation inspired by tabletop roleplaying games.

**Learner:** an adult, early-stage self-directed investor who has encountered the concept of stocks/ETFs but hesitates to invest because outcomes are uncertain.  
**Adventure length:** approximately 12–18 minutes for an MVP.  
**Primary decision:** what proportion of virtual capital to allocate to a single company's ownership certificates versus cash, given the information available on **October 17, 2001**.  

By the end of the mission, a learner should be able to:

1. Distinguish **published company claims**, observable data, unresolved allegations, and later-established facts.
2. Read a small number of financial-statement indicators without confusing revenue, income, cash flow, debt, and equity.
3. Articulate concentration risk and how uncertainty should affect position sizing.
4. Explain why a leadership change, unusual accounting, and deteriorating disclosures warrant inquiry **without treating them as proof of fraud**.
5. Specify a decision, supporting evidence, downside risk, and a falsifiable forecast **before** the future is revealed.
6. Reflect on decision quality separately from the observed result.

**Success criterion:** a coherent decision and post-reveal explanation—not the magnitude or sign of virtual profit.

---


## 2. Evidence conventions and information checkpoints

Statements from historical company filings are presented as information that investors **could have seen at the time**, not independently confirmed economic truth. The same distinction applies to management explanations and later SEC allegations. See the source registry for publication dates and provenance.

| Checkpoint | Historical cutoff | Information available in the case |
|---|---|---|
| **G0 — Introduction** | August 14, 2001 | Earlier public annual and June 2001 reports; August 14 leadership announcement |
| **G1 — New disclosure** | October 16, 2001 | G0 information plus announced third-quarter loss and charges |
| **G2 — Investment decision** | October 17, 2001 | G1 information; decision, investment allocation and forecast recorded |
| **G3 — Historical outcome** | After G2 | The subsequent history, price evolution and identity reveal |
| **G4 — Reflection** | After G3 | Comparison of contemporaneous reasoning with actual outcome |

**Timing note:** an item dated October 16 does not necessarily mean it was available before that day's market close. The case uses an end-of-day information convention. Exact event timestamps should be checked for any intraday trading model.

---


## 3. Company identity and business context

| Attribute | Verified description | Sources |
|---|---|---|
| Legal entity | Enron Corp. (historical company) | [S01], [S02] |
| SEC CIK | `1024401` | [S01], [S02] |
| Historical listed ticker | `ENE` (NYSE) | [S04], [S07] |
| Main location | Houston, Texas, United States | [S03] |
| Relevant business | An energy and commodity trading and services group with wholesale energy, natural gas, electricity, transportation/distribution, retail energy and broadband-related operations | [S01], [S02] |
| Important business model feature | Large trading-related revenues and sizable financial contracts/positions; do not equate gross revenue with cash profit | [S01], [S02] |
| Public audit/reporting framework | U.S. SEC annual Form 10-K and quarterly Form 10-Q filings; statements later challenged and restated | [S01], [S02], [S04], [S08] |

### Distinct actor types (not interchangeable)

- **Jeffrey Skilling** — president and CEO until the public August 14, 2001 resignation announcement; his departure rationale was described in a **company-published statement**. [S03]
- **Kenneth Lay** — chairman who publicly assumed the additional president and CEO roles in August 2001. [S03]
- **Andrew Fastow** — historical CFO associated with later-scrutinized related-party arrangements; his conduct later became the subject of official investigations. [S08], [S10]
- **Arthur Andersen** — Enron's historical auditor. Its role is relevant to discussing the reliability and limitations of audited statements; the complete history of the accounting scandal was not public at G0. [S01], [S10]

---


## 4. Public annual financial information available at G0

**Original data source:** Enron's Form 10-K for the year ended **December 31, 2000**, filed on or about **April 2, 2001**. These are the **original, then-reported amounts**; later restatements make it improper to label them audited economic truth. [S01], [S10]

**Amounts in USD millions, unless stated otherwise.**

| Financial indicator | FY 1998 | FY 1999 | FY 2000 | Learning significance |
|---|---:|---:|---:|---|
| Reported revenue | 31,260 | 40,112 | 100,789 | Revenue expansion alone cannot certify business quality |
| Reported net income | 703 | 893 | 979 | Distinct from reported revenue and from operating cash flow |
| Reported net cash from operating activities | 1,640 | 1,228 | 4,779 | Cash-flow context; avoid simplistic conclusions without understanding composition |
| Reported total assets, year-end | 29,350 | 33,381 | 65,503 | Accounting balances, not the stock's market valuation |

Additional originally reported FY 2000 figures:

- Cash and cash equivalents at year-end: **$1,374 million**. [S01]
- Short-term debt at year-end: **$1,679 million**; long-term debt: **$8,550 million**, as presented on the balance sheet. [S01]
- Original FY 2000 shareholder equity: **$11,470 million**. [S01]
- 2000 reported diluted earnings per share: **$1.12**. [S01]
- Related-party transactions and complex risk-management instruments were discussed within the original 10-K notes. The fact they were disclosed does **not** imply all later problems were knowable or obvious. [S01]

**Suggested G0 player-facing lesson:** "This business reports rapid growth. Which figures help you evaluate the *quality and sustainability* of that growth? What remains uncertain?"

---


## 5. June 2001 quarterly disclosure available at G0

**Original data source:** Enron's Form 10-Q for the quarter ended June 30, 2001, filed **August 14, 2001**. The document is contemporaneous to the opening checkpoint but **subsequently affected by restatement**. [S02], [S10]

### Original figures (USD millions)

| Item | As originally reported | Period | Source |
|---|---:|---|---|
| Revenue | **100,189** | Six months ended June 30, 2001 | [S02] |
| Reported net income | **829** | Six months ended June 30, 2001, including $19m cumulative effect of accounting changes | [S02] |
| Net income before cumulative accounting-change effect | **810** | Same six months | [S02] |
| Reported net cash **used** in operating activities | **(1,337)** | Same six months | [S02] |
| Net margin-deposit activity in CFO reconciliation | **(2,342)** | Same six months | [S02] |
| Management's operating cash flow **excluding** net margin-deposit activity | **1,005** | Same six months | [S02] |
| Net cash provided by financing activities | **1,971** | Same six months | [S02] |
| Cash and cash equivalents | **847** | June 30, 2001 balance | [S02] |
| Short-term debt | **3,457** | June 30, 2001 balance | [S02] |
| Long-term debt | **9,355** | June 30, 2001 balance | [S02] |
| Total assets | **63,392** | June 30, 2001 balance | [S02] |
| Shareholders' equity | **11,740** | June 30, 2001 balance | [S02] |

**Important teaching nuance.** The reported **negative $1,337 million** first-half operating cash flow is a real *reported statement line*, but the filing itself attributes a substantial portion to **margin-deposit flows** and reports a positive figure when those are excluded. The exercise should encourage reading the reconciliation, not falsely teach "negative cash flow proves fraud." [S02]

**G0 questions the player can answer:**

1. How can positive accounting net income coexist with negative reported operating cash flow?
2. What does an increase in short-term debt imply—and what does it *not* prove?
3. How does a single-company position differ from a diversified fund?
4. If you cannot verify the company's underlying risks, what allocation choices remain available?

### Availability restriction

The **reporting period end** is June 30, 2001; the **public filing date** is August 14, 2001. The filing was publicly available by the August 15 opening scene, but not by June 30, the end of the reporting period.

---


## 6. August 14, 2001 management announcement (G0)

**Document:** contemporaneous Enron news release announcing the resignation of Jeffrey Skilling and Kenneth Lay's assumption of president and CEO duties. Preserved as a U.S. Department of Justice trial exhibit. [S03]

**Verified public event:** the company stated that Skilling was resigning for **personal reasons**, and Lay would take the president and CEO roles. [S03]

**Evidence classification:**

- **A resignation occurred:** contemporaneous public fact.
- **"Personal reasons":** explanation stated in the company release, **not an independently established cause**.
- **Lay's positive assessment of business strength and growth:** management opinion, **not evidence of future results**.

**Suggested anonymous guild proclamation:**

> A leading master of the Golden Guild has stepped down unexpectedly. The council says the departure is personal, while the Guild's chairman expresses confidence in its prospects.

The adjective "unexpectedly" may describe the player's surprise; it must **not** become the inference that fraud or collapse is certain. The fictional proclamation is a paraphrase rather than a historical quotation.

**Questions for the player:** "Which part is a verified event? Which part is management's explanation? What additional evidence would you seek?"

---


## 7. October 16, 2001 shock: public information at G1

**Availability:** a contemporaneous Enron news release was issued **October 16, 2001**; a preserved copy is available in a University of Chicago archival collection. The **$618m net loss** and **$1.01bn after-tax charge** therefore have a direct point-in-time source. The **$1.2bn reduction to equity** was disclosed in the contemporaneous results conference call and is corroborated by subsequent SEC testimony. The October 16 release is contemporaneous evidence. The later SEC testimony corroborates the equity figure retrospectively. [S20], [S05], [S06]

| Publicly reported event | Figure | Interpretive caution |
|---|---:|---|
| Enron announced Q3 2001 net loss | **$618 million** | Reported result; distinct from individual charges |
| Announced third-quarter after-tax charge | **$1.01 billion** | Contains asset impairments, restructuring costs and investment-related losses; **not additive to $618m** as a separate quarterly loss |
| Announced reduction in shareholders' equity | **$1.2 billion** | A balance-sheet adjustment disclosed alongside earnings; **not an additional cash payment or independent profit-and-loss charge** |

The contemporaneous company release simultaneously emphasized **$393 million of recurring net income** and **$0.43 recurring earnings per diluted share**, while reporting an overall **$618 million net loss**, or **$0.84 loss per diluted share**, after the special charges. These contrasting presentations create an excellent **G1 reading-comprehension challenge**: reported "recurring" earnings do not erase the actual net loss. The announced $1.01bn charge was described as **$287m asset impairments at Azurix, $180m broadband restructuring, and $544m other investment/structured-finance losses**. These descriptions are management's contemporaneous classifications, not proof that the charges were fully explained. [S20]

**What a G1 player should infer:** the new news materially changes the evidence set. It does **not** license DM knowledge of the November restatement, debt downgrades, or the December bankruptcy.

**Scenario presentation:**

- A new guild proclamation announces a **large quarterly loss**, an **extraordinary write-down**, and a **reduction in the Guild's reported net wealth**.
- The market reacts, but **a specific price and its timestamp can appear only when the Price Engine supplies it**.
- The player may reopen research, revisit NPCs, ask Buddy what a write-down is, or defer an allocation decision until the required lock.

**At the October 17 decision point**, the October 22 SEC inquiry disclosure, November 8 restatement and late-November merger developments had not yet occurred.

---


## 8. Later historical events and restatements

This section documents developments after the October 17 decision date, including later-public facts and retrospective investigative findings.

| Date | Event | Public at that date? | Evidence and usage |
|---|---|---|---|
| **Aug 14, 2001** | Skilling resignation; Lay assumes CEO responsibilities | Yes | Starting public clue; [S03] |
| **Oct 16, 2001** | Q3 loss and charges in earnings release; equity reduction discussed on results call | Yes | G1 clue; [S20], [S05] |
| **Oct 22, 2001** | Enron publicly acknowledges an SEC inquiry | Yes | G3 only because G2 was already Oct 17; [S07], [S12] |
| **Oct 30, 2001** | SEC formal investigation order issued | **Official action**; distinguish from public company disclosure | Retrospective research; public awareness should be dated to its announcement; [S09] |
| **Oct 31, 2001** | Enron publicly announces a formal SEC investigation | Yes | G3 only; [S07], [S09] |
| **Nov 8, 2001** | Enron Form 8-K and release state earlier reports will be restated, including consolidation issues involving JEDI/Chewco and LJM1 | Yes | Major ex-post discovery; [S04] |
| **Nov 9, 2001** | Proposed Dynegy transaction announced | Yes | Subsequent timeline; [S11] |
| **Nov 19, 2001** | Enron files third-quarter Form 10-Q | Yes | Must not enter earlier evidence envelopes; [S05], [S13] |
| **Nov 28, 2001** | Downgrades to below investment grade and Dynegy's termination of proposed merger | Yes | Liquidity and counterparty-risk discussion; [S05], [S11] |
| **Dec 2, 2001** | Enron and certain subsidiaries seek Chapter 11 bankruptcy protection | Yes | Final historical milestone; [S14], [S05] |
| **2002–2004 and later** | Investigations and enforcement actions further describe accounting manipulation, related-party arrangements and misleading disclosures | Later only | Debrief/context, not contemporaneous August/October 2001 knowledge; [S08], [S10] |

### The November 8 restatement announcement — precise figures

In its **November 8, 2001** release, Enron **estimated** the following adjustments to previously reported net income (USD millions): [S04]

| Period | Enron's stated adjustment |
|---|---:|
| 1997 | **−96** |
| 1998 | **−113** |
| 1999 | **−250** |
| 2000 | **−132** |
| 2001 Q1 | **+17** |
| 2001 Q2 | **+5** |
| 2001 Q3 | **−17** |

The same release described additional debt consolidation effects: **+$711m (1997), +$561m (1998), +$685m (1999), +$628m (2000)**. These are **company-announced estimated restatement effects**, not proof of complete or finally adjudicated accounting corrections. [S04]

**Numerical interpretation:** the prior-year adjustments for 1997–2000 sum to **−$591 million**. Including the +$17m and +$5m adjustments for the first two quarters of 2001 gives **−$569 million** across 1997 through the first half of 2001, consistent with the later SEC description of the earlier four-and-a-half-year restatement. The third-quarter adjustment is a distinct item. [S04], [S05]

### Retrospective fraud findings and allegations

The SEC later described schemes that allegedly or demonstrably involved overstated revenue or earnings, understated debt, manipulated reserve accounts, misleading valuation of assets, and non-independent structures. For accuracy, **attribute allegations to the SEC proceedings** and avoid treating all claims in a complaint as identical to a criminal conviction or a separately verified finding. [S08], [S10]

**Historical distinction:** financial reports available during the opening period were originally published figures; subsequent investigations challenged their reliability.

---


## 9. Point-in-time research and knowledge matrix

| Evidence | Earliest verified public date | G0 | G1/G2 | G3/G4 | Status |
|---|---|---:|---:|---:|---|
| 2000 Form 10-K amounts | 2001-04-02 | Yes | Yes | Yes | Company-reported / later questioned |
| 2001 Q2 Form 10-Q | 2001-08-14 | Yes | Yes | Yes | Company-reported / later affected by restatement |
| Skilling resignation release | 2001-08-14 | Yes | Yes | Yes | Public announcement with attributed opinions |
| 2001 Q3 results announcement | 2001-10-16 | **No** | Yes | Yes | Company announcement, retrospectively verified |
| SEC inquiry acknowledged | 2001-10-22 | No | **No** | Yes | Later public event |
| Formal investigation announcement | 2001-10-31 | No | **No** | Yes | Later public event |
| Restatement Form 8-K | 2001-11-08 | No | **No** | Yes | Later public company filing |
| Third-quarter Form 10-Q | 2001-11-19 | No | **No** | Yes | Later public filing |
| Credit downgrades / Dynegy termination | 2001-11-28 | No | **No** | Yes | Later public events |
| Bankruptcy filing | 2001-12-02 | No | **No** | Yes | Later public filing/event |
| Later SEC fraud allegations/findings | 2002–2004+ | No | **No** | Yes | Retrospective only |
| Internal communications later exhibited in court | Varies | No, unless independently public | No, unless independently public | Engine review only | **Private-at-time**; not automatically player-visible |

*All dates use U.S. calendar dates. Verify publication/market hours if you add intraday prices or event-driven trading.*

---


## 10. Fictional campaign adaptation

### Safe fantasy mapping

| Historical object | Player-facing fictional equivalent | Required semantic consistency |
|---|---|---|
| Enron Corporation | **Golden Guild Trading Consortium** | Publicly traded business enterprise |
| Enron common shares | Guild **ownership certificates** | Equity ownership; not gold deposits or guaranteed debt |
| Trading market | Grand Exchange of Aster Vale | Marketable ownership claims with changing prices |
| CEO / chairman | High guild master / guild council chair | Management and governance roles |
| Enron 10-K / 10-Q | Guild annual/quarterly ledger | Reporting period and publication clock retained |
| Income statement | Guild earnings ledger | Income is not cash |
| Cash flow statement | Treasury movement register | Separate from profit |
| Shareholders' equity | Guild net owners' claim | Distinct from spendable cash |
| Accounting write-down | Valuation correction to guild assets | Not a literal monster attack |
| Regulatory investigation | Royal commercial authority inquiry | Released only at the appropriate gate |
| Bankruptcy protection | Guild enters a formal court-supervised insolvency process | Do not equate bankruptcy filing with instant zero value |

**Adaptation principle:** story names, settings and dialogue can be fictional, while the financial facts, relationships and historical returns remain fixed.

### Suggested opening scene (fictionalized, not an original historical quotation)

> Rain taps against the stained-glass windows of Aster Vale's Grand Exchange. Investors cluster beneath a gilded banner of the Golden Guild. A well-known master has unexpectedly stepped down, and the chairman says the consortium remains strong. Your companion CommerzBuddy lays two documents on the table: an annual ledger and a new quarterly report. "Where shall we begin?"

**Player's mission:** investigate information available to a hypothetical investor, decide whether to allocate a portion of virtual money to the Guild's ownership certificates, explain the reasoning and forecast a measurable outcome.

---


## 11. NPCs, investigation objects, and encounter contracts

These NPCs are **fictional teaching characters**, not historical reconstructions of real Enron employees.

| NPC / place | Function | May reveal at G0 | May reveal at G1 | Never permitted |
|---|---|---|---|---|
| **Master Elian Voss — Treasurer** | Voice of company management | Published leadership statement and annual/June reported figures | G1 new reported figures | Certain future outcomes or invented accounting facts |
| **Scholar Mira Fen — Independent researcher** | Critical reading of primary sources | Explain published financial lines, request corroboration | Compare old and new figures; identify unresolved questions | Claim proven fraud from undisclosed future evidence |
| **Broker Ren Tal — Exchange trader** | Sentiment and behavioral biases | Clearly labeled opinions about market mood | Reactions to public G1 announcements | Forecast guaranteed price paths or imply sentiment is proof |
| **CommerzBuddy — Learning ally** | Conceptual support | Define earnings, cash flow, equity, diversification | Explain write-down vs cash loss, concentration risk | Choose a trade for user; leak hidden identity or future |
| **Guild Archive** | Research data room | Authorized G0 financial documents | Plus G1 documents | Future filings or fabricated documents |
| **Grand Exchange** | Market display and allocation | Verified as-of quotes *only if loaded* | Verified as-of quotes *only if loaded* | Synthetic prices masquerading as real |

### Encounter 1 — The Resignation

- **Teaching target:** difference between an observed event and an explanation offered by the company.
- **Free actions:** read the proclamation, ask management questions, question an independent scholar, consult Buddy.
- **Automatic information:** existence and exact nature of the public resignation statement; no roll required.
- **Optional skill check:** `Insight DC 12` → find an *additional* interview prompt or source-comparison checklist.
- **Failure-forward path:** player must compare two presented passages or ask the scholar; no loss of essential evidence.
- **Evidence IDs:** `F-CEO-RESIGN-001`, `F-MGMT-CLAIM-001`; source [S03].

### Encounter 2 — The Quarterly Ledger

- **Teaching target:** separate reported net income from cash-flow dynamics and borrowed funds.
- **Free actions:** inspect the June 2001 report, compare with annual accounts, ask for definition of cash flow.
- **Automatic information:** basic statement extracts and source context.
- **Optional check:** `Investigation DC 14` → identify a **pre-authored** note explaining margin-deposit effects.
- **Failure-forward:** present the statement reconciliation side by side; do not hide it behind dice.
- **Evidence IDs:** `F-Q2-REV-001`, `F-Q2-CFO-001`, `F-Q2-MARGIN-001`; source [S02].

### Encounter 3 — The New Loss Report (G1 only)

- **Teaching target:** how genuinely new public evidence should update beliefs and capital allocation.
- **Automatic information:** the published large reported Q3 loss, after-tax charge, and equity reduction.
- **Optional check:** `Investigation DC 14` → distinguish a write-down from cash outflow using an **approved explanation**, without claiming the underlying accounts are correct.
- **Failure-forward:** Buddy walks through the terms; player can ask the treasurer and the scholar additional questions.
- **Evidence IDs:** `F-Q3-LOSS-001`, `F-Q3-CHARGE-001`, `F-Q3-EQUITY-001`; sources [S20], [S05].

### Encounter 4 — The Crowd at the Exchange

- **Teaching target:** distinguish evidence from popularity, manage concentration risk.
- **Optional check:** `Persuasion/Insight DC 12` for richer **fictional** NPC dialogue; this check cannot create a new financial fact.
- **Learning prompt:** "Would you make the same choice if this position were your entire savings? Why or why not?"

### Failure-forward design

A failed optional check can impose extra dialogue, time in the story, a different NPC route, or a missed **optional** side-clue. It **cannot** remove a mandated report, rewrite an investment price, consume portfolio HP without an actual recorded cost, or end the learning experience.

---


## 12. Financial rules: budget, HP, class abilities, and execution

**Core principle:** `HP = a visualized state of the player's virtual total wealth`, not a separate game currency.

**Character-defined initialization:** The game code determines the player's starting virtual capital, initial HP display and any class-dependent resource modifiers from the selected character. This historical reference does not prescribe those values.

### Holdings model

For a single asset and a cash holding:

```text
wealth_base_t = cash_base_t + units * price_quote_t * FX_quote_to_base_t
              - accrued_unpaid_costs_base_t
HP_t          = character_initial_HP * wealth_base_t / character_initial_wealth_base
```

where `character_initial_HP` and `character_initial_wealth_base` are supplied by the game code for the selected character; `base = EUR`, `quote = USD` for historical ENE shares, and `FX_quote_to_base_t` is the EUR value of one USD **at time t** under a documented FX convention. For a fully historical simulation, source and validate the historical FX series as well as share prices. Alternatively, use an explicitly **simplified fixed-conversion training convention**, clearly labeled as hypothetical; never present that convention as actual historical FX. If the price series/FX is absent, **no actual P&L or HP settlement** should run.

- Buying securities changes **cash into holdings**; it does not itself damage HP, aside from clearly disclosed fees.
- Marked-to-market gains can raise HP **above the initial HP value assigned to that character**.
- A bankruptcy **filing does not automatically set the market price or HP to zero**; use actually validated prices, trading-status records, and (where appropriate) later equity recovery/delisting treatment.
- Cash kept outside the single-stock position is a legitimate choice, not a failed quest.
- Starting capital, initial HP, class-specific resource amounts and their conversion rules come from the **character configuration in game code**, not from this historical reference. Any class differences must be applied consistently and cannot alter verified market outcomes.
- Wizard can spend one research reroll; Rogue can gain one optional investigation advantage; all have equal access to essential facts.
- D20 and DC only affect **fictional investigation opportunities**, never historical prices, real reported numbers, portfolio value, or the chance that Enron goes bankrupt.

### Enron historical price data (companion CSV)

Daily ENE Open, High, Low, Close and share-volume observations for **August 1–December 31, 2001** are included in the companion CSV, transcribed from an archived historical price table maintained by the University of Missouri–Kansas City law/famous-trials collection. [S21] The archive is a **secondary historical compilation**, not a licensed CRSP or original NYSE time series. The dataset includes 102 rows in ascending date order; days without trading are not filled with artificial values.

| Date | Close (USD per share) | Context |
|---|---:|---|
| August 14, 2001 | **42.93** | CEO resignation public announcement |
| August 15, 2001 | **40.25** | Opening campaign trading day |
| October 16, 2001 | **33.84** | Q3 earnings announcement date |
| October 17, 2001 | **32.20** | Decision-day close, **not automatically the execution price** |
| November 28, 2001 | **0.61** | Credit downgrade and merger collapse period |
| November 30, 2001 | **0.26** | Last trading session before December bankruptcy filing |
| December 3, 2001 | **0.40** | Session after bankruptcy announcement |
| December 31, 2001 | **0.60** | End of this extracted dataset; **not a final recovery price** |

An archived historical Enron investor-relations lookup displays matching price and volume figures, although its displayed requested-date label is inconsistent; it is therefore a limited rather than decisive cross-check. [S22] A second copy of the historical PDF is hosted in an Enron research archive. [S23]

**Remaining modeling considerations:** the CSV does not establish corporate-action adjustment rules, dividend treatment, USD/EUR historical exchange rates, a viable purchase time after decision lock, trading suspensions after 2001, or eventual delisting returns. For financial simulation, use a fixed documented execution and valuation policy, with no implied ability to trade at a price observed before the player's decision. Production-grade validation may use CRSP/WRDS where access permits. [S16]

### Example (symbolic illustration; not Enron data)

> If a character starts with virtual portfolio value `B` and initial HP `H`, and an invested position of value `I` loses `r` of its value while the remaining cash is unchanged, the new wealth is `B - I × r` and the updated HP is `H × (B - I × r) / B`. The code provides `B` and `H` for that character; this case reference sets neither value.

---


## 13. Decision, forecast and debrief protocol

At the investment-decision stage, record the selected allocation between single-company equity and cash, reasoning, evidence consulted, downside risk, forecast horizon and the probability of a precisely defined future event. The decision is fixed before the historical outcome is disclosed.

An all-cash allocation is a valid choice. Confidence in one's reasoning is distinct from the probabilistic forecast of a specific market event. A series of repeated forecasts, rather than one observation, is needed to assess calibration.

### Suggested rubric (100 educational XP)

| Dimension | Max | Evaluation |
|---|---:|---|
| Evidence literacy | 25 | Uses contemporaneously available information accurately |
| Risk awareness | 25 | Recognizes uncertainty and single-name concentration |
| Decision consistency | 20 | Allocation coheres with stated resources and horizon |
| Forecast clarity | 15 | Gives a testable event and probability, not vague confidence |
| Post-reveal reflection | 15 | Distinguishes the outcome from whether the decision was justified |

**Assessment principle:** educational XP measures evidence quality, risk awareness, consistency, forecasting clarity and reflection—not speculative position size, lucky returns or trading speed.

### Debrief questions (G4)

1. What was knowable when you committed?
2. Which concerns were evident then, and which only became public afterward?
3. Did your analysis appropriately distinguish managerial claims from independent evidence?
4. Would diversifying or holding some cash have changed your exposure?
5. Did you succeed because of the process, luck, or both?
6. What rule of thumb will you carry into the next mission?

---


## 14. Source registry and direct links

Sources include contemporaneous documents and retrospective materials. Their original publication dates—not present-day access dates—determine what a historical investor could have known at a given time.

| ID | Original source | Period / date | Exposure | Direct URL |
|---|---|---|---|---|
| **S01** | U.S. SEC EDGAR, **Enron Form 10-K**, year ended Dec 31 2000 | Filed April 2, 2001 | Public before G0; **original reported figures** | https://www.sec.gov/Archives/edgar/data/1024401/000102440101500010/ene10-k.txt |
| **S02** | U.S. SEC EDGAR, **Enron Form 10-Q**, quarter ended June 30 2001 | Filed Aug 14, 2001 | Public G0; original reported figures | https://www.sec.gov/Archives/edgar/data/1024401/000102440101500028/ene10-q.txt |
| **S03** | Enron, **Skilling resignation / Lay assumption of CEO duties**, contemporaneous press release preserved by DOJ | Aug 14, 2001 | Public G0; management claims attributed | https://www.justice.gov/archive/enron/exhibit/02-02/BBC-0001/Images/EXH023-00160.PDF |
| **S04** | U.S. SEC EDGAR, **Nov 8 Enron press release as Form 8-K Exhibit 99.1** | Nov 8, 2001 | After the decision date for October 17 decision | https://www.sec.gov/Archives/edgar/data/1024401/000095012901503835/h91831ex99-1.txt |
| **S05** | SEC Chairman/official testimony, **Recent Events Relating to Enron Corporation** | Dec 12, 2001 | Retrospective; G3/G4 verification only | https://www.sec.gov/newsroom/speeches-statements/121201tsrkh-testimony-recent-events-relating-enron-corporation |
| **S06** | U.S. GAO, **Financial Statement Restatements** (GAO-03-138), Enron case discussion and market data graphs | 2002 | Retrospective; G3/G4 corroboration only | https://www.gao.gov/assets/a236068.html |
| **S07** | U.S. Congressional Research Service, **Enron: A Select Chronology of Congressional, Corporate, and Government Activities** (RL31364), mirrored | March 18, 2003 | Retrospective event chronicle, not 2001 source itself | https://www.everycrsreport.com/reports/RL31364.html |
| **S08** | SEC, **Litigation Release No. 18776**, Richard Causey / Jeffrey Skilling / Kenneth Lay | 2004 | Retrospective allegations; G4 only | https://www.sec.gov/enforcement-litigation/litigation-releases/lr-18776 |
| **S09** | SEC, **Litigation Release No. 17270**, Andrew Fastow formal investigative order and subpoena | 2001 | Later procedural record; not G0/G1 | https://www.sec.gov/enforcement-litigation/litigation-releases/lr-17270 |
| **S10** | SEC, **Complaint against Skilling and Causey**, detailed allegations regarding reported statements | 2004 | Retrospective SEC allegations; G4 only | https://www.sec.gov/litigation/complaints/comp18582.htm |
| **S11** | SEC EDGAR, **Enron bankruptcy-related filing including detailed events leading to Chapter 11** | Filed 2003 | Retrospective chronology, G3 only | https://www.sec.gov/Archives/edgar/data/1024401/000095013403015498/h10431exv2w2.txt |
| **S12** | *Washington Post*, **Enron Discloses SEC Inquiry**, contemporary reporting | Oct 23, 2001 | Public after G2 only; G3 | https://www.washingtonpost.com/archive/business/2001/10/23/enron-discloses-sec-inquiry/52a28009-93b5-4ca2-8a82-d39231d1052e/ |
| **S13** | U.S. SEC EDGAR, **Enron third-quarter 2001 Form 10-Q** | Filed Nov 19, 2001 | After the decision date | https://www.sec.gov/Archives/edgar/data/1024401/000095012901504218/h92492e10-q.txt |
| **S14** | U.S. SEC EDGAR, **Enron's Dec 2, 2001 bankruptcy announcement**, Form 8-K exhibit | Dec 2, 2001 | After the decision date | https://www.sec.gov/Archives/edgar/data/1024401/000102440101500046/ex-99_1.txt |
| **S15** | U.S. Congressional Research Service, **Enron and Stock Analyst Objectivity** (RL31348), historical price context and analyst recommendations | 2003 | Retrospective price context only; not exact trading feed | https://www.everycrsreport.com/reports/RL31348.html |
| **S16** | Wharton Research Data Services, **CRSP data documentation / retrieval form** | Current documentation | Data-acquisition guidance, not freely imported prices | https://wrds-www.wharton.upenn.edu/demo/crsp/form/ |
| **S17** | U.S. SEC EDGAR, **Enron Nov 8 Form 8-K main filing** (not only press release exhibit) | Nov 8, 2001 | After the decision date | https://www.sec.gov/Archives/edgar/data/1024401/000095012901503835/h91831e8-k.txt |
| **S18** | SEC, **Complaint against Richard Causey** (filing dates and later allegations) | 2004 | Later verification of original filing dates | https://www.sec.gov/litigation/complaints/comp18551.htm |
| **S19** | U.S. SEC EDGAR, **Enron Dec 2 filing on bankruptcy**, Form 8-K | Filed after Dec 2 event | After the decision date | https://www.sec.gov/Archives/edgar/data/1024401/000102440101500046/ene8-k1214.txt |
| **S20** | **Enron's original Oct 16, 2001 Q3 earnings news release**, archival PDF hosted by University of Chicago | **Oct 16, 2001** | **Public G1**, not G0; contemporaneous primary evidence | https://picker.uchicago.edu/Enron/EarningsRelease%2810-16-01%29.pdf |
| **S21** | University of Missouri–Kansas City, historical ENE stock-price table, daily OHLCV | 1998–2001 historical series | Secondary historical dataset; CSV draws Aug–Dec 2001 | https://law2.umkc.edu/faculty/projects/ftrials/enron/enronstockchart.pdf |
| **S22** | Restored Enron investor-relations, Historical Price Lookup (original Interactive Data/MarketWatch data) | Historical August 2001 price lookup | Archived price cross-check | https://enroncorp.com/corp/investors/stock/history.html |
| **S23** | Enron Historical Stock Data (archived PDF copy) | Historical 1998–2001 series | Secondary duplicate of ENE price table, not independent feed | https://caraellison.wordpress.com/wp-content/uploads/2009/09/enron-historical-data.pdf |

### Quick source-to-mechanic index

| Mechanic / DM activity | Use these sources |
|---|---|
| Opening company lore and growth claims | S01, S02 |
| Leadership-change investigation | S03 |
| Reading annual and quarterly statements | S01, S02 |
| Understanding cash-flow nuance | S02 |
| G1 financial-shock report | **S20 for contemporaneous release**, S05 for the contemporaneous call's equity-reduction disclosure as later documented |
| Understanding the later restatement | S04, S17 |
| Investigations / later governance questions | S08, S09, S10 |
| Historical finale and bankruptcy | S11, S14, S19 |
| Daily ENE market quotations | S21; S22 and S23 for spot checks |
| Long-horizon return / delisting conventions | S06, S15 (context), S16 (licensed research-grade acquisition) |

---
