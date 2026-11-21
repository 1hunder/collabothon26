// Fictional company only. Real identities must never enter the bundle.
import type {
  CampaignState,
  CommitRequest,
  CreateCampaignRequest,
  DebriefData,
  OutcomeReveal,
  WhatIfRow,
  XpResult,
  CreateHeroRequest,
  Hero,
  RevealData,
  QuestJob,
  ScenarioSummary,
  ScenarioView,
  Transaction,
} from '../types';

import { FixtureHttpError, classHp, readDb, writeDb } from './db';
import { fixtureNewCampaign, fixturePlayResponse, fixturePlaySse } from './play';

export { FixtureHttpError, resetFixtureDb } from './db';

export const fixtureScenarioId = 'fixture-lumen';

const fixtureTransactions: Transaction[] = [
  { date: '2026-11-20', merchant: 'Spotify', amount_eur: '-10.99', category: 'music', category_label: 'Music & streaming' },
  { date: '2026-11-19', merchant: 'Lieferando', amount_eur: '-18.40', category: 'food_delivery', category_label: 'Food delivery' },
  { date: '2026-11-18', merchant: 'Uber', amount_eur: '-12.60', category: 'mobility', category_label: 'Rides & mobility' },
];

function fixtureDailyQuest(): QuestJob {
  return {
    id: 'fixture-daily',
    kind: 'daily',
    quest_date: new Date().toISOString().slice(0, 10),
    category: 'music',
    category_label: 'Music & streaming',
    status: 'ready',
    step: 'Ready',
    scenario_id: fixtureScenarioId,
    created_at: new Date().toISOString(),
  };
}

const summaries: ScenarioSummary[] = [
  { id: fixtureScenarioId, industry_shown: 'Lantern oil and lighting', source: 'gate' },
];

const view: ScenarioView = {
  id: fixtureScenarioId,
  invented_name: 'Lumenvale Guild',
  industry_shown: 'Lantern oil and lighting',
  beats: [
    { story_day: 12, headline: 'New oil press opens', facts: ['Output rises to 1,200 barrels.'] },
    { story_day: 84, headline: 'Rival guild cuts prices', facts: ['Prices fall by 8%.'] },
  ],
  chart: Array.from({ length: 85 }, (_, i) => ({
    story_day: i,
    price: Math.round((100 + Math.sin(i / 9) * 12 + i * 0.2) * 100) / 100,
  })),
  company_card: { employees: 4200, founded_days_ago: 3600 },
};

const reveal: RevealData = {
  real_name: 'Example Lantern Co.',
  ticker: 'EXLC',
  start_date: '2001-03-01',
  end_date: '2001-08-31',
  series: Array.from({ length: 6 }, (_, i) => ({
    date: `2001-0${i + 3}-01`,
    price: 40 + i * 3 - (i % 2) * 5,
  })),
  news_points: [
    { story_day: 12, real_date: '2001-04-01', real_price: 43, headline: 'New oil press opens' },
    { story_day: 84, real_date: '2001-06-01', real_price: 46, headline: 'Rival cuts prices' },
  ],
  what_changed: ['Company name', 'All dates, replaced by story days', 'Price level (one hidden factor)'],
  n_guessers: 3,
};

const namePattern = /^[\p{L}\p{N} '-]{2,20}$/u;

function createHero(body: unknown): Hero {
  const db = readDb();
  if (db.hero) throw new FixtureHttpError(409);
  const req = body as Partial<CreateHeroRequest> | undefined;
  const name = (req?.name ?? '').trim();
  if (!namePattern.test(name) || !req?.class || !(req.class in classHp)) throw new FixtureHttpError(422);
  const hero: Hero = {
    name,
    class: req.class,
    total_xp: 0,
    items: [],
    history: [],
    active_campaign_id: null,
  };
  writeDb({ ...db, hero });
  return hero;
}

function chooseHeroClass(body: unknown): Hero {
  const db = readDb();
  const heroClass = (body as Partial<CreateHeroRequest> | undefined)?.class;
  if (!db.hero) throw new FixtureHttpError(404);
  if (db.hero.active_campaign_id) throw new FixtureHttpError(409);
  if (!heroClass || !(heroClass in classHp)) throw new FixtureHttpError(422);
  const hero = { ...db.hero, class: heroClass };
  writeDb({ ...db, hero });
  return hero;
}

function createCampaign(body: unknown): CampaignState {
  const db = readDb();
  const req = body as Partial<CreateCampaignRequest> | undefined;
  if (!db.hero) throw new FixtureHttpError(409);
  const hp = classHp[db.hero.class];
  const campaign: CampaignState = {
    ...fixtureNewCampaign(db.hero, req?.interests ?? []),
    budget_eur: hp * 10,
    horizon_days: 75,
    offers_spread: true,
    commit_draft: null,
  };
  writeDb({ hero: { ...db.hero, active_campaign_id: campaign.id }, campaign });
  return campaign;
}

function abandonCampaign(id: string): null {
  const { hero } = readDb();
  if (hero?.active_campaign_id === id) {
    writeDb({ hero: { ...hero, active_campaign_id: null }, campaign: null });
  }
  return null;
}

const fixtureRate = 0.018775; // invested money keeps 1.8775% (a near-total loss)
const money = (n: number): number => Math.round(n * 100) / 100;

function outcomeFor(budget: number, d: CommitRequest): OutcomeReveal {
  const invested = d.action === 'invest' || d.action === 'spread' ? (d.amount_eur ?? 0) : 0;
  const valueNow = money(invested * fixtureRate);
  const finalValue = money(budget - invested + valueNow);
  return {
    locked_at: 'Day 84, evening',
    horizon_days: 75,
    horizon_label: 'about 75 days',
    time_skip_label: '75 days later…',
    action: d.action,
    amount_eur: d.amount_eur ?? null,
    phase: 'reveal',
    series: Array.from({ length: 160 }, (_, i) => ({
      story_day: i,
      price: Math.round((100 + Math.sin(i / 9) * 12 - Math.max(0, i - 84) * 1.2) * 100) / 100,
    })),
    decision_day: 84,
    breakdown: {
      starting_budget: budget,
      cash_kept: money(budget - invested),
      invested,
      value_now: valueNow,
      fees: 0,
      final_value: finalValue,
      pl_eur: money(finalValue - budget),
      pl_pct: Math.round(((finalValue - budget) / budget) * 1000) / 10,
    },
    investment_return_pct: Math.round((fixtureRate - 1) * 1000) / 10,
    hp_before: budget / 10,
    hp_after: Math.round(finalValue / 10),
    currency_note: "Prices in the company's original currency; exchange-rate changes are not included.",
  };
}

function whatIfFor(budget: number, d: CommitRequest): WhatIfRow[] {
  const row = (key: WhatIfRow['key'], label: string, amount: number): WhatIfRow => {
    const final = money(budget - amount + amount * fixtureRate);
    return {
      key,
      label,
      final_value: final,
      pct: Math.round(((final - budget) / budget) * 1000) / 10,
      hp_after: Math.round(final / 10),
      is_yours: false,
    };
  };
  const rows = [
    row('dont_invest', "Don't invest", 0),
    row('half', 'Invest half', budget / 2),
    row('all', 'Invest everything', budget),
    row('spread', 'Spread everything', budget),
  ];
  const mine = outcomeFor(budget, d).breakdown.final_value;
  const hit = rows.find((r) => r.final_value === mine);
  if (hit) hit.is_yours = true;
  else rows.push({ ...row('yours', 'Your choice', d.amount_eur ?? 0), final_value: mine, is_yours: true });
  return rows;
}

const fixtureXp: XpResult = {
  categories: [
    { name: 'Evidence literacy', score: 21, max: 25, rationale: 'You tied the choice to documents.', quote: 'the debt figures worry me' },
    { name: 'Risk awareness', score: 20, max: 25, rationale: 'You named a concrete downside.', quote: 'could lose most of it' },
    { name: 'Decision consistency', score: 15, max: 20, rationale: 'Your amount matched your confidence.', quote: 'a small stake' },
    { name: 'Forecast clarity', score: 11, max: 15, rationale: 'Your forecast was stated clearly.', quote: 'about 40% likely higher' },
    { name: 'Post-reveal reflection', score: 12, max: 15, rationale: 'You named what to check next time.', quote: 'check the cash flow first' },
  ],
  total: 79,
};

function patchCampaign(patch: Partial<CampaignState>): CampaignState {
  const db = readDb();
  if (!db.campaign) throw new FixtureHttpError(404);
  const campaign = { ...db.campaign, ...patch };
  writeDb({ ...db, campaign });
  return campaign;
}

function lock(body: unknown): unknown {
  const db = readDb();
  const d = body as CommitRequest;
  if (!db.campaign || !d?.action || (d.evidence ?? '').trim().length < 20) throw new FixtureHttpError(422);
  writeDb({ ...db, decision: d, campaign: { ...db.campaign, phase: 'reveal' } });
  return outcomeFor(db.campaign.budget_eur ?? 1000, d);
}

function finish(): unknown {
  const db = readDb();
  if (!db.hero || !db.campaign) throw new FixtureHttpError(409);
  const total = db.campaign.xp?.total ?? 0;
  const newItem = db.hero.items.length === 0
    ? { id: 'ratio-lens', name: 'Ratio Lens', description: 'Shows key ratios in documents.' }
    : null;
  const hero: Hero = {
    ...db.hero,
    total_xp: db.hero.total_xp + total,
    items: newItem ? [...db.hero.items, newItem] : db.hero.items,
    history: [
      ...db.hero.history,
      { campaign_id: db.campaign.id, interests: db.campaign.interests, total_xp: total, decision: db.decision?.action, finished_at: new Date().toISOString().slice(0, 10), result_pct: db.decision ? outcomeFor(db.campaign.budget_eur ?? 1000, db.decision).breakdown.pl_pct : null },
    ],
    active_campaign_id: null,
  };
  writeDb({ ...db, hero, campaign: { ...db.campaign, phase: 'done' } });
  return { total_xp: hero.total_xp, new_item: newItem };
}

function sse(event: string, data: unknown): string {
  return `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`;
}

/** Scripted Campaign Master reply, deliberately cut mid-line to exercise the SSE parser. */
export function fixtureSseChunks(path: string, body?: unknown): string[] | undefined {
  const played = fixturePlaySse(path, body);
  if (played) return played;
  if (/^\/campaigns\/[^/]+\/debrief$/.test(path)) {
    const db = readDb();
    if (!db.campaign || !db.decision) return undefined;
    const debrief: DebriefData = {
      sound_reasoning: 'You weighed the debt figures before acting.',
      overlooked: 'Nothing important',
      luck: 'Much of the result came from news nobody could know on Day 84.',
      forecast_line: 'You said 40% likely higher. It ended lower.',
      reflection_question: 'What would you check first next time?',
      whatif: whatIfFor(db.campaign.budget_eur ?? 1000, db.decision),
    };
    patchCampaign({ phase: 'debrief', debrief });
    const script =
      sse('status', { state: 'writing' }) + sse('done', { text: debrief.sound_reasoning, audio_text_id: null, ...debrief });
    return [script.slice(0, 9), script.slice(9)];
  }
  if (!/^\/campaigns\/[^/]+\/(opening|actions|move|buddy)$/.test(path)) return undefined;
  const text = 'Welcome to the Lumenvale Guild hall. What would you do?';
  const script =
    sse('status', { state: 'writing' }) +
    sse('token', { text: 'Welcome to the Lumenvale Guild hall. ' }) +
    sse('token', { text: 'What would you do?' }) +
    sse('state', { can_decide: false }) +
    sse('done', { text, audio_text_id: null });
  const mid = Math.floor(script.length / 2);
  return [script.slice(0, 7), script.slice(7, mid), script.slice(mid)];
}

export function fixtureResponse(method: string, path: string, body?: unknown): unknown {
  const m = method.toUpperCase();
  const played = fixturePlayResponse(m, path, body);
  if (played !== undefined) return played;
  if (m === 'GET' && path === '/hero') {
    const { hero } = readDb();
    if (!hero) throw new FixtureHttpError(404);
    return hero;
  }
  if (m === 'POST' && path === '/hero') return createHero(body);
  if (m === 'PATCH' && path === '/hero') return chooseHeroClass(body);
  if (m === 'GET' && path === '/me/transactions') return fixtureTransactions;
  if (m === 'POST' && path === '/quests/daily') return fixtureDailyQuest();
  if (m === 'GET' && path === '/quests') return [fixtureDailyQuest()];
  if (m === 'POST' && path === '/quests/generate') {
    return { ...fixtureDailyQuest(), id: 'fixture-extra', kind: 'extra', category: 'gaming', category_label: 'Games & consoles' };
  }
  if (m === 'POST' && path === '/campaigns') return createCampaign(body);
  const abandon = /^\/campaigns\/([^/]+)\/abandon$/.exec(path);
  if (m === 'POST' && abandon) return abandonCampaign(abandon[1]!);
  if (m === 'GET' && /^\/campaigns\/[^/]+$/.test(path)) {
    const { campaign } = readDb();
    if (!campaign || path !== `/campaigns/${campaign.id}`) throw new FixtureHttpError(404);
    return campaign;
  }
  if (m === 'PUT' && /^\/campaigns\/[^/]+\/commit-draft$/.test(path)) {
    patchCampaign({ commit_draft: body as CampaignState['commit_draft'] });
    return null;
  }
  if (m === 'POST' && /^\/campaigns\/[^/]+\/lock$/.test(path)) return lock(body);
  if (m === 'GET' && /^\/campaigns\/[^/]+\/reveal$/.test(path)) {
    const db = readDb();
    if (!db.campaign || !db.decision) throw new FixtureHttpError(409);
    return outcomeFor(db.campaign.budget_eur ?? 1000, db.decision);
  }
  if (m === 'POST' && /^\/campaigns\/[^/]+\/reflection$/.test(path)) {
    const c = patchCampaign({ phase: 'company' });
    return { scenario_id: c.scenario_id };
  }
  if (m === 'POST' && /^\/campaigns\/[^/]+\/xp$/.test(path)) {
    patchCampaign({ phase: 'xp', xp: fixtureXp });
    return fixtureXp;
  }
  if (m === 'POST' && /^\/campaigns\/[^/]+\/finish$/.test(path)) return finish();
  if (m === 'POST' && path === '/session') return { session_id: 'fixture-session' };
  if (m === 'GET' && path === '/scenarios/playable') return summaries;
  if (m === 'GET' && /^\/scenario\/[^/]+\/view$/.test(path)) return view;
  if (m === 'GET' && /^\/scenario\/[^/]+\/reveal$/.test(path)) return reveal;
  if (m === 'POST' && /^\/scenario\/[^/]+\/events$/.test(path)) return { ok: true };
  return undefined;
}
