import { act, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { readDb, writeDb } from '../../api/fixtures/db';
import { readToChoices, setupPlay, skipTitle } from './playTestUtils';

vi.mock('../components/StoryChart', () => ({ default: () => <div role="img" aria-label="Price chart" /> }));

afterEach(() => {
  vi.unstubAllEnvs();
  vi.restoreAllMocks();
  vi.useRealTimers();
});

type User = ReturnType<typeof userEvent.setup>;

async function act1(user: User, text: string): Promise<void> {
  await readToChoices(user);
  await skipTitle(user);
  await user.click(screen.getByRole('button', { name: 'Write your own action…' }));
  await user.type(await screen.findByRole('textbox'), text);
  await user.click(screen.getByRole('button', { name: 'Send' }));
}

describe('new location with an NPC', () => {
  it('shows "Exploring new horizons" with the place name, then the art once ready; the NPC speaks under a verdigris tab', async () => {
    const user = userEvent.setup();
    setupPlay('analyst');
    await act1(user, 'visit the docks warehouse');
    const loading = await screen.findByTestId('exploring-horizons');
    expect(loading).toHaveTextContent('Exploring new horizons');
    expect(loading).toHaveTextContent('The Docks Warehouse');
    const tab = await screen.findByTestId('name-tab');
    expect(tab).toHaveTextContent('Orrin Vale');
    expect(tab).toHaveAttribute('data-kind', 'npc');
    expect(await screen.findByTestId('npc-chip')).toHaveTextContent('Orrin Vale · harbour clerk');
    // art turns ready on the server: the next poll clears the loading state
    const db = readDb();
    await act(async () => {
      writeDb({ ...db, play: { ...db.play!, artReadyAt: { 'docks-warehouse': Date.now() - 1 } } });
    });
    await waitFor(() => expect(screen.queryByTestId('exploring-horizons')).not.toBeInTheDocument(), { timeout: 6000 });
  }, 15000);

  it('lists the generated place on the map with a "new" marker and keeps the Tavern reachable', async () => {
    const user = userEvent.setup();
    setupPlay('analyst');
    await act1(user, 'visit the docks warehouse');
    await screen.findByTestId('exploring-horizons');
    await readToChoices(user);
    await user.click(screen.getByRole('button', { name: 'Map' }));
    const map = await screen.findByRole('dialog', { name: 'The map' });
    expect(within(map).getByRole('button', { name: /Docks Warehouse/ })).toHaveTextContent('you are here');
    expect(within(map).getByRole('button', { name: /Tavern/ })).toBeEnabled();
  }, 15000);

  it('a reckless act escalates to the Master, who deals damage: toast, ticking HP', async () => {
    const user = userEvent.setup();
    setupPlay('analyst');
    await act1(user, 'visit the docks warehouse');
    await readToChoices(user);
    await user.click(screen.getByRole('button', { name: 'Write your own action…' }));
    await user.type(await screen.findByRole('textbox'), 'break into the vault');
    await user.click(screen.getByRole('button', { name: 'Send' }));
    expect(await screen.findByText('The Campaign Master steps in')).toBeInTheDocument();
    expect(await screen.findByTestId('damage-toast')).toHaveTextContent('−5 HP (−€50): The vault guards caught you');
    expect(screen.getByTestId('hp')).toHaveAttribute('data-hit', 'true');
    await waitFor(() => expect(screen.getByTestId('hp')).toHaveTextContent('95 HP · €950'));
    expect(screen.getByTestId('name-tab')).toHaveTextContent('Campaign Master');
  }, 15000);
});
