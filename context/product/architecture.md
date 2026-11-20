# System Architecture Overview: Finance Quest (working title)

- **Version:** 1.2 (LangGraph for agent orchestration, `langchain-anthropic` for Claude calls)
- **Status:** Proposed
- **Inputs:** `context/product/product-definition.md`, plus the principles, components and data model given with `/awos:architecture`.
- **Codebase evidence:** none. The repository holds no source, manifests, infrastructure or CI config yet, so nothing below comes from existing code.

> **How to read this:** choices that came from the brief are unmarked. Choices tagged _(assumption)_ are best-practice defaults that fill a "TBD" or a gap, each with alternatives listed. Confirm or replace them.

---

## 0. Architectural Principles (non-negotiable)

1. **Deterministic code owns all data and every number.** Prices, dates, returns, portfolio values, scores and outcomes come only from the Engine. Claude narrates, advises and judges reasoning. It never produces a price or a result.
2. **Agents only see anonymized data up to `story_date`.** The real identity (the alias map) and every data point after `story_date` stay on the server. The alias map is released only at the reveal.
3. **Every player action is an event.** The debrief, the "checked vs. missed signals" view and the rewind are computed from the event log, never from model memory.
4. **No investment recommendations.** Guardrail system prompts plus an output check on every agent response (see §5).
5. **The hidden future is enforced by the server, not by the UI.** API responses never contain data past the current story clock. Hiding it in the frontend doesn't count.

---

## 1. Application & Technology Stack

- **Frontend framework:** React 18 + TypeScript + Vite, built as a mobile-first single-page app and deployed on Vercel (see §3).
  - **Mocked Commerzbank / StartDepot shell:** static React components (top bar, tab bar, StartDepot overview, savings-plan screen) with no real authentication. Branding assets are used only for the demo mock-up, with the challenge sponsor's approval.
  - **Styling:** Tailwind CSS. _(assumption; alternative: CSS Modules)_
  - **Price chart:** TradingView Lightweight Charts, which suits financial time series, is small and works with touch. _(assumption; alternatives: Recharts, Apache ECharts)_
  - **Presentation page:** a separate route (`/stage`) that renders the player app inside a phone frame, next to a QR code linking to a fresh session on the audience's own phones. The QR code is rendered client-side with `qrcode.react`. _(assumption)_
- **Backend API:** Python 3.12 + FastAPI + Pydantic v2, chosen so the API, engine, generator and data pipeline share one language and one set of data models. _(assumption; brief suggests Python; alternatives: Litestar, Django Ninja)_
  - **Streaming:** Server-Sent Events, so CommerzBuddy and Campaign Master text appears as it is generated, after it passes the guards (see §5). The frontend calls the Railway API directly, not through a Vercel rewrite, so long-lived streams aren't cut off by proxy timeouts.
  - **CORS:** the API allows only the Vercel production domain, Vercel preview domains for this project, and `localhost` in development.
- **Engine (deterministic core, Python module):**
  - **Story clock:** the current `story_date` for each player session. It only moves forward through explicit engine transitions (start, time skip, rewind branch).
  - **Hidden-future gate:** a single filter function that every outbound payload passes through, both API responses and agent inputs. It drops any timeline item, price point or signal dated after the current story clock.
  - **Portfolio math:** position value, return and drawdown over the scaled price path. Uses pure functions with `Decimal` arithmetic.
  - **Forecast scoring:** compares the player's stated expectation and confidence range (`confidence_low`/`confidence_high`) with the realized outcome (whether it landed inside the range, and by how much it missed). It also tracks calibration across one-shots.
  - **Event log writer:** an append-only record of every player action.
  - **Rewind simulator:** replays alternative actions (hold, sell, buy more, or a savings plan) over the same real price path using the portfolio math. The output is a set of numbers the Campaign Master may narrate but not change.
- **Campaign Generator (Python module):**
  - **Candidate search:** maps player interests to a sector or theme list, then picks companies from a curated universe. _(assumption: a hand-curated list of about 50–150 liquid, well-known companies for the prototype)_
  - **Arc heuristic:** scans price history for "lesson" windows, for example a drawdown of at least 25% followed by recovery within 6–24 months, or a sharp drop that keeps falling. Sets `story_date` just after the drop and `reveal_date` at the end of the arc. Thresholds live in configuration. _(assumption)_
  - **Timeline builder:** assembles prices, news items and company-card facts into a single scenario timeline, and tags each item as a **signal** (a hint that matters for the lesson) or noise.
- **Anonymization service (Python module):**
  - **Alias map:** real name, ticker, people, products and places mapped to invented aliases. It is stored on the server only.
  - **Date shift:** one random offset per scenario applied to every date. Relative spacing between events is kept, and the absolute year is hidden.
  - **Price scale:** one random multiplier per scenario applied to every price. Percentage moves are kept and absolute levels are hidden.
  - **Fact scrubbing (text):** a deterministic dictionary replacement from the alias map, followed by a Claude rewrite pass that removes indirect identifiers (famous product names, distinctive events). The rewrite runs through the Number Guard, so no new figures can appear.
  - **Fact scrubbing (images):** no real logos or photos are used. Scene art is generated from scrubbed prompts only (see §4).
  - **Re-identification test:** Claude acts as an adversary, receives the full anonymized scenario and is asked for its top-3 guesses of company and period. If the real company appears in its guesses, the scenario is rejected and regenerated, or rescrubbed with the leaking facts removed. The test result and attempt count are stored with the scenario. This complements the human re-identification test in the product definition.
- **Agent orchestration framework: LangGraph (Python).** Every multi-step agent flow is a LangGraph `StateGraph` with a typed state (Pydantic model or `TypedDict`). The flows are fixed graphs with explicit nodes and conditional edges, not open-ended autonomous agents, so each step is visible and testable.
  - **Claude calls inside nodes:** LLM nodes call Claude through `ChatAnthropic` from `langchain-anthropic`, using LangChain message types throughout the graphs.
    - **Structured output:** `ChatAnthropic.with_structured_output(<Pydantic model>)` for the Campaign Master judgment and debrief, the re-identification guesses and the advice check.
    - **Newer API features:** `effort`, refusal `fallbacks` (with their beta header) and prompt-cache breakpoints are passed through `ChatAnthropic`'s pass-through options (for example `model_kwargs` or content-block `cache_control`) wherever the wrapper has no named parameter for them. ⚠️ When implementation starts, check that the installed `langchain-anthropic` version forwards each of these correctly. If one isn't supported, that single node may call the official `anthropic` SDK directly as a documented exception.
    - **Refusals:** nodes check the response's stop reason (in `response_metadata`) before using the content, and treat a refusal like a failed guard.
  - **Deterministic nodes:** Engine steps (gate, scoring, signal diffing, simulator) are plain Python nodes in the same graphs. They never call a model.
  - **Graphs:**
    1. **Campaign generation graph:** `select_candidates → find_arc → build_timeline → anonymize → scrub_text (LLM) → reid_test (LLM)`, with a conditional edge from `reid_test` back to `scrub_text` (rescrub leaking facts) or to `select_candidates` (new company or period). Attempts are capped (default 3), then the graph falls back to a prepared fixture.
    2. **Agent turn graph (shared by CommerzBuddy and the Campaign Master's story beats):** `build_gated_context → call_agent (LLM) → number_guard → advice_check (LLM) → leak_check`. Any failed guard routes back to `call_agent` once with a corrective note, then to `templated_fallback`.
    3. **Debrief graph:** `compute_outcome → score_forecast → diff_signals → simulate_rewind_branches` (all deterministic) `→ campaign_master_debrief (LLM) → guards → assemble_debrief`.
  - **Invocation model:** one graph run per HTTP request. The player's decision arrives as a normal API call, so the prototype doesn't need LangGraph's human-in-the-loop `interrupt`.
  - **State and memory boundary:** graph state lives only for the duration of a run. If a checkpointer is used for debugging or retries, it is never the source of truth: the event log and the scenario tables are (§0, principle 3). The rewind is built by the Engine's simulator from the event log, not by LangGraph's checkpoint "time travel".
  - **Streaming:** text is streamed to the API layer from the graph with LangGraph's stream modes (`messages` for model tokens, `custom` for guard status), and passed on to the client over SSE only after the guard nodes pass.
- **Agents (Claude API, run as nodes in the LangGraph graphs above):** neither agent runs an autonomous tool loop. Each receives structured JSON built by the Engine, already passed through the hidden-future gate, and nothing else.
  - **Campaign Master:** writes story beats, judges the player's reasoning against the scenario's signals, and runs the debrief. Returns **structured output** (a JSON schema enforced with `output_config.format`), for example `{judgment_quality, reasoning_feedback, luck_factor_explanation, rule_of_thumb, narration}`. Every number shown in the debrief is filled in by the Engine.
  - **CommerzBuddy:** answers player questions and explains concepts (volatility, diversification, savings plans) using the anonymized data room. It never chooses an action for the player. Streamed responses.
  - **Model:** `claude-opus-5-5` for every role (Campaign Master, CommerzBuddy, scrub rewrite, re-identification adversary, advice check), with effort tuned per route. _(assumption)_ Effort is `low` for CommerzBuddy chat and the advice check, `medium` for scrubbing, and `high` for the Campaign Master's judgment and debrief and for the re-identification adversary. Adaptive thinking is on, the default for this model.
  - **Reliability:** server-side refusal fallbacks (`fallbacks: "default"`) are on, and the code checks `stop_reason` before reading content. Prompt caching covers the frozen system prompt and the per-scenario JSON, which is reused across a player's questions.
- **Number Guard (Python module, used as a LangGraph guard node):** extracts every numeric token (amounts, percentages, dates, multipliers) from agent text and checks each against an allowlist the Engine built for that call, allowing for formatting differences such as "−32%", "32 percent" or "€1,250". Any unknown figure causes one regeneration with a corrective note. If the second attempt also fails, the user sees a templated fallback message. Rejections are logged.

---

## 2. Data & Persistence

- **Primary store:** SQLite through SQLModel/SQLAlchemy, a single file that is enough for a hackathon prototype and an on-stage demo. _(assumption; alternative for a pilot: managed PostgreSQL such as Supabase or Railway Postgres, with the same models)_
- **Core data model:**
  - `Player(id, preferences, budget, horizon, skill_level_estimate)`. Anonymous, identified only by a session token (§4, Authentication). No personal data.
  - `Scenario(id, alias_map [server-only], date_shift [server-only], price_scale [server-only], timeline, story_date, reveal_date, signals[], reid_result, source_snapshot_id)`
  - `Event(id, player_id, scenario_id, type, item_id, payload, timestamp)`. Append-only. Types include `open_chart`, `open_news`, `open_company_card`, `ask_buddy`, `submit_decision`, `time_skip`, `rewind_branch`, `reveal`, `savings_plan_setup`.
  - `Decision(id, player_id, scenario_id, text, action, expected_outcome, confidence_low, confidence_high, timestamp)`
  - `Outcome(scenario_id, player_id, price_path, portfolio_result)`. Computed by the Engine.
  - `Debrief(player_id, scenario_id, judgment_vs_luck, checked_signals, missed_signals, rule_of_thumb)`. `checked_signals` and `missed_signals` are derived from `Event` and `Scenario.signals`. Claude only writes the narrative fields.
- **Secrecy boundary for the alias map:** server-only fields live in a separate table (`ScenarioSecret`) that never maps to a response schema. Outbound Pydantic models are separate classes with no secret fields, so a secret field can't leak through accidental serialization. Only the `/reveal` endpoint reads `ScenarioSecret`, and only after a `submit_decision` event exists for that player and scenario.
- **Source data cache:** raw connector results (price series, metadata, news) are cached as Parquet or JSON files keyed by `(source, ticker, range)`, with a fetch timestamp, so generation can be repeated and works offline on stage. _(assumption)_
- **Prepared campaigns (stage demo):** about 2–3 fully generated, re-identification-tested scenarios exported as versioned JSON fixtures in the repo and loaded at startup. The interest picker maps to the closest fixture, and live generation is an optional side path (see product definition §3.1).
- **Analytics:** pilot metrics (savings-plan setup rate, staying invested through a drawdown, calibration over one-shots) are computed by queries on `Event` and `Decision`. There's no separate analytics store.

---

## 3. Infrastructure & Deployment

- **Frontend hosting:** Vercel serves the static Vite build (player app, mocked StartDepot shell, `/stage` presentation page and static assets such as CommerzBuddy sprites and pre-generated scene art). Every pull request gets a preview deploy. The SPA needs a catch-all rewrite to `index.html` so deep links like `/stage` work.
- **Backend hosting:** Railway runs the FastAPI service in one Docker container, with a persistent volume for the SQLite file and source cache.
- **Containerization:** a Python-only Dockerfile for the API. Vercel builds the frontend itself, so the API image needs no Node stage.
- **Wiring:** the frontend reads the API base URL from `VITE_API_BASE_URL`, set per Vercel environment (production, and preview pointing at the same Railway service). _(assumption: one shared Railway API for both Vercel environments during the hackathon)_
- **Environments:** `local` (`uvicorn` + `vite dev`, Vite proxying `/api` to avoid CORS), `preview` (Vercel previews against the Railway API) and `stage` (Vercel production + Railway). _(assumption)_
- **Secrets:** environment variables in Railway (`ANTHROPIC_API_KEY`, the Google GenAI key for image generation, data-provider credentials). Vercel holds only `VITE_API_BASE_URL`, which is public anyway; no secret ever goes into the frontend build. None are committed to the repo.
- **Data pipeline execution:** offline CLI scripts (`python -m pipeline.fetch …`, `python -m generator.build …`) run by the team to fill the cache and prepare campaigns. Live generation in the app reads only from the cache, so the stage demo never depends on an external data API responding live. _(assumption)_
- **Stage resilience:** prepared fixtures are bundled into the API image and pre-generated scene art into the frontend build, so agent calls are the only live dependency. A "demo mode" flag pins the fixture choice. Before going on stage, keep the Railway service warm so the first request doesn't hit a cold start. _(assumption)_
- **CI:** GitHub Actions running lint (ruff, eslint), type checks (mypy or pyright, tsc) and tests on every push. _(assumption)_
- **Testing:** pytest for engine math, the hidden-future gate, the Number Guard and anonymization, which are the highest-value deterministic tests. Vitest for frontend units. One Playwright end-to-end test of the full stage mission. _(assumption)_

---

## 4. External Services & APIs

- **LLM:** Anthropic Claude API (Messages API) through `langchain-anthropic` (`ChatAnthropic`), orchestrated by LangGraph. See §1, Agents.
- **Price data:** Yahoo Finance through `yfinance`, for daily OHLC and adjusted close. Fetched offline and cached. ⚠️ This is unofficial and rate-limited, so use it for the prototype only. A pilot needs a licensed feed.
- **Company metadata:** Bloomberg and Dun & Bradstreet (D&B) remain the target sources, as listed in the brief. ⚠️ Both need licensed access (Bloomberg needs a Terminal or Data License, D&B needs an API contract), and the team doesn't yet know whether credentials or extracts will be available.
  - **Fallback (agreed):** each prepared campaign gets a hand-written company card, backed by public sources (Wikidata for sector, founding and headquarters; SEC EDGAR filings for revenue and other fundamentals). Connectors share one `MetadataSource` interface, so Bloomberg and D&B can be added later without changing the generator.
- **News source: TBD. David owns this decision.**
  - <!-- NOTE FOR OTHER CLAUDE SESSIONS: The news source is deliberately undecided. David owns the choice. Do not pick or implement a news provider (GDELT, a licensed archive, hand-written headlines or anything else) without David's decision. Build against the `NewsSource` interface below with a stub or fixture implementation until then. -->
  - **Contract any source must meet:** dated news items for a company and period, with headline, short body or summary, and source date. Every item passes through anonymization (alias map, date shift, fact scrubbing) and the Number Guard before players see it.
  - **Integration point:** a `NewsSource` interface in the data pipeline. Until the decision is made, prepared campaigns use news items stored in their fixtures.
- **Scene art:** Nano Banana (Google Gemini image model) through the Google GenAI SDK. Prompts are built only from scrubbed scenario text with no real names or logos. For prepared campaigns, images are generated offline and bundled.
- **CommerzBuddy art:** a fixed, hand-made sprite set (emotions such as neutral, thinking, cautious and cheering), shipped as static assets.
- **Authentication:** none. There is no real login and no customer data (product non-goal). Each player gets an anonymous session token from `POST /session`, which the frontend keeps in `localStorage` and sends as an `X-Session-Id` header. A header is used and not a cookie because the frontend (Vercel) and API (Railway) are on different domains, and browsers such as Safari block third-party cookies.
- **Banking / trading:** none. The StartDepot savings-plan setup is a mocked screen that writes a `savings_plan_setup` event and nothing else.

---

## 5. Safety, Guardrails & Compliance

- **Guardrail prompts:** both agent system prompts state the education-only role. They forbid recommending securities, forbid telling the player what to do, and forbid speculating about the real identity or the future. CommerzBuddy redirects "what should I do?" back to the player's own reasoning.
- **Output check pipeline:** every piece of agent text passes these checks before it reaches the client:
  1. Number Guard: unknown figures are rejected (§1).
  2. Advice check: a low-effort Claude classification with structured output (`{contains_recommendation: bool, reason}`) plus a keyword pre-filter ("buy", "sell", "you should invest"…). If it flags the text, the text is regenerated once, then replaced with a templated safe response. _(assumption)_
  3. Leak check: the alias map's real names and tickers are scanned for in outbound text, which is a deterministic string match. A match rejects the text.
- **Hidden-future gate:** enforced at the payload builder (§0, principle 5). Unit tests assert that no API response or agent input contains a date later than the story clock.
- **Disclaimers:** a persistent "Education only — not investment advice" label in the UI, plus a clear message at the reveal and savings-plan steps.
- **Privacy:** no personal data is collected. Free-text answers are stored only against the anonymous session ID. _(assumption: free-text answers are deleted after the event unless the sponsor wants anonymized samples)_

---

## 6. Observability & Monitoring

- **Logging:** structured JSON logs from FastAPI with a request ID and session ID. _(assumption: stdlib `logging` with a JSON formatter, or `structlog`)_
- **Agent telemetry:** each Claude call logs graph, node, model, effort, token usage (`usage_metadata`, including cache reads), latency, `stop_reason`, and guard outcomes (Number Guard, advice, leak). This drives prompt tuning and cost tracking.
- **Graph tracing:** LangSmith tracing is optional and off by default. If it is turned on, it may only be used in local development and with anonymized scenarios, because traces are sent to an external service. _(assumption)_
- **Product analytics:** the `Event` table is the single source for funnel and pilot metrics, and a small admin page or SQL script reports them. _(assumption)_
- **Error tracking:** Sentry free tier for the frontend and backend. _(assumption; optional for the hackathon)_
- **Demo health check:** a `/healthz` endpoint that checks the database, fixtures loaded, and that the Claude API is reachable, for a pre-stage smoke test.

---

## 7. Request Flow (reference)

1. **Start:** the player picks interests. The Generator returns a prepared fixture (demo mode) or builds a scenario from cached data, then anonymizes it and runs the re-identification test. The Engine sets the story clock to `story_date`.
2. **Investigate:** the Data Room calls `GET /scenario/{id}/view`. The hidden-future gate filters the response, and each item the player opens logs an `Event`.
3. **Ask CommerzBuddy:** the Engine builds the JSON context (anonymized, gated). Claude's answer streams through the guards to the client, and an `ask_buddy` event is logged.
4. **Decide:** `POST /decision` stores the `Decision` and logs `submit_decision`.
5. **Time skip:** the Engine advances the clock to `reveal_date` and computes `Outcome` and the forecast score.
6. **Debrief:** the Engine computes checked and missed signals from events and the luck factor from the outcome versus decision quality. The Campaign Master turns that into narrative, structured, Number-Guarded output. The rewind runs on the Engine's simulator.
7. **Reveal:** `GET /reveal` returns the alias map, real dates and real prices, only after a decision exists.
8. **Savings plan:** a mocked StartDepot screen logs `savings_plan_setup`.
