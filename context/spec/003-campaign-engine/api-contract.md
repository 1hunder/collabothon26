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
| `card` | zero or more: dice `{kind:"dice", roll_id, challenge_id, title, dc, bonus: 2, keen_eye_available, keen_eye_left}` or news `{kind:"news", headline, summary, time_skip_label, story_day, framing, framing_audio_text_id}`. |
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
              final, options: ("continue"|"reroll"|"accept")[], rerolled, rerolls_left, keen_eye_left, alt_source|null}

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
| missing | reply ends with "What made you choose that?" |
| thin | reply ends with "Can you say a bit more about why?" (the thin reason is kept) |

When it asks, the decision awaits its answer and the `done` of that turn has `awaiting_reasoning: true`
(suggestions: one "I'd rather skip that" chip). The player's NEXT message to `POST /actions` is
recorded verbatim (appended to a thin first reason), `reasoning_source: "asked"`, and answered with a
short templated, neutral acknowledgement ending "What do you do next?" (no model call, so no praise,
advice or hint). Asked at most once per decision. A clear skip ("skip", "no reason", "rather not")
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
