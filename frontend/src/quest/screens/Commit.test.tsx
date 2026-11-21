import { cleanup, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { readDb } from '../../api/fixtures/db';
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
const evidence = '123456789012345678'; // 18 chars

describe('Commit (SealScroll)', () => {
  it('starts with nothing selected, slider at 50% and Lock disabled', async () => {
    setup();
    expect(await screen.findByRole('radio', { name: 'Invest' })).toHaveAttribute('aria-checked', 'false');
    for (const r of screen.getAllByRole('radio')) expect(r).toHaveAttribute('aria-checked', 'false');
    expect(screen.getByRole('slider')).toHaveValue('50');
    expect(screen.getByRole('slider')).toHaveAttribute('step', '5');
    expect(screen.getByText(/higher at the end of about 75 days than today/)).toBeInTheDocument();
    expect(lockButton()).toBeDisabled();
    expect(screen.queryByLabelText('Amount in euros')).not.toBeInTheDocument();
  });

  it('hides Spread when the campaign does not offer it, shows it otherwise', async () => {
    setup({ offersSpread: false });
    await screen.findByRole('radio', { name: 'Invest' });
    expect(screen.queryByRole('radio', { name: 'Spread the money' })).not.toBeInTheDocument();
  });

  it('offers Spread when the campaign offers it', async () => {
    setup({ offersSpread: true });
    expect(await screen.findByRole('radio', { name: 'Spread the money' })).toBeInTheDocument();
  });

  it('validates amount and evidence, then enables Lock and asks for confirmation', async () => {
    const user = userEvent.setup();
    setup();
    await user.click(await screen.findByRole('radio', { name: 'Invest' }));
    const amount = screen.getByLabelText('Amount in euros');
    await user.type(amount, '1201');
    expect(screen.getByText('Enter an amount from €1 to €1,200.')).toBeInTheDocument();
    await user.clear(amount);
    await user.type(amount, '0');
    expect(screen.getByText('Enter an amount from €1 to €1,200.')).toBeInTheDocument();
    await user.clear(amount);
    await user.type(amount, '400');
    expect(screen.queryByText(/Enter an amount/)).not.toBeInTheDocument();

    await user.type(screen.getByLabelText(/Evidence/), evidence);
    expect(screen.getByText('Explain your reasoning in at least 20 characters.')).toBeInTheDocument();
    await user.click(screen.getByRole('radio', { name: 'Medium' }));
    expect(lockButton()).toBeDisabled();

    await user.type(screen.getByLabelText(/Evidence/), 'a'); // 19 characters
    expect(lockButton()).toBeDisabled();
    expect(screen.getByText('Explain your reasoning in at least 20 characters.')).toBeInTheDocument();
    await user.type(screen.getByLabelText(/Evidence/), 'b'); // 20 characters
    expect(screen.queryByText(/at least 20 characters/)).not.toBeInTheDocument();
    expect(lockButton()).toBeEnabled();
    expect(screen.getByRole('region', { name: 'Summary' })).toHaveTextContent('€400.00');

    await user.click(lockButton());
    expect(screen.getByText("Once locked, you can't change it. Lock?")).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Go back' }));
    expect(screen.queryByText("Once locked, you can't change it. Lock?")).not.toBeInTheDocument();
  });

  it('Back to investigating keeps the typed answers', async () => {
    const user = userEvent.setup();
    const router = setup();
    await user.type(await screen.findByLabelText(/Evidence/), evidence);
    await user.click(screen.getByRole('button', { name: 'Back to investigating' }));
    await waitFor(() => expect(router.state.location.pathname).toBe('/quest/play'));
    expect(readDb().campaign?.commit_draft?.evidence).toBe(evidence);
    // reopening the commit screen later (server phase is commit again, fresh app load)
    cleanup();
    seedAgainKeepDraft();
    renderRoutes(
      [{ path: '/quest/commit', element: <PhaseGuard screen="/quest/commit"><Commit /></PhaseGuard> }],
      ['/quest/commit'],
    );
    expect(await screen.findByLabelText(/Evidence/)).toHaveValue(evidence);
  });

  it('Lock posts the decision, shows the time skip and goes to the outcome', async () => {
    const user = userEvent.setup();
    const router = setup({ heroClass: 'analyst' });
    await user.click(await screen.findByRole('radio', { name: "Don't invest" }));
    await user.type(screen.getByLabelText(/Evidence/), evidence + '90');
    await user.click(screen.getByRole('radio', { name: 'High' }));
    await user.click(lockButton());
    await user.click(screen.getByRole('button', { name: 'Lock' }));
    const skip = await screen.findByText('75 days later…', {}, { timeout: 3000 });
    expect(readDb().decision?.action).toBe('dont_invest');
    await user.click(skip);
    await waitFor(() => expect(router.state.location.pathname).toBe('/quest/outcome'));
  });
});

function seedAgainKeepDraft(): void {
  const db = readDb();
  if (!db.campaign) return;
  // the real server keeps the commit phase for the commit screen; emulate it
  db.campaign.phase = 'commit';
  localStorage.setItem('fq.fixture.v1', JSON.stringify(db));
}
