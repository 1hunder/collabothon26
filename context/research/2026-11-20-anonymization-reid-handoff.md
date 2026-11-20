# Finance Quest: anonymization and re-identification gate (engineering handoff)

Date: 2026-11-20 (Collabothon 2026, day 1).
Audience: the engineer who will write the functional spec and implement this in the Finance Quest repo (React 18 + TS + Vite frontend; planned FastAPI + LangGraph + Claude backend).
Source material: the team concept PDF "Finance Quest — StartDepot Campaign Concept" (@Viktor, 20 Nov 2026), the case file `gamified_investing_articles_ru.md`, and a test run in `collabothon2026\sandbox\2026-11-20_anonymization-reid-test\`.

Sections marked **(proposed)** were not built or tested. They are design suggestions for the spec.

---

## 0. Context

- **Event:** Collabothon 2026, organised by Commerzbank Digital Technology Centre Poland. 20 Nov 09:00 to 22 Nov 18:00, Ogrodowa Office, Ogrodowa 8, Łódź. Teams of 3–6.
- **Challenge track:** Commerzbank "Finance Quest". How can financial learning become engaging enough that entrepreneurs actively seek it out and improve their financial decisions over time? Our concept narrows the audience to StartDepot users aged 18–29.
- **Prizes:** 10,000 PLN for first place per challenge, 2,000 PLN for second, 2,000 PLN audience award. All prizes are in kind.
- **Scope of this conversation:** we built and tested the **anonymization layer** of the concept. That layer turns real market history into a scenario that neither the player nor Claude can recognise. We also built the **re-identification test** (the "re-id gate"), which checks whether that worked. The rest of the product (UI, campaign master, CommerzBuddy) comes from the concept PDF and is summarised here only so the spec has context.

---

## 1. Goal and the component we designed and tested

### 1.1 Product goal (from the concept PDF)
The engine generates short, story-driven one-shot investing campaigns for Commerzbank StartDepot users under 29, each tailored to the player's interests.
1. The player investigates **anonymized real market history** with help from the ally NPC, CommerzBuddy.
2. The player writes a decision in free text and locks a forecast.
3. Only then does the player see what really happened.

- **Learning objective:** research before acting, tell short-term volatility apart from long-term risk, judge one's own confidence honestly, and make a first decision one can explain.
- **Pitch line:** "Claude knows how 2020 ended. Our players don't, and that's the point."

### 1.2 The component under test
**Anonymization layer + re-identification gate.** Input: a real case (company, dated news beats, prices). Output: a disguised scenario. The disguise must:
- hide the company and the period from the player and from the LLM agents (campaign master and CommerzBuddy);
- keep the real direction and rough size of price moves, plus the causal chain and the lesson;
- pass deterministic integrity checks;
- pass an automatic re-identification test before any player sees it.

### 1.3 Headline result
On 6 famous 2023–24 cases (Netflix, Boeing, Nvidia, Meta, Spotify, Intel), **every disguise failed**: 18 of 18 attacks re-identified the company and the start month. This held for all three pipeline versions, and most attackers needed only memory, no web search. The re-id gate itself **worked**: it caught every breach and explained the cause. Conclusion: **case selection matters more than text rewriting**, and the gate must be a mandatory step (see §5 and §6).

---

## 2. User flow and screens (from the concept PDF)

The app is a mobile-first mocked Commerzbank app. The demo starts already logged in and shows a visible "Prototype" label. There is no realistic login screen.

| # | Screen / step | What happens | Notes for the spec |
|---|---|---|---|
| 1 | **StartDepot → Preferences** | Player picks interests (sectors or themes such as gaming or energy), a story budget and a horizon | Inputs to the case selector |
| 2 | **Generation** (loading / side panel) | Engine finds a company and period matching the interests that hold a lesson (e.g. a drop followed by a recovery), pulls prices, news and metadata, anonymizes everything, and the campaign master writes the one-shot | The anonymizer + re-id gate (this doc) run here. In the demo this step is pre-generated |
| 3 | **Story beat** | Campaign master (Claude) sets the scene at an anonymized point in history | Shows only data up to "story today" |
| 4 | **Investigate** | Player chats with CommerzBuddy, opens the price chart up to story today, reads the news, checks the company card | Buddy explains concepts and asks questions back. It never says what to buy |
| 5 | **Decide** | Free-text decision and reasoning, plus the expected outcome and a confidence statement (e.g. "80% sure the price ends between X and Y") | No multiple choice. Forecast is locked before the reveal |
| 6 | **Time skip** | Engine reveals what happened next, with real (disguised-scale) prices | Numbers come from the engine only |
| 7 | **Debrief** | Master separates judgment from luck, comments on the reasoning, leaves one rule of thumb | |
| 8 | **Reveal** (proposed in PDF) | Real company and dates are revealed at the end | |
| 9 | **First real step** (optional) | Player may set up a mocked €25 StartDepot savings plan | Always the player's own choice, never a recommendation |

- **Persistence:** every decision and forecast is saved, so a track record and forecast-accuracy history build up across one-shots.
- **Visuals:** scene art is generated per one-shot. CommerzBuddy and other recurring characters use a fixed sprite set. Generated images contain no real logos, products or faces.
- **Demo setup:** the app runs in a phone frame on a laptop browser, with a QR code to the deployed app. Side panels show (a) how a one-shot is generated, (b) how anonymization disguises the company, (c) what Buddy can and cannot see. The demo uses a pre-generated one-shot with cached model responses and a backup video.

---

## 3. Key decisions, rules and constraints

### 3.1 Architecture principles (concept PDF)
- **Deterministic code owns the data and every number.** Claude only narrates and advises. Any number in Claude's text that the engine did not produce is rejected.
- **Agents only ever see the anonymized scenario, and only up to story today.** The anonymization layer runs on everything fetched, so nothing downstream (agents included) sees real names or dates.
- **The forecast is locked before the reveal.**
- **Data sources (planned):**
  - company search and news from open APIs;
  - metadata from Bloomberg and D&B, if licensed accounts are available at the event (otherwise public metadata);
  - prices from Yahoo Finance via `yfinance`. This library is unofficial, so cache all prices before the demo.

### 3.2 What the AI may and may not do
| Agent | May | May not |
|---|---|---|
| Campaign master (Claude) | Narrate story beats; react to the player's free-text decision; debrief, separating judgment from luck; give one rule of thumb | Play for the player; recommend a specific security; invent numbers; see real names, dates or the future |
| CommerzBuddy (Claude) | Explain concepts; ask questions back; point to the chart, news and company card | Say what to buy or sell; recommend a security; see data beyond story today; know the real company |
| Anonymizer LLM (generator) | Rewrite text per the spec; transplant the industry; drop or replace fingerprint details | Change the number of beats, the lesson or price directions; produce prices or story days (code overwrites them) |
| Attacker LLM (re-id gate) | Guess the real company and period, with and without web search | Read source data or files |

- **Regulatory line:** neither the master nor Buddy recommends a specific security. This keeps the product on the education side of the MiFID II line around investment advice.
- **Product claim to use in the pitch:** "Every one-shot passes an automatic re-identification test before you see it." Do **not** claim "nobody can recognise it" for famous companies. The test disproved that.

### 3.3 Anonymization rules: production spec (verbatim, `src/prod_anonymizer_spec.md`)
```markdown
# Production anonymizer spec (LLM semantic scrub on top of deterministic rules)

Input: one real case (company, people, products, dated news beats, prices).
Output: one JSON scenario with the SAME schema as the POC output:
{scenario_id, company, sector, industry, timeline_note, beats:[{story_day, price, headline, facts[]}]}

Deterministic layer (same as POC):
- Fictional company name, no real people, story days relative to first beat, prices rescaled by one factor.

Semantic layer (LLM):
1. Remove every proper noun that points at the real world: products, models (e.g. aircraft or chip names),
   partners, regulators by name, unions, customers, rivals, cities, countries where they narrow the company down,
   famous shows/brands, slogans or quotes the company is known for.
2. Replace a uniquely famous event with a functional equivalent that teaches the same thing
   (e.g. "a safety incident with one flagship product leads the regulator to halt deliveries"), not a near-copy.
3. Generalise the industry one level up or to a plausible sibling industry, as long as the economic logic
   of the lesson survives (subscriptions stay subscriptions, factories stay factories).
4. Numbers: keep only what the lesson needs. Rescale absolute sizes (users, revenue, headcount, $ amounts)
   by one consistent factor per case and round them; prefer ratios and percentages. No calendar years,
   months, quarter numbers (Q1–Q4) or weekdays anywhere.
5. Percent moves of the stock between beats must stay true to the real data (prices = real x one factor).
6. Keep the causal chain and the lesson. Keep the number of beats and their order.
7. No real logos, faces, or anything that reads as a famous headline when searched.
```

### 3.4 Extra rules added in round 2 (after the attackers' feedback)
These were given to the generator in its prompt (see §4.4.2):
1. Move the story to a different but economically analogous industry when the original combination of events is iconic.
2. Break the fingerprint combination: drop, merge or swap one non-essential detail per case (e.g. stock split, first-ever dividend, interim co-CEOs). Add at most one plausible generic detail.
3. Scale each metric family by its own factor (users, revenue, headcount, deal sizes) and round. Do not preserve ratios between figures.
4. No dating superlatives ("worst in decades", "first time in history", "biggest since"). No phrasing close to real wire headlines.
5. Do not state exact stock-move percentages in the text. Code owns prices and timing: story days are jittered into whole weeks, and each real move is perturbed by ±25% with its direction kept.

**Decision to confirm in the spec:** round 2 trades the "exact real prices" promise for "real direction and rough size". The concept PDF says "real prices". Pick one and say it in the reveal screen.

### 3.5 Re-id gate rules **(proposed thresholds, derived from the test)**
- Gate on the **closed-book** (memory-only) guess: reject if the correct company is anywhere in the top-3, or if the top-1 confidence in the true company is ≥ 30%. These numbers are a starting point and need calibrating on a bigger case set.
- Use the **open-book** (web search) attack as a secondary check, run only on scenarios that passed closed-book.
- Retry the rewrite at most 2–3 times. If the case still fails, **swap the case**: rewriting does not fix famous cases.
- Use 2–3 attacker models (e.g. Claude, GPT, Gemini via LiteLLM). A scenario fails if any one of them breaks it.

---

## 4. Data models, prompts, APIs and code

### 4.1 Source case (real input, never shown to agents or players)
File: `data/source_cases.json` → `{ "_note": str, "cases": SourceCase[] }`. Example (verbatim, one case):
```json
{
  "id": "C2", "company": "Boeing", "ticker": "BA", "aliases": ["The Boeing Company", "BA"], "people": ["Dave Calhoun", "Kelly Ortberg", "Stan Deal"],
  "sector": "Industrials", "industry": "Aerospace manufacturer", "hq": "Arlington, Virginia",
  "products": ["737 MAX 9", "777X", "Alaska Airlines flight 1282", "FAA", "Spirit AeroSystems", "IAM machinists union", "Starliner"],
  "lesson": "Even a famous, dominant company can face a prolonged crisis; brand popularity is not a risk measure.",
  "beats": [
    {"date": "2024-01-08", "price": 229, "headline": "Boeing shares tumble after US grounds some 737 MAX jets", "facts": ["A door plug blew out mid-flight on an Alaska Airlines 737 MAX 9 on Jan 5", "FAA grounds 171 MAX 9 jets for inspections", "Loose bolts found on several aircraft"]},
    {"date": "2024-09-11", "price": 160, "headline": "Boeing faces possible strike over labor contract", "facts": ["33,000 IAM machinists in Seattle area may strike", "Tentative deal offers 25% raises over four years", "Workers wanted 40%"]},
    {"date": "2024-10-11", "price": 150, "headline": "Boeing to cut 17,000 jobs, delay first 777X jet", "facts": ["Cuts 10% of workforce", "First 777X delivery pushed to 2026", "Expects $5bn pre-tax charges; strike in its fifth week"]},
    {"date": "2024-11-05", "price": 155, "headline": "Boeing strike ends as workers accept new contract", "facts": ["Machinists approve 38% raise over four years", "Strike lasted 53 days", "Company raised $24bn in a share sale in October"]}
  ],
  "end": {"date": "2024-12-31", "price": 177, "note": "-32% in calendar 2024"}
}
```
In the test, `products` doubled as a banned-token list (it includes orgs and events, not only products). In the spec, rename it to something like `identifying_terms`. Prices in the test were approximate values recalled from memory. Production must use cached real prices.

### 4.2 Scenario (anonymized output, the only thing agents and the UI see)
```json
{
  "scenario_id": "PROD2-C2",
  "company": "Calderine Medical Systems",
  "sector": "Health Care",
  "industry": "Hospital medical equipment manufacturing",
  "timeline_note": "Story weeks are approximate. Names, places and dates are hidden; amounts and prices are disguised but keep the real direction and rough size of moves.",
  "beats": [
    {"story_day": 0, "price": 279.28,
     "headline": "Calderine shares drop after health regulator halts use of its newest surgical system",
     "facts": ["A mounting component came loose on a recently installed flagship surgical system during a procedure; the patient was not seriously harmed",
               "The regulator orders several hundred installed systems of that model taken out of use until they are inspected",
               "Inspections turn up improperly fastened parts on a number of other units"]},
    {"story_day": 266, "price": 209.45, "headline": "Calderine workers threaten to walk out over a new labour contract", "facts": ["..."]},
    {"story_day": 287, "price": 197.47, "headline": "Calderine plans deep job cuts and pushes back its next-generation system", "facts": ["..."]},
    {"story_day": 308, "price": 202.78, "headline": "Calderine walkout ends as workers back revised contract", "facts": ["..."]}
  ]
}
```
The generator also writes `_generation_notes.json` per batch: `{ "<case id>": { original_industry, transplanted_industry, changes_vs_round1: string[] }, "_pipeline_warning": ... }`.

### 4.3 Attack result (re-id gate output)
```json
{"closed_book":{"guesses":[{"company":"","ticker":"","p":0}],"start":"YYYY-MM","key_clues":[""]},
 "open_book":{"guesses":[{"company":"","ticker":"","p":0}],"start":"YYYY-MM","searches_used":0,"key_clues":[""]},
 "player_view":{"coherence_1to5":0,"issues":[""]}}
```
`attacks/_blind_map.json` maps a blind code to its scenario: `[{"code":"T01","scenario":"PROD-C2"}, ...]`. Attackers only ever see the scenario without its `scenario_id`.

### 4.4 Prompts (verbatim)

#### 4.4.1 Generator, round 1 (production v1)
```text
You are the anonymization layer of an educational investing game ("Finance Quest"). Players see real stock-market history disguised so that neither they nor an LLM can recognise the company or the period; the real company is revealed only at the end.

Read:
- /mnt/user-data/outputs/sandbox/data/source_cases.json (6 real cases)
- /mnt/user-data/outputs/sandbox/src/prod_anonymizer_spec.md (rules you must follow)
- /mnt/user-data/outputs/sandbox/scenarios/poc/POC-C1.json (example of the output schema from the naive rule-based version; yours must be far less recognisable)

For each case write /mnt/user-data/outputs/sandbox/scenarios/prod/PROD-<id>.json (e.g. PROD-C1.json) with the same schema: scenario_id ("PROD-C1"), company (a fictional name not resembling the real one, and different from the POC names), sector, industry (generalised per the spec), timeline_note, beats [{story_day, price, headline, facts[]}].

Hard requirements:
- story_day values: keep the real day gaps between beats (compute from source dates; first beat = 0).
- price: real price x ONE random factor per case between 0.2 and 4 (pick it yourself, different per case, round to 2 decimals). Percentage moves between beats must equal the real ones.
- Keep 2-4 facts per beat, the causal chain, and the lesson the case teaches.
- No calendar years, month names, quarter labels, real product/person/organisation/place names, famous slogans, or distinctive exact figures (like 17,000 jobs, 13.1 million subscribers, $40bn buyback, 10-for-1 split, 53-day strike). Rescale/round counts and money consistently per case.
- Think like an attacker: after drafting each scenario, ask yourself "could a well-read analyst name this company from this text?" If yes, generalise further.

Also write /mnt/user-data/outputs/sandbox/scenarios/prod/_generation_notes.json: for each case, the price factor, the count/money rescale factor, and a short list of what you removed or replaced.

Reply only with a one-line confirmation per file written.
```

#### 4.4.2 Generator, round 2 (re-id loop turn, production v2)
```text
You are the anonymization layer of an educational investing game ("Finance Quest"): players see real stock-market history disguised so neither they nor an LLM can recognise the company or period. A first production version was fully broken by red-team attackers: every one of 6 scenarios was identified with 90-99% confidence.

Read:
- .../data/source_cases.json (6 real cases)
- .../src/prod_anonymizer_spec.md (base rules)
- .../src/round1_attacker_feedback.md (WHY round 1 failed - this is the most important input)
- .../scenarios/prod/PROD-C*.json (the round-1 versions that failed)

Write round-2 scenarios .../scenarios/prod_v2/PROD2-<id>.json (PROD2-C1 ... PROD2-C6), same schema (scenario_id, company, sector, industry, timeline_note, beats[{story_day, price, headline, facts[]}]). Put any placeholder numbers in story_day and price - a deterministic script will overwrite them afterwards with jittered weeks and a perturbed price path, so do NOT describe exact percentage stock moves in the text ("shares fall sharply" is fine; "falls 26%" is not).

New rules for round 2, on top of the base spec:
1. Transplant the story to a different but economically analogous industry when the original combination of events is iconic (e.g. an aerospace safety grounding + strike could become a medical-device recall + nurses'/factory strike; a chip boom could become a battery or networking-equipment boom). Keep the sector label consistent with the new industry. Keep the economic mechanism and the lesson intact.
2. Break the fingerprint combination: you may drop, merge or swap ONE non-essential beat-level detail per case (e.g. stock split, first-ever dividend, interim co-CEOs) and may add one plausible generic detail, as long as the lesson and the price direction at each beat stay true.
3. Scale each metric family by its own factor (users, revenue, headcount, deal sizes differently) and round; do not preserve ratios between figures.
4. No superlatives that date the story ("worst in decades", "first time in history", "biggest since"). No phrasing close to real wire headlines.
5. Keep the same number of beats and the lesson in source_cases.json.

Then write .../scenarios/prod_v2/_generation_notes.json with, per case, the transplanted industry and what you changed versus round 1. Reply with one line per file written.
```

#### 4.4.3 Round-1 attacker feedback fed into the loop (verbatim, `src/round1_attacker_feedback.md`)
```markdown
# What broke the round-1 production disguise (from 6 attacker reports)
1. Real day gaps between beats (0/57/148/245 etc.) = quarterly earnings calendar -> exact dates recovered.
2. Exact real percentage moves between beats -> matched against remembered closing prices.
3. One consistent scale factor for all amounts -> ratios survive; one known figure recovers the factor.
4. Iconic event combinations survive paraphrase: safety grounding + machinists strike + share sale;
   foundry unit loss + plant program + dividend cut + CEO ouster; year-of-efficiency + moonshot division + first dividend;
   paid-sharing crackdown + actors' strike; AI demand + 5x data-center growth + stock split; third layoff round + first full-year profit.
5. Superlatives that date the story: "worst day in decades", "first time in its history", "biggest gain in years".
6. Phrasing close to real wire headlines.
```

#### 4.4.4 Attacker prompt (re-id gate, verbatim; round-1 wording)
```text
You are a red-team tester for an educational investing game. The game shows players REAL stock-market history in disguise: the company name is fictional, people and places are removed, calendar dates are replaced by "story days" counted from the first news item, prices are multiplied by an unknown constant (but percentage moves between news items are real), and some amounts may be scaled. Your job is to find out whether the disguise can be broken.

Do NOT read, list or search any files on disk. Use only the scenario below.

SCENARIO:
{SCENARIO}

Step 1 - closed book: without any tools, name your top 3 guesses for the real listed company (with ticker) and the real start month/year of the first news item, each with a probability (0-100) that it is correct.
Step 2 - open book: now you may use web search (at most 6 searches) to confirm or change your guesses. Again give top 3 company guesses with probabilities, and the start month/year.
Step 3 - player view: rate 1-5 how natural and coherent the scenario reads to a young first-time investor (5 = reads like a real company story, 1 = confusing or obviously fake), and note anything contradictory.

Reply with ONLY one JSON object, no prose:
{"closed_book":{"guesses":[{"company":"","ticker":"","p":0}],"start":"YYYY-MM","key_clues":[""]},
 "open_book":{"guesses":[{"company":"","ticker":"","p":0}],"start":"YYYY-MM","searches_used":0,"key_clues":[""]},
 "player_view":{"coherence_1to5":0,"issues":[""]}}
```
The round-2 wording replaced the first sentence's disguise description with: "...calendar dates are replaced by approximate 'story days', prices and amounts are disguised (the direction and rough size of moves are real), and the industry may be changed to an analogous one." The attacker is always told how the disguise works (worst-case assumption: the method is known).

### 4.5 Code (verbatim, Python 3, stdlib only; all scripts run from the sandbox root)

#### 4.5.1 `src/poc_anonymizer.py`: rule-based baseline
```python
"""POC anonymizer: deterministic rules only (what a first hackathon build does).
- company name, ticker, aliases, people -> placeholders
- dates -> relative to the first beat ("Day 0", "Day +57") plus a fake base year
- prices -> rescaled by a random factor (percent moves stay real)
Facts and headlines are otherwise kept verbatim."""
import json, random, re, sys
from datetime import date

FAKE_NAMES = ["Northwind Media", "Atlas Aero", "Helix Compute", "Orbit Social", "Lumen Audio", "Vertex Silicon"]

def anonymize(case, idx, seed=42):
    rnd = random.Random(seed + idx)
    fake = FAKE_NAMES[idx]
    scale = round(rnd.uniform(0.15, 3.0), 3)
    subs = [case["company"], case["ticker"], *case["aliases"]]
    subs = sorted(set(subs), key=len, reverse=True)
    def scrub(t):
        for s in subs:
            t = re.sub(rf"\b{re.escape(s)}\b", fake, t)
        for i, p in enumerate(case["people"]):
            t = t.replace(p, f"Executive {chr(65+i)}")
            t = t.replace(p.split()[-1], f"Executive {chr(65+i)}")
        return t
    d0 = date.fromisoformat(case["beats"][0]["date"])
    beats = []
    for b in case["beats"]:
        d = date.fromisoformat(b["date"])
        beats.append({
            "story_day": (d - d0).days,
            "price": round(b["price"] * scale, 2),
            "headline": scrub(b["headline"]),
            "facts": [scrub(f) for f in b["facts"]],
        })
    return {
        "scenario_id": f"POC-{case['id']}",
        "company": fake,
        "sector": case["sector"],
        "industry": case["industry"],
        "timeline_note": "Story days are counted from the first news item. Real dates are hidden.",
        "beats": beats,
    }

if __name__ == "__main__":
    src = json.load(open(sys.argv[1]))
    out = sys.argv[2]
    for i, c in enumerate(src["cases"]):
        s = anonymize(c, i)
        json.dump(s, open(f"{out}/{s['scenario_id']}.json", "w"), indent=2, ensure_ascii=False)
        print(s["scenario_id"], "ok")
```

#### 4.5.2 `src/check_integrity.py`: deterministic integrity and leak checks
```python
"""Deterministic checks the engine would run on every generated scenario:
- price moves between beats match the real data (tolerance 1.5 pp)
- story-day gaps match real dates
- leak scan: banned tokens (real names, products, people, years, months, quarters, distinctive figures)"""
import json, re, sys, glob
from datetime import date
src = {c["id"]: c for c in json.load(open("data/source_cases.json"))["cases"]}
MONTHS = r"\b(January|February|March|April|May|June|July|August|September|October|November|December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)\b"
EXTRA = {"C1": ["5.9 million","8.8 million","13.1 million","232 million","260 million","WWE","Hollywood","$7.99"],
         "C2": ["17,000","33,000","171","53 days","38%","$24bn","Seattle","door plug"],
         "C3": ["10-for-1","427%","$11bn","$26bn","$28bn","trillion","generative AI"],
         "C4": ["$40bn","year of efficiency","$50bn","64%","metaverse","$40.1bn"],
         "C5": ["1,500","602 million","236 million","615 million","675 million","€1bn","€168m"],
         "C6": ["15%","50 years","$2.5bn","$12.2","co-CEO","26%"]}
rows = []
for f in sorted(glob.glob(sys.argv[1] + "/*-C*.json")):
    s = json.load(open(f)); cid = s["scenario_id"].split("-")[1]; c = src[cid]
    text = json.dumps(s, ensure_ascii=False)
    banned = [c["company"], c["ticker"], *c["aliases"], *c["people"], *[p.split()[-1] for p in c["people"]], *c["products"], c["hq"].split(",")[0], *EXTRA[cid]]
    leaks = sorted({b for b in banned if re.search(rf"(?<![A-Za-z]){re.escape(b)}(?![A-Za-z])", text, re.I)})
    leaks += sorted(set(re.findall(r"\b(?:19|20)\d\d\b", text))) + sorted(set(re.findall(MONTHS, text))) + sorted(set(re.findall(r"\bQ[1-4]\b", text)))
    rb, sb = c["beats"], s["beats"]
    move_err = max(abs((sb[i+1]["price"]/sb[i]["price"]) - (rb[i+1]["price"]/rb[i]["price"]))*100 for i in range(len(rb)-1)) if len(sb)==len(rb) else 999
    d0 = date.fromisoformat(rb[0]["date"])
    days_ok = len(sb)==len(rb) and all(sb[i]["story_day"] == (date.fromisoformat(rb[i]["date"])-d0).days for i in range(len(rb)))
    rows.append({"scenario": s["scenario_id"], "company_shown": s["company"], "industry_shown": s["industry"], "beats_ok": len(sb)==len(rb), "days_ok": days_ok, "max_price_move_error_pp": round(move_err,2), "leaks": leaks, "n_leaks": len(leaks)})
json.dump(rows, open(sys.argv[2], "w"), indent=2, ensure_ascii=False)
for r in rows: print(r["scenario"], r["industry_shown"][:40], "| days", r["days_ok"], "| move err", r["max_price_move_error_pp"], "| leaks", r["n_leaks"], r["leaks"][:8])
```
Known false positives:
- an executive's surname "Deal" matches the ordinary word "deal";
- the year regex matches a price such as `1993.83`.

The spec should exclude numeric fields from the year scan and match surnames only together with first names. `EXTRA` (distinctive figures per case) was hand-written for the test. In production, extract it automatically from the source facts (numbers, named entities).

For v2, integrity was checked inline instead of with `days_ok`: each move must keep its real direction and stay within ±25% of the real move.
```python
ok = all(((sb[i+1]/sb[i]-1)*(rb[i+1]/rb[i]-1) > 0) and abs((sb[i+1]/sb[i]-1)/(rb[i+1]/rb[i]-1)) <= 1.26
         for i in range(len(rb)-1))
```

#### 4.5.3 `src/prod_v2_postprocess.py`: deterministic timeline and price disguise (runs after the LLM rewrite)
```python
"""Deterministic v2 layer applied AFTER the LLM rewrite:
- story days: jittered so gaps no longer match an earnings calendar (each gap x U(0.7,1.3), rounded to whole weeks)
- price path: each real move perturbed by up to +-25% of its size (direction and rough magnitude kept),
  then rescaled by a new random factor. The time-skip reveal uses this same disguised path."""
import json, random, sys, glob, zlib
src = {c["id"]: c for c in json.load(open("data/source_cases.json"))["cases"]}
for f in sorted(glob.glob("scenarios/prod_v2/PROD2-C*.json")):
    s = json.load(open(f)); cid = s["scenario_id"].split("-")[1]; c = src[cid]
    rnd = random.Random(zlib.crc32(cid.encode()) + 99)
    from datetime import date
    d = [date.fromisoformat(b["date"]) for b in c["beats"]]
    days, cur = [0], 0
    for i in range(1, len(d)):
        gap = (d[i]-d[i-1]).days * rnd.uniform(0.7, 1.3)
        cur += max(7, round(gap/7)*7); days.append(cur)
    p = [b["price"] for b in c["beats"]]; scale = rnd.uniform(0.3, 3.5)
    path = [p[0]*scale]
    for i in range(1, len(p)):
        move = p[i]/p[i-1] - 1
        path.append(path[-1] * (1 + move * rnd.uniform(0.75, 1.25)))
    for i, b in enumerate(s["beats"]):
        b["story_day"] = days[i]; b["price"] = round(path[i], 2)
    s["timeline_note"] = "Story weeks are approximate. Names, places and dates are hidden; amounts and prices are disguised but keep the real direction and rough size of moves."
    json.dump(s, open(f, "w"), indent=2, ensure_ascii=False); print(s["scenario_id"], days, [round(x,1) for x in path])
```
- **Bug fixed during the test:** the first version seeded with `hash(cid)`, which changes on every Python run. It now uses `zlib.crc32`.
- **Spec note:** in production, apply the same transform to the **full daily price series** behind the chart, not only to beat prices. Perturb returns per segment between beats so the chart and the beat prices stay consistent.

#### 4.5.4 `src/score.py`: scoring
```python
"""Scores privacy (re-identification resistance), integrity and player coherence per pipeline.
Privacy per scenario and attacker mode:
  top1 company correct -> breach 1.0 ; correct in top-3 -> 0.5 ; else 0
  start month within 3 months of truth -> +0.25 (capped at 1.0)
privacy = 100 * (1 - mean breach)
integrity = 100 if days_ok and price error < 1.5pp, minus 5 per leaked banned token (min 0)
coherence = attacker player_view 1-5 scaled to 0-100
overall = 0.5*privacy + 0.3*integrity + 0.2*coherence   (privacy is the product's core promise)"""
import json, glob
from datetime import date
src = {c["id"]: c for c in json.load(open("data/source_cases.json"))["cases"]}
bmap = {r["code"]: r["scenario"] for r in json.load(open("attacks/_blind_map.json"))}
integ = {r["scenario"]: r for p in ["poc","prod","prod2"] for r in json.load(open(f"results/integrity_{p}.json"))}
IGNORE = {"PROD-C2": {"Deal"}, "PROD2-C5": {"1993"}}  # false positive: exec surname 'Deal' vs the word 'deal'
def norm(x): return (x or "").lower().replace(".", "").replace(",", "").replace("inc","").strip()
def hit(g, c):
    names = {norm(c["company"]), norm(c["ticker"]), *map(norm, c["aliases"])}
    return norm(g.get("ticker")) in names or any(n and n in norm(g.get("company")) for n in names)
def month_ok(s, d):
    try:
        y, m = map(int, s.split("-")[:2]); t = date.fromisoformat(d)
        return abs((y*12+m) - (t.year*12+t.month)) <= 3
    except Exception: return False
rows = []
for f in sorted(glob.glob("attacks/T*_result.json")):
    code = f.split("/")[-1][:3]; sid = bmap[code]; pipe, cid = sid.split("-"); c = src[cid]; r = json.load(open(f))
    row = {"code": code, "scenario": sid, "pipeline": pipe, "case": c["company"]}
    for mode in ["closed_book", "open_book"]:
        g = r[mode]["guesses"]
        top1 = bool(g) and hit(g[0], c); top3 = any(hit(x, c) for x in g[:3])
        b = 1.0 if top1 else 0.5 if top3 else 0.0
        if month_ok(r[mode].get("start",""), c["beats"][0]["date"]): b = min(1.0, b + 0.25)
        row[mode] = {"top1": top1, "top3": top3, "top1_guess": g[0]["company"] if g else None, "p": g[0].get("p") if g else None, "start": r[mode].get("start"), "breach": b}
    it = integ[sid]; leaks = [l for l in it["leaks"] if l not in IGNORE.get(sid, set())]
    row["integrity"] = max(0, (100 if it["days_ok"] and it["max_price_move_error_pp"] < 1.5 else 50) - 5*len(leaks))
    row["leaks"] = leaks
    row["coherence"] = (r["player_view"]["coherence_1to5"] - 1) / 4 * 100
    row["issues"] = r["player_view"].get("issues", [])
    rows.append(row)
summary = {}
for pipe in ["POC", "PROD", "PROD2"]:
    R = [x for x in rows if x["pipeline"] == pipe]
    cb = sum(x["closed_book"]["breach"] for x in R)/len(R); ob = sum(x["open_book"]["breach"] for x in R)/len(R)
    priv = 100*(1 - (cb+ob)/2); integ_s = sum(x["integrity"] for x in R)/len(R); coh = sum(x["coherence"] for x in R)/len(R)
    summary[pipe] = {"n": len(R),
        "reid_top1_closed_book": f'{sum(x["closed_book"]["top1"] for x in R)}/{len(R)}',
        "reid_top1_open_book": f'{sum(x["open_book"]["top1"] for x in R)}/{len(R)}',
        "reid_top3_open_book": f'{sum(x["open_book"]["top3"] for x in R)}/{len(R)}',
        "privacy_closed_book": round(100*(1-cb),1), "privacy_open_book": round(100*(1-ob),1),
        "privacy": round(priv,1), "integrity": round(integ_s,1), "coherence": round(coh,1),
        "overall": round(0.5*priv + 0.3*integ_s + 0.2*coh, 1)}
    cbp = sum(x["closed_book"]["p"] for x in R)/len(R); obp = sum(x["open_book"]["p"] for x in R)/len(R)
    summary[pipe].update({"mean_attacker_confidence_closed_book": round(cbp,1), "mean_attacker_confidence_open_book": round(obp,1),
        "disguise_strength": round(100-(cbp+obp)/2,1), "lowest_closed_book_confidence": min(x["closed_book"]["p"] for x in R)})
json.dump({"per_scenario": rows, "summary": summary}, open("results/scores.json","w"), indent=2, ensure_ascii=False)
for r in rows: print(r["scenario"], r["case"], "| CB:", r["closed_book"]["top1_guess"], r["closed_book"]["p"], "| OB:", r["open_book"]["top1_guess"], r["open_book"]["p"], "| coh", r["coherence"])
print(json.dumps(summary, indent=2))
```
**Caveat on `disguise_strength`:** it uses the top-1 guess's `p` as the confidence in the true company. That holds here only because every top-1 guess was correct. The production version should take `p` of the correct guess wherever it appears (0 if absent).

### 4.6 Generation pipeline as a LangGraph **(proposed)**
```text
select_case ──► fetch_data ──► deterministic_anonymize ──► llm_semantic_scrub ──► deterministic_postprocess
     ▲                                                                                      │
     │                                                                                      ▼
     │                                                                              integrity_check ──fail──► llm_semantic_scrub (max 2)
     │                                                                                      │ pass
     │                                                                                      ▼
     │                                                            reid_gate_closed_book (2–3 attacker models, parallel)
     │                                                                                      │
     │                       fail & retries < N ──► llm_semantic_scrub (with attacker clues as feedback)
     └──────────── fail & retries ≥ N (swap case) ◄─┤
                                                    │ pass
                                                    ▼
                                    reid_gate_open_book (optional, slower) ──► store_scenario ──► campaign_master_writes_one_shot
```
State object (proposed, Pydantic):
```python
class Beat(BaseModel):
    story_day: int
    price: float
    headline: str
    facts: list[str]

class Scenario(BaseModel):
    scenario_id: str
    company: str
    sector: str
    industry: str
    timeline_note: str
    beats: list[Beat]
    lesson: str                        # copied from source; never revealed before the debrief

class AttackGuess(BaseModel):
    company: str
    ticker: str
    p: float

class AttackResult(BaseModel):
    model: str
    mode: Literal["closed_book", "open_book"]
    guesses: list[AttackGuess]
    start: str                         # "YYYY-MM"
    key_clues: list[str]
    coherence_1to5: int | None = None
    issues: list[str] = []

class GenState(TypedDict):
    source_case: dict                  # real data: server-side only, never sent to agents/UI
    scenario: Scenario | None
    integrity: dict | None
    attacks: list[AttackResult]
    retries: int
    swapped_cases: list[str]
    status: Literal["pending", "passed", "rejected"]
```
Gate decision (proposed):
```python
def gate_passes(attacks: list[AttackResult], truth: SourceCase, max_conf=30) -> bool:
    for a in attacks:
        if a.mode != "closed_book":
            continue
        hits = [g for g in a.guesses[:3] if is_same_company(g, truth)]
        if hits:                       # true company anywhere in top-3 -> fail
            return False
        if month_within(a.start, truth.beats[0].date, months=3) and max(g.p for g in a.guesses) >= max_conf:
            return False
    return True
```

### 4.7 Backend API **(proposed, FastAPI)**
| Method & path | Purpose | Notes |
|---|---|---|
| `POST /campaigns` | Body: `{interests: string[], budget_eur: number, horizon_months: number}`. Starts generation and returns `{campaign_id, status}` | Async job; the demo returns a pre-generated campaign |
| `GET /campaigns/{id}` | Status, current beat index, scenario **truncated to story today** | The server must never send future beats or source data |
| `GET /campaigns/{id}/chart?until=story_today` | Disguised daily price series up to story today | |
| `POST /campaigns/{id}/buddy` | `{message}` → CommerzBuddy reply | Buddy context = scenario up to story today only |
| `POST /campaigns/{id}/decision` | `{text, action, amount_eur, forecast: {low, high, confidence_pct}}` | Locks the forecast. Validate before the time skip |
| `POST /campaigns/{id}/advance` | Time skip: reveals the next beat and its price | Only after a locked decision |
| `GET /campaigns/{id}/debrief` | Master's debrief + rule of thumb | Run the numeric validator: reject any number not produced by the engine |
| `GET /campaigns/{id}/reveal` | Real company and dates | Only after the final beat |
| `GET /admin/scenarios/{id}/gate` | Integrity report and attacker results (for the demo side panel) | |

### 4.8 Frontend **(proposed, React 18 + TS + Vite)**
- **Screens:** Preferences → Generating (progress plus the anonymization side panel) → Story beat → Investigate (tabs: Buddy chat, Chart, News, Company card) → Decide (free text + forecast range slider + confidence %) → Time skip → Debrief → Reveal → optional €25 savings plan (mock).
- **Phone frame:** mobile-first layout inside a phone frame. The wide screen around it holds side panels: generation, anonymization diff (source hidden, show only *what kinds* of things were scrubbed), and "what Buddy can and cannot see".
- **Types:** mirror §4.2 (`Scenario`, `Beat`) and a `Decision` type `{text, action: 'buy'|'sell'|'hold', amountEur, forecast: {low, high, confidencePct}, lockedAt}`.

---

## 5. What was tested, results, what worked and what did not

### 5.1 Test setup
- **Cases:** 6 from the investing-articles file, 2–4 beats each (Netflix 2023–24 password crackdown; Boeing 2024 crisis; Nvidia 2023–24 AI boom; Meta 2023 "year of efficiency"; Spotify 2023–25 path to profit; Intel 2024 decline).
- **Pipelines:** POC (rules only), PROD v1 (rules + LLM scrub), PROD v2 (one re-id loop turn: industry transplant + per-metric scaling + jittered weeks + ±25% move noise).
- **Attackers:** 18 independent Claude sub-agents, one per blinded scenario. Each was told how the disguise works. Each gave closed-book top-3 guesses + start month, then open-book guesses (≤ 6 web searches), plus a 1–5 coherence rating for a first-time investor.
- **Where it ran:** the sandbox `collabothon2026\sandbox\2026-11-20_anonymization-reid-test\` (72 files: data, src, scenarios, attacks, results, README with a log, REPORT.md).

### 5.2 Results
| Pipeline | Re-identified, closed book (top-1) | Re-identified, open book (top-1) | Mean attacker confidence, closed book | Disguise strength | Integrity | Coherence | **Overall** |
|---|---|---|---|---|---|---|---|
| POC | 6/6 | 6/6 | 96.8% | 2 | 44 | 67 | **27 / 100** |
| PROD v1 | 6/6 | 6/6 | 93.3% | 5 | 98 | 75 | **45 / 100** |
| PROD v2 | 6/6 | 6/6 | 87.2% (lowest 75%) | 10 | 100 | 67 | **43 / 100** |

The start month was correct in 18 of 18 attacks. The privacy score is 0 for all three pipelines. Most attackers used 0–1 web searches.

### 5.3 What worked
- **Deterministic integrity checks.** Production v1 and v2 had 0 real leaks, and price moves stayed exact (v1) or within tolerance (v2).
- **The LLM semantic scrub** removed all names, products, years and distinctive figures that the POC leaked.
- **The re-id gate** flagged every breach and returned actionable clues. Feeding those clues back lowered attacker confidence (96.8 → 87.2) and produced the lowest single value (75%, Spotify v2).
- **The pipeline is fully scriptable and reproducible.** The seeding fix made v2 deterministic.

### 5.4 What did not work
- **Event sequences fingerprint famous stories.** Paraphrasing and moving the story to another industry do not hide them. "Safety halt → strike → 10% cuts plus a delayed next model → strike ends" was still Boeing at a surgical-equipment maker.
- **Timing.** Real gaps between beats line up with quarterly earnings dates. Even jittered weeks were mapped back.
- **Scaling.** Ratios inside one metric family survive it (e.g. subscriber net adds of 1 : 1.5 : 2.2, a guidance-vs-consensus gap of 1.54×).
- **Price shape.** Even with ±25% noise, the path confirms a guess.
- **Moving to another industry hurt realism.** Coherence fell to 3/5 for the battery and medtech versions; attackers noted that medtech does not ground hundreds of units at once and utilities do not "race to buy".
- **Recurring narrative bugs in the scenario text:**
  - a "falls" or "slips" headline while the beat price is above the previous beat (the price was taken before the report);
  - reported next-day crashes that are not visible in the beat prices;
  - scaled amounts that look inconsistent with each other;
  - long gaps with no beat while the price moves a lot.

  The spec should define the price timestamp per beat (close after the event) and allow an extra "context" beat for big unexplained moves.
- **Bias of the setup.** n = 6, the attacker is the same model family as the generator, and prices were approximate.

---

## 6. Open questions and next steps

### 6.1 Open questions
1. **Real prices or disguised prices?** The PDF promises real prices; v2 perturbs moves by ±25%. Decide, and state the choice on the reveal screen.
2. **Re-id gate threshold and attacker panel.** Which models, closed-book only or also open-book, and what confidence threshold (proposed: true company not in top-3 and < 30%)?
3. **Case selection.** What counts as "famous enough to reject"? Candidate pre-filters: market cap, US vs non-US listing, year, news volume, whether a Wikipedia page exists.
4. **Blending.** May we use one obscure company's price path with generic news that explains it? If yes, the reveal must say the news was generalised.
5. **Data access** (open questions from the PDF):
   - Bloomberg and D&B licences at the event;
   - which open news and company-search APIs to use, and their rate limits and terms;
   - Reuters/Bloomberg text licensing (use our own paraphrases plus links, never full text).
6. **Numeric validator.** It rejects numbers in Claude's text that the engine did not produce. Define allowed derived numbers (percentages, rounded values).
7. The **product name** is still open.

### 6.2 Next steps
1. **Scale the test.** A colleague is collecting many more cases (smaller and larger companies, other time periods). Ask for them in the `source_cases.json` schema (§4.1), with real cached `yfinance` prices, plus tags: market cap, country/exchange, year, a rough fame score.
2. **Replace sub-agents with an API batch runner** (e.g. LiteLLM with 2–3 models). Generate once, run closed-book attacks on all, open-book only on those that pass, then compute re-id rate per tag group to find the "safe zone". Hackathon budget: about 20–30 cases, one run. *This run was requested ("запусти там") but interrupted before it started, so nothing was run beyond the 6 cases.*
3. **Turn the findings into a case-selection rule**, a cheap pre-filter before generation. Keep the re-id gate as the final check, with 2–3 retries and then a case swap.
4. **Fix the checker:** exclude numeric fields from the year/month scan, extract banned terms automatically from source facts, and compute confidence for the correct guess at any rank.
5. **Apply the price transform to the full daily series**, so the chart matches the beats and the time-skip reveal.
6. **Demo:** 3–5 scenarios that passed the gate, plus one slide with the statistics: "famous cases are re-identified 100% of the time; our gate filters them out; here is the share that passes".
7. **Implement the guardrails in the runtime agents:** Buddy and master context limited to story today, no security recommendations, numeric validator on every model message.

---

## Appendix A: repository and file locations
- Concept and case file: `C:\Users\desktop\main\projects\hackathons\collabothon2026\docs\`
- Test sandbox: `C:\Users\desktop\main\projects\hackathons\collabothon2026\sandbox\2026-11-20_anonymization-reid-test\`
  - `data/source_cases.json` (real inputs)
  - `src/` (anonymizers, spec, post-processor, checker, scorer, attacker prompt, round-1 feedback)
  - `scenarios/poc|prod|prod_v2/` (outputs + generation notes)
  - `attacks/` (blinded inputs T01–T18, condensed attacker results, `_blind_map.json`)
  - `results/` (integrity reports, `scores.json`), `REPORT.md`, `README.md` (with log)
- Re-run:
  ```bash
  python3 src/poc_anonymizer.py data/source_cases.json scenarios/poc
  python3 src/check_integrity.py scenarios/poc results/integrity_poc.json
  python3 src/check_integrity.py scenarios/prod results/integrity_prod.json
  python3 src/prod_v2_postprocess.py      # after the LLM writes scenarios/prod_v2
  python3 src/score.py
  ```

## Appendix B: case-by-case attacker verdicts
| Case | POC (closed / open book) | PROD v1 | PROD v2 (transplanted to) | Main giveaway in v2 |
|---|---|---|---|---|
| Netflix | 97 / 99 | 93 / 98 | 92 / 93 (online education) | Net-add ratios, exclusive deal, rivals cutting content |
| Boeing | 98 / 99 | 95 / 97 | 95 / 96 (surgical systems) | Safety halt → strike → cuts sequence |
| Nvidia | 97 / 99 | 95 / 97 | 88 / 95 (grid batteries) | Guide/consensus ratio 1.54, ~3.5× in a year |
| Meta | 98 / 99 | 95 / 97 | 88 / 90 (online marketplace) | Efficiency → recovery → first dividend arc |
| Spotify | 96 / 99 | 90 / 95 | 75 / 88 (productivity apps) | Layoffs blamed on capital costs, then first full-year profit |
| Intel | 95 / 99 | 92 / 98 | 85 / 95 (pharma + CDMO) | Manufacturing unit loss + plant buildout + dividend cut + CEO ouster |

Values are the attacker's confidence (%) in its top-1 guess, which was the correct company in all 18 attacks.
