# Spec 003: Final wire contract (backend <-> frontend)

- **Status:** implemented in `backend/financequest` and verified by `backend/tests/test_api_contract.py` plus a live run (see the end).
- **Sources:** tech spec §2.5 (003), §2.5 (002), `context/product/shared-contracts-002-003.md`, and what the frontend (`frontend/src/api`, `quest/play`, `quest/screens`) expects.
- **Rule used to settle a field:** the spec wins where it is specific; where the spec is silent the frontend's shape wins if it is reasonable (it is the only reader of the field); a field that carries a number the player sees is a JSON number computed by the server (the frontend never calculates a figure).

## 0. Common rules

| Topic | Contract |
|---|---|
| Session | `POST /session` -> `{session_id}`. Every other endpoint needs header `X-Session-Id`; missing or unknown -> **401** (the client re-creates its session once). Exceptions without the header: `GET /locations/{id}/art`, `GET /tts/{id}` (browser `<img>`/`<audio>`), `/healthz`, `GET /scenarios/playable`, `GET /scenario/{id}/view`. |
| Error envelope | **Every** error, including framework errors, is `{"error": {"code", "message", ...extra}}`. Extra keys: `fields` (422, `{field: message}`), `campaign_id` (409 `campaign_in_progress`), `alt_source` (409 `already_resolved`). The frontend today only reads the HTTP status (401 Unauthorized, 403 RevealLocked, 404 NotFound, 409 Conflict, 422 Validation). |
| Status codes | 404 unknown or foreign campaign; 409 wrong phase / not ready / roll open / no Focus; 422 validation; 403 only `GET /scenario/{id}/reveal` before decision + `debrief_complete`. |
| Numbers | Anything shown to the player as a price or amount of money is a JSON **number** (computed with `Decimal` server side, serialised at the edge, at most 4 decimals, always <= 10,000). Exception: the spec 002 endpoints `/scenario/{id}/view` and `/scenario/{id}/reveal` keep **decimal strings** (see D14). |
| Currency | The quest's money is **gold pieces** ("gp"; 1 HP = 10 gp). Only rendered text changed: JSON field names such as `hp_eur`, `cash_eur`, `amount_eur`, `principal_eur` keep their names (values are gold pieces), and `meta.currency` is `"GP"`. `currency_note` reads "Every figure here is in gold pieces (gp)." Quest replies containing euro, EUR or the euro sign fail the guards. The spec 002 reveal keeps its real-world figures. |
| Time | Story days and labels only ("Day 91", "75 days later…"). The only wall-clock value on the wire is `finished_at` (a date, in the hero history). |
| Cards | A card is `{kind: "dice" \| "news", ...}`. `kind` is the only discriminator, in SSE `card` events and in JSON responses alike (the pending-roll marker in `pending` keeps `type: "roll"`). |
| Idempotency | `client_msg_id` on `actions`, `move`, `buddy` makes a repeat replay the stored reply (same text, same `audio_text_id`, `replayed: true`). |
| IDs | UUID strings, except `audio_text_id` (integer event id). |

## 1. Session and hero

| Method, path | Request | Response |
|---|---|---|
| `POST /session` | - | `{session_id}` |
| `GET /hero` | - | `Hero` or 404 `no_hero` |
| `POST /hero` | `{name, class}` with `class` in `guardian \| analyst \| investigator` | 201 `Hero`; 409 `hero_exists`; 422 `invalid_name` (2-20 chars, letters, digits, space, `-`, `'`) or `validation_error` (bad class) |

```
Hero = {
  name, class, total_xp,
  items: [{id, key, name, description}],        // id == key, e.g. "ratio_lens"; same id as campaign.hero.items[]
  history: [{campaign_id, interests[], total_xp, decision|null, result_pct|null, finished_at: "YYYY-MM-DD"}],
  active_campaign_id: uuid | null
}
```

## 2. Campaign state

`POST /campaigns` (`{interests: string[]}`, 201) and `GET /campaigns/{id}` return the same `CampaignState`. `POST` also: 409 `hero_required`; 409 `campaign_in_progress` (+ `campaign_id`).

```
CampaignState = {
  id, scenario_id, phase, status: "active"|"finished", version,
  scenario: {title, company_name, trade, horizon_label, budget_eur, currency, spread_available},
  hero: {name, class, total_xp, items: string[]},            // item ids
  hp, hp_eur, focus_left, rerolls_left, keen_eye_left, bonus_lead_available,
  budget_eur, horizon_days, offers_spread,                    // flat, used by the commit screen
  turn_count, checkpoint, story_day, story_day_label ("Day 91"),
  news_shown, news: {headline, summary} | null,
  current_location_id | null,
  locations: [{id, key, name, description, fixed, art_status: "placeholder"|"pending"|"ready"|"failed", visited}],
  backlog: [{seq, speaker, text}],         // speaker: "You" | "You (to Buddy)" | "CommerzBuddy" | the reply's name tab ("Campaign Master" or a character)
  clues: [{clue_id, source, title, text}],
  library: {documents: [{id, title, entries: [{id, title, text}]}],
            company_card: {name, trade, size, key_figures: [{id, label, value, period, explain?}]}},   // explain only with Ratio Lens; value may be a string
  price_board: [{day, open, high, low, close}],               // numbers, cut at story today
  characters: [{id, name, role, location}],
  challenges: [{id, title, dc, state: "open"|"rolling"|"final", optional, result, location}],
  pending: {type: "roll", challenge_id, state: "offered"|"rolling"} | null,
  can_decide, opening_done,
  suggestions: string[],                   // NEW: suggestions of the latest Campaign Master reply, for resuming
  commit_draft: {action?, amount_eur?, evidence?, forecast_pct?, confidence?} | null,
  rumours?: string[],                      // only with Rumour Ledger
  outcome?: Outcome   (phase >= reveal), debrief?: Debrief (phase >= debrief), xp?: Xp (phase >= xp)
}
```

Phases (server): `setup -> play <-> commit -> timeskip -> reveal -> debrief -> company -> xp -> done`. `reflect` exists in the enum but the server never stores it (the frontend moves to `/quest/reflect` on its own; a reload there lands on `/quest/debrief`, which is acceptable).

Phase transitions made by endpoints: `opening` (setup -> play); `PUT commit-draft` (play -> commit); `POST resume-play` (commit -> play); `lock` (play|commit -> timeskip); `GET reveal` (timeskip -> reveal); `debrief` (timeskip|reveal -> debrief); `reflection` (-> company); `xp` (-> xp); `finish` (-> done, hero's `active_campaign_id` cleared).

## 3. SSE endpoints

`POST` with `Content-Type: application/json`; response `text/event-stream`. Errors found before streaming (wrong phase, unknown ids, empty text) are plain JSON errors with the status code; errors during streaming are an `error` event.

| Path | Body | Notes |
|---|---|---|
| `/campaigns/{id}/opening` | - | Idempotent: after the first run it replays the stored opening. |
| `/campaigns/{id}/actions` | `{text, client_msg_id?}` | Turn. 409 `roll_open` while a roll is open. |
| `/campaigns/{id}/move` | `{location_id, client_msg_id?}` | Turn. |
| `/campaigns/{id}/narrate-roll` | `{roll_id}` | Only for a final roll (409 otherwise); replays when repeated. |
| `/campaigns/{id}/buddy` | `{text, client_msg_id?, screen?}` | Not a turn. `screen`: `market_square`, `library`, `document:<id>`, `commit`. |
| `/campaigns/{id}/focus/hint` | - | Spends 1 Focus atomically with the stored hint. |
| `/campaigns/{id}/debrief` | - | Needs a locked decision (409 `not_locked`). Replays the stored debrief. |

**Events, in this order**

| Event | Data |
|---|---|
| `status` | `{state: "writing"}` (immediately). |
| `token` | `{text}` (a word plus trailing whitespace; sent only after the reply passed the guards and was stored). |
| `card` | zero or more: dice `{kind:"dice", roll_id, challenge_id, title, dc, bonus: 2, keen_eye_available, keen_eye_left, skill?}` or news `{kind:"news", headline, summary, time_skip_label, story_day, framing, framing_audio_text_id}`. |
| `state` | `{can_decide, turn_count, focus_left, rerolls_left, keen_eye_left, story_day, checkpoint, news_shown, phase, current_location_id, art_ready: [location ids]}` (debrief: `{phase}` only). |
| `done` | see below. |
| `error` | `{code, message}`, e.g. `lost_thread`. The stream ends. |
| `: ping` | comment heartbeat every 5 s (ignored by the parser). |

**`done` payload** (all Campaign Master and Buddy replies): `text`, `speaker`, `audio_text_id`, plus the same fields as `state` (so `can_decide` is always present), `degraded` (templated fallback used) and, per endpoint:

| Endpoint | Extra `done` fields |
|---|---|
| opening | `suggestions[3]`, `opening: true` |
| actions, move | `suggestions[3]`, `show_decide`, `location {id,key,name} \| null`, `first_visit` (moves; else null), `news_text` (the news framing, only when a news card was sent, also on replay), `intent`, `clue_ids_given`, `speaker_id`, `nothing_more_to_uncover`, `card`/`news` (copies of the cards) |
| narrate-roll | `suggestions[3]`, `roll_id` |
| buddy | `mood`, `intent` (speaker is `CommerzBuddy`) |
| hint | `suggestions[3]`, `hint_location` (key or null) |
| debrief | `sound_reasoning, overlooked, luck, forecast_line, reflection_question, whatif[]` (the Debrief shape below), plus `text` (spoken form), `phase` |

Clients must ignore unknown `done` fields.

## 4. JSON play endpoints

| Method, path | Request | Response |
|---|---|---|
| `POST /campaigns/{id}/rolls` | `{challenge_id, mode: "normal"\|"advantage"}` | `RollResult` |
| `POST /campaigns/{id}/rolls/{rid}/reroll` | - | `RollResult` (final) |
| `POST /campaigns/{id}/rolls/{rid}/accept` | - | `RollResult` (final) |
| `POST /campaigns/{id}/focus/bonus-lead` | - | dice card `{kind:"dice", ..., focus_left}`; 409 `no_focus`, `bonus_used`, `roll_open` |
| `GET /campaigns/{id}/journal` | - | `{entries: [{seq, type, ts, ...payload}]}` (also when finished; non-final dice rolls omitted) |
| `PUT /campaigns/{id}/commit-draft` | any subset of `{action, amount_eur, evidence, forecast_pct, confidence}` (`{}` allowed; legacy key `decision` is read as `action`) | **204**. Requires `can_decide`; moves phase `play -> commit`; 409 `locked` after the lock, 409 `not_ready` before the player may decide. |
| `POST /campaigns/{id}/resume-play` | - | `{phase: "play", commit_draft}`; only from `commit` or `play`. |
| `POST /campaigns/{id}/lock` | `CommitRequest` | `Outcome`; idempotent (a second call returns the first outcome); 422 `invalid_commit` + `fields` |
| `GET /campaigns/{id}/reveal` | - | `Outcome` (moves `timeskip -> reveal`); 409 `not_locked` |
| `POST /campaigns/{id}/reflection` | `{text}` (>= 10 chars after trim) | `{scenario_id}`; writes `debrief_complete`; phase `company`; idempotent; 422 `too_short` |
| `POST /campaigns/{id}/xp` | - | `Xp`; 409 until the reflection exists; idempotent |
| `POST /campaigns/{id}/finish` | - | `{total_xp, new_item: {id,key,name,description} \| null}`; idempotent; 409 until XP exists |
| `GET /locations/{id}/art` | - | `image/webp` (404 until `art_status` is `ready`) |
| `GET /tts/{audio_text_id}?voice=dm\|buddy` | - | `audio/wav` of the stored, guarded text |

```
RollResult = {roll_id, challenge_id, title, dice[], used, bonus: 2, total, dc, result: "success"|"setback",
              final, options: ("continue"|"reroll"|"accept")[], rerolled, rerolls_left, keen_eye_left, alt_source|null, skill?}

Ad-hoc skill checks. The Campaign Master (and a Master-created place's NPC, by escalation) routes any
uncertain, skill-based action with no listed challenge to a dice check: `intent: "challenge"` and
`check: {skill: investigation|insight|persuasion|stealth|knowledge, target, difficulty: easy|medium|hard,
stakes}` (a listed `challenge_key` that fits always wins; trivial or certain actions are never rolled).
The engine, not the model, validates the check, opens a `challenge` row (`kind: "skill:<skill>"`,
`title` = the target, DC from the table: easy 10, medium 13, hard 15) and a pending roll, so the turn's
`card` and `done.card` are the ordinary dice card plus `skill` (display name, e.g. "Insight"; absent on
listed challenges). `title` is the target ("Ren Tal"); the client shows "Insight check · DC 13". The same
`skill` is on `challenges[]` in `GET /campaigns/{id}` (a reload rebuilds the card) and on `RollResult`.
Rolls, Keen Eye, Second Look, accept and `narrate-roll` behave as for listed challenges, except:
`alt_source` is always null (there is no alternate source); a success reveals only the one real,
unlocked, not-yet-found, non-dice-gated clue the engine picked when the check opened (a person's own
clues first when the check is aimed at them), else a small non-evidence detail; a natural 20 may add one
more safe detail; a setback never grants key evidence (no failure-forward) and the Master may apply
damage through the usual `hp_change`. At most one check per skill + target + place: a repeat is narrated
("You have already ...") with `card: null` and no new roll.

CommitRequest = {action: "invest"|"dont_invest"|"wait"|"spread", amount_eur?: int (1..budget, invest|spread only),
                 evidence: string (>= 20 chars trimmed), forecast_pct: 0..100 step 5, confidence: "low"|"medium"|"high"}

Outcome = {                                      // POST lock and GET reveal
  locked_at: "Day 91, evening",                  // story moment, never a wall-clock time
  horizon_days, horizon_label ("about 75 days"), time_skip_label ("75 days later…"), decision_day,
  series: [{story_day, price}],                  // through the horizon; only after a decision exists
  action, amount_eur,
  breakdown: {starting_budget, cash_kept, invested, value_now, fees, final_value, pl_eur, pl_pct},
  hp_before, hp_after, investment_return_pct, currency_note, phase
}

Debrief = {sound_reasoning, how_you_reasoned, overlooked, luck, forecast_line, reflection_question,
           whatif: [{key: "dont_invest"|"half"|"all"|"spread"|"yours", label, final_value, pct, hp_after, is_yours}]}

Xp = {categories: [{name, score, max, rationale, quote}], total}    // 5 categories, rubric from the manifest
```

## 5. Spec 002 endpoints used by the quest

| Method, path | Response |
|---|---|
| `GET /scenarios/playable` | `[{id, industry_shown, source}]` |
| `GET /scenario/{id}/view` | `{id, invented_name, industry_shown, story_today, beats[{story_day, headline, facts[]}], chart[{story_day, price: "decimal string"}], company_card}` |
| `POST /scenario/{id}/events` | `{id, type}` (201) |
| `GET /scenario/{id}/reveal` | 403 `reveal_locked` until a decision and `debrief_complete` exist. `{real_name, ticker, start_date, end_date, series[{date, price: "decimal string"}], news_points[{story_day, real_date, real_price: "decimal string", headline}], what_changed[], n_guessers}` |

## 6. Divergences found and how each was settled

| # | Where | Frontend expected | Backend had | Resolution |
|---|---|---|---|---|
| D1 | SSE `status` | `{state}` | `{status}` | **Backend changed** to `{state: "writing"}`. |
| D2 | Cards | `kind` | `type` | **Backend changed** to `kind` (SSE cards, bonus-lead response, stored events). `pending.type` stays. |
| D3 | `GET /hero` `items[]` | `{id, name, description}` | `{key, description}` | **Backend changed**: `{id, key, name, description}`. |
| D4 | `GET /hero` `history[]` | `{campaign_id, interests, total_xp, decision, result_pct, finished_at}` | `{campaign_id, date, interests, decision, pnl_pct, xp}` (strings) | **Backend changed** to the frontend names; `result_pct` is a number. |
| D5 | `finish.new_item` | `{id, name, description}` object | item key string | **Backend changed** to the object. |
| D6 | Commit request key | `action` | `decision` | **Backend changed**: `action` is canonical (the `decision` DB column is `Decision.action`); `decision` is still read as an alias. 422 `fields` key is `action`. |
| D7 | Lock / reveal outcome | `locked_at` (story label), `series[{story_day, price}]`, `breakdown{starting_budget, cash_kept, invested, value_now, fees, final_value, pl_eur, pl_pct}` as numbers | ISO wall-clock `locked_at`, `chart[{day, close}]`, `breakdown{cash, final, pnl, pnl_pct, budget}` as strings | **Backend changed** to the frontend shape. The wall-clock timestamp was also a (minor) real-time leak next to "story days only". |
| D8 | What-if rows | `{key: dont_invest\|half\|all\|spread\|yours, label, final_value, pct, is_yours}` numbers | `{key: dont\|...\|choice, final, pnl_pct, hp_after, is_choice}` strings | **Backend changed** at the wire only (`whatif_out`); the engine, the stored rows and the agent context keep their own format. |
| D9 | Price board rows | numbers | strings | **Backend changed** at the wire only (`board_out`); agents still receive the strings their allowlist is built from. |
| D10 | Library entries | `{id, title, text}` | whole evidence record incl. `checkpoint`, `key`, `location` | **Backend changed**: only `id, title, text` leave the server (no checkpoint names, no key-evidence flag). |
| D11 | Resume suggestions | `suggestions?` in `CampaignState` | missing | **Backend added**, derived from the latest `dm_reply` in the event log (no new column). |
| D12 | Commit screen fields | top-level `budget_eur`, `horizon_days`, `offers_spread` | only in `scenario{}` | **Backend added** the three flat fields (`scenario{}` kept). |
| D13 | Errors | status only | framework errors (401, bad UUID 422, 404 route) were `{detail}` | **Backend changed**: every error is the spec envelope; 422 carries `fields`. |
| D14 | Spec 002 view/reveal prices | `number` (`StoryPoint.price`, `RealPoint.price`, `NewsPoint.real_price`) | decimal strings | **Kept strings** (owner Davyd, tested contract, real prices should not lose precision); frontend coerces (see F1). `id` was missing from `/view`: **backend added**. |
| D15 | `done` details | `speaker, suggestions, show_decide, location, first_visit, news_text, audio_text_id, can_decide` | all present except `news_text` on a replayed reply (the state delta, incl. `can_decide`, was already in `done`) | **Backend changed**: `news_text` also on replay. |
| D16 | Hint reply | `suggestions` | none | **Backend added** to the stored hint reply. |
| D17 | `PUT commit-draft` from play | moves phase to `commit` | already did | **No change**; verified. |
| D18 | `POST resume-play` | not called by the frontend | exists | **No backend change**; frontend must call it (F2). |
| D19 | `CampaignState.resources` | typed (deprecated) | not sent | **No backend change**; frontend drops the type (F4). |
| D20 | Hero class wire values | `guardian\|analyst\|investigator` | same | Match; no change. |
| D21 | `art_status` | `pending\|ready\|failed` | also `placeholder` (fixed locations before any art) | **Frontend** adds `placeholder` (F5). Fixed locations use bundled backgrounds anyway. |
| D22 | `locked_at` in `CampaignState` | not read | real ISO timestamp | **Backend removed** it from the state. |
| D23 | Phase `reflect` | in `CampaignPhase` | never stored | **Accepted**; see §2. |

## 7. Frontend changes required (for the next frontend pass)

| # | File | Change |
|---|---|---|
| F1 | `frontend/src/api/client.ts` (`api.view`, `api.reveal`) | Convert the decimal strings of spec 002 responses to numbers right after the fetch: `chart[].price`, `series[].price`, `news_points[].real_price` -> `Number(x)`. Without it `formatStoryNumber('31.95')` throws a `RangeError` (it requires a number) and the StoryChart gets strings. Update `types.ts` comments accordingly. |
| F2 | `frontend/src/api/campaign.ts` + `frontend/src/quest/screens/Commit.tsx` (`back()`) | Add `resumePlay(id)` = `POST /campaigns/{id}/resume-play` and call it after `saveCommitDraft` before navigating to `/quest/play`. Today only the cache is patched to `play`, so the server stays in `commit` and a reload sends the player back to the commit screen. Update the fixture (`fixtures/index.ts`) to flip the phase back to `play` on that route. |
| F3 | `frontend/src/api/fixtures/index.ts`, `play.ts` | Align the fixtures with the final shapes: `lock`/`reveal` add `horizon_label`, `time_skip_label`, `action`, `amount_eur`, `investment_return_pct`, `phase`; whatif rows add `hp_after`; the 409 for "not ready" on `commit-draft`. The core shapes already match. |
| F4 | `frontend/src/api/types.ts` | Remove `CampaignState.resources` and `HeroResources` (the server sends the flat fields only); make `budget_eur`, `horizon_days`, `offers_spread` required, `suggestions` required (`string[]`); add `status`, `version`, `checkpoint`, `characters`, optional `outcome`; `Outcome` extra optional fields from §4. |
| F5 | `frontend/src/api/types.ts` | `ArtStatus = 'placeholder' \| 'pending' \| 'ready' \| 'failed'`; `NewsCard` optional `framing`, `framing_audio_text_id`; `TurnExtras` optional `can_decide`, `hint_location`, `roll_id`, `mood`, `degraded`, `replayed`. |
| F6 | `frontend/src/quest/screens/Commit.tsx` (`TimeSkip`) | Optional: show `res.time_skip_label` from the lock response instead of building `"{days} days later…"`. |
| F7 | `frontend/src/quest/screens/WhatAreYouInto.tsx` | Optional: on 409 `campaign_in_progress` (`error.campaign_id`) refetch the hero and resume instead of showing the generic failure. `request()` would need to keep the parsed `error` body on `ApiError` (`code`, `fields`). |
| F8 | `frontend/src/quest/play/LibrarySheet.tsx` | Optional: key figures arrive with string values (`"100789"`) from reference packs; format numeric strings with `formatStoryNumber(Number(v))`. |
| F9 | `frontend/src/api/sse.ts` | No change required (it already ignores comments and unknown fields); `done` of `debrief` is read as `DebriefData` and now matches. |

## 8. Verification

- `backend/tests/test_api_contract.py`: error envelope (401, 404, 422 with `fields`), hero shape, SSE `status`/`done` fields and resume `suggestions`, news card `kind` and `news_text` on replay, commit-draft/resume-play/lock/reveal flow and the outcome shape.
- Existing suites updated for D1-D10 (`test_campaign_api.py`, `test_campaign_agents.py`, `test_scenarios_api.py`).
- Live run against uvicorn (`FAKE_LLM=1`, port 8015) on the approved Enron pack, session through finish: in the task report.

## 9. Master intents, Master-created places with an NPC, HP damage

### 9.1 Free-text movement (no API change)

`POST /campaigns/{id}/actions` routes "let's go to the market", "head to the library", "back to the
inn", "visit the guild hall" (synonyms: market/exchange/square/price board; library/archive/records;
tavern/inn/pub; guild hall/council chamber) to `intent: "move"`. The `done` payload then has
`intent: "move"` and `location: {id, key, name}` exactly like `POST /move`.

### 9.2 Master-created places (`new_location`)

The player never creates a place. When the story needs one that does not exist (a counterparty's
warehouse, a ship, a regulator's office) the Campaign Master adds it: a `location` row (no cap on how
many; the Master creates one only when the story needs it), an NPC at it, a Nano Banana art job
(9:16, scrubbed prompt, no text/people/logos), and the player is moved there.

`done` of `POST /actions` when this happens:

```
intent: "new_location"
speaker: "Campaign Master", speaker_kind: "master"
location: {id, key, name}                      // the NEW place; the player is already there
new_location: {
  id, key, name, description,
  art_status: "pending" | "ready" | "failed" | "placeholder",   // "pending" while the job runs
  npc: {id, name, role}                        // id looks like "npc-1a2b3c4d"
}
```
Otherwise `new_location` is `null`. The text introduces the NPC by name; `suggestions[0]` is
"Ask <npc> what they know". Art readiness uses the existing mechanism, nothing new: poll
`GET /campaigns/{id}` (`locations[].art_status`), read `state.art_ready` (ids) in the SSE `state`
event of later turns, or fetch `GET /locations/{id}/art`. The `state` event now also carries the
full `locations` array (same item shape as the campaign state), so the new place is on the map
without a refetch.

Campaign state `locations[]` items gain `generated: bool` and `npc: {id, name, role} | null`
(`null` and `false` for the fixed and seed places).

### 9.3 NPC agent

While the current location is a generated one, `POST /actions` is answered by its NPC, in
character, with the full gated context and the same guards (numbers, leaks, advice, 120 words,
second person, no mechanics talk). The NPC reveals only evidence already unlocked at the current
checkpoint (never future evidence; never dice-gated clues), at most two clues per reply, granted
through the usual `clue_ids_given`.

`done`: `speaker` = NPC name, `speaker_kind: "npc"`, `intent: "talk"`, `escalated: false`.

The NPC hands over to the Campaign Master when the player wants to decide or commit, travel, asks
about other places' evidence or people, attempts something risky, is off-topic, or the scene is
done (and when the NPC's own guards fail). The Master then runs the normal turn for the same
action in the same request: `speaker: "Campaign Master"`, `speaker_kind: "master"`,
`escalated: true`, and the usual `intent` (`move`, `challenge`, `decision_intent`, `new_location`...).
The player can always leave through the map (`POST /move`, the Tavern is always reachable). An
open decision scene is answered by the Master, never by the NPC. NPC turns may take up to 30 s
(NPC call + Master call); other turns keep 15 s.

### 9.4 `speaker_kind` and `hp_change` on every `done`

Every `done` of `/actions`, `/move`, `/narrate-roll`, `/buddy` (also `/opening`, `/focus/hint`,
`/debrief`) now has:

```
speaker_kind: "master" | "npc" | "buddy"
escalated: bool                     // false except an NPC hand-over
hp_change: {delta: int (negative), reason: str, hp: int, hp_eur: int} | null
new_location: {...} | null         // see 9.2
```
`hp_change` is `null` on most turns. The Master may take HP on ANY narrated play turn when it
judges the story costs the hero money: an action gone wrong, an NPC turn, a move or arrival at a
new or existing place, a `new_location` event, a dice result (a success at a price as well as a
setback), the reaction to a decision in a decision scene, or the consequence of news. Always
justified in the text ("You lose 3 HP: ..."), never for merely asking questions, never on
`off_topic` or `decision_intent` turns, and never after the lock (the final outcome stays pure
market maths). `/buddy` never carries damage (`null`).

### 9.5 Damage rules (engine, not the model)

HP is the money bar: 1 HP = 10 euros, `hp_eur = hp * 10`. There is no minimum HP and no total
cap: HP can fall to 0 (budget EUR 0). The engine only bounds one reply to 10 HP (also the schema's
`hp_loss` range, 0 to 10), and a loss is never larger than what the hero owns (cash plus the
drafted position at the board price). Nothing after the lock. The stated number in the text is
rewritten to the applied one. It is persisted (`campaign_run.hp_lost`, event `hp_change`).

Cash in the purse pays first. When cash is not enough the rest comes out of the invested draft: a
`damage` trade (`decisions[].action: "loss"`, `beat: "damage"`, `text` = the reason) removes those
coins at the board price, so the total budget really drops and the per-decision effects still add
up to the result. The investable budget for the result is the current `hp_eur`: the purse, the
outcome and the what-if table all start from the reduced budget. At HP 0 the hero holds nothing:
the lock works with EUR 0 (`starting_budget: 0`, `pl_pct: 0`, no division by zero).

Campaign state: `hp` and `hp_eur` reflect damage; `hp_start` is new (starting HP). `budget_eur`
(and `scenario.budget_eur`) stay the starting budget. `state` SSE events carry `hp`, `hp_eur`.
The reveal `breakdown.starting_budget` is the budget after damage (the shape is otherwise
unchanged); `hp_before` is the HP after damage.

`POST /campaigns/{id}/lock`: when the body has `amount_cents` greater than `hp_eur * 100` the
response is `422` `{"error": {"code": "amount_over_budget", ...}}`. (Without `amount_cents` the
lock behaves as before: what was invested comes from the decisions already written.)

FAKE_LLM never deals damage unless a test queues it (`agents/campaign/fake.py::script_damage`).


## 10. Decision reasoning (why the player chose)

Every decision-scene trade (buy/sell/hold) records the player's reasoning; the final lock records the
Commit screen's note. It is read by the debrief, the XP scoring and the Veteran.

**Capture.** `decide` returns `reasoning` (the player's own reasons copied from the message, or null)
and `reasoning_sufficient` (true only when at least one concrete reason is named: a figure, a clue,
the news, a risk; false for none, "just because", "gut feeling", "I like it"). The engine executes the
trade first, then:

| Case | Result |
|---|---|
| reasoning present and sufficient | stored, `reasoning_source: "inline"`, nothing asked |
| missing | the curious trader asks "... What made you choose that?" |
| thin | the curious trader asks "... Can you tell me a bit more about why?" (the thin reason is kept) |

**The curious trader.** The question never comes from the Campaign Master. A recurring in-world
character, "a curious trader" (fixed per campaign, a fantasy name picked from the campaign id, e.g.
Pell Ashby, Odran Vey, Mirel Tansk), asks it in a short, neutral, templated line (no model call; no
judgement, advice or hint). The Master's decision reply (`text`) does not contain the question. The
`done` of the decision turn gains `reasoning_prompt: {speaker, role: "curious trader", text} | null`
(null when nothing is asked); the trader's line is also stored as its own `dm_reply` event
(`speaker` = the trader, `speaker_kind: "npc"`) so the backlog and replays show it. The client shows
it as one more dialogue page (NPC name tab) after the Master's pages.

When it asks, the decision awaits its answer and the `done` of that turn has `awaiting_reasoning: true`
(suggestions: one "I'd rather skip that" chip). The player's NEXT message to `POST /actions` is
recorded verbatim (appended to a thin first reason), `reasoning_source: "asked"`, and answered ONLY by
the trader thanking the player in a short templated neutral line (the `speaker` SSE event and `done`
carry `speaker` = the trader's name and `speaker_kind: "npc"`; no Master text follows, no model call).
Then the input returns to normal. Asked at most once per decision. A clear skip ("skip", "no reason", "rather not")
records `reasoning_source: "skipped"` (a thin reason already given is kept; otherwise
`reasoning: null`). Travel/exploring wording (or `POST /move`, or the lock) never waits: the question
is dropped as `skipped` and the action runs normally. A follow-up is not blocked by trade words: the
next message is reasoning, not a new decision.

**Fields.** `decisions[]` (campaign state, outcome/lock/reveal) gain `reasoning: string | null` and
`reasoning_source: "inline" | "asked" | "commit" | "skipped" | null` (null while the question is
open; damage `loss` rows never have reasoning). Campaign state gains `awaiting_reasoning: boolean`
(also in every `done`/`state` delta). The lock/reveal outcome gains `final_reasoning:
{reasoning, reasoning_source}` (the Commit note: `"commit"`, or `"skipped"` when left empty). The
Debrief gains `how_you_reasoned` (comment on evidence used, risks considered, consistency, change
when news arrived; kept separate from luck and the result). Veteran timeline decisions gain
`reasoning` and `reasoning_source` ("you said: ...").

**Persistence.** `campaign_trade.reasoning`, `campaign_trade.reasoning_source`, `decision.reasoning`,
`decision.reasoning_source` (migration `0008`). `reasoning_source = "awaiting"` is internal and never
sent. Event `decision_reasoning` `{seq, reasoning, source, skipped}` (`seq: null` for the lock).
Veteran memory is version 2: per-decision `reasoning` snippets (160 chars).

FAKE_LLM: reasoning is read from "because/since/..." or the text after ":" in the decision;
sufficient when it has at least 6 words, a number or a clue word, and is not vague.

## 11. The all-in plot: nothing left at stake

A hero with every coin in the company (or out of it and done) has no reason left to follow the story.
After any decision-scene trade the engine checks, and the Campaign Master responds with one of three
things. The Master chooses the kind (guided by the story; scripted in FAKE_LLM, default `buyback`, queue
`fake.script_offer("loan" | "fast_forward")`); the engine supplies every figure, validates the kind
and executes; the model never produces a number.

**Detection (engine, `service.nothing_at_stake`).** Right after a trade, with the phase `play`:
- *all in*: free cash <= 2% of the starting budget (`hp_start * 10`) and coins held > 0;
- *out for good*: a `sell` that leaves no coins, after an earlier buy, with "done" wording ("I'm done",
  "that's it", "finished", ...).

| Situation | Plot |
|---|---|
| all in, the news has not broken yet (unrevealed checkpoints ahead), no offer made yet | the Master chooses `buyback`, `loan` or `fast_forward` |
| all in at the last checkpoint (news already shown), or an earlier offer was declined or ignored | straight `fast_forward`, no offer |
| out for good | straight `fast_forward` (a buyback or loan makes no sense) |
| all in again after an offer the player took | nothing: the plot goes on |

An offer is made at most once per campaign (event `all_in_offer`). The follow-up "why?" question of the
triggering trade is not asked (it is closed as skipped; an inline reason is kept).

**Offer.** `done.offer` / state `offer` / the open scene `market_scene.beat == "offer"`:
`{kind: "buyback" | "loan", by: {name, role}, terms}`. `by` is a generated in-world character
(a "Guild broker" or a "Moneylender"); the reply uses `speaker_kind: "npc"`. `terms`:
- `buyback`: `{max_eur, price: "today's board price", default_portion: "half"}`. Accepting is a `sell`
  at the board price (`beat: "offer"`); "sell half" / "sell 100" work, a bare "accept" sells half; the
  amount is clamped to what is held.
- `loan`: `{principal_eur, interest_pct: 10, repay_eur, due: "at the end of the horizon"}`; principal =
  50% of the starting budget, flat 10%.

The offer also arrives as a card `{kind: "offer", offer_kind, by, terms, text, suggestions, day_label,
purse, audio_text_id}` after the trade receipt. The player answers by typing to `POST /actions`
(accept / decline / something else). Neutral wording only: the Master never says whether to accept.

**Answers (`POST /actions` while `market_scene.beat == "offer"`).**
- accept a buyback: executes like a decision (receipt card, `Trade.beat = "offer"`), scene closed;
- accept a loan: a `loan` trade (see Persistence): cash +principal now, receipt card with `loan`;
- decline ("no", "decline", "keep", "hold" ...): the Master narrates, then **fast-forward**;
- something else: the normal turn runs and the offer stays open once; the second time the player
  ignores it, **fast-forward**. `offer_ignored` events count them.

**Fast-forward.** The Master narrates the days passing (no result, no figure). The engine seals the
position as it stands (`lock_decision(auto=True)`: `decision` row with the player's latest reasoning,
`reasoning_source: "auto"`, neutral forecast 50% / low confidence, `lock` event with `auto: true`,
`time_skip`) and the phase becomes `timeskip`. The `done` carries `fast_forward: true`,
`all_in: true` and `phase: "timeskip"`; the client opens `/quest/outcome` after the reply is read
(GET `/reveal` then moves the phase to `reveal`, as after a normal lock).

**Fields.** Every `done`: `all_in: bool` (this reply left nothing at stake), `fast_forward: bool`,
`offer` (the open offer or null). Campaign state: `all_in` (derived: free cash <= 2% and coins held),
`offer`. `purse` gains `loan: {lender, principal_eur, repay_eur, interest_eur, label} | null` and, with
a loan, `net_eur` (cash + coins - repayment). `label` reads "Loan from <lender>: +€500 now, repay €550
at the end". Trade receipts with `action: "loan"` carry `loan`. `decisions[]` rows may have
`action: "loan"` (`amount_eur` = principal, `beat: "offer"`).

**Result maths (exact).** `breakdown` gains `loan_repay_eur` and `loan` only when a loan was taken.
`final_value = cash_kept + value_now - loan_repay_eur` (the principal is part of `cash_kept`;
`invested = budget + principal - cash`); `pl_eur = final_value - starting_budget`. `fees` stays 0.
What-if rows keep their alternatives on the plain budget; "Your decisions" includes the loan.
The debrief context shows `loan_repay`.

**Persistence.** No migration. The loan is a `campaign_trade` row (`action: "loan"`, `beat: "offer"`,
`amount_cents` = principal, `price` = repayment in euros as text, `text` = "Loan from <lender>",
`cash_after_cents` includes the principal, `shares_after` unchanged). The open offer lives in
`campaign_run.market_scene` (`{beat: "offer", offer, ignored, text, suggestions}`); events
`all_in_offer {kind, by, terms}` and `offer_ignored {text, count}` are the log.

**Agent nodes.** `campaign_offer` (structured `OfferOut`: kind, name, role, text, suggestions; the
kind must be in the allowed list, else the first allowed is used), `campaign_offer_answer` (the loan
accepted) and `campaign_forward` (the days pass). All run through the guards (number allowlist
includes the offer's own terms and the 10% / 50% rates; no advice; no leak) with prepared templates.

## 11b. The supporting hand: help for a player in trouble

When the player is in trouble the Campaign Master offers one in-world supporting hand, **once per
campaign**. It reuses the offer machinery of section 11 (the open offer is the scene
`market_scene.beat == "offer"`, the answer is typed to `POST /actions`), but declining never ends the
story. The engine detects the trouble, lists the kinds it can really give and supplies every figure;
the Master only chooses among the allowed kinds and voices a generated character (`speaker_kind: "npc"`,
e.g. a guild patron, an old mentor, a moneylender, a sympathetic broker). Neutral and kind; never advice
on what to buy or sell.

**Detection (engine, `service.support_reason`).** Checked after every narrated reply that may have
changed the situation (turn or move, decision-scene answer, reasoning answer, dice narration), with the
phase `play` (so never once the decision is locked). Not while a scene, an offer, a dice check or a
reasoning follow-up is open, and not if a supporting hand was already offered (event `support_offer`).
The first match wins:

| `reason` | Condition |
|---|---|
| `broke` | HP is 0 (budget 0) |
| `low_hp` | damage was taken and HP <= 40% of the starting HP |
| `loss_sale` | a sale lost >= 25% of the amount sold (average-cost basis) |
| `position_down` | coins held are worth >= 30% less than was paid for them, at today's board price |

**No collision.** An open offer (all-in or support) is the open scene, so no second one opens beside it;
a trade that flags the all-in plot opens the all-in offer instead (the support check is skipped that
turn). The all-in offer and the supporting hand are counted separately (`all_in_offer` vs
`support_offer`): once the all-in offer was used, the supporting hand can still come, once.

**Offer.** `done.offer` / state `offer`: `{kind, by: {name, role}, terms, reason}` with
`kind` in `loan | patron_grant | rescue_buyback | second_look` and `reason` in
`low_hp | position_down | loss_sale | broke` (the all-in offers have no `reason`). Also a card
`{kind: "offer", offer_kind, reason, by, terms, text, suggestions, day_label, purse, audio_text_id}`
(in the SSE `card` events and `done.offer_card`). Allowed kinds and `terms` (engine only, gold pieces):
- `loan`: `{principal_eur, interest_pct: 10, repay_eur, due}`; principal = what is left of 50% of the
  starting budget after earlier loans (so smaller after a first loan; **never more than 50% in total**;
  no loan is offered, also in the all-in plot, once the cap is used). The accept path is `accept_loan`.
- `patron_grant`: `{hp, gift_eur, repay: "none"}`; `hp = min(20% of the starting HP, HP lost)`,
  `gift_eur = hp * 10`. Needs HP lost.
- `rescue_buyback`: `{max_eur, price: "today's board price", default_portion: "half"}`; accepting is a
  `sell` at the board price like the all-in buyback. Needs coins held.
- `second_look`: `{gives: "one clue", cost: "free"}`, or `{gives: "one Focus", cost: "free"}` when no
  unlocked, unfound clue is left and Focus is below its start value.
FAKE_LLM picks by `rules.SUPPORT_PREFERENCE` (broke / low_hp: grant > loan > look; position_down:
rescue > loan > look > grant; loss_sale: loan > look > grant), scripted with
`fake.script_support(kind)`. The real Master picks among the allowed kinds (prompt `SUPPORT`).

**Answers (`POST /actions` while the open offer has a `reason`).**
- accept `loan`: a `loan` trade (section 11), receipt card with `loan`;
- accept `patron_grant`: a `grant` trade (below), receipt card `{kind: "trade", action: "grant",
  grant: {amount_eur, label}}`; HP and the budget are restored by `hp * 10` gold, cash +gift;
- accept `rescue_buyback`: executes like a decision (`Trade.beat = "offer"`), "sell half" / "sell 100" work;
- accept `second_look`: one unlocked, unfound clue is revealed (a `clue_found` event, `source:
  "character"`, ids in `clue_ids_given`), no Focus spent; with none left, Focus +1 (event `focus_gain`);
- decline, or something else twice: the Master narrates in a line, the offer closes
  (`support_declined`) and **the story simply goes on** (phase stays `play`, no fast-forward; the
  fast-forward rules of section 11 apply only to the all-in plot);
- something else once: the normal turn runs and the offer stays open (`offer_ignored`).
An accepted help writes `support_taken {kind, by}`.

**Fields.** State: `support_used: bool` (true once a supporting hand was accepted). `purse` gains
`grant: {amount_eur, label: "Patron's help: +200 gp, no repayment"}` **only after a grant**.
`decisions[]` rows may have `action: "grant"` (`amount_eur` = the gift, `beat: "support"`, text
"Patron's help: +200 gp"). `breakdown` gains `patron_grant_eur` **only when a grant was taken**; the
key set is otherwise unchanged (`starting_budget, cash_kept, invested, value_now, fees, final_value,
pl_eur, pl_pct`, plus the loan keys with a loan). `debrief` gains `closing` only when it applies.

**Result maths (exact).** The grant restores HP and cash by the same gold: `starting_budget` (the
budget now = HP * 10) and `cash_kept` both rise by the gift, so a gift is not a profit:
`final_value = cash_kept + value_now - loan_repay_eur`, `pl_eur = final_value - starting_budget`, and
the P&L equals that of the same decisions without the damage and the gift. Several loans add up
(`loan.lender` joins the lenders). What-if rows are unchanged.

**Persistence.** No migration. The grant is a `campaign_trade` row (`action: "grant"`, `beat:
"support"`, `amount_cents` = gift, `cash_after_cents` includes it, `shares_after` unchanged) and
`campaign_run.hp_lost` goes down by the restored HP. Events: `support_offer {kind, by, terms, reason}`,
`support_taken`, `support_declined`, `focus_gain`.

**Agent nodes.** `campaign_support` (structured `SupportOut`: kind in the four kinds, name, role, text,
suggestions; the kind must be in the allowed list, else the engine's preference is used; text <= 100
words, guarded: number allowlist with the offer's own terms, no advice, no leak, prepared template
fallback) and `campaign_support_answer` (narrates taking or declining, no figure).

**Closing line.** If the final result is <= 60% of the starting budget and no supporting hand was
taken, the debrief node may add `closing` (one or two warm sentences, no advice, no figures, <= 45
words; a prepared line is the fallback). It is spoken before the reflection question.

**Edu.** New concept `bouncing_back` "Bouncing back from a loss": detected when a supporting hand is
offered (the offer carries a `reason`); prepared lesson in `edu_lessons.py`; the 3-pending cap applies
like for every concept.

## 12. Educational moments (CommerzBuddy bubbles)

A rule-based, generous detector (`campaign/edu.py`, run in the commit phase of every narrated
reply: actions, NPC turns, moves, dice narration, decision scenes, offers, Buddy) flags up to three
"learning moments". It never calls a model and never produces a figure. Each concept fires at most
once per campaign (`concept_question` once per term). Stored in the event log: `edu_moment`
(id, concept_key, title, turn seq, facts snapshot: whole numbers, gp, the player's quote),
`edu_viewed`, `edu_dismissed`, `edu_lesson` (cached lesson), `edu_skipped` (detected while three
were pending; dropped, and it may fire again once a slot is free).

Catalog (`concept_key`: title): `news_reaction` Reacting to news; `first_trade` Your first trade:
what you actually own; `cash_vs_profit` Profit isn't cash; `debt_and_equity` Debt vs what owners
own; `price_move` Why prices move (board move of 8 percent or more while at the market or on the
price board, or the player asks about the chart); `concentration` All eggs in one basket (all-in or
80 percent of gold in one company); `loan_cost` Borrowing costs; `bouncing_back` Bouncing back from a loss (a supporting hand is offered); `thin_reasoning` Deciding with
evidence; `luck_vs_skill` Luck vs judgement (failed or natural 1/20 check, or damage);
`concept_question` "<Term> in plain words" (the player asks what revenue, profit, cash flow, debt,
dividend, share, price, risk, diversification, equity, margin, earnings or ledger means).

- **State** (`GET /campaigns/{id}`, the SSE `state` event and every `done`):
  `edu: {pending: [{id, concept_key, title}], pending_count: 0..3}`. A moment is pending until its
  lesson is opened (viewed) or it is dismissed.
- **Every SSE `done`** (actions, move, narrate-roll, buddy, scene answers, offers, opening) carries
  `edu_new: [{id, concept_key, title}]`: moments detected this turn (`[]` if none). A replayed reply
  keeps its `edu_new`.
- `POST /campaigns/{id}/edu/{moment_id}/lesson` (JSON, not SSE, at most 10 s, deterministic under
  FAKE_LLM) returns
  `{id, title, what_happened, idea, example, takeaway, check: {question, options: [3 strings], answer_index}}`
  and marks the moment viewed (frees its slot). Asking again returns the same cached lesson. 404 for
  an unknown moment or another player's campaign.
- `POST /campaigns/{id}/edu/{moment_id}/dismiss` returns `{id, status, edu}` (`status` is
  `dismissed`, or the existing `viewed`); idempotent. "Later" in the UI calls nothing.
- The lesson is written by the CommerzBuddy node `campaign_edu_lesson` through the shared guards:
  number allowlist (the moment's snapshot figures; small round numbers, multiples of 5 up to 1,000,
  only in `example` and the quiz), leak terms, advice (prefilter, classifier and a lesson-only
  "never says what to buy or sell" rule), internal identifiers, gold pieces only, whole numbers,
  idea at most 60 words, sentences at most 25 words, three distinct options. Any failure, refusal or
  crash serves the prepared lesson of the concept (`agents/campaign/edu_lessons.py`, also the FAKE
  output).
- Buddy's normal reply context lists the titles of pending moments, so it may mention one; the
  offer and the lesson flow are driven by the UI.
- `buddy_q` events now also store `screen` when the client sent one.

## 13. Quest Board (replaces the daily quest)

After choosing a character the player sees a board of quests. Nothing is generated on login or
when visiting the bank. All text is player-safe: fantasy names, no real company, ticker or year;
every field passes the scenario's leak terms (a hit is replaced by a neutral fallback).

**QuestCard** `{id, kind: "curated"|"personal", status: "ready"|"generating"|"failed", step: string|null, title, company_name, trade, teaser, difficulty: "easy"|"medium"|"hard", horizon_days, budget_gp, learn: [<=3 topics], scenario_id: string|null, played, finished}`

- `id`: curated = the scenario id; personal = the generation job id (stable while generating and after).
- `step`: player-safe progress label while generating (e.g. "Writing the campaign"), else null.
- `scenario_id`: null until `ready`; pass it to `POST /campaigns`.
- `horizon_days`: story days from the decision to the end of the quest (0 while generating).
- `budget_gp`: the hero's starting purse in gold pieces (class HP x 10; 1000 without a hero).
- `played` / `finished`: this session has / has finished a campaign run on the scenario.

**GET /quests/board** -> `{curated: QuestCard[], mine: QuestCard[], suggestion: {theme, category_label, why}}`
- `curated`: every playable scenario that is not a personal quest (reference packs and approved gate scenarios); identical for every player; ordered by `board.order`, then title.
- `mine`: this session's personal quests, newest first, including `generating` and `failed` ones.
- `suggestion`: from the mock spending ranking, e.g. `{theme: "Sportswear & sneakers", category_label: "Sportswear & sneakers", why: "You spent the most on sportswear and sneakers this month"}`.

**GET /quests/board/{id}** -> QuestCard plus `details: {briefing, characters: [{name, role}], places: [string], what_you_do: [3 steps]}`. `id` is a curated scenario id or one of the caller's own personal ids; 404 `quest_not_found` otherwise (another player's personal quest is 404). A `generating`/`failed` card has an empty `characters`/`places` and the teaser as briefing.

**POST /quests/generate** body `{theme?: string}` (max 200 chars; body may be omitted) -> 201 QuestCard with `status: "generating"`. Without a theme, the suggestion's category is used. With a theme it is matched deterministically (keywords, category label words, company names and aliases; a company hit picks that company, else the best category); no match falls back to the suggestion. The theme is stored on the job (`detail.theme`). The job runs research, manifest, disguise, publish; poll `GET /quests/board` until the card is `ready` (or `failed`). A company already used by this player (not failed) is skipped.

**Reference-pack manifest `board` block** (optional): `{title, teaser, difficulty, learn[<=3], order, briefing?}`. When absent it is derived from the manifest (title from `meta.campaign_title`, teaser from world and company card, learn from the rubric categories, difficulty from the encounter DCs) at approve time and stored in `scenario.manifest.board`. Packs approved before this change fall back to the same derivation when the board is built. The board text is scanned like any other player text.

**POST /quests/daily** is deprecated and removed in behaviour: it returns `410` `{error: {code: "daily_quests_removed"}}` and generates nothing. `GET /quests` (job list) stays for compatibility; prefer `/quests/board`.

**POST /campaigns** `{scenario_id, interests?}`: `interests` is optional; any ready board quest can be started (a personal quest only by its owner).
