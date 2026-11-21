/**
 * Acceptance tests for spec 002 (frontend half), one per criterion.
 * @spec: 002-anonymization-reid-gate
 * @regression
 * Criterion ids follow functional-spec.md section 2 (2.<section>.<n>, in checkbox order).
 */
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError, api } from '../../api/client';
import { fixtureResponse, resetFixtureDb } from '../../api/fixtures';
import type { RevealData } from '../../api/types';
import PhaseGuard from '../PhaseGuard';
import RevealGuard from '../RevealGuard';
import { clearQuest } from '../questStore';
import { formatStoryDay, formatStoryNumber } from '../lib/storyNumber';
import Reveal from '../screens/Reveal';
import QuestDisclosure from '../screens/QuestDisclosure';
import { renderRoutes } from '../testUtils';

vi.mock('../components/StoryChart', () => ({
  default: (p: { mode: string; markers?: unknown[]; points: unknown[] }) => (
    <div
      data-testid="chart"
      data-mode={p.mode}
      data-markers={p.markers?.length ?? 0}
      data-points={p.points.length}
    />
  ),
}));

const real: RevealData = {
  real_name: 'Example Lantern Co.',
  ticker: 'EXLC',
  start_date: '2001-03-01',
  end_date: '2001-08-31',
  series: [
    { date: '2001-03-01', price: 40 },
    { date: '2001-08-31', price: 52 },
  ],
  news_points: [
    { story_day: 0, real_date: '2001-03-01', real_price: 40, headline: 'Lamp launched' },
    { story_day: 84, real_date: '2001-05-24', real_price: 43, headline: 'Press opens' },
  ],
  what_changed: [
    'We changed the company name, hid the dates, multiplied prices by a hidden factor, and rewrote the news in our own words. The ups and downs are real.',
  ],
  n_guessers: 3,
};

describe('2.1 / 2.2 story numbers and axis (@spec: 002-anonymization-reid-gate @regression)', () => {
  it('2.1.3 chart axis labels are story days, never dates', () => {
    expect(formatStoryDay(84)).toBe('Day 84');
    expect(formatStoryDay(0)).toBe('Day 0');
  });

  it('2.2.1 no amount above 10,000 and no k/m/bn suffix is ever rendered', () => {
    expect(formatStoryNumber(10_000)).toBe('10,000');
    expect(formatStoryNumber(1250)).toBe('1,250');
    expect(formatStoryNumber(1250)).not.toMatch(/[kmb]/i);
    expect(() => formatStoryNumber(10_001)).toThrow(RangeError);
    expect(() => formatStoryNumber(4_200_000_000)).toThrow(RangeError);
  });
});

describe('2.6 reveal (@spec: 002-anonymization-reid-gate @regression)', () => {
  it('2.6.1 shows the real name, real dates, real price chart with news markers and the table', async () => {
    render(<Reveal data={real} />);
    expect(screen.getByRole('heading', { name: 'Example Lantern Co.' })).toBeInTheDocument();
    expect(screen.getByText(/2001-03-01 to 2001-08-31/)).toBeInTheDocument();
    const chart = await screen.findByTestId('chart');
    expect(chart).toHaveAttribute('data-mode', 'real');
    expect(chart).toHaveAttribute('data-markers', '2');
    const table = screen.getByRole('table');
    expect(table).toHaveTextContent('2001-05-24');
    expect(table).toHaveTextContent('43');
    expect(table).toHaveTextContent('Press opens');
  });

  it('2.6.2 before the debrief is finished the guard returns to the current step and shows no real name', async () => {
    vi.spyOn(api, 'reveal').mockRejectedValue(new ApiError('RevealLocked', 403));
    render(
      <MemoryRouter initialEntries={['/quest/reveal']}>
        <Routes>
          <Route
            path="/quest/reveal"
            element={
              <RevealGuard scenarioId="s1" fallbackPath="/quest/debrief">
                {(d) => <p>revealed {d.real_name}</p>}
              </RevealGuard>
            }
          />
          <Route path="/quest/debrief" element={<p>debrief step</p>} />
        </Routes>
      </MemoryRouter>,
    );
    expect(await screen.findByText('debrief step')).toBeInTheDocument();
    expect(screen.queryByText(/revealed/)).not.toBeInTheDocument();
    vi.restoreAllMocks();
  });

  it('2.6.3 a scenario approved by 3 guessers shows What we changed and the exact testers sentence', () => {
    render(<Reveal data={real} />);
    expect(screen.getByRole('heading', { name: 'What we changed' })).toBeInTheDocument();
    expect(screen.getByText(/hid the dates/)).toBeInTheDocument();
    expect(
      screen.getByText(
        'Before you played, 3 AI testers tried to guess this company. None of them got it.',
      ),
    ).toBeInTheDocument();
  });

  it('2.6.4 no buy button or link and no disclaimer line', () => {
    render(<Reveal data={real} />);
    expect(screen.queryByRole('button')).not.toBeInTheDocument();
    expect(screen.queryByRole('link', { name: /buy|invest|trade|shares/i })).not.toBeInTheDocument();
    expect(screen.queryByText(/buy|purchase|invest in/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/education only|disclaimer|not financial advice/i)).not.toBeInTheDocument();
  });

  it('2.6.5 a reference-pack reveal does not show the AI testers sentence', () => {
    render(<Reveal data={{ ...real, n_guessers: 0 }} />);
    expect(screen.queryByText(/Before you played/)).not.toBeInTheDocument();
    expect(screen.queryByText(/AI testers/)).not.toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'What we changed' })).toBeInTheDocument();
  });
});

describe('2.7 disclosure note (@spec: 002-anonymization-reid-gate @regression)', () => {
  beforeEach(() => {
    vi.stubEnv('VITE_API_MODE', 'fixture');
    resetFixtureDb();
    clearQuest();
    localStorage.clear();
    fixtureResponse('POST', '/hero', { name: 'Mira', class: 'guardian' });
  });
  afterEach(() => vi.unstubAllEnvs());

  function setup() {
    return renderRoutes(
      [
        {
          path: '/quest/disclosure',
          element: (
            <PhaseGuard screen="/quest/disclosure">
              <QuestDisclosure />
            </PhaseGuard>
          ),
        },
        {
          path: '/quest/play',
          element: (
            <PhaseGuard screen="/quest/play">
              <p>story intro</p>
            </PhaseGuard>
          ),
        },
      ],
      ['/quest/disclosure'],
    );
  }

  it('2.7.1 starting a mission shows the note with a Got it button before the first story beat', async () => {
    setup();
    expect(
      await screen.findByText(
        "This story is real market history. We've hidden the company's name, the dates and the price level. You'll find out who it was at the end.",
      ),
    ).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Got it' })).toBeInTheDocument();
    expect(screen.queryByText('story intro')).not.toBeInTheDocument();
  });

  it('2.7.2 tapping Got it closes the note and the story intro appears', async () => {
    setup();
    await userEvent.click(await screen.findByRole('button', { name: 'Got it' }));
    expect(await screen.findByText('story intro')).toBeInTheDocument();
    expect(screen.queryByText(/This story is real market history/)).not.toBeInTheDocument();
  });
});
