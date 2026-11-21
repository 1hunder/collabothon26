import { describe, expect, it } from 'vitest';
import type { CampaignState } from '../../api/types';
import { newsNotices } from './newsNotices';

const base = { news_shown: false, news: null, rumours: undefined } as unknown as CampaignState;

describe('newsNotices', () => {
  it('is empty before any news has broken', () => {
    expect(newsNotices(base, [{ seq: 1, type: 'move', name: 'Tavern' }])).toEqual([]);
  });

  it('lists journal news newest first with its story day', () => {
    const n = newsNotices(base, [
      { seq: 2, type: 'news', headline: 'First', summary: 'a', story_day: 40 },
      { seq: 5, type: 'news', headline: 'Second', summary: 'b', story_day: 84 },
    ]);
    expect(n.map((x) => [x.headline, x.day])).toEqual([['Second', 84], ['First', 40]]);
  });

  it('falls back to the state news, then lists rumours after the news', () => {
    const c = { ...base, news_shown: true, news: { headline: 'Loss', summary: 's' }, rumours: ['Whisper'] } as unknown as CampaignState;
    const n = newsNotices(c, []);
    expect(n.map((x) => [x.kind, x.headline])).toEqual([['News', 'Loss'], ['Rumour', 'Whisper']]);
  });
});
