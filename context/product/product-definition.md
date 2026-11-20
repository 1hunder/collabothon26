# Product Definition: Finance Quest (working title)

- **Version:** 1.0
- **Status:** Proposed
- **Context:** Prototype for Collabothon 2026, Commerzbank challenge "Finance Quest"

> Sections or bullets marked _(assumption)_ were filled in from best-practice defaults, not from the original brief. Confirm or revise them.

---

## 1. The Big Picture (The "Why")

### 1.1. Project Vision & Purpose

Young people don't stay out of investing because they lack information. They stay out because they lack the confidence to act, and traditional financial education feels disconnected from real decisions. Finance Quest gives each young investor a personal, one-shot role-play investing campaign built from real market history with the ending hidden. They make a real judgment call under uncertainty, see what actually happened, and learn to tell good judgment from good luck, so that their first real investment decision is one they can explain and stand behind.

**Why this needs a hidden future:** a chat assistant can't teach this, because it already knows how history ended. The Finance Quest engine anonymizes a real company and period and hides the outcome, so practicing on real history becomes a real test of judgment and not a trivia quiz.

### 1.2. Target Audience

- **Learners (end users):** young people aged 14–25 who are eligible for Commerzbank's StartDepot (free custody up to €20,000, savings plans from €25). Most keep their money in a savings account, know roughly what an ETF is, and haven't invested because they're afraid of losing money. Some already have a little investing experience. The first campaign also works as a placement round that shows how well each learner understands the domain.
- **Buyer:** Commerzbank retail and securities product teams, who want more young customers to make a confident, well-understood first investment in StartDepot.

### 1.3. User Personas

- **Persona 1: "Lena, the cautious saver"** (18, apprentice)
  - **Role:** Saves part of her monthly pay in a savings account. Has heard of ETFs from friends and social media.
  - **Goal:** Wants her money to grow but needs to feel she understands what she's doing before she puts any of it at risk.
  - **Frustration:** Every chart looks scary. She can't tell a normal dip from a real problem, and generic "Investing 101" content feels abstract and unrelated to an actual decision.

- **Persona 2: "Jonas, the overconfident dabbler"** (22, university student)
  - **Role:** Has bought a few single stocks after reading hype online, with mixed results.
  - **Goal:** Wants to prove to himself that he's good at picking investments.
  - **Frustration:** Can't tell whether his past wins came from skill or luck, and tends to act on headlines without researching first.

### 1.4. Success Metrics

**Prototype (Collabothon stage):**

- One complete mission is playable end to end on stage, from interest selection to the real-company reveal and the optional savings-plan step.
- The debrief clearly shows **judgment vs. luck** and **which available signals the player checked vs. missed**.
- Generated scenarios pass a **re-identification test**: players and jury members can't reliably name the real company or period before the reveal. _(assumption: e.g. fewer than 1 in 5 testers names the company correctly before the reveal)_

**Pilot (for the bank):**

- Share of players who set up a first StartDepot savings plan after a campaign.
- Share of players who stay invested through a drawdown (drop in value), both in-game and, where measurable, in StartDepot.
- Forecast calibration improves across one-shots: players' stated confidence matches their actual hit rate more closely over time.

**Learning objectives each campaign must serve:**

1. Research before acting.
2. Tell short-term volatility apart from long-term risk.
3. Judge one's own confidence honestly.
4. Make a first decision one can explain.

---

## 2. The Product Experience (The "What")

### 2.1. Core Features

- **Personal Campaign Generator:** the player picks their interests (for example gaming, fashion, sports, mobility). The generator finds a real company and a real historical period that fit those interests and contain a lesson, such as a sharp drop followed by a recovery. It then anonymizes everything identifying: company name, dates, prices and distinctive facts.
- **Data Room (inside a mocked StartDepot app):** the investigation space. It shows a price chart up to "story today", news items from the period, and an anonymized company card. The player decides what to look at, and the product quietly tracks which signals they checked.
- **CommerzBuddy (ally NPC):** an in-story companion the player can ask questions. It explains concepts and helps the player think, only knows what is available up to "story today", never reveals the outcome, and never gives investment advice.
- **Decision to the Campaign Master:** the player writes their decision and reasoning in free text, along with what they expect to happen and how confident they are.
- **Time Skip, Debrief & Rewind:** a time skip reveals what really happened. The debrief separates judgment from luck, shows which available signals the player checked and which they missed, and lets them rewind to see how other choices would have played out. Finally the real company is revealed, and the player can optionally set up a €25 savings plan in (mocked) StartDepot.

### 2.2. User Journey

1. Lena opens the (mocked) Commerzbank app, enters StartDepot and starts Finance Quest.
2. She picks her interests (say, sneakers and music streaming). The engine generates her personal one-shot campaign: an anonymized company ("Company X") at a story moment right after a sharp price drop.
3. In the Data Room she studies the price chart up to "story today", reads a few news items and checks the company card.
4. She asks CommerzBuddy, "Is a 30% drop normal for a company like this?" and gets an explanation of volatility that contains no hints about the future.
5. She writes to the Campaign Master: _"I'd hold and keep buying a little each month. Revenue is still growing, and the drop looks like a market-wide sell-off. I expect it to recover within two years. Confidence: 60%."_
6. A time skip shows what really happened next.
7. The debrief explains that her decision was well reasoned, notes that the outcome also involved some luck, and points out a signal she missed (a debt warning in one news item). She rewinds and sees how panic-selling would have ended.
8. The real company and period are revealed. Her first campaign also sets her skill level for the next one-shot.
9. She's offered the chance to set up a €25 monthly savings plan in StartDepot. She can accept (mocked) or skip.

---

## 3. Project Boundaries

### 3.1. What's In-Scope for this Version

- A mocked Commerzbank / StartDepot app shell that frames the experience.
- An interest picker that drives scenario selection.
- A campaign generator that picks a fitting real company and lesson period and anonymizes name, dates, prices and identifying facts.
- **Stage demo approach (pre-generated campaigns):** a live demo can't fail because a generated scenario turned out weak or recognizable, so the on-stage mission runs on campaigns prepared in advance. _(assumption)_
  - **Prepared before the event:** the team uses the real generator to create a small set of campaigns (about 2–3) covering popular interest combinations. Each one has a clear lesson (for example a sharp drop followed by a recovery) and has passed the re-identification test.
  - **Still feels personal on stage:** the presenter or audience picks interests in the interest picker, and the product matches them to the closest prepared campaign. The player never sees that it was prepared.
  - **What stays live:** only the scenario is prepared. CommerzBuddy's answers, the player's free-text decision, the debrief (judgment vs. luck, checked vs. missed signals) and the rewind all respond to what the player actually does during the demo.
  - **Showing the generator:** the generator itself is shown separately, for example by creating a new campaign live from audience-chosen interests or by walking through how a prepared campaign was produced and anonymized. If live generation is slow or produces a weak scenario, the demo falls back to a prepared campaign without breaking the flow.
  - **Why it matters to the bank:** it shows that the full experience works end to end today, while making clear that in a pilot every learner gets a freshly generated campaign.
- The Data Room: price chart up to "story today", period news and a company card, with tracking of which signals the player viewed.
- CommerzBuddy as an ally NPC limited to information available at "story today".
- Free-text decision submission with expectation and confidence.
- Time skip, a debrief that separates judgment from luck and checked from missed signals, and a rewind.
- The real-company reveal.
- An optional, mocked €25 savings-plan setup.
- Using the first campaign to estimate the player's level of domain understanding.
- Clear "education only, not investment advice" messaging throughout. _(assumption)_
- A re-identification check on generated scenarios before they are shown.

### 3.2. What's Out-of-Scope (Non-Goals)

- Investment advice or recommendations of specific securities. The product is education only.
- Real trading, real money or real order execution.
- Real login, real customer accounts or real customer data.
- A general-purpose chat assistant. CommerzBuddy only exists inside the campaign.
- Multi-mission progression systems, leaderboards, social or multiplayer features. _(assumption)_
- Live or real-time market data feeds. _(assumption)_
- Languages other than English. The product is English only.
- Handling for minors such as parental consent and age verification, which is deferred to the bank's existing StartDepot onboarding. _(assumption)_
- A native mobile app release. The mocked app only needs to work for the demo. _(assumption)_
