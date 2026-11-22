---
case_id: FQ-GME-2021
version: "1.0"
historic_entity: "GameStop Corp."
fictional_campaign: "The Siege of the Grand Exchange"
market_data_file: "prices.csv"
---

# GameStop Corp. (NYSE: GME): Historical Case Reference

This is the server-only source document for the curated demo quest. Real names appear only here
and in the manifest's `secret` block. Everything player-visible lives in `manifest.json` and is
anonymised. It was written from the *Finance Quest GameStop Release v3* research pack (case
reference, investigation cards, DM rules, anonymised DM packets, event timeline, retrospective SEC
datasets) plus the primary sources listed in section 12.

## 1. Purpose, scope, and learner objective

| Checkpoint | Date | Meaning |
|---|---|---|
| Intro (G0) | 2021-01-11 | Holiday-sales release and the board agreement with RC Ventures |
| Shock (G1) | 2021-01-22 | First huge squeeze day: +51% close, repeated volatility halts |
| Decision (G2) | 2021-01-25 | Pre-market +50% bulletin; wild session, close +18% |
| Horizon (G3) | 2021-02-05 | After the peak (Jan 27) and the collapse |

**Why this window.**
- It is the most famous retail-crowd episode of modern markets, which makes it a strong, emotional
  demo, yet the lesson is fully general: a crowded short, forced buying-back, a crowd-driven rally,
  trading halts and broker restrictions, and a violent reversal.
- The engine buys at the next session's open after the decision date. With G2 on Jan 25 the buy is
  Jan 26's open (split-adjusted $22.14); the Feb 5 close is $15.94, so a decision-day buyer loses
  about 28%. A player who bought at the intro (Jan 11 close $4.99) and held to Feb 5 is up about
  220%. Timing, sizing and luck dominate; the quest separates them from judgement.
- The release pack's own G0/G1/G2 gates (Jan 11, Jan 22, Jan 25 pre-open) are kept; G2 is shifted to
  the Jan 25 session because the engine needs the decision date to be a trading day.
- The price table starts on 2020-10-01 so the market chart shows the long quiet base (the price
  roughly doubled from very low levels through the autumn) before the January explosion.

**Learner objective.**
1. Distinguish fundamental evidence (ledgers, vault, debts), market prices and crowd sentiment.
2. Read metrics with different denominators without concluding the whole business grew.
3. Understand borrowing, short selling, short interest and buying back (covering) as separate steps.
4. Recognise volatility, concentration risk, trading pauses and execution uncertainty.
5. Size a position for the downside; a zero allocation can be a reasoned choice.
6. Separate decision quality from luck after the reveal.

## 2. Evidence conventions and information checkpoints

Dollar figures are US dollars in millions unless stated. Percentages are as reported. Prices are
split-adjusted (the four-for-one split of 2022-07-22); the disguise rescales them anyway.

- **G0 (2021-01-11).** Public: Q3 FY2020 results (2020-12-08), the holiday-sales release and the
  board agreement (both 2021-01-11), RC Ventures' earlier public letters (Nov 2020), price history to
  Jan 11. Not public: anything after Jan 11.
- **G1 (2021-01-22).** Public: the Jan 13 jump after the board news, Citron's Jan 19 short call,
  contemporaneous short-interest reporting (S3 Partners ~139-142% of float as reported in the press in
  January; other providers lower), the Jan 22 close +51% with repeated LULD halts.
- **G2 (2021-01-25).** Public: Reuters' pre-market report (07:28 ET) of an indicative ~+50% move and
  short-covering theories; the Jan 25 session (high ~$159.18 as traded, low ~$61.13, close $76.79).
- **G3/G4 (after lock).** Jan 26-29 climb and broker restrictions (Jan 28), Feb 1-5 collapse, SEC
  staff report (2021-10-18). Debrief only.

## 3. Company identity and business context (as known at G0)

- **Business.** US video-game, console and collectibles retailer with thousands of stores worldwide,
  closing stores and moving toward e-commerce; under pressure from digital game downloads sold by
  console makers directly.
- **Console cycle.** Sony PlayStation 5 and Microsoft Xbox Series X|S launched in November 2020;
  historically new console cycles lifted GameStop's sales for one to two years.
- **Leadership.** CEO George Sherman. RC Ventures (Ryan Cohen, co-founder and former CEO of Chewy)
  held about 12.9% and had publicly pushed for a digital transformation.
- **Short sellers.** GameStop was among the most shorted US stocks; Melvin Capital was a prominent
  short; Citron Research (Andrew Left) publicly called the stock overvalued on Jan 19.

## 4. Public financial information available at G0

Q3 FY2020 (13 weeks to 2020-10-31), earnings release 2020-12-08:

| Line | Q3 FY2020 | Q3 FY2019 |
|---|---|---|
| Net sales | 1,004.7 | 1,438.5 (-30.2%) |
| Comparable store sales | -24.6% | |
| Global e-commerce sales | +257% | |
| Gross profit | 276.3 | 441.1 |
| SG&A | 360.4 | 475.4 |
| Operating loss | (63.0) | (45.6) |
| Net loss | (18.8) | (83.4) |

Balance sheet at 2020-10-31: cash and equivalents 445.9; restricted cash 140.7 (603 with restricted
cash per the release); merchandise inventories 861.0; total assets 2,601.4; long-term debt, net
216.0; total liabilities 2,269.2; stockholders' equity 332.2.

## 5. Announcements and news available at G0

- **2021-01-11, holiday sales** (nine weeks to 2021-01-02): total global sales -3.1%, comparable store
  sales +4.8%, e-commerce +309%. Different denominators; not contradictory.
- **2021-01-11, board agreement:** Ryan Cohen, Alan Attal and Jim Grube (former Chewy executives)
  join the board after an agreement with RC Ventures.

## 6. The shock: public information at G1 and G2

- **2021-01-13:** shares jump about 57% on the board news (close $31.40 as traded).
- **2021-01-19:** Citron Research says it will explain why GME will go back to $20 and calls buyers at
  these levels "the suckers at this poker game"; the stock dips, then resumes rising.
- **Short interest:** press reports quoting S3 Partners put short interest around 139-142% of float
  in January; IHS Markit gave lower readings. Methods differ.
- **2021-01-22:** close $65.01 (+51%), several LULD pauses, record volume.
- **2021-01-25 (decision day):** Reuters pre-market report of ~+50% indicative move; intraday range
  ~$61-$159 (as traded); close $76.79 (+18%), many LULD pauses.

## 7. Later historical events (after the decision; for the reveal and debrief only)

- 2021-01-25: Melvin Capital receives a $2.75 billion injection from Citadel and Point72.
- 2021-01-26: close $147.98 (+93%) after Elon Musk's "Gamestonk!!" tweet late in the day.
- 2021-01-27: close $347.51, the closing peak.
- 2021-01-28: Robinhood and other brokers restrict opening purchases; intraday high $483, low $112,
  close $193.60.
- 2021-01-29: close $325.00. 2021-02-02: $90.00. 2021-02-05: $63.77.
- 2021-10-18: SEC staff report: short covering contributed to discrete jumps but broad positive
  sentiment sustained the rise; no evidence of a gamma squeeze; 40 LULD pauses over six sessions,
  19 on Jan 28; peak reported short interest 122.97% of float.
- 2022-07-22: four-for-one stock split.

## 8. Point-in-time knowledge matrix

| Fact | G0 | G1 | G2 | After |
|---|---|---|---|---|
| Q3 FY2020 ledger and balance sheet | yes | yes | yes | |
| Holiday sales, board agreement | yes | yes | yes | |
| Citron call, short-interest reporting | | yes | yes | |
| Jan 22 surge and halts | | yes | yes | |
| Pre-market bulletin, Jan 25 session | | | yes | |
| Jan 26-Feb 5 prices, broker restrictions | | | | yes |
| SEC report findings | | | | debrief |

## 9. Fictional campaign adaptation

World **Eldervale**; **The Guild of Games and Wonders** (GameStop) issues **wonder-certificates**
(shares) on **The Grand Exchange of Eldervale** (NYSE). Quarterly report: **the Season Ledger**;
annual report: **the Guild's Year-Book**. E-commerce is **courier-raven orders**; consoles are
**wonder-boxes**; the holiday period is **the Midwinter Festival weeks**; LULD pauses are **the
Exchange bell**; short-interest data firms are **the lending houses**; brokers are **the
coin-couriers**; r/WallStreetBets is **the Hall of Many Voices**; Ryan Cohen is **Ryn Callow**;
Citron/Andrew Left is **the Pale Herald**; Melvin Capital is **the Ironvault House**.

Arc: a sleepy, heavily shorted guild (G0) → the crowd's squeeze and the ringing bell (G1) → a wild
decision morning (G2) → the reveal of the peak and the crash.

## 10. NPCs, investigation objects, and encounter contracts

- **Scholar Ysolde Marrow** (Library): ledgers, bases, how borrowed-certificate bets work. Never gives
  a price opinion.
- **Marla Pennywhistle** (Market Square): crowd-caller in the spirit of the retail champion of the
  episode; passionate, can be right or wrong; tells the board's news and the crowd's mood.
- **Treasurer Oswin Hale** (Guild Hall, a Master-created place): official Guild view; the reformers'
  record; never comments on the price.
- Encounters: Three Numbers, Three Bases (Investigation, DC 12); What the New Council Proves (Insight,
  DC 12); The Lending Clerk (Persuasion, DC 14); The Ironvault Runners (Stealth, DC 13). None blocks key
  evidence; each success adds a non-key clue.
- Extra places the Master can open: the Ironvault Counting House, the Hall of Many Voices, the
  Coin-Couriers' Gatehouse.

## 11. Decision, forecast and debrief protocol

The player decides on the morning of G2 how much gold to put in, why, the main downside risk and a
forecast. The engine buys at the next session's open and values the position at the G3 close. The
debrief separates the Guild's ledgers from the crowd, sizing from timing, and judgement from luck;
it presents the SEC findings as later evidence, not as hints that were available in January.

## 12. Source registry (URLs actually used)

- GameStop Q3 FY2020 earnings release (SEC EX-99.1):
  https://www.sec.gov/Archives/edgar/data/1326380/000132638020000132/a991-q3fy20earningsrel.htm
- GameStop Q3 FY2020 10-Q:
  https://www.sec.gov/Archives/edgar/data/1326380/000132638020000134/gme-20201031.htm
- Holiday sales release (2021-01-11):
  https://www.sec.gov/Archives/edgar/data/1326380/000132638021000008/a991-holidaysalesresults20.htm
- Board agreement 8-K (2021-01-11):
  https://www.sec.gov/Archives/edgar/data/1326380/000132638021000006/gme-20210111.htm
- SEC staff report on early-2021 market conditions (2021-10-18):
  https://www.sec.gov/about/reports-publications/staff-report-equity-options-market-structure-conditions-early-2021
- Wikimedia Commons GME close data (CC0):
  https://commons.wikimedia.org/wiki/Data:GME_closing_price_jan-feb_2021.tab
- Bloomberg, "GameStop Short-Sellers Reload Bets After $6 Billion Loss" (S3 data, ~139% of float):
  https://www.bloomberg.com/news/articles/2021-01-25/gamestop-short-sellers-reload-bearish-bets-after-6-billion-loss
- Business Insider (peak 141.8% of float on Jan 4 per S3):
  https://www.businessinsider.in/stock-market/news/short-bets-against-gamestop-are-the-lowest-theyve-been-in-2021-as-the-stock-finds-renewed-life/articleshow/81473825.cms
- Daily OHLCV: Yahoo Finance via yfinance (split-adjusted), https://finance.yahoo.com/quote/GME/history
