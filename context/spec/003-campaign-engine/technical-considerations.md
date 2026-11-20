<!--
This document describes HOW to build the feature at an architectural level.
It is NOT a copy-paste implementation guide.
-->

# Technical Specification: Finance Quest Campaign Engine

- **Functional Specification:** [`functional-spec.md`](./functional-spec.md)
- **Status:** In Review
- **Author(s):** Viktor Kulyk (drafted with Claude). Input from the `python-backend`, `langgraph-agents` and `react-frontend` agents and a code exploration.

---

## 1. High-Level Technical Approach

This feature creates the **backend** (none exists yet) and turns the spec 001 quest stub into the full game.

1. **Backend: `backend/`, FastAPI on Railway.**
   - **Deterministic engine:** owns every number: dice, difficulty, HP, portfolio math, XP caps, Focus, items, gating, the hidden-future gate.
   - **Agent layer:** LangGraph graphs calling Claude (`claude-opus-5-5`) via `langchain-anthropic`. It narrates, routes actions, plans the campaign, debriefs and scores XP, but never produces numbers.
   - **Persistence:** **PostgreSQL**, in a container shared with another in-flight spec that owns provisioning it (see §2.3). Our tables live in their own `campaign` schema. An append-only **event log** is the source of truth for the journal, the backlog, resume and the learning history. Art and audio files go on the Railway volume.
2. **Content: reference documents.**
   - A campaign is built around a **reference pack**: a Markdown case reference with YAML frontmatter, plus an OHLCV price CSV. Example: `Finance_Quest_Enron_Historical_Case_Reference_CLEAN_v2.md` + `Enron_ENE_Historical_OHLCV_2001-08_to_2001-12.csv`.
   - An **import step** turns the pack into a validated, checkpoint-tagged **campaign manifest** and keeps the raw Markdown server-side only (§2.4).
   - The setup graph uses the manifest's encounters, characters and evidence. It generates only the briefing wording, scene dialogue and any extra campaign locations.
   - A `ReferenceDocumentSource` interface lets the future reference-document spec plug in. Today a `FixtureSource` returns the imported Enron pack (`FQ-AV-001`).
3. **Media.**
   - **Backgrounds:**
     - The fixed locations (Tavern, where every journey starts, plus Market Square and Library) use **constant backgrounds**: static assets, the same in every campaign.
     - Each campaign location gets its own background, generated asynchronously with **Nano Banana** (Google GenAI SDK) from a fixed style-guide template plus a style-anchor image.
     - A plain placeholder shows until a background exists.
   - **CommerzBuddy:** appears as a **token icon** with a summon animation, delivered by the team later and mocked until then.
   - **Voice:** the backend generates voice audio with **Gemini TTS** in two fixed voices, one for the DM and one for Buddy. The browser's Web Speech API is the fallback.
4. **Frontend: `frontend/src/quest/`.**
   - New `/quest/*` routes driven by the server's campaign **phase**.
   - **TanStack Query** for REST, plus a small SSE-over-fetch hook for streamed replies.
   - A voice provider that unlocks audio on the first tap.

**What this changes elsewhere:**

- The spec 001 flow changes: Start → hero creation for new players. Spec 001 needs a matching amendment, and the spec 001 e2e tests that expect "What are you into?" right after Start must be updated (§4).
- Architecture §2's data model gains new tables.
- Architecture `/reveal` semantics change: the company identity is released only after the reflection (functional spec 2.14), through a separate endpoint.

---

## 2. Proposed Solution & Implementation Plan (The "How")

### 2.1 Architecture changes

| Area | Change |
|---|---|
| New service | `backend/` FastAPI app (Python 3.12, `uv`, single uvicorn worker), Dockerfile, Railway service with a `/data` volume (art + audio cache) |
| Database | PostgreSQL. The Postgres container/service is **owned and provisioned by another developer's spec** — this spec only connects via `DATABASE_URL` and owns the `campaign` schema (see §2.3) |
| Frontend | New quest routes, API client, TanStack Query, voice module, Lightweight Charts (lazy-loaded) |
| Identity | Anonymous device session: `POST /session` → `session_id` kept in `localStorage["fq.session.v1"]`, sent as `X-Session-Id`. The hero is tied to this session ("this phone and browser"). Clearing site data loses the hero (accepted) |
| Streaming | SSE over `POST` + `fetch` ReadableStream (EventSource can't send headers). The client calls Railway directly with CORS allowlisted; heartbeats, `Cache-Control: no-cache`, `X-Accel-Buffering: no` |
| Guards | The full reply is generated and buffered, guards run, then the server re-streams it word by word. A `status: writing` event is sent immediately (≤1 s) |

### 2.2 Backend layout (`backend/`)

| Path | Responsibility |
|---|---|
| `app/main.py`, `config.py`, `deps.py` | App, CORS, settings (`DEMO_MODE`, keys), session dependency, `/healthz` |
| `app/api/` | Routers: `session`, `hero`, `campaigns`, `locations`, `tts`, health; SSE helper (heartbeat, event names) |
| `app/models/` | SQLModel tables (server-only; never returned directly) |
| `app/schemas/` | Outbound DTOs; must not import secret models |
| `app/engine/` | `gate.py` (GatedView), `clock.py`, `rules.py` (DC table, decide gating, news trigger, turn counting), `dice.py`, `portfolio.py`, `whatif.py`, `xp.py` (clamp, quote check, items), `events.py`, `journal.py` / `views.py` (projections) |
| `app/guard/` | `numbers.py`, `leaks.py`, `advice.py`, `allowlist.py` |
| `app/refdoc/` | `ReferenceDocument` model, loader + invariant checks, `ReferenceDocumentSource` protocol, `FixtureSource` |
| `app/agents/` | LangGraph graphs and nodes (setup, turn, dice-narration, buddy, news/hint, summary, debrief, xp) behind thin Protocols; a fake model factory for tests |
| `app/media/` | `art.py` (Nano Banana jobs, style template, storage), `tts.py` (Gemini TTS, per-sentence cache) |
| `app/fixtures/reference/fq-av-001/` | The Enron pack: `case.md`, `prices.csv`, the reviewed `manifest.json`, pre-generated art for its campaign locations. Also the manifest JSON schema and the style-anchor image |
| `pipeline/import_reference.py` | CLI: Markdown + CSV → draft manifest (LLM-assisted extraction) → validation report for human review |
| `tests/` | pytest suites (§4) |

**Dependencies:**

- **Runtime:** fastapi, uvicorn, sqlmodel, psycopg (v3), alembic, pydantic v2, pydantic-settings, sse-starlette, httpx, langgraph, langchain-anthropic, google-genai.
- **Dev:** pytest, pytest-asyncio, hypothesis, ruff, mypy.

### 2.3 Data model (PostgreSQL via SQLModel)

**Shared database: be careful.** The PostgreSQL container is in scope of another developer's spec, which provisions it and may create its own tables. This spec must not collide with that work:

- **Provisioning:** this spec does not define, start, reset or reconfigure the Postgres service, its Docker/Compose definition, roles or extensions. It reads `DATABASE_URL` only.
- **Schema:** every table below lives in a dedicated **`campaign` schema**. Nothing is created in `public` or in the other spec's schema.
- **Migrations:** Alembic, scoped to our schema, with its own version table (`campaign.alembic_version`, `version_table_schema="campaign"`) so it can't clash with the other spec's migration history. There are no destructive or cross-schema migrations, and tables are never auto-created at app start.
- **Local dev and tests:** tests use a disposable database or schema (e.g. pytest creates and drops a `campaign_test_<uuid>` schema), never the shared dev schema. Local dev points `DATABASE_URL` at the shared container once it exists.
- **Coordination:** confirm with the other developer: the connection string, the role/permissions to create the `campaign` schema, and the Postgres version. **Open item.**

Ids are UUIDs. JSON columns use `JSONB`.

| Table | Key columns | Notes |
|---|---|---|
| `player` | id (= session id), created_at, active_campaign_id | |
| `hero` | player_id (unique), name, class (`guardian`/`analyst`/`investigator`), total_xp | Name rules mirror functional spec 2.1 |
| `hero_item` | hero_id, item_key (`ratio_lens`/`rumour_ledger`/`calm_compass`), earned_campaign_id | unique(hero_id, item_key) |
| `reference_document` | id (case_id), version, content_hash, manifest (JSONB), prices (JSONB rows) | Public manifest only; read raw **only** inside `engine/` |
| `reference_secret` | doc_id, real_name, ticker, real dates, price_scale, date_shift, alias_map, source_note | Read only by the company-reveal endpoint and the leak guard |
| `campaign_run` | id, player_id, hero_id, doc_id/version, interests, phase, status, checkpoint (G0/G1/G2…), clock_date, turn_count, current_location_id, focus_left, rerolls_left, keen_eye_left, bonus_lead_used, news_shown, hp_start, rng_seed (server-only), pending (open roll / pending narration), commit_draft, version | `phase` ∈ setup, play, commit, timeskip, reveal, debrief, reflect, company, xp, done |
| `location` | campaign_id, key, fixed, name, description, art_status (placeholder/pending/ready/failed), art_path | Fixed: tavern (start), market_square, library. Fixed rows point to the constant background key; only campaign rows have generation jobs |
| `challenge` | campaign_id, kind, dc, clue_id, alt_source, location_id, optional, state (open/rolling/final), dice[], total, result, rerolled | `dc` is always looked up from the rule table |
| `clue_state` | campaign_id, clue_id, found_at_seq, source | |
| `event` | campaign_id, seq, type, payload, ts, client_msg_id | unique(campaign_id, seq) and unique(client_msg_id) when present. Types: action, dm_reply, buddy_q, buddy_a, move, dice_roll, reroll, keen_eye, clue_found, news, focus_spend, summary, commit_draft, lock, time_skip, reveal, debrief, reflection, company_reveal, xp, finish |
| `decision` | campaign_id (unique), action, amount_cents, evidence, forecast_pct, confidence, locked_at | Immutable after insert |
| `outcome` | campaign_id, prices used, cash, invested, value_now, fees, final, pnl, pnl_pct, hp_before, hp_after (Decimals as strings) | |
| `debrief` | campaign_id, narrative, overlooked clue_ids, forecast_line, whatif, reflection_text | |
| `xp_award` | campaign_id, per-category score + rationale + quote, total, finished_at | |

The journal, the backlog and the learning history are **projections of `event`** plus `decision`, `outcome` and `xp_award`. There are no separate tables.

### 2.4 Reference pack and campaign manifest

**Input** (one pack per campaign):

| File | Contents (from the Enron sample) |
|---|---|
| `case.md` | **Frontmatter:** `case_id`, `version`, `historic_entity`, `fictional_campaign`, `market_data_file`. **Sections:** purpose and learner objectives; evidence conventions and **checkpoints G0–G4** with cutoff dates; company identity and actors; reported financials per period; announcements; later events; point-in-time knowledge matrix; fantasy mapping; characters (NPCs) with what they may reveal per checkpoint; encounters with DC, evidence IDs and failure-forward; financial rules; decision and debrief protocol with an optional XP rubric; source registry |
| `prices.csv` | `date, open_usd, high_usd, low_usd, close_usd, volume_shares, source_id, source_url`. Ascending dates, no filled gaps |

**Why an import step:** the Markdown contains real names, real dates and everything that happened after the decision (later events, restatements, bankruptcy, sources). It is **never sent to any agent or client**. The importer extracts what the game may use, tags it by checkpoint, and keeps the rest for the reveal.

**Import (`pipeline/import_reference.py`, offline):**

1. Parse the frontmatter and sections, and load the CSV.
2. An LLM-assisted extractor (high effort, structured output) drafts the manifest from the Markdown.
3. Deterministic validation runs.
4. A human reviews the draft, using a validation report that lists each evidence item with its checkpoint and source section.
5. The reviewed `manifest.json` is committed next to the pack.

The game loads only reviewed manifests.

**Manifest (public part)**, validated by a Pydantic model:

| Section | Contents |
|---|---|
| `meta` | `case_id`, `version`, `campaign_title` (fantasy, e.g. "The Golden Guild's Secret"), `learning_objectives[]`, `currency` (e.g. USD) |
| `world` | Fantasy setting name; fantasy names for the company, shares, market, ledgers and statements (from the mapping table); tone notes |
| `checkpoints[]` | `{id: G0\|G1\|G2\|G3\|G4, role: intro\|disclosure\|decision\|outcome\|reflection, cutoff_date, label}`. The Enron pack: G0 intro (2001-08-14, opening scene 08-15), G1 disclosure (10-16), G2 decision (10-17) |
| `company_card` | Fantasy name, trade, size, `key_figures[{label, value, period, checkpoint, explain}]` |
| `evidence[]` | `{id (e.g. F-Q3-LOSS-001), checkpoint, location (library\|market_square\|tavern\|campaign:<key>), kind (ledger\|announcement\|figure\|market\|opinion), title, player_text (fantasy-mapped, no identifiers), figures[], key: bool, teaching_note}` |
| `documents[]` | Library items `{id, checkpoint, title, evidence_ids[]}` (annual ledger, quarterly ledger, proclamations) |
| `characters[]` | `{id, name, role, location, may_reveal{G0: evidence_ids[], G1: [...]}, never[]}` (e.g. Treasurer Elian Voss, Scholar Mira Fen, Broker Ren Tal) |
| `encounters[]` | `{id, title, checkpoint, location, dc, skill_flavor, evidence_ids[], success_clue_id, failure_forward, teaching_target}` (Enron: four encounters, DC 12 / 14 / 14 / 12) |
| `news` | `{checkpoint: G1, time_skip_label ("Two months later…"), headline, summary, evidence_ids[]}` |
| `prices` | Path + row range; `decision_date`, `horizon_end` (default: the last CSV date) |
| `fund` | Optional fund series for Spread (absent in the Enron pack, so Spread is hidden) |
| `rubric` | Optional `[{category, max}]` totalling 100 with a reflection category (Enron: 25/25/20/15/15). Default rubric when absent |
| `campaign_location_seeds[]` | Optional extra places with art subjects (e.g. the Golden Guild Hall) |
| `debrief` | Debrief questions and post-reveal facts (G3/G4 only) |

**Secret part** (`reference_secret`, never sent to agents before reveal):

- the raw `case.md`
- real entity, ticker, actors, city and real dates
- the fantasy↔real alias map
- the later-events timeline and source registry
- the **leak list**: every real name, ticker, product, person, place and real date string in the Markdown

**Validation invariants:**

- **Checkpoints:** they include at least intro, disclosure and decision, in date order.
- **Evidence and documents:** every item's checkpoint is at or before the decision checkpoint, unless it is in `debrief`. No `player_text` matches the leak list.
- **Key evidence:** at least one key item; every key item is reachable without dice, either directly or as an encounter's failure-forward.
- **Encounters:** between 2 and 4, each with a `dc` from 5 to 20.
- **Price table:** it covers the intro date through `horizon_end`; the decision date is a trading day, and a trading day exists after it (the buying day).
- **Rubric:** if present, it totals 100.

### 2.5 API contract

- **Common rules:**
  - All endpoints except `POST /session` require `X-Session-Id`.
  - Errors use one envelope: `{error: {code, message}}`.
  - A request made in the wrong phase gets **409**; an unknown session gets **401**, after which the client re-creates its session.
- **SSE events:** `status` (writing), `token`, `card` (dice | news), `state` (resource deltas, `can_decide`, `art_ready`), `done` (final text, ids, `audio_text_id`), `error`.

| Method & path | Request | Response |
|---|---|---|
| `POST /session` | — | `{session_id}` |
| `GET /hero` | — | `{name, class, total_xp, items[], history[], active_campaign_id}` or 404 |
| `POST /hero` | `{name, class}` | hero; 409 if it exists; 422 on name rules |
| `POST /campaigns` | `{interests[]}` | full campaign state (phase `setup`) |
| `POST /campaigns/{id}/opening` | — | **SSE**: runs the setup graph (with a fallback to the prepared setup), starts art jobs, streams the opening scene |
| `GET /campaigns/{id}` | — | Full resumable state: phase, hero resources (HP, Focus, rerolls, Keen Eye), locations with art status and URLs, backlog, clues, pending card, `can_decide`, `news_shown`, commit draft. After the relevant phases it also includes outcome, debrief and xp |
| `POST /campaigns/{id}/actions` | `{text, client_msg_id}` | **SSE** turn. A repeated `client_msg_id` replays the stored reply ("Try again" is idempotent) |
| `POST /campaigns/{id}/move` | `{location_id}` | **SSE** arrival narration; counts as a turn; 409 while a roll is open |
| `POST /campaigns/{id}/rolls` | `{challenge_id, mode: normal\|advantage}` | `{dice[], bonus:2, total, dc, result, final, options[]}` |
| `POST /campaigns/{id}/rolls/{rid}/reroll` · `/accept` | — | Final roll result |
| `POST /campaigns/{id}/narrate-roll` | `{roll_id}` | **SSE** narration of the final result only |
| `POST /campaigns/{id}/buddy` | `{text, client_msg_id}` | **SSE** Buddy answer (not a turn) |
| `POST /campaigns/{id}/focus/hint` · `/focus/bonus-lead` | — | Hint: SSE · bonus lead: dice card |
| `PUT /campaigns/{id}/commit-draft` | partial commit fields | 204; 409 after lock |
| `POST /campaigns/{id}/lock` | full commit | Outcome summary; idempotent |
| `GET /campaigns/{id}/reveal` | — | Locked-at, horizon, extended chart series, portfolio breakdown, HP change. No identity |
| `POST /campaigns/{id}/debrief` | — | **SSE** debrief (sound reasoning / overlooked / luck / forecast line / reflection question) + `whatif[]` |
| `POST /campaigns/{id}/reflection` | `{text}` (≥10 chars) | `{company: {real_name, real_dates, source_note}}` |
| `POST /campaigns/{id}/xp` | — | `{categories[5]{name, score, max, rationale, quote}, total}` |
| `POST /campaigns/{id}/finish` | — | `{total_xp, new_item?}`; idempotent |
| `GET /campaigns/{id}/journal` | — | Journal entries (also for finished campaigns) |
| `GET /locations/{id}/art` | — | Image bytes (unguessable UUID; `<img>` can't send headers) |
| `GET /tts/{audio_text_id}?voice=dm\|buddy` | — | Audio (cached), generated only from guarded, stored event text — never raw client text |

### 2.6 Engine rules (deterministic)

- **Hidden-future gate:**
  - Agents and response builders receive only a `GatedView(checkpoint, clock_date)`. It contains:
    - price rows up to the clock
    - evidence, documents, encounters and character reveal lists whose checkpoint is at or before the current one
    - the news, only once shown
    - **never** the secret part or the debrief facts
  - **Anonymized presentation:**
    - **Prices:** the board shows prices multiplied by a per-campaign `price_scale`, so percentage moves are preserved while real levels are hidden.
    - **Dates:** shown as fantasy-calendar labels derived by a per-campaign `date_shift` and naming scheme, for example "the 15th of Harvestmoon".
    - Real values appear only after the company reveal.
  - A static test ensures only `engine/` imports the raw document.
  - After lock, only `/reveal` may extend to horizon_end.
- **Dice:**
  - Each roll is a pure function of `(rng_seed, challenge_id, roll_index)`, so reloads and retries can't change it.
  - Total = d20 + 2. A natural 20 always succeeds, a natural 1 always fails, and otherwise the roll succeeds when `total ≥ dc`.
  - Advantage rolls two dice and keeps the higher.
  - Each roll is logged with its dice array.
- **Difficulty:**
  - Manifest encounters use their own `dc`.
  - Challenges the DM adds (only if a pack has fewer than 2 encounters) use the rule table `public_report: 8`, `unusual_figure: 12`, `cross_check: 15`, `obscure_lead: 18`; the LLM supplies only `kind`.
  - The narrator never supplies a DC.
- **One roll per challenge:**
  - The roll moves through the states open → rolling → final.
  - A **reroll** is allowed only for an Analyst who got a setback and has `rerolls_left > 0`. **Keen Eye** must be chosen before rolling.
  - Narration runs only once the result is final.
  - A repeated attempt returns `already_resolved`.
- **Bonus lead:** an extra optional challenge (difficulty 18) using `bonus_clue`, allowed once per campaign, beyond the 2–4 cap. (confirmed).
- **Turns:** actions and moves count as turns. Buddy, rolls, rerolls, Focus actions and the hint do not. (hint: confirmed).
- **Checkpoints and the story clock:**
  - A campaign starts at the intro checkpoint, with the clock at its cutoff date.
  - The news event advances the checkpoint to the disclosure checkpoint, and the clock to the **decision date** (end-of-day convention). The `GatedView` then includes that checkpoint's evidence, documents, encounters and price rows.
  - The clock never moves backwards.
- **News:** after a committed turn, if the news has not yet been shown and either `turn_count ≥ 6`, or the player arrived at Market Square with `turn_count ≥ 3`, a `news` card is emitted and its clue granted.
- **Clue granting:**
  - The DM *proposes* `clue_ids_given`. The engine validates them against reachability and writes `clue_found`.
  - Free clues at a location are granted on visit, and the DM must mention them.
- **`can_decide`:** all key clues found, all free reachable clues found, no open roll or pending narration, and the opening scene complete. Optional challenge-gated non-key clues don't block it.
- **Lock (one transaction):**
  1. Revalidate: amount is whole euros from 1 to `hp_start × 10` for invest or spread; evidence is at least 20 characters after trimming; the forecast is a multiple of 5 from 0 to 100; confidence is one of the allowed values.
  2. Insert the `decision`.
  3. Compute the `outcome`.
  4. Set the phase to `timeskip`.
  5. Log the lock.
- **Portfolio (`Decimal`):**
  - **Buying price:** the **open of the first trading day after the decision date** (Enron: 2001-10-18 open, $31.95). It is never shown to the player before lock.
  - **End value:** the close on `horizon_end` (Enron default: 2001-12-31, $0.60). Bankruptcy or suspension never zeroes the value implicitly; only recorded rows count.
  - `r = close(horizon_end) / open(buy_day) − 1`.
  - **Currency:** prices are in the pack's `currency`. Only `r` is applied to the EUR budget; FX is ignored, and the reveal shows the label "Prices in the company's original currency; exchange-rate changes are not included."
  - **Invest:** `amount × (1 + r)`.
  - **Spread:** half of the amount in the company and half in the fund, each with its own `r`.
  - **Cash:** `budget − amount`.
  - **Fees:** taken from the document (€0 default).
  - **Rounding:** cents use `ROUND_HALF_UP`, % is quantized to 0.1, and **HP = (final / 10) rounded half up**.
- **What-if:** the same function, run for: Don't invest; half the budget; the whole budget; the whole budget spread. The player's row is highlighted. If their amount matches none of these, an extra "Your choice" row is added. (confirmed).
- **XP:**
  - The evaluator returns a score, rationale and quote per category.
  - **Rubric:** the campaign's rubric from the manifest (default 25/25/20/20/10 when absent).
  - The engine clamps each score to its category maximum, checks each quote is a substring of the player's text, scans rationales for profit or loss terms, computes the total, and substitutes a neutral rationale on failure.
  - The evaluator never sees P&L, HP or dice.
- **Finish (idempotent):**
  - Adds the campaign's XP to the hero's total once.
  - When XP is 70 or more, awards the next missing item in this order: Ratio Lens → Rumour Ledger → Calm Compass. Calm Compass gives 4 Focus at the next campaign start.
- **Focus:** spending is atomic with its event. For a hint, the engine picks the target clue (key clues first) and the DM only narrates where to look.
- **Concurrency:** short Postgres transactions with no transaction held across an LLM call; `SELECT … FOR UPDATE` on the `campaign_run` row plus its `version` column (optimistic check); a per-campaign asyncio lock in the single worker; unique constraints for `client_msg_id` and `(campaign_id, seq)`; a connection pool sized small, to respect the shared instance's limits.

### 2.7 Agent layer (LangGraph + `langchain-anthropic`)

| Graph | Nodes | Effort |
|---|---|---|
| **setup** | load GatedView (G0) → `plan_campaign`. **Tavern briefing:** world, the company's fantasy name and trade, objective, known facts, budget, horizon, where to find what (Library documents, Market Square board, which characters are where), Buddy available. It also produces 0–3 extra campaign locations with `art_subject`, extra challenges only if the manifest has fewer than 2 encounters, and 3 suggestions. Encounters, characters and evidence come from the manifest unchanged → engine validation → guards → persist. One retry, then fall back to the prepared setup for the sample doc. 40 s cap | high |
| **turn** | build_ctx → `route` (free / challenge(id) / talk(character_id) / decision_intent / off_topic / move) → narrate (≤150 words, ends with a question, `speaker` (`chronicler` or a manifest `character_id`, used for the name tab), `suggestions[3]`, `clue_ids_given`, `nothing_more_to_uncover`). Characters can only say evidence in their `may_reveal` list for the current checkpoint; the engine checks `clue_ids_given` against it → guards → commit_turn. A challenge ends in a `dice_required` card. Decision intent uses a fixed template | route low · narrate medium |
| **dice narration** | narrate the final result: success → clue text; setback → alt source | low |
| **buddy** | build_ctx (incl. what the player currently has open, e.g. price-board rows or ledger figures, as gated data) → buddy (≤120 words; explains, analyses on-screen data, gives a hint about where to look next without naming unfound evidence text or advising; intent ∈ concept / advice_request / future_request / identity_request; mood for the token's expression) → guards | low |
| **news / hint** | Card text verbatim from the doc; the LLM frames only. Hint: the engine picks the clue, the LLM nudges toward the place | low |
| **summary** | Rolling summary every 6 turns (a derived `summary` event, regenerable) | low |
| **debrief** | Engine: outcome, templated forecast line, unfound clues, what-if → LLM: sound reasoning (quoting the player), overlooked notes, luck, reflection question → guards | high |
| **xp** | After reflection: score → engine clamp / quote / loss-word checks | high |

- **Structured output:** via `with_structured_output(method="json_schema")` or native structured output. Forced tool choice is not used, because it conflicts with adaptive thinking. Any node where the wrapper can't forward `effort`, refusal `fallbacks` or `cache_control` calls the `anthropic` SDK directly, and this is documented.
- **Context per call:**
  1. Stable prefix: the GatedView and campaign plan (cache breakpoint 1).
  2. Role prompt (cache breakpoint 2).
  3. Facts injected from the log every time: found clues, visited locations, challenge states, Focus, turn count, decide flag.
  4. The rolling summary plus the last 8 turns (for Buddy, its own last 6 exchanges).
  5. The player input.
- **Guards** (shared subgraph):
  - **Number guard:** allowlist built per call from the GatedView figures in all formats, plus the free numbers (dice, +2, difficulties, HP / budget, turn and Focus counts, horizon, the player's typed numbers, bare integers 1–10). After lock, outcome and what-if figures are added.
  - **Format checks:** word caps and the ending question.
  - **Leak check:** names and tickers from the alias map, normalized.
  - **Advice check:** keyword prefilter, then a low-effort classifier `{contains_recommendation, promises_profit, predicts_future}`.
  - **On failure:** one corrective retry if more than 5 s remain, otherwise the template "Let's check the numbers in the Library." A refusal stop reason counts as a guard failure.
- **Latency budget:** the writing indicator shows within 1 s; first words arrive in about 5–6 s; a 15 s cap → the `lost_thread` error.

### 2.8 Media

- **Art (Nano Banana):**
  - **Prompt:** a fixed `STYLE_GUIDE` (palette, lighting, viewpoint, detail, aspect ratio) + the scrubbed `art_subject` + a fixed negative block (no logos, text, signage, people or faces) + the repo style-anchor image as the reference.
  - **Jobs:** one asyncio background job per campaign location after setup, with a 60 s timeout and 1 retry.
  - **Storage:** `/data/art/{campaign}/{location}.webp`, with status in the DB and `art_ready` sent over SSE / state.
  - **Recovery:** pending jobs are rescanned at startup; failures keep the placeholder.
  - **Sample campaign:** ships with pre-generated art.
  - **Fixed locations (Tavern, Market Square, Library):**
    - Constant backgrounds are shipped as static frontend assets (`frontend/public/backgrounds/{tavern,market-square,library}.webp`), shared by every campaign.
    - They may be produced once with the same Nano Banana style guide; the team delivers the final files.
    - The opening scene always starts in the Tavern.
  - **Placeholder:** a plain dark backdrop with the location name, used for any missing background. There is no drawn placeholder art.
- **Voice (Gemini TTS):**
  - Two fixed voices, `dm` and `buddy`.
  - Audio is synthesized per sentence from guarded stored text only, and cached by hash(text, voice) on the volume.
  - Fallback: the browser Web Speech API with two distinct voices (pitch/rate variation if only one exists).

### 2.9 Frontend

**Routes** (all under `QuestLayout`; moves inside the quest use `replace` except `/quest/hero`):

| Path | Screen |
|---|---|
| `/quest` | `QuestEntry` resolver: `GET /hero` → 404 → `/quest/hero/new`; otherwise `GET /campaigns/{active}` or `/quest/interests` |
| `/quest/hero/new` | Create your hero |
| `/quest/interests` | What are you into? (replaces the stub; drop its `saveProgress(path, null)`) |
| `/quest/play` | Scene (+ dice card, Buddy panel, journal sheet, news card overlays) |
| `/quest/commit` | Commit form |
| `/quest/reveal` | Time skip → reveal (chart) |
| `/quest/debrief` | Debrief + What if… |
| `/quest/reflect` | Reflection |
| `/quest/company` | Company reveal |
| `/quest/xp` | XP + Finish quest |
| `/quest/hero` | Hero screen (pushed) |
| `/quest/journal/:campaignId?` | Journal of a finished campaign |

- **Navigation from the server:**
  - A single `phaseToPath` function maps phases to routes.
  - A `PhaseGuard` redirects every screen to the server phase's route, so the server wins over a stale `lastPath`.
  - `QuestCard` behaviour is unchanged (Start → `/quest`; Continue → `resumePath`, then reconciled by `PhaseGuard`).
- **Local storage:**
  - `fq.quest.v2` = `{v: 2, status, lastPath, campaignId, savedAt}`. A v1 record is migrated: status and lastPath are kept and `campaignId` is set to null, then resolved via `GET /hero`. Any other version is discarded.
  - `fq.session.v1` holds the session id; `fq.voice.v1` holds the voice preference.
  - The input and Buddy drafts live in `sessionStorage`.
- **API client** (`src/api/`):
  - A `fetch` wrapper adds `X-Session-Id`, bootstraps the session, re-bootstraps once on 401, and returns a typed `ApiError`.
  - TanStack Query handles hero, campaign, journal, reveal and XP. A `useDmStream` reducer (idle / sending / streaming / lost / done) handles SSE, with a 15 s first-event timeout and `client_msg_id` retry.
  - Hand-written DTOs live in `src/api/types.ts`; types are generated from the backend's OpenAPI later.
  - The client never computes game numbers.
- **Components:**
  - `VnStage` (the scene): a `100dvh` stack of layers:
    - `SceneArt`: full-bleed background; the placeholder is swapped in with a crossfade once the image has decoded.
    - No character figures: the name tab identifies the speaker.
    - `BuddyToken`: shown beside the dialogue box when Buddy speaks.
    - `HeroStatus` and the ✕ button along the top.
    - `DialogueBox`, `ChoiceList` and `Dock` (Map, Journal, Buddy, Voice) along the bottom.
  - `DialogueBox`:
    - Name tab and pagination: replies split client-side into pages of ≤50 words at sentence boundaries.
    - Typewriter reveal driven by `requestAnimationFrame`. A tap completes the page, and a further tap advances it.
    - `aria-live="polite"` announces each completed page.
    - Voice reads per page.
  - `ChoiceList`: 3 server suggestions (sent on tap with a `client_msg_id`), "Write your own action…" (opens `ActionInput`: textarea ≥16 px with send), "I'm ready to decide" when `can_decide`, and the Focus actions.
  - `Backlog`: a bottom sheet listing all turns from the campaign state, opened by swiping down on the dialogue box or from the Journal.
  - `MapSheet`: a vellum sheet with a location list and a decorative route. It is disabled while a roll is open.
  - `TitleCard`: location name in the blackletter face; shown on the first visit only, about 1.5 s, skippable on tap.
  - Overlays and screens:
    - `DiceMoment`: full-screen, server-driven state machine. A bronze SVG d20 tumbles in for ~1 s (CSS keyframes); then the chalk-style sum vs difficulty and a blackletter "Success" / "Setback". Keen Eye, Second Look, Accept and Continue as in the spec.
    - `BuddyScene`: tapping the token in the dock plays the summon animation and places the token beside the dialogue box. Buddy speaks in the `DialogueBox` under a verdigris name tab, and a question input is shown.
    - **Placeholder token** (until team art): a verdigris coin with a gilt rim and a simple glyph.
    - **Placeholder summon:** the coin flips and lands with a soft glow, about 0.6 s, and appears without motion under reduced motion.
    - The final token art and animation (Lottie or sprite sheet, the team's choice) drop in behind the same component.
    - `JournalSheet` and `BreakingNewsCard` (a pinned broadsheet notice).
    - `SealScroll` for the commit, with a wax-seal press on lock.
    - `TimeSkipCard`.
    - `RevealChart`: TradingView Lightweight Charts, lazy-loaded, styled as an ink line on vellum.
    - `WhatIfPanel`, `XpScreen` and `HeroScreen`, presented as ledger pages.
  - QuestLayout's absolute ✕ gets a reserved header row so it doesn't overlap the status bar.
- **Voice** (`src/voice/`):
  - The `VoiceProvider { unlock(), speak(textId, text, voice), stop() }` has two implementations: Gemini audio URLs (default) and Web Speech (fallback), chosen by `VITE_TTS`.
  - `unlock()` runs synchronously in the "Find my quest" and "Continue" tap handlers (a silent `Audio` play that is reused).
  - Playback starts after `done`. `stop()` runs on send, on opening Buddy, on the toggle, and on unmount.
- **Visual design system** (functional spec 2.18; reference mock `design/visual-novel-mock.html`):
  - **Tokens:** quest-only Tailwind theme extension under a `quest` namespace, so the bank shell's tokens are untouched:
    - `lapis #22305B`, `lapis-deep #161F3D`
    - `verdigris #3E8A7E`, `verdigris-light #6FB5A8`
    - `gilt #C9A227`, `wax #A8322D`
    - `vellum #E8DCC2`, `vellum-dim #B9AE96`
    - `soot #15121A`
  - **Typefaces:** self-hosted via Fontsource: Alegreya (narration, 19 px / 1.5), Alegreya Sans (UI), Pirata One (title cards, verdicts, scroll headings only).
  - **Shapes:** the dialogue box is a lapis panel with a double gilt inner rule and a gilt name tab (verdigris for Buddy). Choices have a verdigris left rule. Scrolls and the map use a vellum surface. There are no generic card shadows and no uniform radius.
  - **Motion budget:**
    - dice tumble
    - wax-seal press
    - Buddy token summon
    - typewriter text
    - title card
    - The rest is static, and everything respects `prefers-reduced-motion`.
  - **Copy:** sentence case and plain verbs. The narrator voice lives in the dialogue, not in the controls.
  - **Art pipeline:**
    - Constant backgrounds, generated campaign backgrounds and Buddy's token follow the same illustrated style guide used for Nano Banana prompts (§2.8).
    - Placeholder silhouettes use the same palette.
    - Buddy's `mood` (neutral, thinking, cautious, cheering) maps to token states, such as a glow colour or a small badge, until the team's token art defines its expressions.
- **iOS keyboard:** a `visualViewport` → `--vvh` variable keeps the dock visible, and the input is scrolled into view on focus.

### 2.10 Configuration

| Variable | Where | Purpose |
|---|---|---|
| `ANTHROPIC_API_KEY` | Railway | Claude |
| `GOOGLE_GENAI_API_KEY` | Railway | Nano Banana art + Gemini TTS |
| `ART_MODEL`, `TTS_MODEL`, `TTS_VOICE_DM`, `TTS_VOICE_BUDDY` | Railway | Model and voice ids (config, not code) |
| `DATABASE_URL` | Railway | Connection to the shared PostgreSQL (provided by the other spec's setup) |
| `DB_SCHEMA` | Railway | `campaign` (our tables only) |
| `DATA_DIR` | Railway | `/data` volume (art, audio) |
| `CORS_ORIGINS` | Railway | Vercel production + preview + localhost |
| `DEMO_MODE` | Railway | Use the prepared setup and pre-generated art for the sample doc |
| `VITE_API_BASE_URL` | Vercel | Railway API URL |
| `VITE_TTS` | Vercel | `server` (default) or `web` |

---

## 3. Impact and Risk Analysis

**System dependencies:**

- **Spec 001 shell:** this spec relies on `QuestLayout` (blocker, ✕), `QuestCard` Start/Continue and the session unlock. Spec 001 needs an amendment so that Start goes to hero creation for new players.
- **Future specs:** the reference-document spec plugs into `ReferenceDocumentSource`. The end-of-quest savings-plan spec follows `finish`.
- **Architecture doc:** update for PostgreSQL (replacing SQLite), the `campaign` schema, the new tables, the company-reveal endpoint, TTS and `/data`.
- **Other developer's spec (PostgreSQL owner):** we depend on their container. We own only the `campaign` schema and its migrations.

**Potential risks and mitigations:**

| Risk | Mitigation |
|---|---|
| Future data or identity leaking before lock | `GatedView` only; static import test; property test scanning every payload and agent input for dates after the clock; leak guard; secret table read only by the company-reveal endpoint |
| Reference import mis-tags evidence (e.g. a later event marked G0) | Deterministic validation (dates vs checkpoints, leak list) plus mandatory human review of the validation report before a manifest is used |
| Narrator invents numbers or clues | Number guard with a per-call allowlist; the engine validates `clue_ids_given`; difficulty only from the table |
| `langchain-anthropic` doesn't forward `effort` / `fallbacks` / `cache_control`, or structured output conflicts with adaptive thinking | Request-capture test at the start; documented direct-SDK nodes |
| Guard buffering adds latency | Immediate `writing` status; DM turn at medium effort (drop to low if p95 > 6 s); deadline-aware retry; 15 s `lost_thread` + idempotent Try again |
| Setup graph slow or failing on stage | 40 s cap, fallback to the prepared setup; `DEMO_MODE`; warm the API with `POST /session` early |
| SSE buffering or backgrounded tabs on mobile | Heartbeats and no-buffer headers; client recovers via `GET /campaigns/{id}` (pending narration stored) |
| Collision with the other spec's PostgreSQL work | Own `campaign` schema and Alembic version table; never touch provisioning or other schemas; disposable test schemas; coordinate connection details before implementation |
| Shared-DB connection limits / contention | Small pool, short transactions, row locks on `campaign_run`, no transactions across LLM calls |
| Art off-style or showing logos | Fixed template + reference image + scrubbed subject + negative block; placeholder on failure; pre-generated art for the demo |
| TTS latency, cost or iOS autoplay | Per-sentence synthesis with cache; silent unlock on tap; Web Speech fallback; text always shown |
| XP rewarding profit | Outcome withheld from the evaluator context; deterministic clamp, quote and loss-word checks |
| Lost localStorage → lost hero | Accepted for the prototype; documented |
| Existing spec 001 e2e tests break | Update the listed tests as part of this feature (§4) |

---

## Decisions confirmed on 2026-11-20

- **Reference pack:** Markdown case reference + OHLCV CSV, imported into a reviewed, checkpoint-tagged manifest. The Enron pack is the sample. Library = documents; Market Square = price board; Tavern = opening briefing; Buddy analyses on-screen data and gives hints.
- **Difficulty:** an encounter's DC comes from the reference pack, with the fixed table as fallback.
- **XP rubric:** the reference pack's rubric when given, otherwise the default.
- **Buying price:** the next trading day's open after the decision date.
- **Currency:** FX is ignored and labelled on the reveal.

- **Voice:** Gemini TTS with a browser (Web Speech) fallback.
- **Storage:** server-side in PostgreSQL. The Postgres container is owned by another developer's spec; this spec uses its own `campaign` schema and never touches provisioning.
- **Replies:** checked first, then shown. "The Dungeon Master is writing…" appears at once; first words arrive in ~5–6 s.
- **Rule defaults:** the bonus lead is a 5th optional challenge; the Focus hint is not a turn; What-if adds a "Your choice" row when the player's amount matches no preset.

---

## 4. Testing Strategy

- **Backend unit and integration** (pytest; a fake LLM via the model factory):
  - Gate: hypothesis property test that no response or agent input contains data after the clock; static import test; tripwire test that no response schema field matches a `reference_secret` column.
  - Math: table tests, including the 400 / 600 / −25% → €900.00, −10.0%, 90 HP case; Spread, Don't invest and Wait; rounding at .5; Guardian vs Analyst giving the same %.
  - Dice: seed determinism; natural 20 and 1 against each difficulty; advantage; single roll per challenge; reroll sequence with no narration of the first result.
  - Flow: news trigger; `can_decide` gating; lock idempotency and the commit draft after lock (409); resume state equals the projection; finish idempotency and the item order.
  - Agents: every router branch; guard retry → template fallback, including refusal; word caps; rejection of invalid `clue_ids`; setup validation; XP clamp and quote checks.
  - API: `httpx` against the app, asserting the SSE event order.
  - Fixtures:
    - The **Enron pack** (`fq-av-001`).
    - A minimal pack.
    - Tampered manifests that must fail validation: an evidence item at G3 placed before the decision, a leak-list name in `player_text`, missing buy day after the decision date, and a rubric not totalling 100.
  - Enron-specific checks:
    - The buy price is the 2001-10-18 open of $31.95.
    - The end value is the 2001-12-31 close of $0.60.
    - €400 invested and €600 kept ends at €607.51.
    - The G1 documents appear only after the news.
    - No later-event text (restatement, inquiry, bankruptcy) is reachable before lock.
  - Database: each test run creates and drops its own `campaign_test_<uuid>` schema in the configured PostgreSQL; a check that migrations touch only that schema.
- **Live LLM evals** (`pytest -m live_llm`, not in CI):
  - The five safeguard prompts from functional spec 2.16, plus prompt injection, "spell the ticker" and "give me 100 XP", × DM and Buddy, 5 runs each.
  - Post-guard failures must be **0**; raw-model failures are reported separately.
- **Frontend unit** (Vitest + RTL + MSW): questStore v2 and migration; `phaseToPath`; the SSE parser across chunk boundaries; the 15 s timeout (fake timers); hero-name validation; DiceCard branches per class; voice providers with mocked `Audio` and `speechSynthesis`; QuestEntry routing.
- **Frontend e2e** (Playwright, against a mocked API via `page.route` serving SSE bodies, deterministic dice):
  - Happy path through to Finish.
  - Analyst setback → reroll; Investigator Keen Eye.
  - Timeout → Try again.
  - Continue mid-scene and after a reload.
  - Commit validation messages.
  - Reveal numbers for the worked example.
  - Debrief / What-if / company reveal order.
  - Voice toggle remembered.
  - Six viewport projects as today.
- **Existing tests to update** (Start → "Create your hero" for a new player, or a mocked existing hero → "What are you into?"):
  - `e2e/acceptance.spec.ts`: 2.2-AC1, 2.6-AC6, 2.7-AC1/2/4/6/8, and 2.9-AC4 (indirect).
  - `e2e/smoke.spec.ts`: the quest-entry tests and the `leaveQuest` helper.
  - `e2e/layout.spec.ts`: the quest-stub overflow check.
  - `src/quest/QuestLayout.test.tsx`.
  - `questStore.test.ts`: the wrong-version case becomes v1 → v2 migration.
- **Manual pre-stage checks:** a real iPhone (Safari) for audio unlock and voices, the keyboard over the input, safe areas and swipe-back; a real Android device; a full campaign under 15 minutes.
