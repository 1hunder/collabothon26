# Technical Specification: Disguised Real-History Scenarios with a Recognition Check

- **Functional Specification:** [functional-spec.md](./functional-spec.md)
- **Status:** In Review
- **Author(s):** Davyd, with Claude (python-backend, langgraph-agents and vercel-railway-infra specialists; frontend section drafted by the orchestrator because the react-frontend agent was not loaded in this session)

> **Shared contracts:** this spec is implemented in parallel with spec 003 (campaign engine). Ownership, shared tables, routes, display rules and the mission order are fixed in [`context/product/shared-contracts-002-003.md`](../../product/shared-contracts-002-003.md). Where this document disagrees with it, the contract wins.

---

## 1. High-Level Technical Approach

The project gets its first backend: `backend/`, a Python 3.12 package `financequest` managed with `uv`. Its main job is an **offline batch pipeline**, run by the team from the CLI, with these steps:

1. **Intake.** Claude extracts structured source cases from the team's case collection (the 61 cases plus about 39 extra). Daily prices come from yfinance and are cached.
2. **Check.** One **LangGraph** gate graph runs per case, for at most 3 attempts. Each attempt runs these steps in order:
   - code plans every number;
   - the Claude writer produces disguised text with number placeholders;
   - code fills the placeholders and runs the final scan;
   - 3 Claude guessers answer from memory;
   - if they all miss, the same 3 guessers try again using Claude's server-side `web_search` tool (up to 12 uses each);
   - code applies the pass/fail rules.
3. **Store.** Runs, attempts, guesses and results go into **PostgreSQL**, run in a container locally and as Railway's managed Postgres when deployed.
4. **Report.** A static HTML/JSON check report is built from the database.
5. **Export.** Approved scenarios are exported as versioned fixtures and served by a small **FastAPI** service, whose reveal endpoint is gated.

On the frontend, this spec adds three shared pieces to the existing Vite/React app:

- the disclosure note;
- the Reveal screen;
- shared display rules: a story-day chart wrapper and number formatting capped at 10,000.

It also adds a typed API client that has a fixture mode, so the frontend can be built before the backend is deployed.

**Confirmed stack decisions (2026-11-20):**

- LangGraph with `langchain-anthropic`.
- Claude's built-in web search tool.
- PostgreSQL in a container. This replaces the SQLite plan in architecture §2–§3; see §2.9.
- Case intake by Claude extraction plus yfinance.
- All model calls use `claude-opus-5-5`.

---

## 2. Proposed Solution & Implementation Plan (The "How")

### 2.1 Backend layout (`backend/`, package `financequest`)

| Path | Responsibility |
|---|---|
| `config.py` | Pydantic Settings: env vars and every threshold (see 2.8), recorded into each `CheckRun.config` |
| `db/models.py`, `db/session.py`, `db/migrations/` | SQLModel tables (2.2), engine/session, Alembic |
| `pipeline/intake.py` | Runs `intake_graph`; validation, tagging, skip flags; writes a spot-check CSV |
| `pipeline/prices.py`, `pipeline/fx.py` | yfinance fetch → Parquet cache with gap flags; market cap → EUR at the story year (rate recorded) |
| `pipeline/sources.py` | `MetadataSource` / `NewsSource` interfaces. **News stays fixture-backed: the news provider is David's decision (architecture §4)** |
| `engine/disguise.py` | Pure transforms: `NumberPlan` (price factor, story days, amount factors), daily-series transform, placeholder filling |
| `engine/gate.py` | Hidden-future gate for outbound payloads (drops post-story points) |
| `reid/scan.py`, `reid/match.py`, `reid/rules.py` | Final scan, guess matching, pass/fail verdict |
| `reid/graph.py`, `reid/prompts/` | LangGraph `intake_graph` and `gate_graph`; writer and guesser prompts |
| `reid/batch.py` | asyncio batch runner over cases, resumable |
| `report/stats.py`, `report/render.py`, `report/templates/` | Summary statistics; Jinja HTML (no external assets) and JSON |
| `api/main.py`, `api/deps.py`, `api/routers/` | FastAPI app, `X-Session-Id` dependency, scenario/reveal/playable routers |
| `cli.py` | Typer CLI (2.6) |
| `fixtures/` | Exported approved scenarios (versioned JSON) |
| `tests/` | pytest (section 4) |

The sandbox scripts in `../sandbox/2026-11-20_anonymization-reid-test/src/` are the reference for the scan, the matching and the jitter. They are ported and hardened, not imported.

### 2.2 Data model (PostgreSQL via SQLModel + Alembic)

The **secrecy boundary** follows architecture §2: tables marked *server-only* never map to a response schema, and outbound Pydantic models are separate classes.

| Table | Key columns | Notes |
|---|---|---|
| `source_case` *(server-only)* | id, company, ticker, exchange, country, currency, lesson, story_year, market_cap_eur, size_band, fame, identifying_terms (JSON), known_names (JSON: parent, subsidiaries, former names), status (ok/skipped/untagged), skip_reason, origin (md61/extra), spot_checked | One row per candidate |
| `source_beat` *(server-only)* | case_id → source_case, idx, real_date, real_price, headline, facts (JSON) | 2–6 per valid case |
| `price_series` *(server-only)* | case_id, ticker, first_date, last_date, n_points, gap_flags, cache_ref, fetched_at | Daily rows in a Parquet cache; rebuildable by the CLI |
| `check_run` | id, label, started_at, finished_at, config (JSON: model, thresholds, seed salt), n_cases | One per batch run |
| `attempt` | id, run_id, case_id, n (1–3), number_plan (JSON), scenario_json, scan_result (JSON), avg_readability, verdict, fail_reason (enum: real_date_found, recognised_name, recognised_date, unreadable, error) | All attempts are kept for the report |
| `guess` | attempt_id, guesser (persona), round (memory/web), top3 (JSON), start_month, start_year, start_conf, clues (JSON), readability, readability_issues, searches_used, queries, citations, recognised | One per guesser per round |
| `case_result` | case_id, run_id, final_status (approved/rejected/skipped/error), approved_attempt_id, recognised_first_attempt | The **playable list** is the latest result per case |
| `scenario` *(player-facing)* | id, case_id (nullable for reference packs), attempt_id (nullable), **source** (`gate`/`reference_pack`), invented_name, industry_shown, story_days (JSON), beats (JSON, disguised), chart_series (JSON, by story day), company_card, **manifest** (JSONB, nullable; spec 003 fills it for reference packs), status (playable/retired) | Only `playable` is served |
| `scenario_secret` *(server-only, reveal only)* | scenario_id, real_name, ticker, real_beats (JSON with real dates and prices), price_series_ref, price_factor, amount_factors (incl. money factor), seed, what_changed (JSON list), n_guessers (0 for reference packs), **leak_terms** (JSON) | Read only by the reveal endpoint and spec 003's leak guard |

**Shared `event` and `decision` tables.** This spec's first migration creates both with the **full columns from the shared contract §3**, so spec 003 can write to them without altering them:

- `event`: id, session_id, scenario_id, campaign_id, seq, type, payload, client_msg_id, ts
- `decision`: id, session_id, scenario_id, campaign_id, action, amount_cents, evidence, forecast_pct, confidence, locked_at

Spec 003 inserts the `decision` at lock and writes `debrief_complete` when the player submits the reflection. Those two rows are what unlocks the reveal.

### 2.3 Deterministic algorithms (`engine/disguise.py`, `reid/*`)

The rule throughout: **code owns every number, date and verdict. The models only write text and give guesses.**

- **`NumberPlan`.** Built once per case and reused across all attempts, so a rewrite keeps the same numbers.
  - **Price factor.** Let `max_real` be the highest value in the full daily series. Choose `f = m × 10^k`, with `m` drawn from a bounded seeded range, so that `max_real × f ≤ 10,000` and the displayed prices have 3–4 integer digits.
  - Apply `f` to every daily point, and take the beat prices from that same series. That keeps every move exact; a property test checks it stays within 1 percentage point.
  - **Story days.** Each real gap between news items is multiplied by `U(0.7, 1.3)` and rounded to whole weeks, with a minimum of 7 days. The daily series is re-timed linearly between beats.
  - **Seeding.** The seed is `zlib.crc32(case_id) + run_salt`, not `hash()`; this fixes the sandbox's reproducibility bug. The seed is stored in `scenario_secret`.
  - **Amounts.**
    - **Money:** every money amount in a case (revenue, profit or loss, cash flow, cash, debt, equity, deal size) shares **one money factor**, chosen so the case's largest money value is ≤ 10,000. Money-to-money ratios stay true.
    - **Other families:** each non-money family (users, headcount, …) gets its own factor, ≤ 10,000.
    - **Rounding:** 2 significant figures.
    - **Ratios:** ratio-type figures (for example "25% raise") are tokenised with identity scaling.
- **Placeholders.** The writer sees the real facts with each amount replaced by a family-tagged token (`{A1}`, `{A2}`, …), plus each beat's direction and size as a word (for example "down, large"), never a number. Code then fills the tokens. Any digit run left in the writer's text that isn't a token fails the scan.
- **Final scan (`reid/scan.py`).** The scan runs over prose fields only, so numeric fields can't trigger the year regex. It fails on:
  - the real name, ticker, aliases or identifying terms, matched on word boundaries and case-insensitively. Executive surnames that are also common words (for example "Deal") are matched only together with the first name;
  - a 4-digit year (`19xx` or `20xx`), a month name or abbreviation, `Q1`–`Q4`, or a weekday;
  - "million", "billion", "m" or "bn" used as units, or any amount over 10,000;
  - a phrase on the dating-superlatives list;
  - stray digits (see Placeholders);
  - a price move off by more than 1 percentage point.
- **Guess matching (`reid/match.py`).** Normalise to casefold, then strip punctuation and legal suffixes (Inc, Corp, plc, AG, SE, Ltd, N.V.). A guess is correct on an exact normalised match with the company, ticker, parent, a subsidiary or a former name. It is also correct when one of those names, 4 or more characters long, appears as a substring of the guess (the sandbox `hit()` logic).
- **Verdict (`reid/rules.py`).** An attempt fails if any of these is true:
  - the scan fails;
  - any guesser in either round names the real company among its top 3;
  - any guesser's start guess is within 3 months of the real start with confidence ≥ 30;
  - the average readability is below 3;
  - a guesser call fails after retries. This is never treated as a pass; after the retries the case is marked `error`.

  After 3 failed attempts the case is `rejected`. If the scan or the memory round fails, the web round is skipped.
- **Skip rules (intake).** A case is skipped if it has no lesson, no identifying terms or a missing price, or fewer than 2 or more than 6 beats. A case with missing tags gets `untagged`. A market cap within 5% of €2bn or €10bn is also flagged `untagged` for review.
- **Bands.** Size bands: small (under €2bn), mid (€2–10bn), large (over €10bn). Fame is `f(size_band, is_us_listed)`:
  - high: large and US-listed;
  - medium: large and not US-listed, or mid and US-listed;
  - low: everything else.
- **Statistics.**
  - N = checked cases; skipped cases are counted separately.
  - First-attempt recognition share.
  - Approved count and share.
  - Approval share per fame level and per size band.

### 2.4 Agent graphs (`reid/graph.py`, LangGraph + `ChatAnthropic`, model `claude-opus-5-5`)

**`intake_graph`**, run once, offline:

1. `split_cases` (code): one chunk per case heading.
2. `extract_case` (LLM, structured output `SourceCaseDraft`, effort low): reads one case per call. It extracts only what the text states, uses null when something is missing, and never extracts prices; prices come from the cache.
3. `validate_case` (code): applies the skip rules and tagging.

**`gate_graph`**, one case:

- **Nodes, in order:**
  1. `plan_numbers` (code, once per case).
  2. `write_disguise` (LLM, structured output `DisguiseDraft`, effort medium).
  3. `fill_and_scan` (code). If the scan fails, go to `record_attempt`.
  4. `guess_memory` (LLM, 3 guessers in parallel via `Send`, no tools, effort medium).
  5. `judge_memory` (code). If it fails, go to `record_attempt`.
  6. `guess_web` (LLM, the same 3 guessers with `web_search` bound with `max_uses=12`, effort high).
  7. `judge_web` (code).
  8. `record_attempt` (code).
- **Routing after `record_attempt`:**
  - pass → END `approved`;
  - fail with fewer than 3 attempts → `write_disguise` in rewrite mode;
  - otherwise → END `rejected`.
- **State (`GateState`):**
  - `case`: server-only, never put into the guessers' input;
  - `attempt`;
  - `numbers`;
  - `scenario`;
  - `scan_result`;
  - `guesses`;
  - `clues`: deduplicated and tagged by category (event order, ratios, timing, chart shape, industry, phrasing);
  - `attempts`: the history list, which is what gets persisted;
  - `status`;
  - `telemetry`.
- **Rewrite mode.** The writer gets the previous scenario, the tagged clue list and the fixed round-1 feedback checklist (handoff §4.4.3). It must break each cited clue: move the story to a similar industry while keeping its economic mechanism, drop or merge one non-essential detail, and avoid dating superlatives. The writer is never told which company a guesser named; it gets only the clues.
- **Guessers.** There are 3, all Claude, each with a fresh message list (no shared memory) and a short persona suffix on a shared cached prefix:
  1. a generalist analyst;
  2. a forensic reader who works from event order, ratios and earnings-calendar timing;
  3. an industry specialist who tries to detect a moved industry and map it back.

  Their input is only the disguised scenario plus a plain description of the disguise rules, never the hidden factors.
- **Schemas** (field lists):
  - `DisguiseDraft`: company_name, sector, industry, industry_moved, transplant_note, beats[story_day_index, headline, facts[] with tokens], changes_vs_previous[].
  - `GuesserReport`:
    - top3[company, ticker, confidence 0–100] (exactly 3);
    - start_month, start_year, start_confidence;
    - clues[category, text];
    - readability 1–5;
    - readability_issues[].

    Code adds searches_used, queries and citations for the web round.
- **Web search.** The tool is bound with `bind_tools([{"type": "web_search_<latest>", "name": "web_search", "max_uses": 12}])`. Queries come from the `server_tool_use` blocks and citations from the `web_search_tool_result` blocks. `searches_used` is the count of `server_tool_use` blocks, cross-checked against `usage.server_tool_use.web_search_requests`.
- **⚠️ Spike first (blocking):**
  1. **Structured output with a server tool.** `with_structured_output` forces a tool choice, which may conflict with `web_search` and with thinking. Fallback: bind `GuesserReport` as a normal tool next to `web_search` with `tool_choice=auto`, or validate JSON from the final text block with Pydantic.
  2. **Pass-through options.** Check that the installed `langchain-anthropic` forwards `effort`, `fallbacks` and the server-tool blocks. If it doesn't, `guess_web` is the documented exception and calls the `anthropic` SDK directly (architecture §1).
  3. **Organisation access.** Confirm web search is enabled for the organisation's API key.
- **Reliability.**
  - Check `stop_reason` before reading content. A refusal is retried once with `fallbacks`, then recorded as an `error` for that guesser.
  - `ChatAnthropic(max_retries=5)`, plus case-level jittered backoff on 429 and 529 errors.
  - Prompt caching (`cache_control`) on the writer and guesser system prompts.
- **Telemetry per call:** case, attempt, node, persona, effort, token counts (including cache reads and writes), web searches, latency, `stop_reason`, retries, outcome. Totals go in the report footer.

**Batch runner (`reid/batch.py`, plain asyncio):**

- A semaphore of `CHECK_CONCURRENCY` (default 4, then tune) caps the cases running at once.
- Each finished case's result is committed immediately, so `check run` resumes without redoing finished cases.
- LangGraph checkpoints are never the source of truth.

### 2.5 API contracts (FastAPI, player-facing parts of this spec only)

Every route requires `X-Session-Id`, issued by `POST /session` (architecture §4). CORS is limited to the Vercel production and preview origins plus localhost.

| Method & path | Response / behaviour |
|---|---|
| `GET /scenarios/playable` | `[{id, industry_shown, source}]`: latest-approved gate scenarios plus reviewed reference packs, `status=playable` only; never the real name |
| `GET /scenario/{id}/view` | Disguised view up to story today (gated): invented name, industry, beats `{story_day, headline, facts}`, chart points `{story_day, price}`, company card. No dates ever |
| `POST /scenario/{id}/events` | `{type}` writes an `Event` (this spec needs `debrief_complete`; 409 unless a `Decision` exists for the session) |
| `GET /scenario/{id}/reveal` | **403** unless a `Decision` and a `debrief_complete` event exist for this session and scenario. Body: `{real_name, ticker, start_date, end_date, series:[{date, price}], news_points:[{story_day, real_date, real_price, headline}], what_changed:[string], n_guessers}` (no disclaimer; `n_guessers` is 0 for reference packs, and then the frontend omits the testers sentence) |
| `GET /healthz` | Database, fixtures loaded, Claude reachable, playable count |

A contract test asserts that no field from `scenario_secret` appears in any non-reveal response.

### 2.6 CLI (`python -m financequest …`, Typer)

| Command | Purpose |
|---|---|
| `db upgrade` | Alembic `upgrade head` |
| `intake --md ../docs/gamified_investing_all_61_cases_english.md [--extra extra_cases.md]` | Extract, validate and tag cases; write `intake_spotcheck.csv` for the team |
| `prices fetch [--case ID \| --all]` | yfinance → Parquet cache, gap flags |
| `check run --label X [--cases all\|ids] [--concurrency N] [--dry-run-fake-llm]` | Run the gate over the batch; resumable |
| `report build --run ID --out report.html` | HTML and JSON report |
| `fixtures export --approved --out backend/fixtures/` | Versioned JSON of approved scenarios plus their secrets, loaded by the API at startup |

**Report format:**

- **Header (exact):** `[N] cases checked · [X]% recognised on first attempt · [Y] approved ([Z]%)`.
- **Then:**
  - approval share by fame level and by size band;
  - the playable list;
  - skipped cases with their reasons;
  - the caveat "Claude-only guessers are a weaker test than mixed providers".
- **Per case:** every attempt, with every guesser's top 3 guesses and confidence, start guess and confidence, clues, readability and fail reason.
- **Footer:** the telemetry totals.

### 2.7 Frontend (`frontend/src`)

The existing conventions from spec 001 apply: `src/quest/` never imports from `src/shell/`, steps inside the quest navigate with `replace`, and copy is in English.

| Path | Responsibility |
|---|---|
| `src/api/client.ts` | `fetch` wrapper: `VITE_API_BASE_URL`, `X-Session-Id` (session from `POST /session`, kept in localStorage behind try/catch), typed errors (403 → `RevealLocked`) |
| `src/api/types.ts` | `ScenarioView`, `RevealData`, `NewsPoint` mirroring 2.5 |
| `src/api/fixtures/` + `VITE_API_MODE=fixture` | Fixture mode so the screens can be built before the backend is deployed. Fixtures use a **fictional** company only; real identities never go into the bundle |
| `src/quest/lib/storyNumber.ts` | Shared formatter: plain grouped numbers ≤ 10,000, no million/billion/k suffixes; `formatStoryDay(n)` → "Day 84" |
| `src/quest/components/StoryChart.tsx` | Shared wrapper around TradingView Lightweight Charts with a story-day axis and optional news markers; **lazy-loaded** with `React.lazy` to keep it out of the main bundle. The Data Room spec reuses it |
| `src/quest/components/DisclosureNote.tsx` | The spec 2.7 note with a "Got it" button; shown at every mission start before the first story beat |
| `src/quest/screens/Reveal.tsx` | Route `/quest/reveal` (the company reveal in spec 003's flow, after the reflection), styled with spec 003's quest tokens:<br>• real name and dates<br>• `StoryChart` in real-date mode with news markers<br>• a news-point table (real date, real price)<br>• the "What we changed" list<br>• "Before you played, {G} AI testers tried to guess this company. None of them got it.", only when G > 0<br>• no disclaimer and no buy button |
| `src/quest/questStore.ts` | **Owned by spec 003** (`fq.quest.v2` = `{v: 2, status, lastPath, campaignId, scenarioId, disclosureSeen, savedAt}`). This spec only reads `scenarioId` and reads/writes `disclosureSeen` through the store's accessors |
| `src/quest/RevealGuard.tsx` | If the API returns 403, or the campaign phase is not yet `company`, redirect with `replace` to the server-phase route (spec 003's `PhaseGuard` logic) |

### 2.8 Configuration (env vars)

| Var | Used by | Purpose |
|---|---|---|
| `DATABASE_URL` | API, CLI, CI | Postgres DSN (normalised to `postgresql+psycopg://`) |
| `ANTHROPIC_API_KEY` | CLI (API only for `/healthz`) | Claude and web search |
| `MODEL_ID` | CLI | Default `claude-opus-5-5` |
| `GUESSERS_PER_ATTEMPT` | CLI | Default 3 (minimum 2) |
| `WEB_SEARCH_MAX_USES` | CLI | Default 12 |
| `MAX_ATTEMPTS` | CLI | 3 |
| `CHECK_CONCURRENCY` | CLI | Cases in parallel (default 4) |
| `DB_POOL_SIZE`, `DB_MAX_OVERFLOW` | API, CLI | Default 5 / 5; keep `CHECK_CONCURRENCY × pool` below Postgres `max_connections` |
| `CACHE_DIR` | CLI | Price cache |
| `DEMO_MODE`, `CORS_ORIGINS`, `LOG_LEVEL` | API | |
| `VITE_API_BASE_URL`, `VITE_API_MODE` | Vercel / Vite | API URL; `fixture` or `live` |

The thresholds (3-month window, 30%, readability 3, ±30% jitter, the 10,000 cap) live in `config.py` and are recorded into each run. `.env.example` is committed; `.env` is gitignored.

### 2.9 Infrastructure

- **Local.** `docker-compose.yml` at the repo root runs these services:
  - `db`: `postgres:16-alpine`, with named volume `pgdata`, port published to localhost only, a `pg_isready` healthcheck and credentials from `.env`;
  - `api`: optional, under compose profile `api`.

  The default loop is `docker compose up -d db`, then uvicorn, the CLI and pytest on the host.
- **Backend image (`backend/Dockerfile`).** Base `python:3.12-slim`, non-root user, dependencies installed in an early layer. It bundles the migrations and `fixtures/`. The CLI runs from the same image.
- **Railway.**
  - Two services: `api` and **Railway managed Postgres**, which comes with a volume, backups and `DATABASE_URL`. Wire it as `DATABASE_URL=${{Postgres.DATABASE_URL}}`.
  - Run `alembic upgrade head` as the pre-deploy command, and set the healthcheck to `/healthz`.
  - Production deploys and any deletion of services or volumes need the user's explicit confirmation.
- **Batch execution.** The batch runs locally against local Postgres. Then `fixtures export` writes approved scenarios to JSON, which is committed and imported into Railway (`fixtures import` or `psql` via the proxy URL). Run `pg_dump` after every batch. Freeze the dataset on Saturday night and do the final import on Sunday morning, before the 18:00 deadline.
- **CI (GitHub Actions).** The backend job has a `postgres:16` service and runs ruff, mypy, `alembic upgrade head` on an empty database, and pytest with fake LLMs, so it needs no API key. The frontend job is unchanged.
- **Architecture amendment.** Architecture §2–§3 (SQLite on a Railway volume) needs updating to PostgreSQL, as above. The Parquet price cache stays file-based and can be rebuilt.

---

## 3. Impact and Risk Analysis

**System dependencies:**

- This is the first backend in the repo. It creates the API, the session and the `Event`/`Decision` foundation that the Data Room, CommerzBuddy, decision and debrief specs will build on.
- The `StoryChart`, `storyNumber` and API client are shared frontend pieces for those specs.
- The interest picker (a separate spec) will choose from `GET /scenarios/playable`.

**Risks and mitigations:**

| Risk | Mitigation |
|---|---|
| Structured output may not work together with the server `web_search` tool through `langchain-anthropic` | Spike on day 1 (2.4). Fallbacks: a report-tool pattern, or a direct `anthropic` SDK call for `guess_web` |
| Cost and time of 100 cases with up to 12 searches per guesser. Rough estimate: about 1,400 calls; web rounds are 70–80% of the tokens; low hundreds of USD | Skip the web round after a memory fail. Cache the system prompts. Run a 5-case fake dry run, then a 2-case live smoke test with telemetry, before the full run. Set a spend limit. Resumable runs |
| Too few cases approved (famous cases always fail) | Expected. The extra cases skew to low fame. Fallback per the functional spec: add more low-fame cases, never relax the rule |
| Same-family bias (Claude writes and Claude guesses) | 3 diverse personas plus the web round; the caveat is stated in the report |
| Nondeterminism: one pass is one sample | Record raw responses. Re-running a case is allowed. Use low temperature where the API allows |
| yfinance gaps or delistings (for example Lilium), non-US currencies | Gap flags lead to Skipped: missing price. FX to EUR at the story year, with the rate recorded. Values near band boundaries are flagged untagged |
| Intake extraction drops or invents identifying terms | `spot_checked` gates the batch; the team reviews the CSV |
| Writer invents digits or leaks terms | The stray-digit and term scan fails the attempt before any guesser cost is spent |
| Real identity leaking to the client | Separate outbound models; `scenario_secret` is read only by the reveal endpoint; a contract test; frontend fixtures are fictional; the reveal is gated server-side (403), not only in the UI |
| Postgres connection exhaustion under concurrency | Pool limits; `CHECK_CONCURRENCY × pool` stays below `max_connections` |
| Data loss and stage resilience | `pg_dump` after each batch; fixtures in git and in the image; `/healthz` ping before going on stage |
| News source still undecided | Cases carry their own curated news (fixture-backed `NewsSource`); no provider is picked here |

---

## 4. Testing Strategy

- **pytest, deterministic code, no network:**
  - `NumberPlan`: maximum ≤ 10,000; same seed gives the same result across processes (subprocess with a different `PYTHONHASHSEED`); moves stay within 1 percentage point (hypothesis property test); whole weeks and gap ratios between 0.7 and 1.3; amounts rounded to 2 significant figures and ≤ 10,000.
  - Scan: a table-driven test including the false positives ("Deal" as an ordinary word, 1993 as an amount), weekdays, quarters, month abbreviations, stray digits, million/billion.
  - Matching: aliases, suffixes, tickers, parent, subsidiary, former name; the boundaries of the 3-month window and the 30% threshold.
  - Verdict, routing for attempts 1–3, skip rules, fame and size functions, and the statistics with an exact summary line.
- **Graph tests with a fake chat model.** Scripted runs: pass on the first attempt; fail then pass; fail 3 times then rejected; scan fail; refusal; web round skipped after a memory fail. Replayed real responses (with `server_tool_use` and `web_search_tool_result` blocks) test the search parsing.
- **API tests.** The reveal returns 403 without a decision and a debrief event, and 200 once both exist. No secret keys appear in view or playable responses. The gate drops post-story points.
- **Frontend.**
  - Vitest/RTL: `storyNumber` (never above 10,000, no suffixes); `DisclosureNote` ("Got it" closes it); `Reveal` (every required element, no buy button, the G sentence); `RevealGuard` (redirects before the debrief).
  - Playwright in fixture mode: the disclosure note appears at mission start; opening `/quest/reveal` before the debrief redirects to the current step.
- **Live (opt-in behind an env var).** A 2-case smoke test with Boeing 2024 (expected to fail on the first attempt) and one obscure case, to confirm the spikes, the telemetry and the cost estimate. Then a 5-case dry run and the 100-case run.
- Every new test is annotated `@spec: 002-anonymization-reid-gate` and validated RED-first (per the project's QA conventions).
