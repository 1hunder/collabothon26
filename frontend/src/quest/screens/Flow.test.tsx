import { cleanup, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { readDb } from '../../api/fixtures/db';
import { investDecision, seedCampaign } from '../../test/seedCampaign';
import PhaseGuard from '../PhaseGuard';
import { getQuestMeta, startQuest } from '../questStore';
import { renderRoutes } from '../testUtils';
import Debrief from './Debrief';
import Outcome from './Outcome';
import Reflect from './Reflect';
import RevealRoute from './RevealRoute';
import Xp from './Xp';

vi.mock('../components/StoryChart', () => ({
  default: (p: { mode: string; points: unknown[] }) => (
    <div data-testid="chart" data-mode={p.mode} data-points={p.points.length} />
  ),
}));

beforeEach(() => {
  vi.stubEnv('VITE_API_MODE', 'fixture');
  localStorage.clear();
  sessionStorage.clear();
});
afterEach(() => {
  cleanup();
  vi.unstubAllEnvs();
});

const guard = (path: string, el: React.ReactNode) => ({
  path,
  element: <PhaseGuard screen={path}>{el}</PhaseGuard>,
});
const routes = [
  guard('/quest/outcome', <Outcome />),
  guard('/quest/debrief', <Debrief />),
  guard('/quest/reflect', <Reflect />),
  guard('/quest/reveal', <RevealRoute />),
  guard('/quest/xp', <Xp />),
  { path: '/overview', element: <p>bank app</p> },
];

describe('Outcome', () => {
  it('shows the server figures as whole numbers, including the 607.51 case', async () => {
    seedCampaign({ phase: 'reveal', decision: investDecision });
    renderRoutes(routes, ['/quest/outcome']);
    expect(await screen.findByText('Locked at Day 84, evening · horizon 75 days')).toBeInTheDocument();
    expect(screen.getByTestId('chart')).toHaveAttribute('data-mode', 'story');
    const dl = screen.getByText('Final value').closest('div');
    expect(dl).toHaveTextContent('€608');
    expect(screen.getByText('Starting budget').closest('div')).toHaveTextContent('€1,000');
    expect(screen.getByText('Cash kept').closest('div')).toHaveTextContent('€600');
    expect(screen.getByText('Invested').closest('div')).toHaveTextContent('€400');
    expect(screen.getByText('Value now').closest('div')).toHaveTextContent('€8');
    expect(screen.getByText('Fees').closest('div')).toHaveTextContent('€0');
    expect(screen.getByText('Profit / loss').closest('div')).toHaveTextContent('−€392 (−39%)');
    expect(screen.getByText('100 HP → 61 HP')).toBeInTheDocument();
    expect(
      screen.getByText("Prices in the company's original currency; exchange-rate changes are not included."),
    ).toBeInTheDocument();
    const decisions = screen.getByRole('region', { name: 'Your decisions' });
    expect(decisions).toHaveTextContent('#1 · Day 2 · Put in €200');
    expect(decisions).toHaveTextContent('I put 200 coins in, the guild looks strong.');
    expect(decisions).toHaveTextContent('−€196');
  });

  it('moves on to the debrief', async () => {
    const user = userEvent.setup();
    seedCampaign({ phase: 'reveal', decision: investDecision });
    const router = renderRoutes(routes, ['/quest/outcome']);
    await user.click(await screen.findByRole('button', { name: 'See the debrief' }));
    await waitFor(() => expect(router.state.location.pathname).toBe('/quest/debrief'));
    expect(await screen.findByRole('heading', { name: 'Sound reasoning' })).toBeInTheDocument();
  });
});

describe('Debrief', () => {
  it('renders the three parts, the forecast line and highlights the player row', async () => {
    seedCampaign({ phase: 'debrief', decision: investDecision });
    // load the debrief through the real stream path (resume case)
    renderRoutes(routes, ['/quest/debrief']);
    for (const h of ['Sound reasoning', 'Overlooked', 'Luck']) {
      expect(await screen.findByRole('heading', { name: h })).toBeInTheDocument();
    }
    expect(screen.getByText('You said 40% likely higher. It ended lower.')).toBeInTheDocument();
    const rows = screen.getAllByRole('listitem');
    const mine = rows.filter((r) => r.getAttribute('aria-current') === 'true');
    expect(mine).toHaveLength(1);
    expect(mine[0]).toHaveTextContent('Your decisions');
    expect(screen.getByText('Never invest')).toBeInTheDocument();
    expect(screen.getByText('Everything at your first decision, then hold')).toBeInTheDocument();
    expect(screen.getByText('Everything on decision day, then hold')).toBeInTheDocument();
    expect(screen.getByText('What would you check first next time?')).toBeInTheDocument();
  });
});

describe('Reflect', () => {
  it('gates on 10 characters, then opens the company reveal', async () => {
    const user = userEvent.setup();
    seedCampaign({ phase: 'reflect', decision: investDecision });
    const router = renderRoutes(routes, ['/quest/reflect']);
    const submit = await screen.findByRole('button', { name: 'Submit reflection' });
    expect(submit).toBeDisabled();
    await user.type(screen.getByRole('textbox'), 'too short');
    expect(submit).toBeDisabled();
    expect(screen.queryByText(/Example Lantern/)).not.toBeInTheDocument();
    await user.type(screen.getByRole('textbox'), '!');
    expect(submit).toBeEnabled();
    await user.click(submit);
    await waitFor(() => expect(router.state.location.pathname).toBe('/quest/reveal'));
    expect(await screen.findByRole('heading', { name: 'Example Lantern Co.' })).toBeInTheDocument();
  });
});

describe('Reflect while the server is still in debrief', () => {
  it('stays on the reflection screen (the server never stores reflect)', async () => {
    seedCampaign({ phase: 'debrief', decision: investDecision });
    const router = renderRoutes(routes, ['/quest/reflect']);
    expect(await screen.findByRole('button', { name: 'Submit reflection' })).toBeInTheDocument();
    expect(router.state.location.pathname).toBe('/quest/reflect');
  });
});

describe('Xp and finish', () => {
  it('lists the rubric categories (25/25/20/15/15), the total, and finishes the quest', async () => {
    const user = userEvent.setup();
    startQuest();
    seedCampaign({ phase: 'xp', decision: investDecision });
    const router = renderRoutes(routes, ['/quest/xp']);
    expect(await screen.findByText('Evidence literacy')).toBeInTheDocument();
    const maxes = ['25', '25', '20', '15', '15'];
    const items = screen.getAllByRole('listitem');
    expect(items).toHaveLength(5);
    items.forEach((li, i) => expect(li).toHaveTextContent(new RegExp(`/ ${maxes[i]}$|/ ${maxes[i]}[^0-9]`)));
    expect(screen.getAllByRole('blockquote')).toHaveLength(5);
    expect(screen.getByText('Total 79 / 100')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Finish quest' }));
    expect(await screen.findByText('Total XP: 79')).toBeInTheDocument();
    expect(screen.getByText('New item: Ratio Lens')).toBeInTheDocument();
    expect(getQuestMeta().inProgress).toBe(false);
    expect(readDb().hero?.total_xp).toBe(79);
    await user.click(screen.getByRole('button', { name: 'Back to the bank' }));
    await waitFor(() => expect(router.state.location.pathname).toBe('/overview'));
  });
});
