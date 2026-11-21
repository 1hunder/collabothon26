import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { readDb } from '../../api/fixtures/db';
import { fixtureResponse, resetFixtureDb } from '../../api/fixtures';
import PhaseGuard from '../PhaseGuard';
import QuestLayout from '../QuestLayout';
import { clearQuest, getQuestMeta } from '../questStore';
import { getQuestPick, setQuestPick } from '../selectedQuest';
import * as client from '../../api/client';
import { renderRoutes } from '../testUtils';
import HeroCreate from './HeroCreate';
import QuestDisclosure from './QuestDisclosure';

beforeEach(() => {
  vi.stubEnv('VITE_API_MODE', 'fixture');
  resetFixtureDb();
  clearQuest();
  localStorage.clear();
  sessionStorage.clear();
  setQuestPick(null);
  fixtureResponse('POST', '/hero', { name: 'Mira', class: 'guardian' });
});
afterEach(() => vi.unstubAllEnvs());

function setup(newHero = false) {
  return renderRoutes(
    [
      {
        element: <QuestLayout />,
        children: [
          { path: '/quest/hero/new', element: <PhaseGuard screen="hero-new"><HeroCreate /></PhaseGuard> },
          { path: '/quest/disclosure', element: <PhaseGuard screen="/quest/disclosure"><QuestDisclosure /></PhaseGuard> },
        ],
      },
      { path: '/quest/play', element: <PhaseGuard screen="/quest/play"><p>play screen</p></PhaseGuard> },
    ],
    [{ pathname: '/quest/disclosure', state: { newHero, origin: '/overview' } }],
  );
}

describe('QuestDisclosure', () => {
  it('starts a campaign without a confirmation step', async () => {
    setup();
    expect(await screen.findByText('play screen')).toBeInTheDocument();
    expect(readDb().campaign?.interests).toEqual([]);
    expect(getQuestMeta()).toMatchObject({ campaignId: readDb().campaign?.id });
  });

  it('lets the player retry a failed campaign start', async () => {
    const request = client.request;
    let attempts = 0;
    const spy = vi.spyOn(client, 'request').mockImplementation((method, path, body) => {
      if (method === 'POST' && path === '/campaigns' && ++attempts === 1) {
        return Promise.reject(new Error('Offline'));
      }
      return request(method, path, body);
    });
    try {
      setup();
      await userEvent.click(await screen.findByRole('button', { name: 'Try again' }));
      expect(await screen.findByText('play screen')).toBeInTheDocument();
      expect(attempts).toBe(2);
    } finally {
      spy.mockRestore();
    }
  });
});

describe('QuestDisclosure with a personal quest picked on the card', () => {
  it('sends its scenario and interest, and clears the pick', async () => {
    setQuestPick({ scenarioId: 'fixture-lumen', category: 'music', categoryLabel: 'Music & streaming' });
    const spy = vi.spyOn(client, 'request');
    setup();
    expect(await screen.findByText('play screen')).toBeInTheDocument();
    expect(spy).toHaveBeenCalledWith('POST', '/campaigns', { interests: ['Music'], scenario_id: 'fixture-lumen' });
    expect(getQuestPick()).toBeNull();
    spy.mockRestore();
  });
});
