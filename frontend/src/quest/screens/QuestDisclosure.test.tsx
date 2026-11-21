import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { readDb } from '../../api/fixtures/db';
import { fixtureResponse, resetFixtureDb } from '../../api/fixtures';
import PhaseGuard from '../PhaseGuard';
import QuestLayout from '../QuestLayout';
import { clearQuest, getQuestMeta } from '../questStore';
import { renderRoutes } from '../testUtils';
import HeroCreate from './HeroCreate';
import QuestDisclosure from './QuestDisclosure';

beforeEach(() => {
  vi.stubEnv('VITE_API_MODE', 'fixture');
  resetFixtureDb();
  clearQuest();
  localStorage.clear();
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
  it('returns to the saved character when disclosure follows hero creation', async () => {
    setup(true);
    await screen.findByRole('button', { name: 'Got it' });
    await userEvent.click(screen.getByRole('button', { name: 'Back' }));
    expect(await screen.findByRole('textbox', { name: 'Name' })).toHaveValue('Mira');
    expect(screen.getByRole('radio', { name: /The Guardian/ })).toBeChecked();
    await userEvent.click(screen.getByRole('button', { name: 'Continue' }));
    expect(await screen.findByRole('button', { name: 'Got it' })).toBeInTheDocument();
  });

  it('shows disclosure before creating a campaign with no interests', async () => {
    setup();
    expect(await screen.findByText(/This story is real market history/)).toBeInTheDocument();
    expect(readDb().campaign).toBeNull();
    expect(getQuestMeta().disclosureSeen).toBe(false);
    await userEvent.click(screen.getByRole('button', { name: 'Got it' }));
    expect(await screen.findByText('play screen')).toBeInTheDocument();
    expect(readDb().campaign?.interests).toEqual([]);
    expect(getQuestMeta()).toMatchObject({ disclosureSeen: true, campaignId: readDb().campaign?.id });
  });
});
