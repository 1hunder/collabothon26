import type { CampaignState, JournalEntry } from '../../api/types';

export interface Notice {
  key: string;
  kind: 'News' | 'Rumour';
  headline: string;
  summary: string;
  day: number | null;
}

const str = (v: unknown): string => (typeof v === 'string' ? v : '');

/**
 * In-story news only. The journal the API already returns holds every news item that has fired
 * (the server cuts it at story today); the campaign state's single `news` is the fallback and
 * rumours already heard follow, without a day.
 */
export function newsNotices(c: CampaignState, journal: readonly JournalEntry[] | undefined): Notice[] {
  const fromJournal: Notice[] = (journal ?? [])
    .filter((e) => e.type === 'news')
    .map((e) => ({
      key: `news-${e.seq}`,
      kind: 'News' as const,
      headline: str(e.headline),
      summary: str(e.summary),
      day: typeof e.story_day === 'number' ? e.story_day : null,
    }))
    .reverse();
  const news: Notice[] =
    fromJournal.length === 0 && c.news_shown && c.news
      ? [{ key: 'news-state', kind: 'News', headline: c.news.headline, summary: c.news.summary, day: null }]
      : fromJournal;
  const rumours: Notice[] = (c.rumours ?? []).map((t, i) => ({ key: `rumour-${i}`, kind: 'Rumour' as const, headline: t, summary: '', day: null })).reverse();
  return [...news, ...rumours];
}
