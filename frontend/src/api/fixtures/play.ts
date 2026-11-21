// Fixture mode for the play endpoints (spec 003 tech 2.5): campaign state, turns, rolls, Buddy,
// Focus actions, journal and scripted SSE. Fictional company only; mirrors the backend's shapes.
import {
  FixtureHttpError,
  classHp,
  readDb,
  writeDb,
  type FixtureDb,
  type FixtureEvent,
  type FixturePlay,
} from './db';
import type {
  BacklogEntry,
  CampaignState,
  ClueEntry,
  DiceCard,
  Hero,
  JournalEntry,
  LibraryDocument,
  PlayLocation,
  PriceRow,
  RollResult,
} from '../types';

const SCENARIO_ID = 'fixture-lumen';
const START_DAY = 60;
const NEWS_DAY = 84;
const ROLL_BONUS = 2;
const BONUS_DC = 18;

const loc = (key: string, name: string, description: string, fixed: boolean): PlayLocation => ({
  id: `loc-${key}`,
  key,
  name,
  description,
  fixed,
  art_status: 'pending',
  visited: false,
});

const locations = (): PlayLocation[] => [
  loc('tavern', 'Tavern', 'A low room that smells of wax and wet wool. Guild notices cover one wall.', true),
  loc('market_square', 'Market Square', 'Stalls, shouting brokers and a tall price board above the fountain.', true),
  loc('library', 'Library', 'Shelves of ledgers and proclamations. A scholar copies figures by candlelight.', true),
  loc('lamp-works', 'The Lamp Works', 'Hot glass, long benches and a foreman who counts every barrel twice.', false),
];

function priceRows(toDay: number): PriceRow[] {
  const close = (i: number): number => Math.round((100 + Math.sin(i / 9) * 12 + i * 0.2) * 100) / 100;
  const out: PriceRow[] = [];
  for (let day = 1; day <= toDay; day += 1) {
    const open = close(day - 1);
    const c = close(day);
    out.push({
      day,
      open,
      high: Math.round((Math.max(open, c) + 1.2) * 100) / 100,
      low: Math.round((Math.min(open, c) - 1.2) * 100) / 100,
      close: c,
      volume: 1000 + ((day * 37) % 400),
    });
  }
  return out;
}

const introDocs = (): LibraryDocument[] => [
  {
    id: 'doc-ledger',
    title: 'Guild ledger, year one',
    entries: [{ id: 'clue-ledger', title: 'Barrels sold', text: 'The guild sold 1,200 barrels of lamp oil, up from 900.' }],
  },
];

const newsDoc: LibraryDocument = {
  id: 'doc-loss',
  title: 'Quarterly loss notice',
  entries: [{ id: 'clue-news', title: 'A loss is announced', text: 'The guild reports a loss of 340 coins after a write-down.' }],
};

function emptyPlay(): FixturePlay {
  return { events: [], rolls: {}, replays: {} };
}

const playOf = (db: FixtureDb): FixturePlay => db.play ?? emptyPlay();

function addEvent(play: FixturePlay, type: string, payload: Record<string, unknown> = {}): FixtureEvent {
  const ev: FixtureEvent = { seq: play.events.length + 1, type, ...payload };
  play.events.push(ev);
  return ev;
}

function backlogOf(events: FixtureEvent[]): BacklogEntry[] {
  const out: BacklogEntry[] = [];
  for (const e of events) {
    const text = String(e.text ?? '');
    if (e.type === 'action') out.push({ seq: e.seq, speaker: 'You', text });
    else if (e.type === 'dm_reply') out.push({ seq: e.seq, speaker: String(e.speaker ?? 'Campaign Master'), text });
    else if (e.type === 'buddy_q') out.push({ seq: e.seq, speaker: 'You (to Buddy)', text });
    else if (e.type === 'buddy_a') out.push({ seq: e.seq, speaker: 'CommerzBuddy', text });
  }
  return out;
}

/** Fresh campaign in phase `setup`, as the backend returns it from POST /campaigns. */
export function fixtureNewCampaign(hero: Hero, interests: string[]): CampaignState {
  const hp = classHp[hero.class];
  return {
    id: crypto.randomUUID(),
    scenario_id: SCENARIO_ID,
    phase: 'setup',
    interests,
    hero: { name: hero.name, class: hero.class, total_xp: hero.total_xp, items: hero.items.map((i) => i.id) },
    hp,
    hp_eur: hp * 10,
    suggestions: [],
    focus_left: 3,
    rerolls_left: hero.class === 'analyst' ? 1 : 0,
    keen_eye_left: hero.class === 'investigator' ? 1 : 0,
    bonus_lead_available: true,
    turn_count: 0,
    story_day: START_DAY,
    story_day_label: `Day ${START_DAY}`,
    news_shown: false,
    news: null,
    current_location_id: null,
    locations: locations(),
    backlog: [],
    clues: [],
    library: {
      documents: introDocs(),
      company_card: {
        name: 'Lumenvale Guild',
        trade: 'Lantern oil and lighting',
        size: 'About 4,200 workers',
        key_figures: [{ id: 'barrels', label: 'Barrels sold', value: 1200, period: 'last year' }],
      },
    },
    price_board: priceRows(START_DAY),
    challenges: [
      { id: 'ch-report', title: 'Spot what is off in the half-year ledger', dc: 12, state: 'open', optional: false, result: null, location: 'library' },
    ],
    pending: null,
    can_decide: false,
    opening_done: false,
    budget_eur: hp * 10,
    horizon_days: 75,
    offers_spread: true,
    commit_draft: null,
  };
}

// ---- helpers over the stored campaign ---------------------------------------------------------

interface Ctx {
  db: FixtureDb;
  c: CampaignState;
  play: FixturePlay;
}

function ctx(): Ctx {
  const db = readDb();
  if (!db.campaign) throw new FixtureHttpError(404);
  return { db, c: db.campaign, play: playOf(db) };
}

function save({ db, c, play }: Ctx): void {
  c.backlog = backlogOf(play.events);
  c.can_decide = c.phase === 'play' && c.opening_done && c.pending === null && c.clues.length >= 2 && c.news_shown;
  writeDb({ ...db, campaign: c, play });
}

function grantClue(x: Ctx, clueId: string, title: string, text: string, source: string): void {
  if (x.c.clues.some((k) => k.clue_id === clueId)) return;
  const clue: ClueEntry = { clue_id: clueId, source, title, text };
  x.c.clues.push(clue);
  addEvent(x.play, 'clue_found', { clue_id: clueId, title, text, source });
}

const freeClueAt: Record<string, { id: string; title: string; text: string }> = {
  library: { id: 'clue-ledger', title: 'Barrels sold', text: 'The guild sold 1,200 barrels of lamp oil, up from 900.' },
  market_square: { id: 'clue-board', title: 'The price board', text: 'The price has drifted up for sixty days, with thin trading.' },
};

function sse(event: string, data: unknown): string {
  return `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`;
}

function textTokens(text: string): string[] {
  const mid = Math.floor(text.length / 2);
  const cut = text.indexOf(' ', mid);
  return cut === -1 ? [text] : [text.slice(0, cut + 1), text.slice(cut + 1)];
}

/** One scripted turn as SSE chunks, deliberately split mid-event to exercise the parser. */
function script(text: string, done: Record<string, unknown>, cards: Record<string, unknown>[] = [], canDecide = false): string {
  return (
    sse('status', { state: 'writing' }) +
    textTokens(text).map((t) => sse('token', { text: t })).join('') +
    cards.map((card) => sse('card', card)).join('') +
    sse('state', { can_decide: canDecide }) +
    sse('done', { text, audio_text_id: null, ...done })
  );
}

const chunked = (s: string): string[] => {
  const mid = Math.floor(s.length / 2);
  return [s.slice(0, 7), s.slice(7, mid), s.slice(mid)];
};

const openingText =
  'Welcome, traveller, to the Gilded Tavern. Rain taps the shutters, and the whole room is talking about one name: the Lumenvale Guild, makers of lantern oil for half the city. ' +
  'Your purse holds the coins the guild has lent you to invest, and you have about seventy-five days before the next fair. ' +
  'Your goal is to learn enough about the guild to decide whether to put coins into its shares, keep them, or wait. ' +
  'So far you know only that its price has crept upward for sixty days and that a rival guild has opened a stall nearby. ' +
  'The Library holds the ledgers and proclamations, and Market Square shows the price board and the loud opinions of the crowd. ' +
  'A scholar waits in the Library, and a broker shouts from the Square. CommerzBuddy can be called whenever you wish. ' +
  'What would you do?';

const startSuggestions = [
  'Head to the Library to read the ledgers',
  'Walk to Market Square and study the price board',
  'Ask the barkeep what people say about the guild',
];

// ---- SSE endpoints ----------------------------------------------------------------------------

function replayed(x: Ctx, key: string): string[] | null {
  const hit = x.play.replays[key];
  return hit === undefined ? null : chunked(hit);
}

function remember(x: Ctx, key: string | null, s: string): string[] {
  if (key !== null) x.play.replays[key] = s;
  return chunked(s);
}

function fireNews(x: Ctx): Record<string, unknown> {
  x.c.news_shown = true;
  x.c.story_day = NEWS_DAY;
  x.c.story_day_label = `Day ${NEWS_DAY}`;
  x.c.news = {
    headline: 'The guild reports a loss',
    summary: 'The Lumenvale Guild announced a loss of 340 coins after writing down its oil stocks.',
  };
  x.c.price_board = priceRows(NEWS_DAY);
  x.c.library.documents = [...introDocs(), newsDoc];
  const card = { kind: 'news', headline: x.c.news.headline, summary: x.c.news.summary, time_skip_label: '24 days later…', story_day: NEWS_DAY };
  addEvent(x.play, 'news', card);
  grantClue(x, 'clue-news', 'A loss is announced', newsDoc.entries[0]?.text ?? '', 'news');
  const text = 'The notice is nailed to the board for everyone to read. How does this news change your thinking? What would you do?';
  addEvent(x.play, 'dm_reply', { speaker: 'Campaign Master', text });
  return { card, text };
}

function countTurn(x: Ctx, arrivedAt?: string): { card: Record<string, unknown>; text: string } | null {
  x.c.turn_count += 1;
  const due = x.c.turn_count >= 6 || (arrivedAt === 'market_square' && x.c.turn_count >= 3);
  return !x.c.news_shown && due ? (fireNews(x) as { card: Record<string, unknown>; text: string }) : null;
}

function openingSse(): string[] {
  const x = ctx();
  const key = 'opening';
  const hit = replayed(x, key);
  if (hit) return hit;
  const tavern = x.c.locations.find((l) => l.key === 'tavern');
  if (tavern) {
    tavern.visited = true;
    x.c.current_location_id = tavern.id;
  }
  x.c.phase = 'play';
  x.c.opening_done = true;
  x.c.suggestions = startSuggestions;
  addEvent(x.play, 'dm_reply', { speaker: 'Campaign Master', text: openingText, opening: true });
  const out = remember(x, key, script(openingText, { speaker: 'Campaign Master', suggestions: startSuggestions }));
  save(x);
  return out;
}

/** Fixture art for a generated place turns ready a few seconds after it is created. */
const FIXTURE_ART_MS = 6_000;

/** Called on every campaign GET: pending art whose time has come becomes ready. */
export function fixtureSettleArt(): void {
  const db = readDb();
  const due = db.play?.artReadyAt;
  if (!db.campaign || !due) return;
  let changed = false;
  for (const l of db.campaign.locations) {
    const at = due[l.id];
    if (l.art_status === 'pending' && at !== undefined && Date.now() >= at) {
      l.art_status = 'ready';
      changed = true;
    }
  }
  if (changed) writeDb(db);
}

function npcReply(x: Ctx, npcName: string, text: string, extra: Record<string, unknown> = {}): { speaker: string; extras: Record<string, unknown> } {
  addEvent(x.play, 'dm_reply', { speaker: npcName, text });
  return { speaker: npcName, extras: { speaker: npcName, speaker_kind: 'npc', escalated: false, ...extra } };
}

function actionSse(body: { text?: string; client_msg_id?: string }): string[] {
  const x = ctx();
  const key = body.client_msg_id ? `actions:${body.client_msg_id}` : null;
  if (key) {
    const hit = replayed(x, key);
    if (hit) return hit;
  }
  const text = (body.text ?? '').trim();
  if (!text) throw new FixtureHttpError(422);
  if (x.c.pending) throw new FixtureHttpError(409);
  addEvent(x.play, 'action', { text });
  const wantsDecide = /decide|ready to invest/i.test(text);
  const wantsRoll = /ledger|report|figure|spot|check|odd/i.test(text) && x.c.challenges.some((c) => c.id === 'ch-report' && c.state === 'open');
  let reply = 'The scholar nods slowly. "A fair question. Look closely at the figures, and compare them with the crowd\'s opinions." What would you do?';
  const cards: Record<string, unknown>[] = [];
  let showDecide = false;
  if (wantsRoll) {
    const card = offerRoll(x, 'ch-report');
    cards.push(card);
    reply = 'You lean over the half-year ledger and run a finger down the columns. Something about the totals looks odd.';
  } else if (wantsDecide) {
    showDecide = x.c.clues.length >= 2 && x.c.news_shown;
    reply = showDecide ? 'Ready to make your decision?' : 'Not yet. There is still something to uncover first. What would you do?';
  }
  const here = x.c.locations.find((l) => l.id === x.c.current_location_id);
  const done: Record<string, unknown> = { speaker: 'Campaign Master', speaker_kind: 'master', escalated: false, hp_change: null };
  let speaker = 'Campaign Master';
  let suggestions = ['Check the ledger for anything odd', 'Visit Market Square', 'Ask the scholar what a write-down is'];
  if (/docks?|warehouse/i.test(text) && !wantsRoll && !wantsDecide) {
    // The Master invents a place with its own NPC; art is painted in the background.
    const id = 'docks-warehouse';
    let made = x.c.locations.find((l) => l.id === id);
    if (!made) {
      made = { id, key: id, name: 'The Docks Warehouse', description: 'Crates stamped with the guild seal tower over a damp stone floor.', fixed: false, art_status: 'pending', visited: true, npc: { id: 'orrin-vale', name: 'Orrin Vale', role: 'harbour clerk' }, generated: true };
      x.c.locations.push(made);
      x.play.artReadyAt = { ...(x.play.artReadyAt ?? {}), [id]: Date.now() + FIXTURE_ART_MS };
    }
    made.visited = true;
    x.c.current_location_id = id;
    const intro = 'You slip into the Docks Warehouse. A tired man looks up from a tally board. "Orrin Vale, harbour clerk. Not many come asking after the guild\'s crates. What do you want to know?"';
    const r = npcReply(x, 'Orrin Vale', intro);
    reply = intro;
    speaker = r.speaker;
    Object.assign(done, r.extras, {
      location: { id, key: id, name: made.name },
      new_location: { id, key: id, name: made.name, description: made.description, art_status: made.art_status, npc: made.npc },
    });
    suggestions = ['Ask Orrin about the guild\'s crates', 'Ask how busy the docks are', 'Return to the Tavern'];
  } else if (/vault|break in|steal|smash|threaten/i.test(text) && !wantsRoll && !wantsDecide) {
    // Reckless: the Master steps in and the hero pays for it.
    const delta = -5;
    x.c.hp += delta;
    x.c.hp_eur = x.c.hp * 10;
    reply = 'The guards are faster than you hoped. A cudgel finds your ribs before you reach the door, and your purse is lighter for the trouble. What would you do?';
    Object.assign(done, {
      speaker_kind: 'master',
      escalated: here?.npc !== undefined && here.npc !== null,
      hp_change: { delta, reason: 'The vault guards caught you', hp: x.c.hp, hp_eur: x.c.hp_eur },
    });
    addEvent(x.play, 'hp_change', { delta, reason: 'The vault guards caught you' });
  } else if (here?.npc && !wantsRoll && !wantsDecide) {
    reply = `"Good question," says ${here.npc.name}. "The crates left for the guild's rival twice this month, and nobody signed for them." What would you do?`;
    const r = npcReply(x, here.npc.name, reply);
    speaker = r.speaker;
    Object.assign(done, r.extras);
    suggestions = ['Ask who signed for the crates', 'Return to the Tavern'];
  }
  const news = countTurn(x);
  if (speaker === 'Campaign Master') addEvent(x.play, 'dm_reply', { speaker, text: reply });
  x.c.suggestions = suggestions;
  if (news) cards.push(news.card);
  const out = remember(x, key, script(reply, { ...done, suggestions, show_decide: showDecide, ...(news ? { news_text: news.text } : {}) }, cards));
  save(x);
  return out;
}

function moveSse(body: { location_id?: string }): string[] {
  const x = ctx();
  if (x.c.pending) throw new FixtureHttpError(409);
  const target = x.c.locations.find((l) => l.id === body.location_id);
  if (!target) throw new FixtureHttpError(404);
  const first = !target.visited;
  target.visited = true;
  x.c.current_location_id = target.id;
  addEvent(x.play, 'move', { location_id: target.id, key: target.key, name: target.name, first_visit: first });
  const free = freeClueAt[target.key];
  if (free) grantClue(x, free.id, free.title, free.text, 'location');
  const news = countTurn(x, target.key);
  const text = first ? `You arrive at the ${target.name}. ${target.description} What would you do?` : `You are back at the ${target.name}. What would you do?`;
  addEvent(x.play, 'dm_reply', { speaker: 'Campaign Master', text });
  const suggestions = ['Look around carefully', 'Talk to someone nearby', 'Check the map for another place'];
  x.c.suggestions = suggestions;
  const out = chunked(
    script(text, { speaker: 'Campaign Master', suggestions, first_visit: first, location: { id: target.id, key: target.key, name: target.name }, ...(news ? { news_text: news.text } : {}) }, news ? [news.card] : []),
  );
  save(x);
  return out;
}

function buddySse(body: { text?: string; client_msg_id?: string }): string[] {
  const x = ctx();
  const key = body.client_msg_id ? `buddy:${body.client_msg_id}` : null;
  if (key) {
    const hit = replayed(x, key);
    if (hit) return hit;
  }
  const text = (body.text ?? '').trim();
  if (!text) throw new FixtureHttpError(422);
  addEvent(x.play, 'buddy_q', { text });
  const answer = /should i|buy|sell/i.test(text)
    ? "That's your call. What evidence would make you more or less confident?"
    : 'A drawdown is how far a price has fallen from its last high. It says how much it hurt, not why. What would you want to know first?';
  addEvent(x.play, 'buddy_a', { speaker: 'CommerzBuddy', text: answer });
  const out = remember(x, key, script(answer, { speaker: 'CommerzBuddy' }));
  save(x);
  return out;
}

function hintSse(): string[] {
  const x = ctx();
  if (x.c.focus_left < 1) throw new FixtureHttpError(409);
  x.c.focus_left -= 1;
  addEvent(x.play, 'focus_spend', { kind: 'hint' });
  const text = 'A clue still waits in the Library. The scholar can show you where the ledger totals are written. What would you do?';
  addEvent(x.play, 'dm_reply', { speaker: 'Campaign Master', text });
  const out = chunked(script(text, { speaker: 'Campaign Master', suggestions: startSuggestions, hint_location: 'library' }));
  save(x);
  return out;
}

function narrateSse(body: { roll_id?: string }): string[] {
  const x = ctx();
  const ch = x.c.challenges.find((c) => c.id === body.roll_id);
  if (!ch || ch.state !== 'final') throw new FixtureHttpError(409);
  const text =
    ch.result === 'success'
      ? 'The numbers fall into place. A line in the ledger does not match the total on the cover, and you copy it down. What would you do?'
      : 'The scholar is called away and the page smudges. The same facts are posted on the Market Square board instead. What would you do?';
  addEvent(x.play, 'dm_reply', { speaker: 'Campaign Master', text, roll_id: ch.id });
  const suggestions = ['Visit Market Square', 'Ask the scholar a question', 'Take another look at the ledger'];
  x.c.suggestions = suggestions;
  const out = chunked(script(text, { speaker: 'Campaign Master', suggestions }));
  save(x);
  return out;
}

/** Scripted SSE for the play endpoints, or undefined when the path is not one of them. */
export function fixturePlaySse(path: string, body?: unknown): string[] | undefined {
  const m = /^\/campaigns\/[^/]+\/(opening|actions|move|buddy|narrate-roll|focus\/hint)$/.exec(path);
  // no campaign yet: let the generic scripted reply serve (SSE parser tests)
  if (!m || !readDb().campaign) return undefined;
  const b = (body ?? {}) as Record<string, string>;
  switch (m[1]) {
    case 'opening':
      return openingSse();
    case 'actions':
      return actionSse(b);
    case 'move':
      return moveSse(b);
    case 'buddy':
      return buddySse(b);
    case 'narrate-roll':
      return narrateSse(b);
    default:
      return hintSse();
  }
}

// ---- dice -------------------------------------------------------------------------------------

function offerRoll(x: Ctx, challengeId: string): DiceCard & Record<string, unknown> {
  const ch = x.c.challenges.find((c) => c.id === challengeId);
  if (!ch) throw new FixtureHttpError(404);
  x.c.pending = { type: 'roll', challenge_id: challengeId, state: 'offered' };
  return {
    kind: 'dice',
    roll_id: ch.id,
    challenge_id: ch.id,
    title: ch.title,
    dc: ch.dc,
    bonus: ROLL_BONUS,
    keen_eye_available: x.c.hero.class === 'investigator' && x.c.keen_eye_left > 0,
    keen_eye_left: x.c.keen_eye_left,
  };
}

function rollPayload(x: Ctx, id: string, dice: number[], final: boolean, options: RollResult['options'], rerolled: boolean): RollResult {
  const ch = x.c.challenges.find((c) => c.id === id);
  if (!ch) throw new FixtureHttpError(404);
  const used = Math.max(...dice);
  const total = used + ROLL_BONUS;
  const success = used === 20 || (used !== 1 && total >= ch.dc);
  const result = success ? 'success' : 'setback';
  ch.result = result;
  return {
    roll_id: id,
    challenge_id: id,
    title: ch.title,
    dice,
    used,
    bonus: ROLL_BONUS,
    total,
    dc: ch.dc,
    result,
    final,
    options,
    rerolled,
    rerolls_left: x.c.rerolls_left,
    keen_eye_left: x.c.keen_eye_left,
    alt_source: success ? null : 'the price board in Market Square',
  };
}

function finalize(x: Ctx, id: string): void {
  const ch = x.c.challenges.find((c) => c.id === id);
  if (!ch) return;
  ch.state = 'final';
  x.c.pending = null;
  if (ch.result === 'success') {
    const text = id === 'ch-bonus' ? 'A bonus lead: the foreman keeps a second set of books.' : 'One ledger line does not match its total.';
    grantClue(x, id === 'ch-bonus' ? 'clue-bonus' : 'clue-report', id === 'ch-bonus' ? 'A bonus lead' : 'The odd ledger line', text, 'dice');
  }
}

function doRoll(body: { challenge_id?: string; mode?: string }): RollResult {
  const x = ctx();
  const id = body.challenge_id ?? '';
  const ch = x.c.challenges.find((c) => c.id === id);
  if (!ch) throw new FixtureHttpError(404);
  if (ch.state === 'final' || ch.state === 'rolling') throw new FixtureHttpError(409);
  const advantage = body.mode === 'advantage';
  if (advantage) {
    if (x.c.hero.class !== 'investigator' || x.c.keen_eye_left < 1) throw new FixtureHttpError(409);
    x.c.keen_eye_left -= 1;
    addEvent(x.play, 'keen_eye', { challenge_id: id });
  }
  const bonus = id === 'ch-bonus';
  const analystMiss = !bonus && x.c.hero.class === 'analyst';
  const first = advantage ? [9, 14] : bonus ? [19] : analystMiss ? [5] : [14];
  x.play.rolls[id] = { first, second: [17], rerolled: false };
  const canReroll = analystMiss && x.c.rerolls_left > 0;
  const probe = rollPayload(x, id, first, true, ['continue'], false);
  const final = probe.result === 'success' || !canReroll;
  const out: RollResult = final ? probe : { ...probe, final: false, options: ['reroll', 'accept'] };
  if (final) finalize(x, id);
  else {
    ch.state = 'rolling';
    x.c.pending = { type: 'roll', challenge_id: id, state: 'rolling' };
  }
  addEvent(x.play, 'dice_roll', { ...out });
  save(x);
  return out;
}

function doReroll(id: string): RollResult {
  const x = ctx();
  const ch = x.c.challenges.find((c) => c.id === id);
  const roll = x.play.rolls[id];
  if (!ch || !roll || ch.state !== 'rolling' || x.c.rerolls_left < 1) throw new FixtureHttpError(409);
  x.c.rerolls_left -= 1;
  roll.rerolled = true;
  const out = rollPayload(x, id, roll.second, true, ['continue'], true);
  finalize(x, id);
  addEvent(x.play, 'dice_roll', { ...out });
  save(x);
  return out;
}

function doAccept(id: string): RollResult {
  const x = ctx();
  const ch = x.c.challenges.find((c) => c.id === id);
  const roll = x.play.rolls[id];
  if (!ch || !roll || ch.state !== 'rolling') throw new FixtureHttpError(409);
  const out = rollPayload(x, id, roll.first, true, ['continue'], false);
  finalize(x, id);
  addEvent(x.play, 'dice_roll', { ...out });
  save(x);
  return out;
}

function bonusLead(): DiceCard & Record<string, unknown> {
  const x = ctx();
  if (x.c.focus_left < 1 || !x.c.bonus_lead_available || x.c.pending) throw new FixtureHttpError(409);
  x.c.focus_left -= 1;
  x.c.bonus_lead_available = false;
  x.c.challenges.push({ id: 'ch-bonus', title: 'A bonus lead', dc: BONUS_DC, state: 'open', optional: true, result: null, location: null });
  addEvent(x.play, 'focus_spend', { kind: 'bonus_lead' });
  const card = offerRoll(x, 'ch-bonus');
  save(x);
  return card;
}

function journalEntries(): JournalEntry[] {
  const { play } = ctx();
  const types = new Set(['move', 'action', 'dice_roll', 'clue_found', 'buddy_q', 'buddy_a', 'news', 'focus_spend']);
  return play.events
    .filter((e) => types.has(e.type) && (e.type !== 'dice_roll' || e.final === true))
    .map((e) => ({ ...e }));
}

/** Play-slice JSON endpoints, or undefined when the route is not one of them. */
export function fixturePlayResponse(method: string, path: string, body?: unknown): unknown {
  const m = method.toUpperCase();
  const b = (body ?? {}) as Record<string, string>;
  let hit: RegExpExecArray | null;
  if (m === 'POST' && /^\/campaigns\/[^/]+\/rolls$/.test(path)) return doRoll(b);
  if (m === 'POST' && (hit = /^\/campaigns\/[^/]+\/rolls\/([^/]+)\/reroll$/.exec(path))) return doReroll(hit[1] ?? '');
  if (m === 'POST' && (hit = /^\/campaigns\/[^/]+\/rolls\/([^/]+)\/accept$/.exec(path))) return doAccept(hit[1] ?? '');
  if (m === 'POST' && /^\/campaigns\/[^/]+\/focus\/bonus-lead$/.test(path)) return bonusLead();
  if (m === 'GET' && /^\/campaigns\/[^/]+\/journal$/.test(path)) return { entries: journalEntries() };
  if (m === 'PUT' && /^\/campaigns\/[^/]+\/commit-draft$/.test(path)) {
    // Opening the commit screen moves the server phase; the draft itself is stored by the commit slice.
    const x = ctx();
    if (x.c.phase === 'play') {
      x.c.phase = 'commit';
      save(x);
    }
  }
  if (m === 'POST' && /^\/campaigns\/[^/]+\/resume-play$/.test(path)) {
    const x = ctx();
    if (x.c.phase === 'commit') {
      x.c.phase = 'play';
      save(x);
    }
    return { phase: 'play', commit_draft: x.c.commit_draft ?? null };
  }
  return undefined;
}
