# Functional Specification: Disguised Real-History Scenarios with a Recognition Check

- **Topic:** Turning real market stories into disguised one-shot scenarios, and checking each one with AI "guessers" before any player sees it
- **Status:** In Review
- **Author:** Davyd (with Claude), from the team's anonymization test of 2026-11-20

---

## 1. Overview and Rationale (The "Why")

**Finance Quest** is a learning game inside a mock Commerzbank banking app for young first-time investors. Each game is a short **one-shot mission** built from a real piece of stock-market history. A mission runs in this order:

1. **Story intro:** a company's situation is set up at a moment in the past, called "story today".
2. **Investigation (the "Data Room"):** the player reads news items, looks at the price chart up to story today, and reads a company card. They can ask questions of **CommerzBuddy**, an AI helper character that explains concepts but never gives advice.
3. **Decision:** the player writes what they would do and why, and how confident they are.
4. **Time skip:** the game shows what happened next.
5. **Debrief:** the **Campaign Master**, the AI narrator character, explains which parts of the result came from good judgment and which came from luck.
6. **Reveal:** the real company and period are shown.

This only works if the player cannot tell which company and period they are looking at. If they can, the mission becomes a memory quiz ("I know that company recovered"), and the lesson is lost. The AI characters have the same problem: an AI that recognises the story could hint at the ending.

The team tested this on 2026-11-20 with six famous company stories from 2023–24 (including Netflix, Boeing and Nvidia). Each story was disguised in three increasingly careful ways, and AI guessers recognised all 18 versions, company and start month, mostly from memory. What gave them away was rarely a name. It was:

- the order of events;
- the timing of the news, which matched companies' regular quarterly results dates;
- the ratios between figures;
- the shape of the price chart.

The automatic recognition check itself worked: it caught every recognisable version and explained why.

This feature therefore has two parts:

1. **Disguise.** An AI writer automatically turns each real case into a disguised scenario, following fixed rules: an invented company name, story days instead of calendar dates, rescaled prices and amounts, and rewritten news.
2. **Recognition check (the "gate").** Several AI guessers then try to name the real company and period. Any scenario a guesser recognises is rewritten at most twice. If it is still recognised, the case is dropped and a different case is used instead. Players only ever get scenarios that passed.

The honest product claim becomes: **"Every one-shot built from a source case passes an automatic recognition check before you see it."** We will not claim "nobody can recognise it". Campaigns built from hand-prepared **reference packs** (spec 003, e.g. the Enron case) do not go through the recognition check; the team reviews them instead (see 2.3). They still follow every display rule in 2.1 and 2.2.

**Success measures for this feature (stage prototype):**

- At least 3, and ideally 5, approved scenarios exist for the stage demo.
- A check report covers the whole candidate batch, so the team can show one statistic on stage: cases checked, share recognised, share approved.

A separate product-level metric, outside this feature's acceptance, is that fewer than 1 in 5 human testers name the real company before the reveal.

---

## 2. Functional Requirements (The "What")

### 2.1 Players only see the disguised version of a scenario before the reveal

**As a** player, **I want** the story, chart, news, company card and AI answers to describe an unfamiliar company, **so that** my decision rests on my judgment, not my memory.

Before the reveal, the rules below apply to everything the player sees: the story intro, every news item, the company card, the price chart and its labels, CommerzBuddy's answers and the Campaign Master's narration.

- **Name.** The company has an invented name. It shares no word with the real company name, does not start with the same three letters, and does not contain the stock ticker.
- **Time.** Time is shown only as story days counted from the start of the story (for example "Day 84"), in the same unit on every screen. No calendar year, month name, quarter label (Q1–Q4) or weekday appears anywhere. Gaps between news items are rounded to whole weeks and may be stretched or shortened by up to 30%, so they no longer line up with companies' regular quarterly results dates.
- **Named things.** No real product, brand, person, city, country, named regulator, union, partner, rival, customer or famous slogan is named. General terms are allowed: continents ("in Europe"), roles ("the regulator", "the central bank", "a major customer") and the industry.
- **Amounts.**
  - **Money:** every amount of money in a case (revenue, profit or loss, cash flow, cash, debt, equity, deal sizes) is multiplied by **one shared hidden money factor**, so comparisons between money figures stay true. For example, profit versus cash flow, or debt versus cash, keep their real relationship, and the ledger lessons still work.
  - **Other kinds of amount:** users, headcount and similar each get their own hidden factor. Ratios between money and these figures (for example revenue per employee) therefore no longer match reality.
  - **Range and rounding:** each factor is chosen so every amount shown falls between 0 and 10,000, rounded to two significant figures. No amount is written in millions or billions, because young players find small, comparable numbers easier to grasp.
- **News wording.** News items are rewritten in plain words and do not reuse the wording of real headlines. They contain no phrase that compares the event with a span of years or with the company's whole history, such as "worst in decades", "biggest since …", "first time in its history" or "all-time record".
- **Industry.** The industry shown may be the real one, a more general version of it (for example "streaming entertainment" becomes "online subscription media"), or a different but economically similar industry (for example an aircraft-safety crisis retold as a medical-device recall). If the industry is moved, the business logic behind the lesson must still hold (subscriptions stay subscriptions, factories stay factories). The readability rating in 2.3 catches stories that no longer read as believable.

**Acceptance Criteria:**

- [ ] Given an approved scenario, when the player reads every story intro, news item, company card and chart label before the reveal, then they find no calendar year, month name, quarter label or weekday.
- [ ] Given an approved scenario, when the player reads every screen before the reveal, then neither the real company name nor its ticker appears, and none of the case's identifying terms (its real products, executives, home city and partners) appears either.
- [ ] Given an approved scenario, when the player opens the price chart, then the time axis shows story days counted from the start, not dates.
- [ ] When the player asks CommerzBuddy, directly or indirectly, which company or year this is (for example "Which real company is this?", "Is this Boeing?" or "Is this 2024?"), then CommerzBuddy says it doesn't know and that the answer is revealed at the end, and it names no company or year.
- [ ] When the player reads any Campaign Master narration before the reveal, then it names no real company and no calendar year.
- [ ] Given a news item that reports a price drop, when the player looks at the chart, then the price on that news item's story day is lower than at the previous news item (and the same holds for rises).

### 2.2 Price moves stay true to history; only the level changes

**As a** player, **I want** the ups and downs I see to be the real ones, **so that** what I learn about volatility and risk is real.

- Every percentage price move, both between news items and along the chart, matches the real history to within one percentage point.
- Only the overall price level is multiplied by one hidden factor. The factor is chosen so every price shown in the story falls between 0 and 10,000.
- The time skip and the reveal use the same price path, so nothing jumps between screens.

**Acceptance Criteria:**

- [ ] Given an approved scenario, when the player reads every price and amount before the reveal, then none is above 10,000, and none is written in millions or billions.
- [ ] Given an approved scenario, when the player compares the percentage change between two news items in the game with the same two news items in the reveal's table of real dates and prices (see 2.6), then the two percentages differ by no more than one percentage point.
- [ ] When the player moves from the decision through the time skip to the reveal, then the price shown for each story point is the same on every screen.

### 2.3 A scenario is playable only after it passes the recognition check

**As a** player, **I want** to be sure the story is not one I or an AI can simply recognise, **so that** the challenge is fair.

**As a** team member preparing the demo, **I want** the check to run automatically on each candidate case, **so that** only safe scenarios reach players.

**Each attempt runs in this order:**

1. **Disguise.** The AI writer produces a disguised scenario from the real case, following 2.1 and 2.2.
2. **Final scan.** The scenario fails if its text contains the real name, the ticker, any of the case's identifying terms, a calendar year, a month name, a quarter label or a weekday, or if its price moves differ from the real history by more than one percentage point.
3. **Guess from memory.** At least 2 guessers each receive only the disguised scenario and a plain description of the disguise rules (not the hidden factors). Each guesser works in its own separate session. It gives its top 3 company guesses with a confidence for each, its guess of the start month and year with a confidence, and a 1–5 rating of how natural the story reads to a first-time investor.
4. **Guess with web search (required).** If the scenario has passed so far, the same guessers try again with web search, up to 12 searches each. Each guesser plans its own searches as an investigator would, deciding which clues to look up and in what order.

**A guesser has recognised the scenario if any of these is true:**

- It names the real company among its top 3 guesses. A guess counts as correct if it names the real company, its ticker, its parent company, a subsidiary or a former name, ignoring spelling, punctuation and legal suffixes such as "Inc".
- It guesses the start month and year to within 3 months of the real start with a confidence of 30% or more.

**Outcomes:**

- An attempt **fails** if any guesser recognises the scenario, or if the average readability rating is below 3 of 5 (reason: "Reads unnaturally").
- After a failed attempt, the AI writer automatically rewrites the scenario in the same run, using the guessers' stated clues. There are at most 3 attempts in total.
- After 3 failed attempts, the case's final status is **Rejected: too recognisable**. It is never offered to players.
- A case whose attempt passes every step gets the final status **Approved**.

**Reference packs (spec 003) skip the guessers.**
- A hand-prepared campaign reference pack, such as the Enron case, does not go through the guess rounds.
- It still must pass the **final scan** (step 2) on everything a player can see before the reveal.
- It becomes playable only after a team member has reviewed it.
- It appears in the list of playable scenarios marked as a reference pack.

**Guessers:** for the hackathon, all guessers use Claude, each in its own separate session. The report notes that guessers from the same family as the AI writer give a weaker test than guessers from mixed providers.

**Acceptance Criteria:**

- [ ] Given one of the six famous test cases (for example Boeing 2024) as a candidate, when the check finishes, then the report shows at least one attempt marked "Failed" with each guesser's guesses and stated clues.
- [ ] Given one of the six famous test cases as a candidate, when the check finishes after 3 failed attempts, then its final status is "Rejected: too recognisable", and it is missing from the report's list of playable scenarios.
- [ ] Given a candidate that every guesser misses in both rounds, with a clean final scan and an average readability of 3 or more, when the check finishes, then its final status is "Approved" and it appears in the list of playable scenarios.
- [ ] Given a candidate whose disguised text still contains a calendar year, when the attempt is checked, then that attempt shows "Failed" with the reason "Real date found in text".
- [ ] When a player starts a quest, then the scenario they get is in the list of playable scenarios: either an approved case or a reviewed reference pack.
- [ ] Given a reference pack whose player-visible text contains a calendar year, when the pack is checked, then it is not playable and shows the reason "Real date found in text".

### 2.4 The team checks a batch of candidate cases in one run

**As a** team member, **I want** to run the check on a whole batch of candidate cases at once, **so that** we learn which kinds of cases stay hidden and build the demo from those.

- Each candidate case has:
  - the real company and its ticker;
  - a one-sentence lesson;
  - 2–6 dated news items, each with a price;
  - a list of identifying terms (products, people, places, partners).
- Each case is also tagged with:
  - company size: small (market value under €2bn), mid (€2–10bn) or large (over €10bn);
  - country or exchange;
  - the year of the story;
  - a fame rating of low, medium or high, set by a simple rule:
    - **high:** a large company listed in the US;
    - **medium:** any other large company, or a mid-size company listed in the US;
    - **low:** every other case (small companies, and mid-size companies listed outside the US).
- A case with no lesson, no identifying terms, a missing price, or fewer than 2 or more than 6 news items is listed as **Skipped: incomplete case**, and the run continues with the others. A case with missing tags is checked and shown as "untagged".
- The first run covers 100 candidate cases: the team's collection of 61 documented company stories, plus further cases the team adds to reach 100. The extra cases should be mostly small, mid-size and non-US companies. The batch ranges from famous US large caps to obscure companies, so the report shows where the line falls between recognisable and safe.
- Approved scenarios stay playable until a later run gives that same case a different result. The list of playable scenarios always reflects the latest result for each case.
- If fewer than 3 cases are approved, the team adds more low-fame and small or mid-size cases and runs again. The pass rule is never relaxed to reach the number.

**Acceptance Criteria:**

- [ ] Given a batch of 100 candidate cases, when the team runs the check, then one report lists all 100 cases, each with a final status of Approved, Rejected or Skipped.
- [ ] Given a candidate case with only one news item, when the team runs the check, then the report lists it as "Skipped: incomplete case" and the other cases are still checked.

### 2.5 The check report explains every result

**As a** team member, **I want** to see why each case passed or failed, **so that** I can choose demo scenarios and explain the approach to the jury.

**For each case, the report shows:**

- the real company, the invented name, the tags and the final status;
- every attempt, with each guesser's top 3 guesses and confidence, its start-date guess and confidence, its stated clues, the average readability rating, and the reason the attempt failed (if it did).

**At the top, a summary shows:**

- **N**, the number of cases checked (Skipped cases are counted separately);
- the share of checked cases recognised on their first attempt;
- the number and share of cases approved;
- the approval share for each fame rating and each company size;
- the list of playable scenarios.

**Acceptance Criteria:**

- [ ] When the team opens the check report, then the first thing they see is a summary line in the form "[N] cases checked · [X]% recognised on first attempt · [Y] approved ([Z]%)".
- [ ] When the team opens a rejected case, then they see all of its attempts, each with every guesser's guesses, confidence and stated clues (for example "order of events: safety halt → strike → job cuts").
- [ ] When the team looks at the summary, then they see the approval share for each fame rating (low, medium, high) and each company size (small, mid, large).

### 2.6 The reveal shows the real company and what was changed

**As a** player, **I want** to learn which real company and period I was playing, and how the story was disguised, **so that** I trust it was real and can look it up.

- The reveal comes at the end of the mission, after the time skip, the debrief and the player's reflection. Spec 003 defines that flow; there, this reveal is the "company reveal" step.
- The reveal screen shows:
  - the real company name and the real start and end dates;
  - a chart of the real historical prices with the in-game news items marked on it;
  - a table listing each news item with its real date and real price;
  - a "What we changed" list in plain words, for example: "We changed the company name, hid the dates, multiplied prices by a hidden factor, and rewrote the news in our own words. The ups and downs are real."
  - **The check result:** "Before you played, [G] AI testers tried to guess this company. None of them got it." Here G is the number of different guessers that checked the approved version. This line appears only for scenarios that went through the recognition check, not for reference packs.
- The reveal never suggests buying the revealed company's shares.

**Acceptance Criteria:**

- [ ] Given the player has submitted a decision, finished the debrief and submitted their reflection, when they reach the reveal, then they see the real company name, the real dates, the real price chart with news markers, and the table of real dates and prices.
- [ ] Given the player has not yet finished the debrief, when they try to reach the reveal (for example with the browser's forward button), then they don't see the real company name and are returned to the step they were on.
- [ ] Given a scenario approved by 3 different guessers, when the player views the reveal, then they see the "What we changed" list and the sentence "Before you played, 3 AI testers tried to guess this company. None of them got it."
- [ ] When the player views the reveal, then no button or text offers to buy the revealed company's shares, and no disclaimer line is shown (the demo carries no "Education only" label).
- [ ] Given a reference-pack campaign, when the player views the reveal, then the sentence "Before you played, … AI testers…" is not shown.

### 2.7 Before starting, the player is told the story is real but disguised

**As a** player, **I want** to know up front that this is real history in disguise, **so that** I take it seriously and don't feel tricked at the end.

- The note appears at the start of every mission, before the first story beat, and is dismissed with a "Got it" button. In spec 003's flow it appears right after "Find my quest" and before the Campaign Master's Tavern briefing.

**Acceptance Criteria:**

- [ ] When the player starts a mission, then before the first story beat they see the note "This story is real market history. We've hidden the company's name, the dates and the price level. You'll find out who it was at the end." with a "Got it" button.
- [ ] When the player taps "Got it", then the note closes and the story intro appears.

---

## 3. Scope and Boundaries

### In-Scope

- The disguise rules for every scenario a player sees (2.1, 2.2), produced automatically by an AI writer.
- The automatic recognition check: final scan, guessers from memory and with web search, up to 3 attempts, rejection (2.3).
- Batch checking of the team's candidate cases, with tags and the list of playable scenarios (2.4).
- The check report for the team, including the summary for the stage slide (2.5).
- The reveal's real identity, real-price table, "What we changed" list and check result (2.6).
- The disclosure note at the start of each mission (2.7).
- An approved set of at least 3 scenarios for the stage demo.

### Out-of-Scope

- The interest picker, and how a player's interests are matched to a playable scenario (separate quest-flow spec).
- Creating new scenarios live while a player waits. For the prototype, players only get scenarios that were checked in advance. With up to 12 web searches per guesser, a check would take far too long for a waiting player.
- Blending sources (one company's price chart combined with general news written to explain it), because it would weaken the "real history" promise.
- The stage presentation page and its side panels (separate spec). This spec only provides the statistics and check results those panels would show.
- The Data Room screens, CommerzBuddy, the Campaign Master, the time skip, debrief, rewind and savings plan themselves. Spec 003 (campaign engine) builds these: the Data Room is its Library and Market Square locations. This spec only sets the disguise rules they must follow.
- Generated scene art (separate spec). Its only rule here: no real logos, products or faces.
- A study with human testers trying to recognise the company (a product-level metric, run separately).

---

## Change Log

- 2026-11-20 — alignment with spec 003 (campaign engine), team decisions — Five changes:
  - **Amounts (2.1):** all money amounts in a case now share one hidden money factor, so ledger lessons keep working.
  - **Reference packs (2.3):** spec 003's hand-prepared packs skip the guess rounds, but must pass the final scan and a team review before they are playable.
  - **Reveal (2.6):** it now follows the player's reflection. The "Education only" label is removed, at the team's decision: no disclaimer anywhere in the demo. The "AI testers" line shows only for gate-checked scenarios.
  - **Disclosure note (2.7):** placed before the Tavern briefing.
  - **Data Room:** realised by spec 003.
