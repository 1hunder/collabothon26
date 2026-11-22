import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { DmStream, DmStreamState } from '../../api/useDmStream';
import type { VeteranOverview, VeteranTimeline as Timeline } from '../../api/veteran';
import DialogueBox, { VETERAN_NAME } from './DialogueBox';
import HotspotLayer from './HotspotLayer';
import VeteranPortrait from './VeteranPortrait';
import VeteranScene from './VeteranScene';
import VeteranTimeline from './VeteranTimeline';

function stream(state: DmStreamState = { phase: 'idle' }): DmStream {
  return { state, send: vi.fn(), retry: vi.fn(), reset: vi.fn() };
}

function done(extras: Record<string, unknown>, text = 'Pull up a stool. What sort of quest are you after?'): DmStream {
  return stream({
    phase: 'done', clientMsgId: 'm1', text, cards: [], audioTextId: 'v1', canDecide: null,
    extras: { text, speaker: VETERAN_NAME, mood: 'listening', suggestions: ['Tell me a story', 'Why luck?', "I'll be back"], show_timeline: false, audio_text_id: 'v1', ...extras },
  });
}

const QUEST = {
  campaign_id: 'c-1', number: 1, title: 'The Saltwind Charter', company: 'Golden Guild', real_name: 'Enron Corporation',
  result: 'loss' as const, pnl_pct: -12.5, forecast: 'overconfident', tags: ['panic_sell'], xp: 120, finished_at: '2026-11-20',
};

const overview = (over: Partial<VeteranOverview> = {}): VeteranOverview => ({
  name: 'Brannoc Greyhallow', speaker: VETERAN_NAME, speaker_id: 'veteran', has_memory: true, running: true,
  quests: [QUEST], profile: null, lessons: [], messages: [], ...over,
});

/** Tap through the dialogue (typewriter) until the choices show. */
async function toChoices(): Promise<void> {
  const box = screen.getByTestId('dialogue-box');
  for (let i = 0; i < 4 && screen.queryByTestId('dialogue-box'); i += 1) await userEvent.click(box);
}

beforeEach(() => window.sessionStorage.clear());

describe('VeteranScene', () => {
  it('greets on arrival: one request with no topic, never to a campaign path', () => {
    const s = stream();
    render(<VeteranScene stream={s} overview={overview()} onClose={vi.fn()} onTimeline={vi.fn()} />);
    expect(s.send).toHaveBeenCalledTimes(1);
    expect(s.send).toHaveBeenCalledWith({ text: '', topic: null });
    expect(screen.getByText('Brannoc puffs on his pipe…')).toBeInTheDocument();
    expect(screen.queryByTestId('veteran-figure')).toBeNull();
  });

  it('speaks under his own wax-red name tab, then offers the remembered roads', async () => {
    const s = done({});
    render(<VeteranScene stream={s} overview={overview()} onClose={vi.fn()} onTimeline={vi.fn()} />);
    expect(screen.getByTestId('name-tab')).toHaveTextContent('Brannoc');
    expect(screen.getByTestId('name-tab')).toHaveClass('bg-quest-wax-light');
    await toChoices();
    expect(screen.getByText('Which road shall we walk back down?')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: /The Saltwind Charter/ }));
    expect(s.send).toHaveBeenCalledWith({ text: '', topic: 'c-1' });
  });

  it('offers his suggestions, the timeline and your own words once a road is chosen', async () => {
    const s = done({ show_timeline: true, topic: 'c-1' });
    const onTimeline = vi.fn();
    const { rerender } = render(<VeteranScene stream={stream()} overview={overview()} onClose={vi.fn()} onTimeline={onTimeline} />);
    rerender(<VeteranScene stream={done({})} overview={overview()} onClose={vi.fn()} onTimeline={onTimeline} />);
    await toChoices();
    await userEvent.click(screen.getByRole('button', { name: /The Saltwind Charter/ }));
    rerender(<VeteranScene stream={s} overview={overview()} onClose={vi.fn()} onTimeline={onTimeline} />);
    await toChoices();
    await userEvent.click(screen.getByRole('button', { name: 'Decision timeline' }));
    expect(onTimeline).toHaveBeenCalledWith('c-1');
    await userEvent.click(screen.getByRole('button', { name: 'Tell me a story' }));
    expect(s.send).toHaveBeenCalledWith({ text: 'Tell me a story', topic: 'c-1' });
  });

  it('a new hero gets his suggestions only, and can write their own words', async () => {
    const s = done({});
    render(<VeteranScene stream={s} overview={overview({ has_memory: false, quests: [] })} onClose={vi.fn()} onTimeline={vi.fn()} />);
    await toChoices();
    expect(screen.queryByText('Which road shall we walk back down?')).toBeNull();
    await userEvent.click(screen.getByRole('button', { name: 'Write your own…' }));
    await userEvent.type(screen.getByRole('textbox', { name: 'What do you tell Brannoc?' }), 'Why do you keep a ledger?');
    await userEvent.click(screen.getByRole('button', { name: 'Say it' }));
    expect(s.send).toHaveBeenCalledWith({ text: 'Why do you keep a ledger?', topic: null });
  });

  it('Leave the fire closes the conversation; a lost thread offers Try again', async () => {
    const onClose = vi.fn();
    const { unmount } = render(<VeteranScene stream={done({})} overview={overview()} onClose={onClose} onTimeline={vi.fn()} />);
    await toChoices();
    await userEvent.click(screen.getByRole('button', { name: 'Leave the fire' }));
    expect(onClose).toHaveBeenCalled();
    unmount();
    const lost = stream({ phase: 'lost', clientMsgId: 'm', reason: 'x' });
    render(<VeteranScene stream={lost} overview={overview()} onClose={vi.fn()} onTimeline={vi.fn()} />);
    await userEvent.click(screen.getByRole('button', { name: 'Try again' }));
    expect(lost.retry).toHaveBeenCalled();
  });
});

describe('Veteran voice and figure', () => {
  it('reads his lines with the veteran voice', () => {
    const onPageShown = vi.fn();
    render(<DialogueBox speaker={VETERAN_NAME} text="Short." instant onAdvance={vi.fn()} onPageShown={onPageShown} />);
    expect(onPageShown).toHaveBeenCalledWith('Short.', 'veteran', null);
  });

  it('draws the four moods', () => {
    for (const mood of ['listening', 'pondering', 'approving', 'stern'] as const) {
      const { container, unmount } = render(<VeteranPortrait mood={mood} />);
      expect(container.querySelector(`svg[data-mood="${mood}"]`)).not.toBeNull();
      unmount();
    }
  });

  it('makes the seated man a tap target, hidden while something else is open', async () => {
    const onOpen = vi.fn();
    const { rerender } = render(<HotspotLayer locationKey="tavern" active onOpen={onOpen} />);
    await userEvent.click(screen.getByRole('button', { name: /Talk to Brannoc/ }));
    expect(onOpen).toHaveBeenCalledWith('veteran');
    rerender(<HotspotLayer locationKey="tavern" active={false} onOpen={onOpen} />);
    expect(screen.queryByRole('button', { name: /Talk to Brannoc/ })).toBeNull();
  });
});

describe('VeteranTimeline', () => {
  const TL: Timeline = {
    campaign_id: 'c-1', number: 1, title: 'The Saltwind Charter', company: 'Golden Guild', real_name: 'Enron Corporation',
    decisions: [
      { seq: 1, beat: 'opening', when: 'At the start', day: 'Day 3', action: 'buy', amount_eur: 300, text: 'The ledgers look clean.', judgement: 'sound', luck: 'cruel', tags: [] },
      { seq: 2, beat: 'news', when: 'When the news broke', day: 'Day 40', action: 'sell', amount_eur: 250, text: 'Get out before it sinks!', judgement: 'hasty', luck: 'kind', tags: ['panic'] },
    ],
    forecast: { pct: 85, confidence: 'high', band: 'overconfident', market: 'down' },
    result: { kind: 'loss', pnl_pct: -12.5, pnl_eur: -125, final_eur: 875, budget_eur: 1000 },
    missed: ["Harbour master's notice"], xp: 120, sound_overall: false,
  };

  afterEach(() => vi.unstubAllGlobals());

  it('shows each decision with judgement and luck apart, and keeps a lesson', async () => {
    const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
      if (url.endsWith('/session')) return new Response(JSON.stringify({ session_id: 's' }), { status: 201 });
      if (url.includes('/timeline')) return new Response(JSON.stringify(TL), { status: 200 });
      if (url.endsWith('/hero/veteran/lessons') && init?.method === 'POST') {
        return new Response(JSON.stringify({ id: 1, text: 'x', campaign_id: 'c-1', quest_title: 'T', created_at: '2026-11-21' }), { status: 201 });
      }
      return new Response('{}', { status: 200 });
    });
    vi.stubGlobal('fetch', fetchMock);
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={qc}>
        <VeteranTimeline campaignId="c-1" onClose={vi.fn()} />
      </QueryClientProvider>,
    );
    const rows = await screen.findAllByTestId('timeline-row');
    expect(rows).toHaveLength(2);
    expect(rows[0]).toHaveTextContent('Sound');
    expect(rows[0]).toHaveTextContent('Cruel');
    expect(rows[1]).toHaveTextContent('Hasty');
    expect(rows[1]).toHaveTextContent('Get out before it sinks!');
    expect(screen.getByText(/Surer than the evidence allowed/)).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText('Lesson learned'), 'Reread my reasons before I sell.');
    await userEvent.click(screen.getByRole('button', { name: 'Keep in journal' }));
    await waitFor(() => expect(screen.getByRole('button', { name: 'Kept in your journal' })).toBeDisabled());
    const post = fetchMock.mock.calls.find(([u, i]) => String(u).endsWith('/lessons') && i?.method === 'POST');
    expect(JSON.parse(String(post?.[1]?.body))).toEqual({ text: 'Reread my reasons before I sell.', campaign_id: 'c-1' });
  });

  it('shows the real case: real company, real dates and dollar prices, real headlines', async () => {
    const real: Timeline = {
      ...TL,
      real_case: {
        company: 'Enron Corporation', ticker: 'ENE',
        start: { date: '1 August 2001', price: '$43' }, decision_day: { date: '7 September 2001', price: '$31' },
        end: { date: '30 November 2001', price: '26 cents' },
        move_pct: -99, move_after_decision_pct: -99, high: '$43', low: '26 cents',
        decisions: [
          { seq: 1, action: 'buy', date: '3 August 2001', price: '$42' },
          { seq: 2, action: 'sell', date: '16 October 2001', price: '$34' },
        ],
        events: [{ date: '14 August 2001', headline: 'CEO Jeffrey Skilling resigns', price: '$43' }],
      },
    };
    vi.stubGlobal('fetch', vi.fn(async (url: string) => {
      if (url.endsWith('/session')) return new Response(JSON.stringify({ session_id: 's' }), { status: 201 });
      if (url.includes('/timeline')) return new Response(JSON.stringify(real), { status: 200 });
      return new Response('{}', { status: 200 });
    }));
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={qc}>
        <VeteranTimeline campaignId="c-1" onClose={vi.fn()} />
      </QueryClientProvider>,
    );
    const rows = await screen.findAllByTestId('timeline-row');
    expect(rows[1]).toHaveTextContent('In history: 16 October 2001, share at $34');
    const section = screen.getByRole('region', { name: 'The real case' });
    expect(section).toHaveTextContent('Enron Corporation (ENE)');
    expect(section).toHaveTextContent('1 August 2001 – 30 November 2001: $43 → 26 cents (-99%)');
    expect(screen.getByTestId('real-event')).toHaveTextContent('14 August 2001 · $43CEO Jeffrey Skilling resigns');
  });

  it('a quest without real history shows no real-case section', async () => {
    vi.stubGlobal('fetch', vi.fn(async (url: string) => {
      if (url.endsWith('/session')) return new Response(JSON.stringify({ session_id: 's' }), { status: 201 });
      if (url.includes('/timeline')) return new Response(JSON.stringify({ ...TL, real_case: null }), { status: 200 });
      return new Response('{}', { status: 200 });
    }));
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={qc}>
        <VeteranTimeline campaignId="c-1" onClose={vi.fn()} />
      </QueryClientProvider>,
    );
    await screen.findAllByTestId('timeline-row');
    expect(screen.queryByRole('region', { name: 'The real case' })).toBeNull();
    expect(screen.queryByTestId('real-when')).toBeNull();
  });
});
