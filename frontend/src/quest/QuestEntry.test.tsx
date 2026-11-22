import { screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { fixtureResponse, resetFixtureDb } from '../api/fixtures';
import PhaseGuard from './PhaseGuard';
import QuestEntry from './QuestEntry';
import { clearQuest } from './questStore';
import { renderRoutes } from './testUtils';

beforeEach(() => {
  vi.stubEnv('VITE_API_MODE', 'fixture');
  resetFixtureDb();
  clearQuest();
  localStorage.clear();
});
afterEach(() => vi.unstubAllEnvs());

// Plain screens: QuestEntry itself must pick the destination, not a guard further along.
const entryRoutes = [
  { path: '/quest', element: <QuestEntry /> },
  { path: '/quest/hero/new', element: <p>hero screen</p> },
  { path: '/quest/board', element: <p>board screen</p> },
  { path: '/quest/play', element: <p>play screen</p> },
];

const routes = [
  { path: '/quest', element: <QuestEntry /> },
  { path: '/quest/hero/new', element: <p>hero screen</p> },
  { path: '/quest/board', element: <PhaseGuard screen="/quest/board"><p>board screen</p></PhaseGuard> },
  { path: '/quest/play', element: <PhaseGuard screen="/quest/play"><p>play screen</p></PhaseGuard> },
  { path: '/quest/commit', element: <PhaseGuard screen="/quest/commit"><p>commit screen</p></PhaseGuard> },
];

describe('QuestEntry', () => {
  it('no hero -> create your hero', async () => {
    const router = renderRoutes(entryRoutes, ['/quest']);
    expect(await screen.findByText('hero screen')).toBeInTheDocument();
    expect(router.state.location.pathname).toBe('/quest/hero/new');
  });

  it('hero without a campaign -> the quest board', async () => {
    fixtureResponse('POST', '/hero', { name: 'Mira', class: 'analyst' });
    const router = renderRoutes(entryRoutes, ['/quest']);
    expect(await screen.findByText('board screen')).toBeInTheDocument();
    expect(router.state.location.pathname).toBe('/quest/board');
  });

  it('active campaign -> the route of its phase', async () => {
    fixtureResponse('POST', '/hero', { name: 'Mira', class: 'analyst' });
    fixtureResponse('POST', '/campaigns', { interests: ['Tech'] });
    const router = renderRoutes(entryRoutes, ['/quest']);
    expect(await screen.findByText('play screen')).toBeInTheDocument();
    expect(router.state.location.pathname).toBe('/quest/play');
  });
});

describe('PhaseGuard', () => {
  it('redirects a stale screen to the server phase route', async () => {
    fixtureResponse('POST', '/hero', { name: 'Mira', class: 'analyst' });
    fixtureResponse('POST', '/campaigns', { interests: ['Tech'] });
    const router = renderRoutes(routes, ['/quest/commit']);
    expect(await screen.findByText('play screen')).toBeInTheDocument();
    expect(router.state.location.pathname).toBe('/quest/play');
  });

  it('sends a campaign screen without a campaign to the board', async () => {
    fixtureResponse('POST', '/hero', { name: 'Mira', class: 'analyst' });
    renderRoutes(routes, ['/quest/play']);
    expect(await screen.findByText('board screen')).toBeInTheDocument();
  });
});
