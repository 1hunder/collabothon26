import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { fixtureResponse, resetFixtureDb } from '../../api/fixtures';
import PhaseGuard from '../PhaseGuard';
import { clearQuest, getQuestMeta } from '../questStore';
import { renderRoutes } from '../testUtils';
import WhatAreYouInto from './WhatAreYouInto';

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
      { path: '/quest/interests', element: <PhaseGuard screen="/quest/interests"><WhatAreYouInto /></PhaseGuard> },
      { path: '/quest/play', element: <PhaseGuard screen="/quest/play"><p>play screen</p></PhaseGuard> },
    ],
    ['/quest/interests'],
  );
}

describe('WhatAreYouInto', () => {
  it('shows exactly the six interests, greets a returning hero, and gates Find my quest', async () => {
    setup();
    expect(await screen.findByText('Welcome back, Mira')).toBeInTheDocument();
    const names = screen.getAllByRole('button', { pressed: false }).map((b) => b.textContent);
    expect(names).toEqual(['Gaming', 'Fashion', 'Sports', 'Mobility', 'Music', 'Tech']);
    const find = screen.getByRole('button', { name: 'Find my quest' });
    expect(find).toBeDisabled();
    await userEvent.click(screen.getByRole('button', { name: 'Music' }));
    expect(find).toBeEnabled();
    await userEvent.click(screen.getByRole('button', { name: 'Music' }));
    expect(find).toBeDisabled();
  });

  it('Find my quest shows the disclosure note; Got it records it and opens play', async () => {
    setup();
    await userEvent.click(await screen.findByRole('button', { name: 'Gaming' }));
    await userEvent.click(screen.getByRole('button', { name: 'Find my quest' }));
    expect(await screen.findByText(/This story is real market history/)).toBeInTheDocument();
    expect(getQuestMeta().disclosureSeen).toBe(false);
    await userEvent.click(screen.getByRole('button', { name: 'Got it' }));
    expect(await screen.findByText('play screen')).toBeInTheDocument();
    expect(getQuestMeta()).toMatchObject({ disclosureSeen: true, campaignId: 'fixture-campaign' });
  });
});
