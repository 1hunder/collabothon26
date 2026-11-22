// Fictional guilds only. The board fixture: three curated notices and one personal quest that is
// still being written when the board first opens and becomes ready after FIXTURE_GENERATE_MS.
import type { BoardSuggestion, QuestBoard, QuestCard, QuestCardDetail, QuestDetails } from '../types';
import { FixtureHttpError } from './db';

export const FIXTURE_GENERATE_MS = 6000;
const STEPS = ['Reading your ledger', 'Researching the guild', 'Inking the notice'];

const suggestion: BoardSuggestion = {
  theme: 'Games & consoles',
  category_label: 'Games & consoles',
  why: 'You spent the most on games this month.',
};

interface Entry {
  card: QuestCard;
  details: QuestDetails;
}

const curated: Entry[] = [
  {
    card: {
      id: 'q-lantern',
      kind: 'curated',
      status: 'ready',
      step: null,
      title: 'The Lantern Guild Gambit',
      company_name: 'Lantern Guild',
      trade: 'Lamp oil and lighting',
      teaser: 'A guild of oil-pressers is expanding into three new towns. Is the glow worth the gold?',
      difficulty: 'easy',
      horizon_days: 75,
      budget_gp: 1000,
      learn: ['Reading a price chart', 'News versus noise', 'Position sizing'],
      scenario_id: 'fixture-lumen',
      played: false,
      finished: false,
    },
    details: {
      briefing:
        'The Lantern Guild presses oil for every street lamp from the harbour to the hills. A new press has just opened and rumours of a rival run through the taverns. You hold a purse of gold and a quill. Decide what the guild is worth before the story runs on.',
      characters: [
        { name: 'Master Orrin', role: 'Guildmaster of the Lantern Guild' },
        { name: 'Pell the Lamplighter', role: 'Eyes on every street' },
      ],
      places: ['The Pressing Hall', 'Harbour Lamp Market', 'The Guild Archive'],
      what_you_do: ['Read the guild papers', 'Weigh the news from the market', 'Commit your decision in your own words'],
    },
  },
  {
    card: {
      id: 'q-shipwright',
      kind: 'curated',
      status: 'ready',
      step: null,
      title: 'Keel and Cannon',
      company_name: 'Saltmarsh Shipwrights',
      trade: 'Shipbuilding',
      teaser: 'A shipwright guild wins a royal order, then the timber price jumps. Hold your nerve or sell?',
      difficulty: 'medium',
      horizon_days: 120,
      budget_gp: 1500,
      learn: ['Cost shocks', 'Diversifying a purse', 'Patience'],
      scenario_id: 'fixture-keel',
      played: true,
      finished: false,
    },
    details: {
      briefing:
        'Saltmarsh Shipwrights have built the realm\'s finest hulls for three generations. A royal order fills their yard, but timber is getting dearer by the week. Their fortunes depend on how well they manage the squeeze.',
      characters: [{ name: 'Dame Ysolt', role: 'Master shipwright' }, { name: 'Harl Voss', role: 'Timber merchant' }],
      places: ['The Slipway', 'Timber Wharf'],
      what_you_do: ['Study the yard\'s books', 'Follow the timber price', 'Decide when to buy, hold or sell'],
    },
  },
  {
    card: {
      id: 'q-spice',
      kind: 'curated',
      status: 'ready',
      step: null,
      title: 'The Saffron Ledger',
      company_name: 'House of Ember Spice',
      trade: 'Spice trading',
      teaser: 'A spice house hits a rich season, but one caravan goes missing. Fortune or folly?',
      difficulty: 'hard',
      horizon_days: 180,
      budget_gp: 2500,
      learn: ['Concentration risk', 'Reading rumours', 'Expecting the unexpected'],
      scenario_id: 'fixture-spice',
      played: true,
      finished: true,
    },
    details: {
      briefing:
        'House of Ember Spice trades saffron, pepper and rarer things across the desert roads. A missing caravan could be a disaster or just a delay. Only the ledger knows.',
      characters: [{ name: 'Madame Zarif', role: 'Head of the Spice House' }],
      places: ['The Caravanserai', 'The Counting Room', 'The Night Bazaar'],
      what_you_do: ['Question the caravan masters', 'Check the ledger against rumours', 'Lock in your decision'],
    },
  },
];

let personal: { id: string; theme: string; createdAt: number; card: QuestCard; details: QuestDetails }[] = [];
let seeded = false;
let counter = 0;

function makePersonal(theme: string, createdAt: number): void {
  counter += 1;
  const id = `q-mine-${counter}`;
  const t = theme.trim() || suggestion.theme;
  personal.unshift({
    id,
    theme: t,
    createdAt,
    card: {
      id,
      kind: 'personal',
      status: 'generating',
      step: STEPS[0]!,
      title: '',
      company_name: '',
      trade: '',
      teaser: '',
      difficulty: 'medium',
      horizon_days: 90,
      budget_gp: 1200,
      learn: [],
      scenario_id: null,
      played: false,
      finished: false,
    },
    details: { briefing: '', characters: [], places: [], what_you_do: [] },
  });
}

/** Lazily start the one personal quest that is "being written" when the player first sees the board. */
function seed(): void {
  if (seeded) return;
  seeded = true;
  makePersonal(suggestion.theme, Date.now());
}

function settle(p: (typeof personal)[number], now: number): void {
  const age = now - p.createdAt;
  if (age < FIXTURE_GENERATE_MS) {
    p.card = { ...p.card, step: STEPS[Math.min(STEPS.length - 1, Math.floor(age / (FIXTURE_GENERATE_MS / STEPS.length)))]! };
    return;
  }
  if (p.card.status === 'ready') return;
  const name = p.theme.replace(/\b\w/g, (c) => c.toUpperCase());
  p.card = {
    ...p.card,
    status: 'ready',
    step: null,
    title: `The ${name} Venture`,
    company_name: `${name} Traders`,
    trade: name,
    teaser: `A young guild in the ${p.theme.toLowerCase()} trade asks for your judgement before the season turns.`,
    scenario_id: `fixture-${p.id}`,
    learn: ['Following the money', 'Weighing a young company'],
  };
  p.details = {
    briefing: `${name} Traders are new to the trade and loud about it. Your task is to decide whether their promise holds, using only what the papers and the market tell you.`,
    characters: [{ name: 'Tamsin Reed', role: 'Founder of the guild' }],
    places: ['The Workshop', 'The Market Square'],
    what_you_do: ['Read the guild papers', 'Follow the news', 'Commit your decision'],
  };
}

function settleAll(): void {
  seed();
  const now = Date.now();
  personal.forEach((p) => settle(p, now));
}

export function resetFixtureBoard(): void {
  personal = [];
  seeded = false;
  counter = 0;
}

export function fixtureBoardResponse(method: string, path: string, body?: unknown): unknown {
  if (method === 'GET' && path === '/quests/board') {
    settleAll();
    const board: QuestBoard = { curated: curated.map((e) => e.card), mine: personal.map((p) => p.card), suggestion };
    return board;
  }
  const one = /^\/quests\/board\/([^/]+)$/.exec(path);
  if (method === 'GET' && one) {
    settleAll();
    const entry = [...curated, ...personal].find((e) => e.card.id === one[1]);
    if (!entry) throw new FixtureHttpError(404);
    const detail: QuestCardDetail = { ...entry.card, details: entry.details };
    return detail;
  }
  if (method === 'POST' && path === '/quests/generate') {
    seed();
    const theme = (body as { theme?: string } | undefined)?.theme ?? '';
    makePersonal(theme, Date.now());
    return personal[0]!.card;
  }
  return undefined;
}
