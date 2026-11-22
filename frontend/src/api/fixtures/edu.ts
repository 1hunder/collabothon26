// Fixture mode for learning moments: they appear on the demo path and are served as lessons.
import { FixtureHttpError, readDb, writeDb } from './db';
import type { EduLesson, EduMoment } from '../types';

interface Concept {
  moment: EduMoment;
  due: (c: NonNullable<ReturnType<typeof readDb>['campaign']>) => boolean;
  lesson: Omit<EduLesson, 'id' | 'title'>;
}

const visited = (c: { locations: { key: string; visited: boolean }[] }, key: string): boolean =>
  c.locations.some((l) => l.key === key && l.visited);

const concepts: Concept[] = [
  {
    moment: { id: 'edu-profit-cash', concept_key: 'profit_vs_cash', title: "Profit isn't cash" },
    due: (c) => visited(c, 'library'),
    lesson: {
      what_happened:
        'In the Library you read that the guild booked a fine profit, yet one ledger line did not match the total on the cover.',
      idea: 'Profit is what the books say you earned. Cash is the coins actually in the strongbox. A guild can sell oil on credit, write the sale down as profit, and still wait months for the coins.',
      example:
        'Imagine you sell 100 barrels and the buyer promises to pay next season. Your ledger shows a profit today, but your purse is no fuller until the buyer pays.',
      takeaway: 'Always ask: did the profit turn into cash?',
      check: {
        question: 'A guild shows a big profit but its strongbox is nearly empty. What is a likely reason?',
        options: ['Buyers have not paid yet', 'The guild sold nothing', 'Profit and cash are always equal'],
        answer_index: 0,
      },
    },
  },
  {
    moment: { id: 'edu-price-value', concept_key: 'price_vs_value', title: "A rising price isn't proof" },
    due: (c) => visited(c, 'market_square'),
    lesson: {
      what_happened: 'On the price board you saw the guild share climb for sixty days, with only a few traders buying.',
      idea: 'A price tells you what the last buyer paid, not what the business is worth. When few people trade, a small push can move the price a long way.',
      example: 'If only three people trade a share all week, one eager buyer can lift the price 5 coins without anything changing in the guild.',
      takeaway: 'A climbing price is a clue, not an answer.',
      check: {
        question: 'Why is a rising price alone weak evidence?',
        options: ['It may reflect a few eager buyers', 'Prices never reflect anything', 'It proves the guild is growing'],
        answer_index: 0,
      },
    },
  },
  {
    moment: { id: 'edu-news', concept_key: 'reacting_to_news', title: 'Reacting to news' },
    due: (c) => c.news_shown,
    lesson: {
      what_happened: 'A notice announced that the guild lost 340 coins, and the price board jumped around right after.',
      idea: 'News moves prices fast, and the first reaction is often too big. Ask what changed for the business, not only how the headline feels.',
      example: 'A loss caused by a one-off write-down may matter less than a loss caused by customers leaving.',
      takeaway: 'Pause, then ask what the news really changes.',
      check: {
        question: 'What is a calm first step after surprising news?',
        options: ['Work out what it changes for the business', 'Sell at once', 'Ignore it'],
        answer_index: 0,
      },
    },
  },
];

const byId = (id: string): Concept | undefined => concepts.find((k) => k.moment.id === id);

/** Raises newly due moments (max 3 waiting) and returns them. */
function raise(): EduMoment[] {
  const db = readDb();
  const c = db.campaign;
  if (!c) return [];
  const seen = new Set(db.eduSeen ?? []);
  const pending = c.edu?.pending ?? [];
  const fresh = concepts.filter((k) => !seen.has(k.moment.id) && k.due(c)).map((k) => k.moment).slice(0, 3 - pending.length);
  const next = [...pending, ...fresh];
  c.edu = { pending: next, pending_count: next.length };
  writeDb({ ...db, campaign: c, eduSeen: [...seen, ...fresh.map((m) => m.id)] });
  return fresh;
}

/** Adds `edu_new` to the `done` event of a scripted reply, and `edu` to its `state` event. */
export function withEdu(chunks: string[]): string[] {
  const fresh = raise();
  const edu = readDb().campaign?.edu ?? { pending: [], pending_count: 0 };
  const patch = (event: string, extra: Record<string, unknown>) => (all: string): string =>
    all.replace(new RegExp(`(event: ${event}\\ndata: )(.*)\\n`), (_m, head: string, json: string) => `${head}${JSON.stringify({ ...(JSON.parse(json) as object), ...extra })}\n`);
  const joined = patch('done', { edu_new: fresh })(patch('state', { edu })(chunks.join('')));
  const mid = Math.floor(joined.length / 2);
  return [joined.slice(0, 7), joined.slice(7, mid), joined.slice(mid)];
}

/** POST lesson (marks viewed) or dismiss (marks dismissed); both take the moment off the pending list. */
export function eduFixtureLesson(id: string, dismiss: boolean): EduLesson | null {
  const k = byId(id);
  if (!k) throw new FixtureHttpError(404);
  const db = readDb();
  if (db.campaign?.edu) {
    const pending = db.campaign.edu.pending.filter((m) => m.id !== id);
    db.campaign.edu = { pending, pending_count: pending.length };
    writeDb(db);
  }
  return dismiss ? null : { id, title: k.moment.title, ...k.lesson };
}
