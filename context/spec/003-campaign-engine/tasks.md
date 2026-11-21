# Tasks: Finance Quest Campaign Engine

Spec: `context/spec/003-campaign-engine/`. Shared contract: `context/product/shared-contracts-002-003.md` (wins on conflicts). Builds on spec 002's `backend/financequest` package and frontend shared pieces.

Plan approved for execution by the user's `/awos:implement` instruction on 2026-11-20.

Notes:
- All LLM, image and TTS calls use fakes in automated tests.
- The live Enron campaign run happens after the user adds `ANTHROPIC_API_KEY` and `GOOGLE_GENAI_API_KEY` to `.env`.

---

- [x] **Slice 1: Enron reference pack imported and playable as a scenario**
  - [x] Implement `financequest/refpack/`:
    - the manifest Pydantic model per tech §2.4
    - validation invariants, including spec 002's final scan on every player-visible field, the leak list, the checkpoint order, the buy day after the decision date, and a rubric totalling 100
    - the importer CLI `refpack import <case.md> <prices.csv>`: an LLM-assisted draft through the model factory, a fake in tests, plus a validation report
    - `refpack approve <case_id>`: writes `scenario` (`source = reference_pack`, disguised fields via spec 002's `NumberPlan` with the shared money factor and story days, plus `manifest`) and `scenario_secret` (`n_guessers = 0`, `leak_terms`, the CSV ref)

    Then author by hand, as the reviewed manifest, `backend/financequest/fixtures/reference/fq-av-001/manifest.json` from the repo-root Enron Markdown, and copy the Markdown and CSV there as `case.md` and `prices.csv`. The manifest covers:
    - checkpoints G0/G1/G2
    - evidence with IDs, checkpoint, location and fantasy-mapped player text with no real names, dates or raw millions
    - Library documents
    - characters (Elian Voss, Mira Fen, Ren Tal) with `may_reveal` per checkpoint
    - 4 encounters with DCs 12/14/14/12
    - the G1 news with "N days later…" in story days
    - the rubric 25/25/20/15/15
    - the decision date 2001-10-17
    - `horizon_end` 2001-12-31
    - 1–2 campaign location seeds

    Tests:
    - the manifest validates
    - tampered manifests fail
    - after `refpack approve`, the Enron scenario appears in `GET /scenarios/playable`

    **[Agent: python-backend]**

- [x] **Slice 2: Campaign engine core (hero, campaign run, rules, math)**
  - [x] Add a migration in spec 002's Alembic history, following its head, for `player`, `hero`, `hero_item`, `campaign_run`, `location`, `challenge`, `clue_state`, `outcome`, `debrief`, `xp_award` (tech §2.3).

    Implement `financequest/campaign/`:
    - `clock.py`: checkpoints and the story clock
    - `engine/gate.py` extension: `GatedView(checkpoint, clock)`
    - `dice.py`: a seeded pure function, nat 20/1, advantage
    - `rules.py`: DC from the manifest, else the table; decide gating; news trigger; turn counting
    - `portfolio.py`: Decimal; buy at the next trading day's open after the decision date; end at the `horizon_end` close; FX ignored; rounding; HP
    - `whatif.py`
    - `xp.py`: the rubric from the manifest or the default; clamp; quote check; loss-word check
    - `focus.py` and items
    - event projections (journal, backlog)
    - `adapter.py`: gate scenario → minimal manifest

    Routers:
    - `GET/POST /hero`
    - `POST /campaigns`
    - `GET /campaigns/{id}`
    - rolls, reroll, accept
    - move
    - `focus/*`
    - `PUT commit-draft`
    - `lock` (inserts the shared `decision`)
    - `reveal` (outcome)
    - `reflection` (writes `debrief_complete`, returns `scenario_id`)
    - `xp`
    - `finish`
    - `journal`

    The narration endpoints call the agent Protocols (fakes for now).

    Tests per tech §4:
    - the gate property test
    - the Enron math: buy $31.95 → end $0.60; €400 invested + €600 kept → €607.51
    - dice determinism
    - lock idempotency
    - finish and items

    **[Agent: python-backend]**

- [x] **Slice 3: Agent graphs, guards and streaming narration**
  - [x] Implement `financequest/agents/campaign/` with `ChatAnthropic` (`claude-opus-5-5`, effort per tech §2.7) behind a model factory with a scripted fake. The graphs:
    - **setup:** the Tavern briefing; encounters, characters and evidence from the manifest; 0–3 extra locations with `art_subject`; 3 suggestions; fall back to the prepared setup
    - **turn:** the router (free / challenge / talk / decision_intent / off_topic / move) → narrate (≤150 words, `speaker`, suggestions, `clue_ids_given` checked against `may_reveal`, `nothing_more_to_uncover`)
    - **dice narration:** final result only
    - **buddy:** ≤120 words; explains, analyses on-screen data, hints, never advises
    - **news/hint**
    - **rolling summary**
    - **debrief:** sound / overlooked / luck / forecast line / reflection question; the what-if comes from the engine
    - **xp**

    Guards subgraph:
    - number guard with a per-call allowlist
    - leak guard (`leak_terms`)
    - advice classifier
    - word caps
    - retry once, then the template "Let's check the numbers in the Library."

    SSE endpoints (`opening`, `actions`, `move`, `narrate-roll`, `buddy`, `focus/hint`, `debrief`):
    - `status: writing` within 1 s
    - buffered and guarded, then streamed word by word
    - heartbeats
    - a 15 s first-token deadline → `error lost_thread`
    - idempotent `client_msg_id`

    Fake-LLM tests: every router branch, guard retry/fallback incl. refusal, invalid `clue_ids` rejected, the five safeguard prompts handled by guards. **[Agent: langgraph-agents]**

- [x] **Slice 4: Media (backgrounds and voice)**
  - [x] Implement `financequest/media/art.py` and `media/tts.py`, and register both providers in the model factory.
    - **Art:** Nano Banana through the Google GenAI SDK. A fixed style-guide prompt + the scrubbed `art_subject` + the negative block + the style-anchor image. An asyncio job per campaign location writes `DATA_DIR/art/{campaign}/{location}.webp`, with `art_status` and `art_ready` on SSE/state. Pending jobs are rescanned at startup, and a failure keeps the placeholder. `GET /locations/{id}/art`.
    - **Voice:** Gemini TTS with voices `dm` and `buddy`, per-sentence synthesis, a hash cache, and `GET /tts/{audio_text_id}?voice=` generating only from stored guarded text.

    Tests with fakes. Add placeholder style-anchor and constant background files (simple plain backdrops) under the frontend `public/backgrounds/`. **[Agent: langgraph-agents]**

- [x] **Slice 5: Quest flow frontend: entry, hero, interests, disclosure, routing**
  - [x] Implement:
    - `questStore` v2 (`fq.quest.v2`, migrating v1)
    - TanStack Query hooks and the SSE-over-fetch helper (`useDmStream`: 15 s timeout, Try again with `client_msg_id`) on top of spec 002's `api/client.ts`
    - `QuestEntry` resolver, `phaseToPath`, `PhaseGuard`
    - routes per tech §2.9 (`/quest/hero/new`, `/quest/interests`, `/quest/play`, `/quest/commit`, `/quest/outcome`, `/quest/debrief`, `/quest/reflect`, `/quest/reveal` = spec 002's `Reveal.tsx`, `/quest/xp`, `/quest/hero`, `/quest/journal`)
    - "Create your hero" (name rules, three class cards)
    - "What are you into?"
    - spec 002's `DisclosureNote` after "Find my quest"
    - the quest-only `quest` Tailwind tokens and the Alegreya / Alegreya Sans / Pirata One fonts (spec 003 §2.18)

    Update the spec 001 tests that assumed Start → "What are you into?" (acceptance, smoke, layout, QuestLayout, questStore). **[Agent: react-frontend]**

- [x] **Slice 6: Visual-novel play screen**
  - [x] Implement:
    - `VnStage` with `SceneArt` (constant backgrounds, generated art, plain placeholder) and `HeroStatus`
    - `DialogueBox`: name tab, ≤50-word pages, typewriter, tap to complete or advance
    - `ChoiceList`: suggestions sent on tap, "Write your own action…", "I'm ready to decide" when `can_decide`, Focus actions
    - `Backlog`, `JournalSheet`
    - `MapSheet` with Tavern / Market Square / Library / campaign locations, plus `TitleCard`
    - Market Square price board with spec 002's `StoryChart`; Library documents and company card
    - `DiceMoment`: bronze d20 tumble, Keen Eye / Second Look / Accept / Continue
    - `BuddyScene` with the placeholder token and summon animation
    - `BreakingNewsCard` and the "N days later…" card

    Everything is driven by the API (`useDmStream` + campaign state). Component tests. **[Agent: react-frontend]**

- [x] **Slice 7: Decision to finish, and voice**
  - [x] Implement:
    - `SealScroll` commit: validation, a lock confirmation, the wax-seal animation
    - the "N days later…" time skip
    - `/quest/outcome`: portfolio breakdown, HP change, `StoryChart`, the currency note
    - the debrief with three parts, the forecast line and `WhatIfPanel`
    - reflection (≥10 chars) → spec 002's reveal
    - the XP screen with the campaign rubric and Finish
    - the hero screen with items and history

    Also the voice module (`VoiceProvider`: server audio default, Web Speech fallback; unlock on "Find my quest" / "Continue"; stop on send / Buddy open / toggle; the persisted toggle).

    Component tests. **[Agent: react-frontend]**

- [x] **Slice 8: End-to-end Enron campaign on fakes**
  - [x] Add a backend demo mode with deterministic scripted narration (`FAKE_LLM=1`) so the full stack runs without keys. Then:
    1. Start Postgres + API (FAKE_LLM) + the Vite preview.
    2. With the Playwright MCP, play the Enron campaign as a user: new hero → interests → disclosure → Tavern → Library / Market Square → a dice check → Buddy → news → commit and seal → outcome (€607.51 case) → debrief → reflection → company reveal → XP → Finish.
    3. Verify the spec acceptance criteria along the way, and no real names or dates before the reveal.
    4. Stop every process by PID and delete the screenshots. **[Agent: qa-testing]**

- [x] **Slice 9: Feature Testing & Regression**

  > Verifies the whole feature end-to-end against functional-spec.md, run after all implementation slices are complete.
  - [x] Read functional-spec.md acceptance criteria in full. Generate acceptance-level tests that verify the entire feature as a whole — not individual slices. Cover applicable layers (unit for pure logic, integration for service interactions, e2e for user flows) based on the project's testing stack. Write tests with RED validation (must fail before implementation is confirmed done). Annotate each test with `@spec: 003-campaign-engine` and `@regression` if suitable for long-term regression. **[Agent: qa-testing]**
  - [x] Run all generated tests. All must pass. Fix any failures before proceeding. **[Agent: qa-testing]**

- [x] **Slice 10: Live Enron campaign (needs keys in `.env`)**
  - [x] With real `ANTHROPIC_API_KEY` and `GOOGLE_GENAI_API_KEY`:
    1. Run the live LLM evals (the five safeguard prompts × the Campaign Master and Buddy).
    2. Play the full Enron campaign through the UI with the Playwright MCP, as a user.
    3. Report latency, guard outcomes, art and voice, and any defects.
    4. Stop every process by PID. **[Agent: qa-testing]**

  Done 2026-11-21 with live Claude and Gemini TTS. Gemini image generation is blocked by the key's quota (`limit: 0`), and the placeholder fallback was verified. The defects found in the live run are fixed on `feat/scene-hotspots`.
