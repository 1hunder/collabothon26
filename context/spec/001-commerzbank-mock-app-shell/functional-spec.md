# Functional Specification: Mocked Commerzbank Mobile App Shell

- **Topic:** A demo look-alike of the Commerzbank mobile banking app that serves as the starting screen from which players open Finance Quest
- **Status:** In Review
- **Author:** Viktor Kulyk (drafted with Claude)

---

## 1. Overview and Rationale (The "Why")

Finance Quest is meant to live inside the bank's own app, not as a separate game. The challenge argues that young people lack the confidence to act, not information, so the practice has to feel close to the place where a real first investment would happen. A believable copy of the Commerzbank mobile app gives the jury and test players that feeling: they "open their banking app", see their (fictional) accounts and a StartDepot with nothing in it yet, and start their first quest from there.

The shell is a starting point only. It needs enough of the real app's look and structure to be instantly recognisable as Commerzbank, one clear way into Finance Quest, and a way back. Everything else in the banking app can be visibly present but unavailable.

**Success looks like:**

- When someone who has not seen the demo before is shown the Overview for 5 seconds and asked "Which bank's app is this?", they answer "Commerzbank".
- Someone who has not seen the demo before opens Finance Quest from the Overview in no more than 2 taps, without being told where to tap.
- Nobody mistakes the demo for a real banking app: it never asks for real credentials or shows real customer data, and unsupported features say "Not available in this demo."

---

## 2. Functional Requirements (The "What")

**Terms used in this spec:**

- **Shell:** the demo banking app described here: everything the player sees before entering Finance Quest and after leaving it.
- **Finance Quest:** the investing-education game the shell leads into. Its first screen is the interest picker, titled **"What are you into?"**. That screen and the rest of the game are defined in separate specifications.
- **Demo persona:** the fictional customer whose accounts the shell shows.
- **Demo address:** the web address at which the demo is opened in a phone or laptop browser.
- **Tappable element:** any button, card, list entry, quick action or tab. Greetings, balances, the logo and plain text lines (such as product facts) are not tappable.
- **"Not available" message:** the short message shown when the player taps a tappable element that the demo doesn't support (defined in 2.7).

### 2.1 Opening the demo

- Opening the demo address shows a welcome screen that mimics the real app's biometric unlock:
  - the bank's logo, brand colours and the greeting **"Welcome back, Lena"**
  - a single **"Unlock with Face ID"** button with a face-scan icon
- Tapping the button plays a **simulated Face ID animation**: a face-scan outline animates for about 1.5 seconds and turns into a check mark. The Overview then appears. No camera is used and nothing about the player is scanned.
- There are **no input fields**: no customer number, PIN or password.
- Reloading the page, or opening the demo address again, always starts at the welcome screen.
  - **Acceptance Criteria:**
    - [ ] When the player opens the demo address on a phone, then they see a welcome screen with the bank's logo, the greeting "Welcome back, Lena" and a single button labelled "Unlock with Face ID".
    - [ ] When the player looks at the welcome screen, then there is no field asking for a customer number, PIN, password or any other personal detail.
    - [ ] When the player taps "Unlock with Face ID", then a face-scan animation plays for about 1.5 seconds, ends in a check mark, and the Overview screen appears.
    - [ ] When the player taps "Unlock with Face ID", then the phone does not ask for camera access and does not trigger its real Face ID.
    - [ ] When the player reloads the page while on any shell screen, then the welcome screen appears.

### 2.2 Demo labelling

- The shell shows **no demo label or strip**. The screens look like the real app from the top edge down. The demo stays clearly fictional because:
  - the unlock is simulated and asks for no credentials (2.1)
  - all data is fixed and fictional, including the "DE00 0000…" account number (2.10)
  - unsupported features say "Not available in this demo." (2.8)
  - **Acceptance Criteria:**
    - [ ] When the player views the welcome screen, the Overview, the StartDepot screen or the first Finance Quest screen, then the text "Demo — Collabothon 2026" does not appear and the top bar or screen content starts at the top of the screen.

### 2.3 Top bar

- Every shell screen except the welcome screen has a **top bar** at the top of the screen.
  - **Overview:** the top bar shows the bank's logo on the left.
  - **Other screens:** it shows the screen's title, for example "Investments" or "StartDepot".
  - The StartDepot screen also has a **back arrow** at the left of the top bar. No other shell screen has one.
  - The top bar has no other tappable elements.
  - **Acceptance Criteria:**
    - [ ] When the Overview is showing, then the top bar shows the bank's logo and no back arrow.
    - [ ] When the Investments screen or a placeholder screen is showing, then the top bar shows that screen's title and no back arrow.
    - [ ] When the StartDepot screen is showing, then the top bar shows the title "StartDepot" and a back arrow on the left.

### 2.4 Overview (home screen)

- The Overview is the shell's home screen, modelled on the real app's financial overview. From top to bottom it shows:
  1. The greeting **"Hello, Lena"**.
  2. The **total balance** across the persona's accounts.
  3. **Account cards:**
     - a **StartKonto** current account card showing a fictional balance (€1,240.50) and a fictional account number ("DE00 0000 0000 0000 0000 00")
     - a **StartDepot** card showing a depot value of €0.00 and the line "No investments yet"
  4. A row of **quick actions**: Transfer, Cards, Postbox.
  5. A **Finance Quest card**:
     - title "Finance Quest" and subtitle "Learn to invest with real market history — risk-free"
     - a "Start" button and a "New" badge in its top corner
     - it is full width, has a brand-yellow background (the account cards are white), and is taller than either account card
  - **Acceptance Criteria:**
    - [ ] When the Overview appears, then the player sees, in this order from top to bottom:
      - the greeting "Hello, Lena"
      - the total balance €1,240.50
      - a StartKonto card showing €1,240.50 and "DE00 0000 0000 0000 0000 00"
      - a StartDepot card showing €0.00 and "No investments yet"
      - the quick actions Transfer, Cards and Postbox
      - a yellow Finance Quest card with a "New" badge and a "Start" button
    - [ ] When the player views the Overview on a phone screen 360 to 430 pixels wide, then the Finance Quest card's title and "Start" button are fully visible after scrolling down no more than one screen height.
    - [ ] When the player taps a quick action (Transfer, Cards or Postbox), then the "Not available" message appears and the player stays on the Overview.

### 2.5 Bottom navigation

- A bottom tab bar is visible on every shell screen after the welcome screen. Its tabs are, left to right: **Overview, Payments, Investments, Service, Profile**.
  - **Highlighting:** the tab the current screen belongs to is highlighted. The StartDepot screen belongs to Investments, so Investments is highlighted there, however the player got to it.
  - **Working tabs:** Overview and Investments open working screens.
  - **Placeholder tabs:** Payments, Service and Profile each open a simple placeholder screen with the tab's title and the line "This area isn't part of the demo."
  - **Tapping the highlighted tab:** returns to that tab's main screen. For example, tapping Investments while on the StartDepot screen shows the Investments screen.
  - **Acceptance Criteria:**
    - [ ] When the player is on any shell screen other than the welcome screen, then a tab bar showing Overview, Payments, Investments, Service and Profile, in that order, is visible at the bottom of the screen.
    - [ ] When the player taps Investments, then the Investments screen appears and the Investments tab is highlighted.
    - [ ] When the player taps Payments, Service or Profile, then a screen titled with that tab's name appears showing "This area isn't part of the demo."
    - [ ] When the player taps Overview from any other tab, then the Overview appears and the Overview tab is highlighted.
    - [ ] When the player opens the StartDepot screen from the Overview, then the Investments tab is highlighted.
    - [ ] When the player taps Investments while on the StartDepot screen, then the Investments screen appears.

### 2.6 Investments and StartDepot screens

- The **Investments** screen lists the persona's depots. It shows one entry: **StartDepot**, value €0.00. Tapping it opens the **StartDepot screen**.
- Tapping the StartDepot card on the Overview also opens the StartDepot screen.
- The StartDepot screen shows, below its top bar:
  1. The depot value, €0.00.
  2. An empty state: "You don't have any investments yet."
  3. Three product facts, worded as on the bank's website:
     - "No custody fees up to €20,000 depot value"
     - "Savings plans from €25 a month"
     - "For pupils, students and trainees"
  4. A **Finance Quest card** with the title "Practise before you invest" and a "Start your first quest" button.
  5. A **"Set up savings plan"** button.
- The **back arrow** returns to the screen the player came from: the Overview or the Investments screen.
- **"Set up savings plan"** always shows the "Not available" message in this shell. The savings plan offered at the end of a quest is part of the end-of-quest flow, not this button.
- Balances and the StartDepot empty state never change, whether or not the player has played Finance Quest. Only the Finance Quest cards change while a quest is unfinished (see 2.7).
- **Acceptance Criteria:**
    - [ ] When the player taps the StartDepot card on the Overview, then the StartDepot screen appears showing "StartDepot" in the top bar, €0.00, "You don't have any investments yet.", the three product facts, the "Start your first quest" button and the "Set up savings plan" button.
    - [ ] When the player taps Investments and then the StartDepot entry, then the same StartDepot screen appears.
    - [ ] When the player taps "Set up savings plan", then the "Not available" message appears and the player stays on the StartDepot screen.
    - [ ] When the player opened the StartDepot screen from the Overview and taps the back arrow, then the Overview appears.
    - [ ] When the player opened the StartDepot screen from the Investments screen and taps the back arrow, then the Investments screen appears.
    - [ ] When the player has left a quest and returns to the StartDepot screen, then it still shows €0.00 and "You don't have any investments yet." and its Finance Quest card shows "Continue".

### 2.7 Entering and leaving Finance Quest

- Finance Quest can be started from two places:
  - the Finance Quest card on the Overview ("Start")
  - the Finance Quest card on the StartDepot screen ("Start your first quest")
- Both open the first Finance Quest screen, "What are you into?".
- **While Finance Quest is open:**
  - The bank's top bar and bottom tab bar are hidden, so the game uses the full screen.
  - A **close (✕)** button sits at the top right of every Finance Quest screen.

- **Leaving:** tapping ✕, or using the phone's or browser's back gesture or button inside Finance Quest, asks for confirmation: "Leave the quest? You can continue where you left off." The options are **"Leave"** and **"Stay"**.
- **Resuming:** a quest the player left unfinished is kept on the same phone and browser, even after a page reload, until the quest is finished.
  - While a quest is unfinished, both Finance Quest cards show a **"Continue"** button instead of "Start" / "Start your first quest", plus the line "Quest in progress".
  - Tapping "Continue" opens the Finance Quest screen the player was last on, with everything they had done.
  - Once the quest is finished, the cards return to their "Start" buttons.
- **Back on shell screens:** the phone's or browser's back gesture or button behaves like the back arrow on the StartDepot screen. On other shell screens it returns to the previously viewed shell screen.
- **Acceptance Criteria:**
    - [ ] When the player taps "Start" on the Overview's Finance Quest card, then the screen "What are you into?" opens and the bank's top bar and tab bar are no longer visible.
    - [ ] When the player taps "Start your first quest" on the StartDepot screen, then the screen "What are you into?" opens.
    - [ ] When the player taps ✕ inside Finance Quest, then they see "Leave the quest? You can continue where you left off." with the buttons "Leave" and "Stay".
    - [ ] When the player uses the browser's back button inside Finance Quest, then the same leave confirmation appears.
    - [ ] When the player taps "Leave", then they return to the shell screen from which they started the quest, with the top bar and tab bar visible again.
    - [ ] When the player taps "Stay", then the message closes and they remain on the same Finance Quest screen.
    - [ ] When the player has left a quest unfinished and returns to the Overview, then the Finance Quest card shows "Quest in progress" and a "Continue" button instead of "Start".
    - [ ] When the player taps "Continue", then the Finance Quest screen they last left opens, showing what they had already done.
    - [ ] When the player has left a quest unfinished, reloads the page and unlocks again, then the Finance Quest card still shows "Continue".

### 2.8 Unavailable features

- Every tappable element that isn't part of the demo shows the same "Not available" message: **"Not available in this demo."**
  - It disappears on its own after 3 seconds or when tapped, and the player stays on the same screen.
  - Tapping another unavailable element while the message is showing replaces it with a fresh message and restarts its 3-second timer. Two messages never stack.
  - No tappable element may do nothing at all.
- **Acceptance Criteria:**
    - [ ] When the player taps the StartKonto card or a quick action, then the message "Not available in this demo." appears and the player stays on the same screen.
    - [ ] When 3 seconds have passed or the player taps the message, then the message disappears.
    - [ ] When the player taps two unavailable elements in quick succession, then only one "Not available in this demo." message is visible.
    - [ ] When a tester taps every button, card, list entry, quick action and tab across the shell, then each one either opens a screen described in this spec or shows "Not available in this demo.", and none does nothing.

### 2.9 Look and feel

- The shell follows the bank's current visual identity:
  - **Colours:** brand yellow (#FFD700) as the accent and on the Finance Quest cards; dark petrol (#002E3C) for text, primary buttons and the highlighted tab; warm grey (#F1EFED) for screen backgrounds and white for cards.
  - **Shapes:** cards with about 16-pixel rounded corners and fully rounded ("pill-shaped") buttons.
  - **Typeface:** Gotham, the bank's typeface, or the closest freely available geometric sans-serif if Gotham can't be used.
  - **Logo:** the bank's ribbon logo on the welcome screen and in the Overview's top bar. The Commerzbank challenge owners have approved use of their logo and colours in this prototype.
- **Theme:** light mode only.
- **Language:** all text is in English. The product names "StartDepot" and "StartKonto" stay unchanged.
- **Screen size:** the shell is designed for phone screens 360 to 430 pixels wide. On a wider screen (tablet or laptop) it appears as a centred column at most 430 pixels wide.
- **Acceptance Criteria:**
    - [ ] When a tester inspects the Overview, then:
      - the Finance Quest card is yellow #FFD700
      - body text and the "Unlock with Face ID" and "Start" buttons are dark petrol #002E3C
      - the screen background is #F1EFED
      - cards have visibly rounded corners of about 16 pixels
      - buttons are fully rounded
    - [ ] When the player opens the shell on a phone 360 to 430 pixels wide, then no text is cut off and no horizontal scrolling is needed on any shell screen.
    - [ ] When the shell is opened in a laptop browser window wider than 1,000 pixels, then it appears as a centred column no wider than 430 pixels.
    - [ ] When the player reads any shell screen, then all text is in English except the product names StartDepot and StartKonto.

### 2.10 Fictional data only

- Every name, balance and account number in the shell is fictional and the same for every player:
  - **Persona:** Lena, 16. The shell does not show her age on any screen.
  - **Account numbers:** shown in an obviously fake format, "DE00 0000 0000 0000 0000 00".
- The shell shows no transactions.
- The shell never asks for or shows any of the player's real personal or banking information.
- **Acceptance Criteria:**
    - [ ] When two different people open the demo on different phones, then both see the persona name Lena, the same balances and the same account number.
    - [ ] When the player views the StartKonto card, then the account number shown is "DE00 0000 0000 0000 0000 00".

---

## 3. Scope and Boundaries

### In-Scope

- Welcome screen with a simulated Face ID unlock and no credentials; reload returns to it
- Top bar, the Overview with the persona's StartKonto and StartDepot, quick actions and the Finance Quest card
- Bottom tab bar with two working tabs (Overview, Investments) and three placeholder tabs
- Investments list and StartDepot screen with product facts and the Finance Quest entry
- Entering Finance Quest from the Overview and StartDepot, leaving it with confirmation, and resuming an unfinished quest
- A consistent "Not available in this demo." message for everything unsupported
- The bank's visual identity, phone-first, English, light mode
- Fixed fictional persona and data

### Out-of-Scope

- Finance Quest itself:
  - the content of "What are you into?"
  - every later screen: Data Room, CommerzBuddy, decision, time skip, debrief, rewind, reveal
  
  These are separate specifications. This spec covers only the way into and out of Finance Quest and the ✕ button shown on top of it.
- The end-of-quest €25 savings-plan setup flow. It is specified with the end-of-quest flow, because the investment the plan targets must not amount to recommending the revealed company. Because the persona is 16, that flow must mention that a real StartDepot for under-18s is opened with parental consent.
- The presentation page with the phone frame and QR code for the stage. It is a separate specification.
- Real login, Face ID, photoTAN, or any real banking function: transfers, cards, postbox, orders, the AI assistant, notifications, transaction lists.
- German-language version, dark mode, and accessibility beyond readable text sizes and contrast.
- Personalising the persona or data per player.
- Any change to the shell's balances or depot content after the player has played Finance Quest. Only the Finance Quest cards change, to show "Continue" while a quest is unfinished.

---

## Change Log

_Dated amendments made after the spec was first written — typically by `/awos:spec` in Update Mode when a bug fix changed documented behavior. Each entry records the date, the source reference (bug id or fix description), and what behavior changed and why. Leave empty until the first amendment._

- 2026-11-20 — user change request ("remove demo - Collabothon 2026 label on top") — Removed the demo strip from every screen. 2.2 now requires that no demo label is shown, and the top bar or screen content starts at the top of the screen. The references to the strip in the top bar, Finance Quest and success criteria were updated to match. Reason: the user wants the shell to look like the real app from the top edge.
