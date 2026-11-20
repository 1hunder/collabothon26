# Tasks: Disguised Real-History Scenarios with a Recognition Check

Spec: `context/spec/002-anonymization-reid-gate/`. Shared contract: `context/product/shared-contracts-002-003.md` (wins on conflicts).

Plan approved for execution by the user's `/awos:implement` instruction ("implement both specs to the end… no need to stop") on 2026-11-20.

Notes:
- The team's 61-case collection and the sandbox scripts are not in this repository, so intake and batch runs are built and tested with a fake LLM and small fixture cases.
- Live runs need `ANTHROPIC_API_KEY` in `.env`.

---

- [x] **Slice 1: Backend skeleton, database and session**
  - [x] Create `backend/` (uv, Python 3.12, package `financequest`).
    - **Config:** `config.py` (Pydantic Settings incl. every threshold from 2.8), `db/session.py`, SQLModel models base.
    - **Alembic:** the base migration contains every spec-002 table (source_case, source_beat, price_series, check_run, attempt, guess, case_result, scenario incl. `source` + `manifest`, scenario_secret incl. `leak_terms`). It also contains the shared `event` and `decision` tables with the full columns from the shared contract §3.
    - **API:** FastAPI app with CORS, `POST /session` (UUID session row/table), the `X-Session-Id` dependency and `/healthz`.
    - **Tooling:** `cli.py` (Typer) with `db upgrade`; ruff, mypy, pytest config; `.env.example`; `.gitignore` for `.env`.
    - **Tests:** session issue/validate, healthz. **[Agent: python-backend]**
  - [x] Add `docker-compose.yml` at the repo root (`db`: postgres:16-alpine, named volume, localhost-only port 5432 or `PG_PORT`, healthcheck, creds from `.env`) and `backend/Dockerfile` (python:3.12-slim, non-root, bundles migrations + fixtures). Add a GitHub Actions backend job (postgres:16 service, ruff, mypy, `alembic upgrade head`, pytest with fake LLMs). **[Agent: vercel-railway-infra]**
  - [x] Verify: `docker compose up -d db`; `uv run alembic upgrade head` on an empty DB; `uv run pytest`; start uvicorn in the background (record PID) and `curl -X POST /session` → session id, `curl /healthz` → ok; stop uvicorn by PID; leave the db container running for later slices. **[Agent: qa-testing]**

- [x] **Slice 2: Deterministic disguise, final scan, matching and verdict**
  - [x] Implement `engine/disguise.py`:
    - `NumberPlan`:
      - price factor so the max is ≤ 10,000, with 3–4 integer digits
      - story days: gaps × U(0.7, 1.3), rounded to whole weeks, minimum 7, with a linear re-time
      - crc32 seed + run salt
      - **one shared money factor** for all money families
      - own factors for other families
      - 2 significant figures, ≤ 10,000
    - Daily-series transform and placeholder filling (`{A1}` tokens; a stray digit fails).

    Also implement `engine/gate.py` (drop points after story today), `reid/scan.py` (final scan per tech 2.3), `reid/match.py` (normalisation, aliases, substring ≥ 4), `reid/rules.py` (verdict, routing, skip rules, size/fame bands) and `report/stats.py`.

    Unit and hypothesis tests as listed in tech §4. **[Agent: python-backend]**

- [x] **Slice 3: Intake and gate graphs, batch runner, report and CLI (fake-LLM runnable)**
  - [x] Implement `reid/graph.py`:
    - `intake_graph`: split → extract `SourceCaseDraft` → validate.
    - `gate_graph`: plan_numbers → write_disguise → fill_and_scan → guess_memory (3 personas, in parallel) → judge_memory → guess_web (`web_search`, `max_uses` 12) → judge_web → record_attempt, with routing up to 3 attempts and rewrite mode from clues.
    - Prompts live in `reid/prompts/`.
    - `ChatAnthropic` (`claude-opus-5-5`) behind a model factory with a scripted fake model.
    - Structured outputs with a fallback when the server tool conflicts; the direct `anthropic` SDK is allowed for `guess_web`.
    - Telemetry per call.

    Graph tests with the fake model: pass first; fail then pass; three fails → rejected; scan fail; refusal; web skipped after a memory fail. **[Agent: langgraph-agents]**
  - [x] Implement `pipeline/intake.py`, `pipeline/prices.py` (yfinance → Parquet cache with gap flags; the network is mocked in tests), `pipeline/fx.py`, `pipeline/sources.py` (fixture `NewsSource`), `reid/batch.py` (asyncio semaphore, resumable, commit per case) and `report/render.py` (Jinja HTML + JSON, exact header line).

    CLI commands: `intake`, `prices fetch`, `check run --dry-run-fake-llm`, `report build`, `fixtures export/import`.

    Add 3 small fixture source cases (fictional + 1 real famous) so a fake-LLM batch runs end to end. **[Agent: python-backend]**
  - [x] Verify:
    1. Run `check run --dry-run-fake-llm` on the fixture cases.
    2. Run `report build`.
    3. Open the report: the summary line has the exact format, and there are per-case attempts and the skipped list.
    4. Export the fixtures.
    5. Delete the temporary report files. **[Agent: qa-testing]**

- [x] **Slice 4: Player API for scenarios and the gated reveal**
  - [x] Implement routers:
    - `GET /scenarios/playable`: `{id, industry_shown, source}`.
    - `GET /scenario/{id}/view`: gated, story days only, no secrets.
    - `POST /scenario/{id}/events`.
    - `GET /scenario/{id}/reveal`: 403 unless a `decision` and a `debrief_complete` event exist for the session and scenario. The body has no disclaimer, and `n_guessers` may be 0.

    Separate outbound models. Contract test: no `scenario_secret` key appears in non-reveal responses.

    Load exported fixtures at startup into `scenario` / `scenario_secret`. **[Agent: python-backend]**
  - [x] Verify with curl against a running API on the fixture data:
    - playable list
    - view (no dates, no real name)
    - reveal → 403
    - insert a decision + `debrief_complete` → 200

    Stop the API by PID. **[Agent: qa-testing]**

- [x] **Slice 5: Shared frontend pieces**
  - [x] Add to `frontend/src`:
    - **API client:** `api/client.ts` (`VITE_API_BASE_URL`, `X-Session-Id` from `POST /session` stored as `fq.session.v1`, typed errors incl. `RevealLocked` on 403, `VITE_API_MODE=fixture|live` with fictional-only fixtures in `api/fixtures/`) and `api/types.ts`.
    - **Shared helpers:** `quest/lib/storyNumber.ts` (≤ 10,000, no suffixes, `formatStoryDay`) and `quest/components/StoryChart.tsx` (lazy Lightweight Charts, story-day axis, news markers, real-date mode).
    - **Disclosure:** `quest/components/DisclosureNote.tsx`.
    - **Reveal:** `quest/screens/Reveal.tsx`:
      - real name and dates
      - real chart with markers
      - news table
      - "What we changed"
      - the testers sentence only when `n_guessers > 0`
      - no disclaimer, no buy button

      Styled with quest tokens. Plus `quest/RevealGuard.tsx` (server 403 → redirect).

    Vitest/RTL tests per tech §4. **[Agent: react-frontend]**

- [x] **Slice 6: Feature Testing & Regression**

  > Verifies the whole feature end-to-end against functional-spec.md, run after all implementation slices are complete.
  - [x] Read functional-spec.md acceptance criteria in full. Generate acceptance-level tests that verify the entire feature as a whole — not individual slices. Cover applicable layers (unit for pure logic, integration for service interactions, e2e for user flows) based on the project's testing stack. Write tests with RED validation (must fail before implementation is confirmed done). Annotate each test with `@spec: 002-anonymization-reid-gate` and `@regression` if suitable for long-term regression. **[Agent: qa-testing]**
  - [x] Run all generated tests. All must pass. Fix any failures before proceeding. **[Agent: qa-testing]**
