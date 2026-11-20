# Shared Contracts: Spec 002 (Disguise + Recognition Gate) ↔ Spec 003 (Campaign Engine)

- **Specs:**
  - [`002-anonymization-reid-gate`](../spec/002-anonymization-reid-gate/) (owner: Davyd)
  - [`003-campaign-engine`](../spec/003-campaign-engine/) (owner: Viktor)
- **Agreed:** 2026-11-20
- **Purpose:** let both specs be implemented **in parallel** without overlap or conflict. Where a spec's own text disagrees with this file, **this file wins**. Change it only with both owners' agreement.

---

## 1. Ownership

| Area | Spec 002 (Davyd) | Spec 003 (Viktor) |
| --- | --- | --- |
| Backend package | Creates `backend/` with package `financequest`: `pyproject`, `config.py`, `db/` (session, models base, **Alembic**), `docker-compose.yml` (Postgres), Dockerfile, CI | Adds modules inside the same package; creates no second package |
| Session | `POST /session`, `X-Session-Id` dependency, CORS | Uses them |
| Disguise and gate | `engine/disguise.py` (`NumberPlan`, including the shared money factor), `reid/*` (scan, match, rules, graphs), intake, prices, batch, report, CLI | Reuses `reid/scan.py` to scan reference packs |
| Hidden-future gate | `engine/gate.py` (drops data after story today) | Extends `engine/gate.py` with checkpoints (`GatedView(checkpoint, clock)`) |
| Scenarios | Tables `scenario`, `scenario_secret`; `/scenarios/playable`, `/scenario/{id}/view`, `/scenario/{id}/events`, `/scenario/{id}/reveal` (company reveal) | Reference-pack import writes into the same tables; plays any playable scenario |
| Shared tables | Creates `event` and `decision` **with the full columns in §3**, in its first migration | Writes to them; adds its own tables in later migrations |
| Campaign engine | — | `financequest/campaign/` (clock, dice, portfolio, what-if, XP, Focus and items, journal), `financequest/agents/` (campaign graphs), `financequest/refpack/` (import + CLI `refpack import`), `financequest/media/` (art, TTS), routers `hero`, `campaigns`, `locations`, `tts` |
| Campaign tables | — | `player`, `hero`, `hero_item`, `campaign_run`, `location`, `challenge`, `clue_state`, `outcome`, `debrief`, `xp_award` |
| Frontend: shared pieces | `src/api/client.ts` (the single fetch wrapper: session, typed errors, fixture mode), `src/api/types.ts` (002 types), `src/quest/lib/storyNumber.ts`, `src/quest/components/StoryChart.tsx`, `src/quest/components/DisclosureNote.tsx`, `src/quest/screens/Reveal.tsx` (company reveal) | Uses them. Adds TanStack Query hooks and the SSE helper in `src/api/` on top of `client.ts` |
| Frontend: quest flow | — | All `/quest/*` routing, the visual-novel screens, voice, `questStore` v2 |

## 2. One database, one migration history

- **Database:** PostgreSQL as set up by spec 002 (docker-compose `postgres:16` locally, Railway managed Postgres when deployed), in the **default schema**.
- **Migrations:** **one Alembic history** in `backend/financequest/db/migrations`. Spec 003's migrations follow spec 002's head. Before merging, rebase `down_revision` so the history stays linear.
- **Configuration:** `DATABASE_URL`, `DB_POOL_SIZE` and `DB_MAX_OVERFLOW` as defined by spec 002.

## 3. Shared tables

| Table | Columns | Notes |
| --- | --- | --- |
| `scenario` | 002's columns + **`source`** (`gate` \| `reference_pack`) + **`manifest`** (JSONB, nullable) | Gate scenarios have `manifest = null`. Reference packs fill both the 002 fields (invented name, industry shown, story days, disguised beats, story-day chart, company card) and `manifest` (checkpoints, evidence, characters, encounters, rubric — spec 003 §2.4). Only `status = playable` rows are served |
| `scenario_secret` | 002's columns (real name, ticker, real beats, price series ref, price factor, amount factors, seed, what changed, `n_guessers`) + **`leak_terms`** (JSON) | For reference packs: `n_guessers = 0`, `price_series_ref` = the pack's CSV, and the raw case Markdown is stored by reference. Read only by the reveal endpoint and the leak guard |
| `event` | `id, session_id, scenario_id, campaign_id (nullable), seq (nullable), type, payload JSONB, client_msg_id (nullable, unique), ts` | One table for both specs. Spec 003 writes **`debrief_complete`** when the player submits the reflection, which is what unlocks 002's reveal |
| `decision` | `id, session_id, scenario_id, campaign_id (nullable), action, amount_cents, evidence, forecast_pct, confidence, locked_at` | Spec 003 inserts it at lock. Spec 002's reveal checks that it exists for the session and scenario |

## 4. Where scenarios come from

The campaign engine (003) plays any row from `GET /scenarios/playable`:

- **Approved gate scenarios** (002, `source = gate`). Spec 003's adapter builds a minimal manifest:
  - the earlier beats become introduction-checkpoint evidence in Market Square and the Library
  - the last beat before story today becomes the "new disclosure" news event
  - the decision is at story today
  - the Campaign Master voices generic characters (a broker, a scholar, a treasurer)
  - encounters take their difficulty from spec 003's fixed table
- **Reviewed reference packs** (003, `source = reference_pack`, e.g. the Enron case). They **do not go through the guessers**. They must pass 002's **final scan** on all player-visible text and a team review before they are marked playable.

Interest matching picks from this list; until a matcher exists, any playable scenario will do.

## 5. Display rules (both specs)

Everything a player sees before the company reveal follows spec 002 §2.1–2.2:

- **Time:** shown only as **story days** ("Day 84", "60 days later…", horizon "about 75 days"). No year, month, quarter or weekday, and no fantasy-calendar dates.
- **Prices:** one hidden price factor. Percentage moves stay true to within 1 percentage point. Everything shown is ≤ 10,000.
- **Money amounts:** **one shared hidden money factor per case**, so ledger lessons such as profit vs cash flow or debt vs cash survive. Other kinds of amount (users, headcount…) get their own factors. Values are ≤ 10,000, rounded to 2 significant figures, never written in millions or billions.
- **Names:** no real names, tickers, products, people or places.
- **Real values:** they appear only on the company reveal, after the player's reflection.

## 6. Mission flow and screens

- **Order:**
  1. Hero creation (new players)
  2. "What are you into?"
  3. "Find my quest"
  4. **Disclosure note (002) with "Got it"**
  5. Tavern briefing
  6. Play
  7. Commit and lock
  8. Time skip
  9. Outcome reveal
  10. Debrief with What-if
  11. Reflection (writes `debrief_complete`)
  12. **Company reveal (002)**
  13. XP
  14. Finish
- **Routes:** `/quest/reveal` is the **company reveal** (002's `Reveal.tsx`). Spec 003's outcome screen is **`/quest/outcome`**. Spec 003's `POST /campaigns/{id}/reflection` returns `{scenario_id}`, and the frontend then calls 002's `GET /scenario/{id}/reveal`.
- **Look and feel:** 002's screens use spec 003's quest look and feel (§2.18 palette and typefaces) through the shared `quest` theme tokens.
- **Local storage:**
  - Session id: `fq.session.v1`.
  - Quest record (owned by 003): `fq.quest.v2` = `{v: 2, status, lastPath, campaignId, scenarioId, disclosureSeen, savedAt}`.
  - 002 reads `scenarioId` and `disclosureSeen`. Its `RevealGuard` relies on the server's 403 and the campaign phase, not on a client-side step list.
- **Disclaimer:** none anywhere in the demo, including the reveal.
- **Naming:**
  - The narrator is the **Campaign Master**, which is also the dialogue name tab.
  - The ally is **CommerzBuddy**.
  - The "Data Room" is spec 003's **Library** (documents) plus **Market Square** (price board).

## 7. Working in parallel

1. **002 lands the skeleton first:** the package, compose, the Alembic base migration (with `scenario` including `source` and `manifest`, `scenario_secret` including `leak_terms`, and `event` and `decision` with the §3 columns), `POST /session`, and `client.ts` with fixture mode.
2. **Until then, 003 builds against fakes:**
   - the engine's pure modules (dice, portfolio, clock)
   - the agent graphs with a fake LLM
   - the reference-pack importer, against a local test database
   - the visual-novel frontend in fixture mode
3. **Contract tests on both sides:**
   - 002: no `scenario_secret` field appears in any non-reveal response; the reveal returns 403 until a `decision` and a `debrief_complete` event exist.
   - 003: an adapted gate scenario and the Enron pack both load and play to the reveal.
