import { act, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { fixtureResponse, resetFixtureDb } from '../../api/fixtures';
import { readDb } from '../../api/fixtures/db';
import { FIXTURE_GENERATE_MS } from '../../api/fixtures/board';
import * as client from '../../api/client';
import PhaseGuard from '../PhaseGuard';
import { clearQuest } from '../questStore';
import { renderRoutes } from '../testUtils';
import QuestDisclosure from '../screens/QuestDisclosure';
import QuestBoard from './QuestBoard';

beforeEach(() => {
  vi.stubEnv('VITE_API_MODE', 'fixture');
  resetFixtureDb();
  clearQuest();
  localStorage.clear();
  fixtureResponse('POST', '/hero', { name: 'Mira', class: 'guardian' });
});
afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllEnvs();
});

function setup() {
  return renderRoutes(
    [
      { path: '/quest/board', element: <PhaseGuard screen="/quest/board"><QuestBoard /></PhaseGuard> },
      { path: '/quest/disclosure', element: <PhaseGuard screen="/quest/disclosure"><QuestDisclosure /></PhaseGuard> },
      { path: '/quest/play', element: <PhaseGuard screen="/quest/play"><p>play screen</p></PhaseGuard> },
    ],
    ['/quest/board'],
  );
}

describe('QuestBoard', () => {
  it('shows guild notices, your quests (one being written) and stamps', async () => {
    setup();
    expect(await screen.findByRole('button', { name: 'Open quest: The Lantern Guild Gambit' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Open quest: Keel and Cannon' })).toBeInTheDocument();
    expect(screen.getByText('Played')).toBeInTheDocument();
    expect(screen.getByText('Finished')).toBeInTheDocument();
    const mine = screen.getByRole('region', { name: 'Your quests' });
    expect(within(mine).getByRole('button', { name: /Commission a new quest/ })).toBeInTheDocument();
    expect(within(mine).getByRole('status')).toHaveTextContent('A quest is being written');
    // difficulty is text, whole-number gold
    const lantern = screen.getByRole('button', { name: 'Open quest: The Lantern Guild Gambit' });
    expect(lantern).toHaveTextContent('Easy');
    expect(lantern).toHaveTextContent('75 days');
    expect(lantern).toHaveTextContent('1,000 gp');
  });

  it('opens a quest, reads its details, and closes it with Close and Esc', async () => {
    setup();
    await userEvent.click(await screen.findByRole('button', { name: 'Open quest: The Lantern Guild Gambit' }));
    const dialog = await screen.findByRole('dialog', { name: 'The Lantern Guild Gambit' });
    expect(await within(dialog).findByText('Master Orrin')).toBeInTheDocument();
    expect(within(dialog).getByText('The Pressing Hall')).toBeInTheDocument();
    expect(within(dialog).getByText('Reading a price chart')).toBeInTheDocument();
    expect(within(dialog).getByRole('button', { name: 'Start this quest' })).toBeEnabled();
    await userEvent.click(within(dialog).getByRole('button', { name: 'Close' }));
    expect(screen.queryByRole('dialog')).toBeNull();
    await userEvent.click(screen.getByRole('button', { name: 'Open quest: The Lantern Guild Gambit' }));
    await screen.findByRole('dialog');
    await userEvent.keyboard('{Escape}');
    expect(screen.queryByRole('dialog')).toBeNull();
  });

  it('offers Play again on a finished quest', async () => {
    setup();
    await userEvent.click(await screen.findByRole('button', { name: 'Open quest: The Saffron Ledger' }));
    expect(await screen.findByRole('button', { name: 'Play again' })).toBeEnabled();
  });

  it('Start posts /campaigns with the scenario_id and enters play', async () => {
    const spy = vi.spyOn(client, 'request');
    setup();
    await userEvent.click(await screen.findByRole('button', { name: 'Open quest: Keel and Cannon' }));
    await userEvent.click(await screen.findByRole('button', { name: 'Start this quest' }));
    expect(await screen.findByText('play screen')).toBeInTheDocument();
    expect(spy).toHaveBeenCalledWith('POST', '/campaigns', { scenario_id: 'fixture-keel' });
    expect(readDb().campaign?.scenario_id).toBe('fixture-keel');
    spy.mockRestore();
  });

  it('commissions with the suggestion ("Use this")', async () => {
    const spy = vi.spyOn(client, 'request');
    setup();
    await userEvent.click(await screen.findByRole('button', { name: /Commission a new quest/ }));
    const dialog = await screen.findByRole('dialog', { name: 'Commission a new quest' });
    expect(within(dialog).getByText('Games & consoles')).toBeInTheDocument();
    expect(within(dialog).getByText('You spent the most on games this month.')).toBeInTheDocument();
    await userEvent.click(within(dialog).getByRole('button', { name: 'Use this' }));
    expect(spy).toHaveBeenCalledWith('POST', '/quests/generate', {});
    await vi.waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    expect(within(screen.getByRole('region', { name: 'Your quests' })).getAllByRole('status')).toHaveLength(2);
    spy.mockRestore();
  });

  it('commissions with a typed theme', async () => {
    const spy = vi.spyOn(client, 'request');
    setup();
    await userEvent.click(await screen.findByRole('button', { name: /Commission a new quest/ }));
    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).getByRole('button', { name: 'Commission' })).toBeDisabled();
    await userEvent.type(within(dialog).getByLabelText(/tell me what you/i), 'electric cars');
    await userEvent.click(within(dialog).getByRole('button', { name: 'Commission' }));
    expect(spy).toHaveBeenCalledWith('POST', '/quests/generate', { theme: 'electric cars' });
    spy.mockRestore();
  });

  it('polls while a quest is generating and shows it once ready', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    setup();
    const mine = await screen.findByRole('region', { name: 'Your quests' });
    expect(within(mine).getByRole('status')).toBeInTheDocument();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(FIXTURE_GENERATE_MS + 4100);
    });
    expect(await within(mine).findByRole('button', { name: 'Open quest: The Games & Consoles Venture' })).toBeInTheDocument();
    expect(within(mine).queryByRole('status')).toBeNull();
  });
});
