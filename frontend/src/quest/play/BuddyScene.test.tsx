import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { DmStream, DmStreamState } from '../../api/useDmStream';
import BuddyScene, { BUDDY_GREETING } from './BuddyScene';
import { BUDDY_DRAFT_KEY } from './useSessionDraft';

function stream(state: DmStreamState = { phase: 'idle' }): DmStream {
  return { state, send: vi.fn(), retry: vi.fn(), reset: vi.fn() };
}

beforeEach(() => window.sessionStorage.clear());

describe('BuddyScene', () => {
  it('speaks under the CommerzBuddy tab and opens the question box', () => {
    render(<BuddyScene stream={stream()} onClose={() => undefined} />);
    expect(screen.getByTestId('name-tab')).toHaveTextContent('CommerzBuddy');
    expect(screen.getByTestId('name-tab')).toHaveClass('bg-quest-verdigris-light');
    expect(screen.getByRole('textbox', { name: 'Your question for CommerzBuddy' })).toBeInTheDocument();
    expect(document.querySelector('svg.animate-summon')).toBeNull();
    expect(screen.getByTestId('dialogue-live')).toBeInTheDocument();
    expect(BUDDY_GREETING.length).toBeGreaterThan(0);
  });

  it('keeps the typed draft when closed and reopened', async () => {
    const first = render(<BuddyScene stream={stream()} onClose={() => undefined} />);
    await userEvent.type(screen.getByRole('textbox'), 'What is a drawdown');
    first.unmount();
    expect(window.sessionStorage.getItem(BUDDY_DRAFT_KEY)).toBe('What is a drawdown');
    render(<BuddyScene stream={stream()} onClose={() => undefined} />);
    expect(screen.getByRole('textbox')).toHaveValue('What is a drawdown');
  });

  it('sends the question and clears the draft; Ask is disabled for empty text', async () => {
    const s = stream();
    render(<BuddyScene stream={s} onClose={() => undefined} />);
    expect(screen.getByRole('button', { name: 'Ask' })).toBeDisabled();
    await userEvent.type(screen.getByRole('textbox'), '  ');
    expect(screen.getByRole('button', { name: 'Ask' })).toBeDisabled();
    await userEvent.type(screen.getByRole('textbox'), 'What is a drawdown');
    await userEvent.click(screen.getByRole('button', { name: 'Ask' }));
    expect(s.send).toHaveBeenCalledWith({ text: 'What is a drawdown' });
    expect(window.sessionStorage.getItem(BUDDY_DRAFT_KEY)).toBeNull();
  });

  it('shows the answer under the Buddy tab and offers Try again when the thread is lost', () => {
    const done = stream({ phase: 'done', clientMsgId: 'm', text: 'A drawdown is a fall.', cards: [], audioTextId: null, canDecide: null, extras: {} });
    const { unmount } = render(<BuddyScene stream={done} onClose={() => undefined} />);
    expect(screen.getByTestId('name-tab')).toHaveTextContent('CommerzBuddy');
    unmount();
    const lost = stream({ phase: 'lost', clientMsgId: 'm', reason: 'x' });
    render(<BuddyScene stream={lost} onClose={() => undefined} />);
    expect(screen.getByRole('alert')).toHaveTextContent('CommerzBuddy lost the thread.');
  });

  it('Close Buddy calls onClose', async () => {
    const onClose = vi.fn();
    render(<BuddyScene stream={stream()} onClose={onClose} />);
    await userEvent.click(screen.getByRole('button', { name: 'Close Buddy' }));
    expect(onClose).toHaveBeenCalled();
  });
});
