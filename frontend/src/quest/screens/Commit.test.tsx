import { cleanup, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { readDb, writeDb } from '../../api/fixtures/db';
import { seedCampaign } from '../../test/seedCampaign';
import PhaseGuard from '../PhaseGuard';
import { renderRoutes } from '../testUtils';
import Commit from './Commit';

beforeEach(() => {
  vi.stubEnv('VITE_API_MODE', 'fixture');
  sessionStorage.clear();
  localStorage.clear();
});
afterEach(() => vi.unstubAllEnvs());

function setup(opts: { heroClass?: 'guardian' | 'analyst'; offersSpread?: boolean } = {}) {
  seedCampaign({ phase: 'commit', heroClass: opts.heroClass ?? 'guardian', offersSpread: opts.offersSpread });
  return renderRoutes(
    [
      {
        path: '/quest/commit',
        element: (
          <PhaseGuard screen="/quest/commit">
            <Commit />
          </PhaseGuard>
        ),
      },
      { path: '/quest/play', element: <p>play screen</p> },
      { path: '/quest/outcome', element: <p>outcome screen</p> },
    ],
    ['/quest/commit'],
  );
}

const lockButton = (): HTMLElement => screen.getByRole('button', { name: 'Lock my decision' });
const note = 'The debt figures still worry me.';

describe('Commit (SealScroll)', () => {
  it('lists the decisions written during the campaign, asks only forecast and confidence, Lock disabled', async () => {
    setup();
    const list = await screen.findByRole('region', { name: 'Your decisions' });
    expect(list).toHaveTextContent('Day 2');
    expect(list).toHaveTextContent('Put in €200.00');
    expect(list).toHaveTextContent('I put 200 coins in, the guild looks strong.');
    expect(list).toHaveTextContent('Day 83');
    expect(list).toHaveTextContent('Held');
    expect(screen.queryByRole('radio', { name: 'Invest' })).not.toBeInTheDocument();
    expect(screen.queryByLabelText('Amount in euros')).not.toBeInTheDocument();
    expect(screen.getByRole('slider')).toHaveValue('50');
    expect(screen.getByRole('slider')).toHaveAttribute('step', '5');
    expect(screen.getByText(/higher at the end of about 75 days than today/)).toBeInTheDocument();
    for (const r of screen.getAllByRole('radio')) expect(r).toHaveAttribute('aria-checked', 'false');
    expect(lockButton()).toBeDisabled();
  });

  it('a confidence enables Lock, which asks for confirmation; the note is optional', async () => {
    const user = userEvent.setup();
    setup();
    await user.click(await screen.findByRole('radio', { name: 'Medium' }));
    expect(lockButton()).toBeEnabled();
    await user.click(lockButton());
    expect(screen.getByText("Once locked, you can't change it. Lock?")).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Go back' }));
    expect(screen.queryByText("Once locked, you can't change it. Lock?")).not.toBeInTheDocument();
  });

  it('Back to investigating keeps the typed answers', async () => {
    const user = userEvent.setup();
    const router = setup();
    await user.type(await screen.findByLabelText(/Anything to add/), note);
    await user.click(screen.getByRole('button', { name: 'Back to investigating' }));
    await waitFor(() => expect(router.state.location.pathname).toBe('/quest/play'));
    expect(readDb().campaign?.commit_draft?.evidence).toBe(note);
    cleanup();
    seedAgainKeepDraft();
    renderRoutes(
      [{ path: '/quest/commit', element: <PhaseGuard screen="/quest/commit"><Commit /></PhaseGuard> }],
      ['/quest/commit'],
    );
    expect(await screen.findByLabelText(/Anything to add/)).toHaveValue(note);
  });

  it('Lock posts forecast and confidence, shows the time skip and goes to the outcome', async () => {
    const user = userEvent.setup();
    const router = setup({ heroClass: 'analyst' });
    await user.click(await screen.findByRole('radio', { name: 'High' }));
    await user.click(lockButton());
    await user.click(screen.getByRole('button', { name: 'Lock' }));
    const skip = await screen.findByText('75 days later…', {}, { timeout: 3000 });
    expect(readDb().decision).toMatchObject({ forecast_pct: 50, confidence: 'high' });
    await user.click(skip);
    await waitFor(() => expect(router.state.location.pathname).toBe('/quest/outcome'));
  });
});

describe('Commit budget after damage', () => {
  it('uses the current hp_eur as the budget and blocks Lock when the position is over it', async () => {
    const user = userEvent.setup();
    setup();
    const db = readDb();
    writeDb({ ...db, campaign: { ...db.campaign!, hp_eur: 150, purse: { cash_eur: 0, position_eur: 400 } as never } });
    cleanup();
    renderRoutes([{ path: '/quest/commit', element: <PhaseGuard screen="/quest/commit"><Commit /></PhaseGuard> }], ['/quest/commit']);
    expect(await screen.findByTestId('budget')).toHaveTextContent('€150.00');
    expect(screen.getByRole('alert')).toHaveTextContent('more than your budget of €150.00');
    await user.click(screen.getByRole('radio', { name: 'High' }));
    expect(lockButton()).toBeDisabled();
  });

  it('handles a 422 amount_over_budget from the server', async () => {
    const user = userEvent.setup();
    setup();
    await user.click(await screen.findByRole('radio', { name: 'High' }));
    const db = readDb();
    // the server sees damage the screen has not: Lock is refused
    writeDb({ ...db, campaign: { ...db.campaign!, hp_eur: 100 } });
    await user.click(lockButton());
    await user.click(screen.getByRole('button', { name: 'Lock' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('more than your budget of €100.00');
    expect(screen.queryByText('Could not lock your decision. Please try again.')).not.toBeInTheDocument();
  });
});

function seedAgainKeepDraft(): void {
  const db = readDb();
  if (!db.campaign) return;
  // the real server keeps the commit phase for the commit screen; emulate it
  db.campaign.phase = 'commit';
  localStorage.setItem('fq.fixture.v1', JSON.stringify(db));
}
