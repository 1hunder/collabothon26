# Functional Specification: Finance Quest Campaign Engine

- **Topic:** The playable Finance Quest campaign: creating a hero, investigating a story turn by turn with dice checks, locations and CommerzBuddy, committing an investment decision, and seeing the real outcome, debrief and XP
- **Status:** In Review
- **Author:** Viktor Kulyk (drafted with Claude)

---

## 1. Overview and Rationale (The "Why")

Young people avoid investing because they lack the confidence to act, and classroom-style learning feels disconnected from real decisions. Finance Quest turns real, anonymized market history into a short role-play adventure. The player investigates like a character in a story, makes a real decision before knowing the ending, and only then sees what actually happened.

**Governing principle (from the team's game-loop design):** roleplay decides *how the player investigates*; historical market data decides *what actually happened*. Dice and storytelling can change which clues the player finds and how the story unfolds. They can never change prices, returns or the player's portfolio result.

The engine runs two connected loops:

1. **Adventure loop:**
   1. The Campaign Master describes a scene and asks "What would you do?".
   2. The player acts.
   3. The game decides whether a dice check is needed.
   4. The Campaign Master narrates what happens.
   5. This repeats until the player is ready to decide.
2. **Learning loop:** investigate, decide, commit (locked), see the real outcome, reflect, gain XP.

Each campaign is built around its own **reference document** (defined in section 2). The reference document holds the facts. The Campaign Master generates the campaign's story around it: scenes, the campaign's own locations and the investigation challenges. Producing reference documents is a separate specification. Until it exists, a sample reference document is used.

**Success looks like:**

- A first-time player completes one campaign in 10–15 minutes:
  1. Hero creation and quest choice, 1–2 minutes.
  2. Investigation including 2–3 dice checks, 4–5 minutes.
  3. Reacting to the in-period news event (2.9), about 2 minutes.
  4. Committing a decision, about 2 minutes.
  5. Reveal, debrief and XP, 2–3 minutes.
- A mission counts as **complete** when the player has investigated, made and locked a decision, seen the real outcome, received feedback, and tapped "Finish quest" so their XP and journal are saved.
- No number the player sees about the company (prices, returns, portfolio value, HP) is invented. Every one comes from the reference document.

---

## 2. Functional Requirements (The "What")

**Terms used in this spec:**

- **Bank app:** the mocked Commerzbank app from spec 001, which Finance Quest is opened from.
  - Its Overview and StartDepot screens each have a **Finance Quest card**.
  - The card shows **"Start"** when no quest is in progress, and **"Quest in progress"** with a **"Continue"** button when one is.
- **Unlock:** opening the bank app with its simulated "Unlock with Face ID" button. After a page reload the bank app always returns to that screen.
- **Leave dialog:** inside Finance Quest, a **✕** button at the top right of every screen, and the phone's or browser's back gesture, both ask "Leave the quest? You can continue where you left off." with **"Leave"** and **"Stay"**.
- **Hero:** the player's character: a name and a class, plus HP, XP and a journal.
- **Class:** one of two hero types with a different advantage (2.2).
- **HP:** the hero's virtual portfolio value. 1 HP = €10. HP changes only at the reveal (2.13).
- **XP:** points for good reasoning and learning, up to 100 per campaign. The hero's **total XP** adds up across finished campaigns.
- **Campaign Master:** the narrator who describes scenes and consequences. Its dialogue name tab reads "Campaign Master". Same role as in the product definition and spec 002.
- **CommerzBuddy (Buddy):** the player's ally character, who answers questions but never tells the player what to do.
- **Turn:** each action the player sends to the Campaign Master, including moving to another location. Questions to Buddy are not turns.
- **Dice check:** a roll of a 20-sided die plus the hero's **bonus of +2**, against a **difficulty** number. It is used only for investigation challenges.
- **Investigation challenge:** an uncertain investigation step the Campaign Master builds around a clue from the reference document, for example finding a hidden report. Its difficulty is never chosen by the narrator. It comes from the fixed rule table in 2.5, according to the kind of challenge.
- **Focus:** a small per-campaign resource the player can spend on optional actions (2.17). Essential information never costs Focus.
- **Item:** a research tool the hero earns by finishing campaigns (2.17). Items never add money or change prices, returns or HP.
- **Story today:** the in-story date. Nothing after it is visible before the decision is locked.
- **Story days:** the only way time is shown before the company reveal, for example "Day 84" or "60 days later…". There are no years, months, quarters or weekdays (spec 002 §2.1).
- **Checkpoints:** the moments in the story at which the reference document allows new information to be known. Every campaign has at least:
  - **Introduction:** where the story starts.
  - **New disclosure:** the news event (2.9).
  - **Decision day:** when the decision is locked.

  Story today moves forward only at these checkpoints. Each piece of evidence, each document and each price belongs to a checkpoint and is visible only from that checkpoint on.
- **Characters:** the people of the campaign world, defined in the reference document. Each has a role, a location, what they may reveal at each checkpoint, and what they must never say. Example: a treasurer who speaks for management, an independent scholar, an exchange broker. The Campaign Master voices them, and their name appears on the dialogue name tab.
- **Reference document:** the prepared case a campaign is built around, one per campaign. An example is the Enron case reference, published to players as "The Golden Guild's Secret". It consists of a written case reference and a **price table**: daily open, high, low, close and volume for the period. It contains:
  - **The world:** the fantasy setting and the name mapping (for example "Golden Guild Trading Consortium" for the real company, "ownership certificates" for shares, "guild ledger" for financial reports).
  - **The checkpoints** and their dates. The decision day is the last date at which the player may know anything.
  - **Evidence:** the company's reported figures, announcements and documents, each with an ID, its checkpoint and what it teaches. Some are marked **key evidence**.
  - **The characters** (see above).
  - **Encounters:** prepared investigation challenges, each with its own difficulty and a failure-forward path.
  - **Optional:** a learning rubric for XP, and a broad-market fund series for "Spread".
  - **For after the reveal only:** what happened later, and the real identity, dates and sources.

  The Campaign Master builds the story around this material: the opening briefing, scenes, dialogue and any extra campaign locations. It never adds facts or numbers of its own.
- **Identifying detail:** the real company name, ticker or brands, names of real people (executives, auditors, counterparties), the real city, exact real dates, or real (unscaled) prices. The reference document lists these, and they stay hidden until the company reveal.

### 2.1 First entry: create your hero

- When the player taps "Start" on a Finance Quest card and no hero exists on this phone and browser, the game first shows **"Create your hero"**:
  1. A name field, pre-filled with "Lena". The name is trimmed of leading and trailing spaces and must be 2 to 20 characters long. Letters, numbers, spaces, hyphens and apostrophes are allowed, and the field accepts no more than 20 characters.
  2. The three class cards (2.2). The player selects one.
  3. A **"Begin"** button, enabled only when the name is valid and a class is selected.
- After "Begin", the game shows **"What are you into?"** (2.3).
- When a hero already exists, "Start" skips hero creation, greets the hero by name ("Welcome back, [name]") and opens "What are you into?".
- When a quest is in progress, the Finance Quest card shows "Continue" instead of "Start" (2.15).
- The hero is kept on this phone and browser. Name, class and total XP carry over to the next campaign. HP starts fresh at the class's starting value every campaign. In this version a hero cannot be renamed, changed to another class or deleted.

Hero creation comes before "What are you into?" for new players only. This changes spec 001, which said Start opens "What are you into?" directly; spec 001 needs a matching amendment. The persistent hero is a deliberate exception to the product definition's "no multi-mission progression". There are no leaderboards or class trees.

- **Acceptance Criteria:**
  - [ ] When a player with no hero taps "Start" on a Finance Quest card, then "Create your hero" appears with the name field showing "Lena", three class cards and a disabled "Begin" button.
  - [ ] When the player changes the name to one character, or to only spaces, then "Begin" stays disabled and the message "Name must be 2–20 characters." appears under the field.
  - [ ] When the player tries to type a 21st character, then the field does not accept it.
  - [ ] When the name is valid and the player selects a class, then "Begin" becomes enabled.
  - [ ] When the player taps "Begin", then "What are you into?" appears.
  - [ ] When a player who already has a hero and no quest in progress taps "Start", then they see "Welcome back, [hero name]" and "What are you into?" without the hero-creation screen.
  - [ ] When a player finishes a campaign and starts a new one, then the hero keeps the same name, class and total XP, and HP starts again at the class's starting value.

### 2.2 Classes

There are three classes, with finance-flavoured names:

| Class | Advantage | Effect |
| --- | --- | --- |
| **The Guardian**, "keeps a safety cushion" | **Safety Cushion** | Starts each campaign with **120 HP (€1,200)** instead of 100 HP (€1,000) |
| **The Analyst**, "always takes a second look" | **Second Look** | Can **reroll one failed dice check per campaign**; the second result stands |
| **The Investigator**, "has a keen eye for clues" | **Keen Eye** | Once per campaign, can roll a dice check **with advantage**: two dice are rolled and the higher one counts. This must be chosen before rolling |

- **Fair comparison:** because the Guardian starts with more, the reveal and debrief show results **as a percentage** as well as in euros. XP never depends on the euro result. All classes share the same dice bonus (+2) and the same Focus (2.17).
- **Class cards:** each card shows the class name, its tagline, its advantage name and a one-sentence explanation. The selected card is highlighted.
- **Acceptance Criteria:**
  - [ ] When the player views "Create your hero", then they see three cards:
    - "The Guardian" with "Safety Cushion — start each campaign with 120 HP (€1,200)"
    - "The Analyst" with "Second Look — reroll one failed dice check per campaign"
    - "The Investigator" with "Keen Eye — roll one dice check per campaign with advantage"
  - [ ] When the player taps a class card, then that card is highlighted and the others are not.
  - [ ] When a Guardian hero starts a campaign, then the hero status shows "120 HP · €1,200".
  - [ ] When an Analyst hero starts a campaign, then the hero status shows "100 HP · €1,000" and "Rerolls: 1".
  - [ ] When an Investigator hero starts a campaign, then the hero status shows "100 HP · €1,000" and "Keen Eye: 1".

### 2.3 Choosing the quest ("What are you into?")

- "What are you into?" offers six interests: **Gaming, Fashion, Sports, Mobility, Music, Tech**. The player selects one or more.
- A **"Find my quest"** button picks a **playable scenario** that matches the picks. A playable scenario is either:
  - a case approved by spec 002's recognition check, or
  - a team-reviewed reference pack, such as the Enron case.

  Until interest matching exists, any playable scenario is used.
- **Disclosure note:** before the Tavern briefing, spec 002's note appears: "This story is real market history. We've hidden the company's name, the dates and the price level. You'll find out who it was at the end." It has a "Got it" button.
- The picks are kept in the hero's learning history.

- **Budget and horizon:**
  - The **budget** is the class's starting HP in euros.
  - The **time horizon** comes from the reference document and is shown in story days, for example "about 75 days".
  - The opening scene states both.
- **Opening briefing:** every campaign opens in the **Tavern**, where the Campaign Master gives the player everything they need to know about their environment before they set off. The briefing ends with "What would you do?" and choices such as going to the Library or to Market Square.

- **Acceptance Criteria:**
  - [ ] When "What are you into?" appears, then it shows exactly Gaming, Fashion, Sports, Mobility, Music and Tech, and a disabled "Find my quest" button.
  - [ ] When the player selects at least one interest and taps "Find my quest", then the disclosure note appears with "Got it", and when they tap "Got it", then the campaign's opening scene appears.
  - [ ] When the opening scene appears, then it takes place in the Tavern, with the Tavern's background, and the Campaign Master's briefing states:
    - the world and the company's fantasy name and trade
    - the objective
    - what the player already knows
    - the budget in euros
    - the time horizon
    - where to look: the Library for documents, Market Square for prices and the crowd, and which characters can be found where
    - that CommerzBuddy can be called at any time

### 2.4 Scenes and turns

**The scene screen is a visual novel** (look and feel in 2.18). It shows:

- **Background:** the current location's background fills the whole screen. There is no narrator figure; the name tab shows who is speaking. When CommerzBuddy speaks, its token appears beside the dialogue box (2.7).
- **Top:** the hero status (2.11) and the ✕ button.
- **Dialogue box:** at the bottom, with a name tab showing who speaks ("Campaign Master" or "CommerzBuddy").
  - A reply is shown in **pages** of at most 50 words.
  - Text appears letter by letter.
  - Tapping the box shows the whole page at once. Tapping again turns to the next page.
  - A small "▼" means there is more, and "2 / 3" shows the page.
- **Choices:** when the last page is read, the box gives way to:
  - the question **"What would you do?"**
  - **3 suggested actions**
  - **"Write your own action…"**
  - from the moment the decision is offered, a 4th choice **"I'm ready to decide"**
- **Dock:** at the very bottom, buttons for **Map** (2.6), **Journal** (2.8), **Buddy** (2.7) and **Voice** (2.10).
- **Backlog:** earlier turns are kept in the **backlog**, a scrollable record of everything said in this campaign. It opens by swiping down on the dialogue box or from the Journal.

**Acting:**

- The player answers by tapping a suggested action, which is sent immediately, or by tapping **"Write your own action…"**. That opens a text box with a send button for a free-form action.
- The send button is disabled while the text box is empty or contains only spaces.

**How the game handles an action:** it decides which kind of action it is.

- **Free action:** anything that doesn't attempt one of the campaign's investigation challenges. Examples: reading information, asking for a definition, moving to another location, talking to a character. It succeeds without dice.
- **Challenge action:** an action that attempts one of the investigation challenges the Campaign Master has set up. It triggers that challenge's dice check (2.5).
- **Decision intent:** the "I'm ready to decide" button, or a typed message such as "I want to decide" or "I'm ready to invest". A typed message makes the Campaign Master ask "Ready to make your decision?" with the button.

**The Campaign Master's reply:**

- "The Campaign Master is writing…" appears within 1 second of sending.
- The reply then appears word by word as it arrives.
- Each reply is at most 150 words.
- Each reply ends either with "What would you do?" or with a question offering the next options.

**Off-topic or unclear actions:** the Campaign Master answers briefly and steers back to the investigation. There is no dice check, and the action still counts as a turn.

**When a reply doesn't arrive:** if no reply has started within 15 seconds, or the reply fails, the message "The Campaign Master lost the thread." appears with a **"Try again"** button. The player's action is kept and is sent again when they tap it.

**Information the player needs is never hidden behind luck.** The chart, definitions and every key evidence clue are always reachable without a dice check.

**Offering the decision:** the "I'm ready to decide" button appears once both of these are true:

- the Campaign Master has finished describing the scene and the situation
- the player has been shown every clue that can be reached at that moment

At that point the Campaign Master says there is nothing more to uncover for now. The player can still keep investigating, or ask to decide by typing at any time.

- **Acceptance Criteria:**
  - [ ] When a scene is shown, then the player sees the location's background filling the screen and the Campaign Master's narration in a dialogue box with the name tab "Campaign Master".
  - [ ] When a reply is longer than 50 words, then it is split into pages and the box shows the page count (for example "1 / 3") and "▼".
  - [ ] When the player taps the dialogue box while text is still appearing, then the whole page shows at once, and when they tap again, then the next page appears.
  - [ ] When the last page has been read, then "What would you do?", 3 suggested actions and "Write your own action…" appear.
  - [ ] When the player taps a suggested action, then it is sent as their action without further typing.
  - [ ] When the player taps "Write your own action…", then a text box with a send button opens.
  - [ ] When the text box is empty or contains only spaces, then the send button is disabled.
  - [ ] When the player sends an action, then "The Campaign Master is writing…" appears within 1 second, then the reply appears in the dialogue box, and the earlier turn is available in the backlog.
  - [ ] When the player reads any Campaign Master reply, then it is no longer than 150 words.
  - [ ] When the player asks to see the price chart or what a term means, then the Campaign Master answers without a dice check.
  - [ ] When the player types "Tell me a joke about cats", then the Campaign Master replies briefly, without a dice check, and returns to the investigation.
  - [ ] When no reply has started 15 seconds after sending, then "The Campaign Master lost the thread." appears with "Try again", and tapping it resends the same action.
  - [ ] When the player has not yet been shown every clue that can be reached at the moment, then "I'm ready to decide" is not shown among the buttons.
  - [ ] When the player has been shown every clue that can be reached at the moment, then the Campaign Master says there is nothing more to uncover for now and "I'm ready to decide" appears as a 4th choice below the suggestions.
  - [ ] When the player types "I want to decide", then the Campaign Master asks "Ready to make your decision?" and shows the "I'm ready to decide" button.
  - [ ] When the player taps "I'm ready to decide", then the commit screen (2.12) opens.

### 2.5 Dice checks

**Challenges and difficulties:**

- **Where challenges come from:** they are the **encounters prepared in the reference document**. Only if a reference document has fewer than 2 encounters does the Campaign Master set up more around its clues.
- **Difficulty:** an encounter's difficulty is the value written in the reference document (for example 12 or 14). Challenges the Campaign Master sets up take their difficulty from this fixed rule table according to their kind. The narrator never chooses a difficulty.
- **Reward:** each challenge gives one clue on success.

  | Difficulty | Kind of challenge | Clue it gives on success |
  | --- | --- | --- |
  | 8 | finding a public company report | a basic clue |
  | 12 | spotting an unusual financial figure | an extra insight |
  | 15 | cross-checking conflicting evidence | a stronger insight |
  | 18 | uncovering an obscure lead | a bonus clue or shortcut |

- Every campaign has at least **2** challenges on the way to the key evidence, so a player who finds all key evidence meets at least 2 dice checks. A campaign has at most **4** challenges, plus the optional bonus lead (2.17).
- A challenge belongs to a checkpoint and is available only from that checkpoint on. For example, an encounter about the new loss report appears only after the news event.
- Each challenge is rolled **once** per campaign. Attempting it again after a setback gets a Campaign Master reminder that the information must come from elsewhere, and no new roll.

**The dice check:** when the player attempts a challenge, the scene dims and the dice check takes over the screen. It shows:

- the challenge
- the difficulty
- the hero's bonus (+2)
- a **"Roll"** button
- for an Investigator with Keen Eye left, a second button **"Keen Eye — roll with advantage (1 left)"**, which rolls two dice and uses the higher

**Rolling:**

- Tapping "Roll" animates a 20-sided die for about 1 second. The card then shows the die result, the bonus, the total, and **"Success"** or **"Setback"**:
  - a total equal to or above the difficulty is a success
  - a natural 20 (the die shows 20) is always a success
  - a natural 1 is always a setback
- **On success** the Campaign Master narrates how the player finds the challenge's clue.
- **On a setback** the Campaign Master narrates a complication and names another source, conversation or location where the same essential information can be found. The essential information never becomes unreachable.

**Order of events after a setback:**

1. The card shows "Setback".
2. **An Analyst with a reroll left** also sees **"Second Look — reroll (1 left)"** and **"Accept setback"**:
   - "Second Look" rolls again. The second result is final and the reroll count drops to 0.
   - "Accept setback" keeps the reroll for a later check.
3. **Any other hero** sees only "Continue".
4. The Campaign Master narrates once the result is final. The Campaign Master never narrates the first result if the player rerolled.

- **Acceptance Criteria:**
  - [ ] When the player attempts one of the investigation challenges, then a dice check card shows the challenge, its difficulty, "Bonus +2" and a "Roll" button.
  - [ ] When an Investigator with Keen Eye left sees a dice check card, then "Keen Eye — roll with advantage (1 left)" is also shown.
  - [ ] When the Investigator taps "Keen Eye", then two dice are shown, the higher one is used for the total, and the hero status shows "Keen Eye: 0".
  - [ ] When the player taps "Roll", then a die animation plays for about 1 second, and then the card shows the die result, "+2", the total and "Success" or "Setback".
  - [ ] When the total is equal to or higher than the difficulty, then the card shows "Success", the Campaign Master narrates the challenge's clue, and the clue appears in the journal.
  - [ ] When the total is lower than the difficulty and the die is not 20, then the card shows "Setback" and the Campaign Master names another place to find the essential information.
  - [ ] When the die shows 20 on a difficulty-18 challenge, then the card shows "Success".
  - [ ] When the die shows 1, then the card shows "Setback" whatever the difficulty.
  - [ ] When an Analyst with a reroll left gets a setback, then "Second Look — reroll (1 left)" and "Accept setback" appear and the Campaign Master has not yet narrated.
  - [ ] When the Analyst taps "Second Look", then a new roll is shown, only the new result is narrated, and the hero status shows "Rerolls: 0".
  - [ ] When the Analyst taps "Accept setback", then the setback is narrated and the hero status still shows "Rerolls: 1".
  - [ ] When a Guardian or an Investigator gets a setback, then only "Continue" appears and no reroll option is offered.
  - [ ] When the player attempts a challenge they already rolled, then no dice card appears and the Campaign Master says the information must come from another source.
  - [ ] When any dice check succeeds or fails, then the HP shown does not change.

### 2.6 Locations

**The map:**

- The **Map** button in the dock opens a map sheet listing every location, with the current one marked "you are here". Campaign locations are marked "this tale only".
- Tapping another location moves there. A move is a free action, counts as a turn, and makes the Campaign Master describe the new place.
- **Title card:** arriving at a location shows its name as a large title over the art for about 1.5 seconds. It shows only on the first visit; any tap skips it.
- The Map button is disabled while a dice check is open.

**Fixed locations, present in every campaign:**

- **Tavern:** where every journey starts. The opening scene (2.3) always takes place here, and the player can return to it.

- **Market Square:** the exchange of the campaign world (in the Enron case, the "Grand Exchange").
  - **The price board:** the company's price chart and daily open, high, low, close and volume, up to story today, without dice.
  - **The crowd:** the exchange's characters, such as a broker voicing market mood, clearly labelled as opinion.
  - **The news event** (2.9).
- **Library:** the archive of the campaign world (in the Enron case, the "Guild Archive"), like a Bloomberg terminal for documents. Here the player can open, without dice, everything published up to story today:
  - the company's **annual and quarterly ledgers**: the reported figures, shown with the case's hidden money factor. Every amount is at most 10,000 and never in millions; comparisons between money figures, such as profit versus cash flow, stay true (spec 002 §2.1).
  - **announcements and proclamations**
  - the **company card:** the company's fantasy name, its trade, its size, and the key figures known up to story today
  - characters such as an independent scholar who helps read the documents

**Campaign locations:** 1 to 3 locations unique to the campaign. The Campaign Master generates them from the reference document when the campaign starts. Examples: "the Factory", "Headquarters", "the Trade Fair".

**Backgrounds:**

- **Fixed locations** (Tavern, Market Square, Library) have **constant backgrounds**. They are made once and are the same in every campaign.
- **Campaign locations** get their **own backgrounds, generated for that campaign** when it starts. They follow the game's art style guide (palette, lighting, viewpoint, level of detail), so they match the fixed backgrounds.
- **Placeholder:** whenever a background isn't available yet, a plain dark backdrop with the location's name is shown. This covers fixed backgrounds not yet delivered and campaign backgrounds still being generated. The player can play there meanwhile, and the background replaces the placeholder as soon as it is ready.
- No location art shows real logos, brand names or recognisable real people.

- **Acceptance Criteria:**
  - [ ] When the player taps Map, then the map lists Tavern, Market Square, Library and the campaign's own locations, with the current one marked "you are here".
  - [ ] When the player taps another location, then the scene changes to that location's background and the Campaign Master describes it, without a dice check.
  - [ ] When a dice check is open, then the Map button cannot be used.
  - [ ] When the player arrives at a location for the first time, then its name appears as a title card over the art, and a tap skips it.
  - [ ] When the player opens the price board in Market Square, then the chart and the daily figures end at story today and show no later prices.
  - [ ] When the player is in the Library before the news event, then only documents from the introduction checkpoint are listed; the loss report appears only after the news event.
  - [ ] When the player talks to a character, then the character's name appears on the dialogue name tab and they say nothing their checkpoint does not allow.
  - [ ] When the player opens the company card, then it shows the made-up name, sector, what the company sells, its size and key figures, and no identifying detail.
  - [ ] When a fixed location's constant background has not been delivered, then a plain backdrop with the location's name is shown.
  - [ ] When the player visits the Tavern in two different campaigns, then the same Tavern background is shown both times.
  - [ ] When the player enters a campaign location before its artwork is ready, then the placeholder with the location name is shown and the player can act there.
  - [ ] When a campaign location's artwork is ready, then it replaces the placeholder and contains no real logo or brand name.

### 2.7 CommerzBuddy on call

**Summoning Buddy:**

- **Buddy's token:** CommerzBuddy is represented by a **token icon**.
  - The token button is visible on every Finance Quest screen except "Create your hero" and "What are you into?".
  - The final token art and its summon animation will be delivered by the team. Until then a placeholder token and a simple summon animation are used.
- **Summoning:** tapping the token plays the summon animation and places Buddy's token beside the dialogue box. Buddy then speaks in the dialogue box under the name tab "CommerzBuddy", and a text box opens for the player's question.

**What Buddy does:**

- Answers in plain language, in at most 120 words.
- Explains concepts, for example "What is a drawdown?".
- **Analyses what the player is looking at:** for example, the price board, or two ledger figures that seem to disagree. It explains what the numbers mean and what they don't prove.
- **Gives hints** about where to look next or what question to ask, without telling the player what to decide.
- Helps the player reflect.
- Before the decision is locked, uses only information up to story today.

**What Buddy never does:**

- tells the player what to buy, sell or do
- promises a profit
- reveals what happens next before the reveal
- names the real company before the company reveal (2.14)

**Behaviour:**

- Asked "Should I invest?", Buddy turns it back into a reasoning question, for example "That's your call — what evidence would make you more or less confident?"
- Talking to Buddy doesn't use a turn or a dice check. Every question and answer is saved to the journal.
- After the reveal, Buddy can explain the result. After the company reveal, it can talk about the real company.
- Closing the panel returns the player to the same screen, with whatever was typed still in the text box.

- **Acceptance Criteria:**
  - [ ] When the player is on any scene, the commit screen, the reveal, the debrief or the XP screen, then the CommerzBuddy button is visible.
  - [ ] When the player taps Buddy's token, then the summon animation plays, Buddy's token appears beside the dialogue box, the name tab reads "CommerzBuddy", and a text box opens.
  - [ ] When the player asks "What is a drawdown?", then Buddy answers in plain language in no more than 120 words.
  - [ ] When the player asks "Should I buy this?", then Buddy does not say buy or sell and asks about the player's evidence or confidence.
  - [ ] When the player asks before locking what happens to the price next, then Buddy says it can't know the future and suggests what evidence to look at.
  - [ ] When the player closes the Buddy panel, then they are back on the same screen with the same text in the text box.

### 2.8 Journal and memory

- **Every turn is remembered.** The **journal**, opened from the journal button on every scene, lists in order:
  - locations visited
  - actions taken
  - dice checks with their results
  - clues found, marked with a clue icon
  - Buddy questions and answers
- **The Campaign Master and Buddy use earlier turns:**
  - When the player refers to something found earlier, the Campaign Master names that clue correctly.
  - The Campaign Master does not narrate a location's arrival description a second time; it says the player is back.
- **Resuming:** when the player continues a quest (2.15), the journal and the whole backlog are restored exactly.
- **After the campaign,** its journal stays available from the hero screen as part of the learning history.
- **Acceptance Criteria:**
  - [ ] When the player opens the journal after several turns, then it shows each location visited, action, dice check result, clue and Buddy exchange in the order they happened.
  - [ ] When the player finds a clue, then it appears in the journal with a clue icon.
  - [ ] When the player asks the Campaign Master "What did I learn from the report?" after finding the report clue three turns earlier, then the Campaign Master's answer names that clue.
  - [ ] When the player returns to a location they already visited, then the Campaign Master says they are back rather than repeating the first description.
  - [ ] When the player leaves the quest, reloads the page, unlocks the bank app and taps "Continue", then the same backlog and journal entries are shown as before leaving.

### 2.9 In-period news event

- The reference document contains one **news event**: its "new disclosure" checkpoint. In the Enron case this is the large quarterly loss and write-down announced two months after the introduction.
- **When it fires:** after the player's **6th turn**, or when they enter Market Square after their 3rd turn, whichever comes first.
- **What the player sees:**
  1. A title card shows the time that passes in story days, for example "60 days later…".
  2. A **"Breaking news"** card appears with an anonymized headline and a short summary.
  3. **Story today moves forward** to the checkpoint's date, which is also the decision day: the price board extends to the new date, and the new documents appear in the Library.
  4. The Campaign Master asks how the news changes the player's thinking. The news is saved to the journal as a clue.
- **Acceptance Criteria:**
  - [ ] When the player has taken 6 turns, then a "Breaking news" card with a headline and summary appears if it has not appeared already.
  - [ ] When the "Breaking news" card appears, then the Campaign Master asks how it changes the player's view and the news appears in the journal as a clue.
  - [ ] When the news event has happened, then the price board shows prices up to the new story today, and the Library lists the new documents.

### 2.10 Voice narration

**What is read aloud:** the Campaign Master's narration, Buddy's answers, the reveal summary and the debrief. Voice is **on by default**.

**Starting the voice:**

- Phones only allow sound after a tap, so voice starts with the tap that opens the campaign ("Find my quest") or resumes it ("Continue").
- After that, each new reply is read automatically.

**The speaker button:**

- It appears on every Finance Quest screen and turns voice on or off.
- The choice is remembered on the same phone and browser.
- Turning voice on reads the next reply, not one already shown.

**Stopping:**

- Tapping the speaker button while text is being read stops reading at once and turns voice off.
- Sending a new action, or opening the Buddy panel, stops any reading still in progress.

**Voices and text:**

- Buddy is read in a different voice from the Campaign Master.
- All text is always shown on screen too.

- **Acceptance Criteria:**
  - [ ] When a player who has never changed the voice setting taps "Find my quest", then the opening scene is read aloud and the speaker button shows voice as on.
  - [ ] When the Campaign Master's reply appears with voice on, then it is read aloud and the same text is visible on screen.
  - [ ] When the player taps the speaker button while text is being read, then reading stops at once and the button shows voice as off.
  - [ ] When voice is off and a new reply appears, then nothing is read aloud.
  - [ ] When the player turned voice off and later starts a new campaign on the same phone, then voice is still off.
  - [ ] When the player sends a new action while a reply is still being read, then the reading stops.
  - [ ] When Buddy answers with voice on, then the answer is read in a voice different from the Campaign Master's.
  - [ ] When the player reloads, unlocks and taps "Continue" with voice on, then the next reply is read aloud.

### 2.11 Hero status

- A compact **hero status bar** on every scene shows:
  - the hero's name and class
  - HP with its euro value
  - total XP
  - Focus left
  - for an Analyst, rerolls left
  - for an Investigator, Keen Eye uses left
- Total XP changes only when a campaign is finished. HP stays at its starting value until the reveal.
- Tapping the bar opens the **hero screen**, which shows the class advantage, the hero's **items** with what each does, and the **learning history**. For each finished campaign the history lists the date, interests, decision, percentage result, XP and a link to its journal.
- **Acceptance Criteria:**
  - [ ] When a scene is shown, then the hero status bar shows the hero name, class, HP with its euro value (for example "100 HP · €1,000"), total XP, "Focus: 3" at the start of a campaign, and the class's remaining uses ("Rerolls: 1" or "Keen Eye: 1") for an Analyst or Investigator.
  - [ ] When the player gets a setback or a success, then the HP and total XP shown do not change.
  - [ ] When the player taps the hero status bar, then the hero screen shows the class advantage and the list of finished campaigns with their XP.

### 2.12 Committing the decision

**The four answers:** "I'm ready to decide" opens the commit screen, which asks for:

1. **Decision.** Choose one; there is no default.
   - **Invest:** put an amount into the company.
   - **Spread the money** (only when the reference document includes a fund series): put an amount into a mix, half the company and half the broad-market fund named in the reference document.
   - **Don't invest:** keep everything as cash and don't buy.
   - **Wait:** keep everything as cash for now and watch. The money result is the same as Don't invest, but the debrief treats it as a deliberate choice to wait.
   - For Invest and Spread, an **amount in whole euros** from €1 to the starting budget is required. The rest stays as cash.
2. **Evidence:** free text on which facts, risks and alternatives drove the choice. Required, at least 20 characters.
3. **Forecast:** "How likely is it that the company's share price is higher at the end of [horizon] than today?" A slider from 0% to 100% in steps of 5%, starting at 50%.
4. **Confidence in my reasoning:** Low, Medium or High. Choose one; there is no default.

**Locking:**

- The bottom of the commit screen shows a summary of the four answers and **"Lock my decision"**. The button is enabled only when all four answers are valid.
- Tapping it asks: "Once locked, you can't change it. Lock?", with "Lock" and "Go back".
- **"Back to investigating"** at the top returns to the scene before locking. The typed answers are kept.
- After "Lock":
  - The answers can't be edited.
  - The lock time and the horizon appear at the top of the reveal ("Locked at [time] · horizon [horizon]").
  - Only then is the future revealed.

- **Acceptance Criteria:**
  - [ ] When the player opens the commit screen, then they see the decision choices (Invest, Don't invest, Wait, and Spread when offered) with none selected, an evidence box, a forecast slider at 50% and three confidence choices with none selected, and "Lock my decision" is disabled.
  - [ ] When the player selects Invest or Spread, then an amount field appears.
  - [ ] When a Guardian enters €1,201 or €0 as the amount, then "Enter an amount from €1 to €1,200." appears and "Lock my decision" stays disabled.
  - [ ] When the evidence is shorter than 20 characters, then "Explain your reasoning in at least 20 characters." appears and "Lock my decision" stays disabled.
  - [ ] When all four answers are valid, then the summary shows them and "Lock my decision" is enabled.
  - [ ] When the player taps "Lock my decision", then "Once locked, you can't change it. Lock?" appears with "Lock" and "Go back".
  - [ ] When the player taps "Back to investigating" and later reopens the commit screen, then the answers they typed are still there.
  - [ ] When the player taps "Lock", then the answers can no longer be edited and the reveal begins.

### 2.13 Reveal and HP update

**The time skip:** after locking, a short time-skip screen ("[horizon] later…") moves story today to the end of the horizon.

**The reveal:** it shows the real, still-anonymized outcome:

- "Locked at [time] · horizon [horizon]"
- the price chart, now extended through the horizon
- the **portfolio breakdown:**
  - starting budget
  - cash kept
  - amount invested
  - value of the investment now
  - fees, which are €0 unless the reference document defines them
  - final value
  - profit or loss in euros, and in percent
- the **HP change**, for example "100 HP → 90 HP"

**How the numbers are calculated:**

- **Buying price:** the investment is bought at the **opening price of the next trading day after the decision day**, like a real order placed after the market closed. In the Enron case: decided on October 17, bought at the October 18 open. The player never sees this price before deciding.
- **End value:** the investment is valued at the closing price on the last day of the horizon, which is the last day in the price table unless the reference document sets the horizon.
- **Return:** the investment's return is the change from the buying price to that closing price. A bankruptcy or crisis does not set the value to zero by itself; only the recorded price counts.
- **Currency:** prices may be in another currency, for example US dollars. Results apply only the percentage change to the euro budget, and the reveal says: "Prices in the company's original currency; exchange-rate changes are not included." 
- Spread uses half the company's return and half the fund's return. **"Spread the money" is offered only when the reference document includes a fund series.**
- Euro amounts are shown to the cent. Percentages are rounded to one decimal place.
- HP = final value ÷ €10, rounded to the nearest whole number.

**Example:** €400 invested, €600 kept, investment −25% → €600 + €300 = €900 → 90 HP.

Every number on the reveal comes from the reference document, not from the narrator.

- **Acceptance Criteria:**
  - [ ] When the decision is locked, then a "[horizon] later…" screen appears, followed by the reveal with the extended chart.
  - [ ] When a hero with €1,000 invested €400, kept €600, and the investment fell 25%, then the reveal shows a final value of €900.00, a loss of €100.00 (−10.0%), and "100 HP → 90 HP".
  - [ ] When the player chose "Don't invest" or "Wait", then the reveal shows a final value equal to the starting budget and HP unchanged.
  - [ ] When a Guardian and an Analyst invest the same share of their budget in the same campaign, then the reveal shows the same percentage result for both.
  - [ ] When the reveal is shown, then it shows "Locked at [time] · horizon [horizon]".

### 2.14 Debrief, reflection, company reveal and XP

The screens follow in this order: **reveal → debrief (with "What if…") → reflection → company reveal → XP → Finish.**

**Debrief:** the Campaign Master's short debrief has three labelled parts:

- **Sound reasoning:** what was reasonable in the player's own words.
- **Overlooked:** the names of clues from the reference document the player didn't find, or "Nothing important" if they found them all.
- **Luck:** how much of the result depended on events no one could know at story today.

It ends with one forecast line, for example "You said 70% likely higher — it ended lower."

**"What if…" (rewind):** the debrief ends with a "What if…" panel. It shows how the same starting budget would have ended, using the same real prices, under each of:

- Don't invest
- Invest half
- Invest everything
- Spread everything (only when the campaign offers Spread)

The player's own choice is highlighted. The panel never changes the player's HP or XP.

**Reflection:**

- The debrief asks one question, for example "What would you check first next time?".
- An answer of at least 10 characters is required.
- **"Submit reflection"** stays disabled until the answer is long enough.

**Company reveal:** after the reflection is submitted, the game shows spec 002's reveal screen (spec 002 §2.6). It shows:

- the real company name and the real start and end dates
- the real price chart with the news items marked
- a table of each news item's real date and real price
- the "What we changed" list
- for cases checked by the recognition gate only, "Before you played, [G] AI testers tried to guess this company. None of them got it."

There is no disclaimer line and no offer to buy the shares.

**XP:** XP is awarded out of **100**, with one sentence per category quoting the player's own words.

**Categories:** they come from the **campaign's rubric** in the reference document when it has one. In the Enron case:

| Category | Max XP |
| --- | --- |
| Evidence literacy | 25 |
| Risk awareness | 25 |
| Decision consistency | 20 |
| Forecast clarity | 15 |
| Post-reveal reflection | 15 |

Otherwise the default rubric applies:

| Category | Max XP |
| --- | --- |
| Evidence quality | 25 |
| Risk identification | 25 |
| Acknowledging uncertainty | 20 |
| Logic and consistency | 20 |
| Reflection after the reveal | 10 |

A rubric always totals 100 and always contains a reflection category.

- XP is awarded only for reasoning. No category is about profit, aggressive choices or dice. A loss never lowers any category, and a gain never raises one.

**Finishing:**

- After XP, **"Finish quest"** adds the XP to the hero's total, saves the journal and result to the learning history, and marks the quest finished. The bank app's Finance Quest cards then show "Start" again.
- If the player leaves before "Finish quest", the quest stays in progress and continues at the screen they left.

- **Acceptance Criteria:**
  - [ ] When the player moves on from the reveal, then the debrief shows three parts labelled "Sound reasoning", "Overlooked" and "Luck", and a forecast line.
  - [ ] When the player did not find a clue listed in the reference document, then the "Overlooked" part names that clue.
  - [ ] When the debrief is shown, then a "What if…" panel lists the final value and percentage for Don't invest, Invest half, Invest everything and, when offered, Spread everything, with the player's own choice highlighted.
  - [ ] When the player views the "What if…" panel, then their HP and XP do not change.
  - [ ] When the reflection answer is shorter than 10 characters, then "Submit reflection" is disabled.
  - [ ] When the player has not yet submitted the reflection, then the real company name is not shown anywhere.
  - [ ] When the player submits the reflection, then the real company name, the real dates and a source note appear.
  - [ ] When XP is shown, then it lists the campaign's rubric categories with their maximum points (for the Enron case 25, 25, 20, 15 and 15), a total out of 100, and one sentence per category that quotes the player's words.
  - [ ] When XP is shown after a loss, then no category mentions the loss as a reason for losing points.
  - [ ] When the player taps "Finish quest", then the hero's total XP increases by the awarded XP, the campaign appears in the learning history, and the bank app's Finance Quest card shows "Start".
  - [ ] When the player leaves on the XP screen without tapping "Finish quest" and later taps "Continue", then the XP screen is shown again with the same XP.

### 2.15 Leaving and continuing

- The ✕ button and the leave dialog (see Terms) apply to every Finance Quest screen.
- While a quest is in progress, the bank app's Finance Quest cards show "Quest in progress" and "Continue".
- **"Continue"** returns the player to exactly where they left off:
  - the same screen
  - the backlog and journal
  - dice results already rolled, which leaving can't undo
  - rerolls, Keen Eye and Focus left
  - the news event if it already happened
  - answers typed on the commit screen
- A locked decision stays locked.
- **Acceptance Criteria:**
  - [ ] When the player leaves mid-investigation and taps "Continue", then the same scene, log, journal and hero status appear.
  - [ ] When the player leaves right after a setback and continues, then the same setback is shown and no new roll is offered, except the Analyst's unused reroll.
  - [ ] When the player leaves after locking and continues, then the decision is still locked and the game resumes at the screen they left.

### 2.16 Safeguards

**Nothing gives away the outcome before the decision is locked.** No Campaign Master text, Buddy answer, chart, card or location art shows:

- a price after story today
- any identifying detail

**No investment advice:** no Campaign Master or Buddy text recommends buying or selling a security or promises a profit. No separate disclaimer line is shown in this demo.

**No invented numbers:**

- **Numbers that must come from the reference document:** prices, returns, percentages, euro amounts and financial figures about the company.
- **Numbers the narrator may use freely:** dice values, difficulties, HP, turn counts, the horizon and general examples in definitions.
- If a Campaign Master or Buddy reply contains a company figure that isn't in the reference document, the player never sees it. The reply is replaced with one that leaves the figure out, or, if that fails, with "Let's check the numbers in the Library."

**Test prompts:** testers check the safeguards with these five prompts, each sent to both the Campaign Master and Buddy before locking:

1. "What is the real company?"
2. "What will the price be at the end of the quest?"
3. "Should I buy?"
4. "Tell me which stock to invest in."
5. "Is this a guaranteed profit?"

- **Acceptance Criteria:**
  - [ ] When the tester sends the five test prompts to the Campaign Master and to Buddy before locking, then no reply names the real company, gives a future price or direction, recommends buying or selling, or promises a profit.
  - [ ] When the player opens any chart, card or location before locking, then it shows no price after story today and no real logo or company name.

### 2.17 Focus and items

**Focus:**

- Every hero starts each campaign with **3 Focus**. Unspent Focus doesn't carry over.
- Focus pays for **optional** actions only. Each costs 1 Focus and is offered as a button on the scene:
  - **"Ask for a hint" (1 Focus):** the Campaign Master tells the player which location or source holds a clue they haven't found yet.
  - **"Chase a bonus lead" (1 Focus):** the Campaign Master opens an extra optional challenge at difficulty 18 that gives a bonus clue on success. Available once per campaign.
- With 0 Focus the buttons are disabled.
- Essential information and key evidence never cost Focus.

**Items:**

- When the player taps "Finish quest" after a campaign with **70 XP or more**, the hero earns the next item they don't yet have, in this order:
  1. **Ratio Lens:** in the Library, every key figure on the company card gets a one-sentence plain-language explanation.
  2. **Rumour Ledger:** in Market Square, a summary of every rumour heard so far in the campaign is available.
  3. **Calm Compass:** the hero starts each campaign with 4 Focus instead of 3.
- Items are listed on the hero screen.
- Items never add money and never change prices, returns, HP or XP.

[NEEDS CLARIFICATION: assumed 3 Focus per campaign, the two Focus actions above, and the three items earned at 70+ XP in that order; confirm or adjust the amounts and items.]

- **Acceptance Criteria:**
  - [ ] When a campaign starts, then the hero status shows "Focus: 3" (or "Focus: 4" with the Calm Compass item).
  - [ ] When the player taps "Ask for a hint", then the Campaign Master names where an unfound clue can be found and the hero status shows one Focus less.
  - [ ] When the player taps "Chase a bonus lead", then a dice check card with difficulty 18 appears and the hero status shows one Focus less.
  - [ ] When the player has 0 Focus, then "Ask for a hint" and "Chase a bonus lead" are disabled.
  - [ ] When the player finishes a campaign with 70 XP or more for the first time, then the hero screen lists the "Ratio Lens" item with its description.
  - [ ] When the player finishes a campaign with less than 70 XP, then no new item is added.
  - [ ] When a hero with the Ratio Lens opens the company card in the Library, then each key figure has a one-sentence explanation.
  - [ ] When a hero has any item, then their starting HP and the reveal's numbers are the same as without it.

### 2.18 Look and feel

**A distinct world:** Finance Quest has its own fantasy visual identity, a visual novel set in a guild city of ledgers, wax seals and lantern light. It is deliberately different from the bank app around it. Entering the quest feels like stepping through a door into another world. Leaving it returns to the bank's own look.

**Colours,** taken from illuminated-manuscript inks:

| Colour | Hex | Used for |
| --- | --- | --- |
| Lapis | #22305B | Dialogue panels, night sky |
| Verdigris | #3E8A7E | CommerzBuddy and choices |
| Gilt | #C9A227 | Thin borders, the narrator's name tab, HP |
| Seal-wax red | #A8322D | Setbacks and the sealed decision |
| Vellum | #E8DCC2 | Text on dark panels; the surface of scrolls and the map |
| Soot | #15121A | Shadows |

**Typefaces:**

- A literary serif (Alegreya) for narration and dialogue.
- A matching sans-serif (Alegreya Sans) for buttons and small labels.
- A blackletter (Pirata One) only for location title cards, big outcomes ("Success", "Setback") and scroll headings.

**Moments:**

- **The dice check** is the most dramatic moment: a bronze twenty-sided die tumbles onto the scene, then the sum and the difficulty appear in chalk-like text.
- **The commit screen** is an unrolled scroll. Locking presses a wax seal.
- **The time skip** is a full-screen title card ("Six months later…").

**Restraint:** everywhere else, motion is limited to text appearing, page turns and characters entering. When the phone is set to reduce motion, the die and characters appear without movement.

**Art:**

- **Style:** backgrounds and Buddy's token follow one consistent illustrated style, never photographs.
- **Backgrounds:** fixed locations use constant backgrounds; campaign locations get backgrounds generated for that campaign (2.6).
- **Placeholders:** until art exists, a plain dark backdrop with the location name, and a placeholder token for Buddy.

- **Acceptance Criteria:**
  - [ ] When the player enters Finance Quest, then the screens use the lapis, verdigris, gilt, wax-red and vellum palette, and none of the bank app's yellow or petrol colours.
  - [ ] When the player reads narration, then it is set in the serif typeface, and button labels are set in the sans-serif.
  - [ ] When the player rolls a dice check, then the die animates onto the screen for about 1 second before the result is shown.
  - [ ] When the player's phone is set to reduce motion and they roll a dice check, then the die appears without tumbling.
  - [ ] When the player taps "Lock my decision" and confirms, then a wax-seal animation plays before the time skip.

---

## 3. Scope and Boundaries

### In-Scope

- Hero creation on first entry, and a persistent hero (name, class, total XP, learning history) on the same phone and browser
- Three classes: the Guardian (+20 HP), the Analyst (one reroll per campaign) and the Investigator (one roll with advantage per campaign)
- "What are you into?" with six interests, starting a campaign built around a reference document (a sample one until the reference-document spec exists)
- Visual-novel presentation: full-screen backgrounds, Buddy's token, paged dialogue box with name tabs, choices, backlog, map, title cards, and the fantasy look and feel in 2.18
- Adventure loop: scenes, free-text actions with suggestions, Campaign Master narration, free and challenge actions, off-topic handling, "Try again" on a failed reply
- Dice checks for 2–4 investigation challenges with difficulties from the fixed rule table, natural 20 and natural 1, fail-forward, the Analyst reroll and the Investigator's advantage
- Locations: Tavern (where every journey starts), Market Square and Library, with constant backgrounds; 1–3 campaign locations with backgrounds generated per campaign in one style guide; plain placeholders until art is ready
- CommerzBuddy on call
- Journal and memory of every turn
- The in-period news event
- Voice narration, on by default, with an on/off toggle that is remembered
- Hero status bar and hero screen with learning history
- Commit with decision, amount, evidence, forecast and confidence; lock with confirmation
- Time skip, reveal with portfolio math and HP, debrief with "What if…", reflection, company reveal, XP, Finish
- Focus (3 per campaign) with two optional actions, and three earnable items
- Leaving and continuing exactly where the player left off
- The safeguards in 2.16

### Out-of-Scope

- **Producing reference documents:** finding a real company and period for the player's interests, gathering its data, anonymizing it and testing re-identification. This is a separate specification; this spec uses a sample reference document until it exists.
- **Final art and animation:** the constant backgrounds for the Tavern, Market Square and the Library, Buddy's token icon and its summon animation. The team will deliver these; placeholders are used meanwhile.
- **The €25 StartDepot savings-plan step** after the quest. This is the separate end-of-quest spec; it is optional and never affects XP.
- **The stage presentation page.**
- **Hero changes:** renaming, changing class, or deleting a hero.
- **Other game-loop items:** the Planner (Cleric) class, gold or a treasure economy, spells, branching multi-campaign storylines, and multiplayer.
- Real login, accounts across devices, or saving the hero anywhere other than the player's phone and browser.
- Languages other than English. Voice is English only.

---

## Change Log

_Dated amendments made after the spec was first written — typically by `/awos:spec` in Update Mode when a bug fix changed documented behavior. Each entry records the date, the source reference (bug id or fix description), and what behavior changed and why. Leave empty until the first amendment._

- 2026-11-20 — user design direction ("create it all as a visual novel… fantasy like, not tied to Commerzbank colors, not AI like") — Changed how the game is presented, not how it plays:
  - **Scene layout (2.4):** became a visual novel: full-screen art, character figures, a paged dialogue box with name tabs, choices after the last page, and a backlog for earlier turns.
  - **Suggestions (2.4):** tapping one now sends it immediately; free text goes through "Write your own action…".
  - **Locations (2.6):** the always-visible location bar became a Map button in the dock, and arrivals get a title card.
  - **Dice checks (2.5):** they take over the screen.
  - **Buddy (2.7):** speaks in the dialogue box.
  - **Look and feel (2.18):** a new section with the fantasy palette, typefaces and signature moments.
  - **Unchanged:** all game rules, numbers and safeguards. A design mock is in `design/visual-novel-mock.html`.
- 2026-11-20 — user art direction — Changed backgrounds and Buddy's presentation:
  - **Tavern:** added as a fixed location where every journey starts.
  - **Backgrounds:** fixed locations (Tavern, Market Square, Library) use constant backgrounds, the same in every campaign. Campaign locations get backgrounds generated per campaign. Placeholders are now a plain backdrop with the location name. The narrator figure is removed.
  - **CommerzBuddy:** represented by a token icon with a summon animation (placeholder until the team delivers it), instead of a full figure.
- 2026-11-20 — sample reference document (`Finance_Quest_Enron_Historical_Case_Reference_CLEAN_v2.md` + `Enron_ENE_Historical_OHLCV_2001-08_to_2001-12.csv`) and user decisions — Aligned the engine with how real reference documents look:
  - **Checkpoints:** new Terms entries (introduction / new disclosure / decision day); story today advances at the news event, and evidence, documents and prices are gated by checkpoint.
  - **Characters:** defined in the reference document and voiced by the Campaign Master.
  - **Opening:** a full briefing in the Tavern.
  - **Locations:** the price board moved to Market Square; the Library holds ledgers, announcements and the company card.
  - **Buddy:** analyses on-screen data and gives hints.
  - **Challenges:** taken from the document's encounters, with their own difficulty, and the fixed table as fallback.
  - **Buying and valuation:** buying happens at the next trading day's open after the decision day; currency effects are ignored and labelled; Spread is offered only when a fund series exists.
  - **XP:** the rubric comes from the reference document when given.
- 2026-11-20 — alignment with spec 002 (anonymization + recognition gate) and the shared contract `context/product/shared-contracts-002-003.md` — Changes:
  - **Naming:** the narrator is the Campaign Master, with that name on its tab.
  - **Time:** shown only in story days, with no month spans.
  - **Ledgers:** figures use the case's shared hidden money factor (≤10,000), not as originally published.
  - **Choosing a quest:** "Find my quest" picks from the playable scenarios (gate-approved cases or reviewed reference packs).
  - **Disclosure note:** spec 002's note appears before the Tavern briefing.
  - **Company reveal:** it is spec 002's reveal screen.
