import { QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { createQueryClient } from '../../api/queryClient';
import { resetFixtureDb } from '../../api/fixtures';
import { getQuestPick, setQuestPick } from '../../quest/selectedQuest';
import PersonalQuests from './PersonalQuests';
import RecentTransactions from './RecentTransactions';

beforeEach(() => {
  vi.stubEnv('VITE_API_MODE', 'fixture');
  resetFixtureDb();
  sessionStorage.clear();
  setQuestPick(null);
});
afterEach(() => vi.unstubAllEnvs());

function withQueries(ui: React.ReactNode) {
  return render(<QueryClientProvider client={createQueryClient()}>{ui}</QueryClientProvider>);
}

describe('PersonalQuests', () => {
  it('shows today’s quest by spending category and makes it the card’s pick once ready', async () => {
    withQueries(<PersonalQuests busy={false} onPlay={vi.fn()} />);
    expect(await screen.findByText(/Music & streaming/)).toBeInTheDocument();
    expect(screen.getByText(/Ready · picked from your spending/)).toBeInTheDocument();
    await waitFor(() => expect(getQuestPick()?.category).toBe('music'));
  });

  it('Generate another quest lists a new quest; Play picks it and starts', async () => {
    const onPlay = vi.fn();
    withQueries(<PersonalQuests busy={false} onPlay={onPlay} />);
    await userEvent.click(await screen.findByRole('button', { name: 'Generate another quest' }));
    expect(await screen.findByText('Games & consoles')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Play' }));
    expect(onPlay).toHaveBeenCalledTimes(1);
    expect(getQuestPick()?.category).toBe('gaming');
  });

  it('Regenerate today’s quest asks for a fresh generation and shows the result', async () => {
    withQueries(<PersonalQuests busy={false} onPlay={vi.fn()} />);
    await userEvent.click(await screen.findByRole('button', { name: "Regenerate today's quest" }));
    expect(await screen.findByText(/Music & streaming/)).toBeInTheDocument();
  });

  it('while a quest is in progress, Play asks to end it first; Cancel keeps the current pick', async () => {
    setQuestPick({ scenarioId: 'keep', category: 'x', categoryLabel: 'X' });
    const onPlay = vi.fn();
    withQueries(<PersonalQuests busy onPlay={onPlay} />);
    await userEvent.click(await screen.findByRole('button', { name: 'Generate another quest' }));
    expect(await screen.findByText('Games & consoles')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Play' }));
    expect(onPlay).not.toHaveBeenCalled();
    expect(getQuestPick()?.scenarioId).toBe('keep');
    await userEvent.click(screen.getByRole('button', { name: 'Cancel' }));
    expect(screen.getByRole('button', { name: 'Play' })).toBeInTheDocument();
    expect(getQuestPick()?.scenarioId).toBe('keep');
  });

  it('while a quest is in progress, confirming ends it and plays the picked quest', async () => {
    const onPlay = vi.fn();
    withQueries(<PersonalQuests busy onPlay={onPlay} />);
    await userEvent.click(await screen.findByRole('button', { name: 'Generate another quest' }));
    expect(await screen.findByText('Games & consoles')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Play' }));
    await userEvent.click(screen.getByRole('button', { name: 'End current and play' }));
    expect(onPlay).toHaveBeenCalledTimes(1);
    expect(getQuestPick()?.category).toBe('gaming');
  });

  it('renders nothing without a query client (bank shell unit tests)', () => {
    const { container } = render(<PersonalQuests busy={false} onPlay={vi.fn()} />);
    expect(container).toBeEmptyDOMElement();
  });
});

describe('RecentTransactions', () => {
  it('lists the mock spending with merchant, category and amount', async () => {
    withQueries(<RecentTransactions />);
    expect(await screen.findByText('Recent transactions')).toBeInTheDocument();
    expect(screen.getByText('Spotify')).toBeInTheDocument();
    expect(screen.getByText(/Music & streaming/)).toBeInTheDocument();
    expect(screen.getByText('-€10.99')).toBeInTheDocument();
  });
});
