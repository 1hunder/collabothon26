import { act, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { DiceCard, RollResult } from '../../api/types';
import DiceMoment, { TUMBLE_MS, type DiceApi } from './DiceMoment';

const card: DiceCard = {
  kind: 'dice',
  roll_id: 'r1',
  challenge_id: 'r1',
  title: 'Spot what is off in the ledger',
  dc: 12,
  bonus: 2,
  keen_eye_available: false,
  keen_eye_left: 0,
};

const result = (over: Partial<RollResult>): RollResult => ({
  roll_id: 'r1',
  challenge_id: 'r1',
  title: card.title,
  dice: [14],
  used: 14,
  bonus: 2,
  total: 16,
  dc: 12,
  result: 'success',
  final: true,
  options: ['continue'],
  rerolled: false,
  rerolls_left: 0,
  keen_eye_left: 0,
  alt_source: null,
  ...over,
});

function setup(c: DiceCard, api: Partial<DiceApi>) {
  const onResolved = vi.fn();
  const full: DiceApi = {
    roll: vi.fn(() => Promise.resolve(result({}))),
    reroll: vi.fn(() => Promise.resolve(result({}))),
    accept: vi.fn(() => Promise.resolve(result({}))),
    ...api,
  };
  render(<DiceMoment card={c} api={full} onResolved={onResolved} />);
  return { api: full, onResolved };
}

beforeEach(() => {
  // reduced motion: no tumble delay in the branch tests
  vi.stubGlobal('matchMedia', (q: string) => ({ matches: q.includes('reduce'), addEventListener: () => undefined, removeEventListener: () => undefined }));
});
afterEach(() => vi.unstubAllGlobals());

describe('DiceMoment', () => {
  it('shows the challenge, Difficulty, Bonus +2 and Roll', () => {
    setup(card, {});
    expect(screen.getByText(card.title)).toBeInTheDocument();
    expect(screen.getByText(/Difficulty 12/)).toBeInTheDocument();
    expect(screen.getByText(/Bonus \+2/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Roll' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Keen Eye/ })).not.toBeInTheDocument();
  });

  it('names the skill on an unplanned check', () => {
    setup({ ...card, skill: 'Insight', dc: 13, title: 'Ren Tal' }, {});
    expect(screen.getByText('Ren Tal')).toBeInTheDocument();
    expect(screen.getByText(/Insight check · DC 13/)).toBeInTheDocument();
  });

  it('success: shows the sum against the difficulty, the verdict and Continue only', async () => {
    const { onResolved } = setup(card, {});
    await userEvent.click(screen.getByRole('button', { name: 'Roll' }));
    expect(await screen.findByTestId('dice-sum')).toHaveTextContent('14 + 2 = 16 against 12');
    expect(screen.getByTestId('dice-verdict')).toHaveTextContent('Success');
    expect(screen.queryByRole('button', { name: /Second Look/ })).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Continue' }));
    expect(onResolved).toHaveBeenCalledWith(expect.objectContaining({ result: 'success' }));
  });

  it('Investigator with Keen Eye: the extra button rolls with advantage and shows both dice', async () => {
    const { api } = setup({ ...card, keen_eye_available: true, keen_eye_left: 1 }, {
      roll: vi.fn(() => Promise.resolve(result({ dice: [9, 14], used: 14 }))),
    });
    await userEvent.click(screen.getByRole('button', { name: 'Keen Eye — roll with advantage (1 left)' }));
    expect(api.roll).toHaveBeenCalledWith('advantage');
    expect(await screen.findByText(/Two dice: 9 and 14/)).toBeInTheDocument();
  });

  it('Guardian or Investigator setback: only Continue, no reroll option', async () => {
    setup(card, { roll: vi.fn(() => Promise.resolve(result({ dice: [5], used: 5, total: 7, result: 'setback' }))) });
    await userEvent.click(screen.getByRole('button', { name: 'Roll' }));
    expect(await screen.findByTestId('dice-verdict')).toHaveTextContent('Setback');
    expect(screen.getByRole('button', { name: 'Continue' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Second Look/ })).not.toBeInTheDocument();
  });

  it('Analyst setback: Second Look and Accept setback, and nothing is narrated yet', async () => {
    const { onResolved } = setup(card, {
      roll: vi.fn(() => Promise.resolve(result({ dice: [5], used: 5, total: 7, result: 'setback', final: false, options: ['reroll', 'accept'], rerolls_left: 1 }))),
    });
    await userEvent.click(screen.getByRole('button', { name: 'Roll' }));
    expect(await screen.findByRole('button', { name: 'Second Look — reroll (1 left)' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Accept setback' })).toBeInTheDocument();
    expect(onResolved).not.toHaveBeenCalled();
  });

  it('Second Look rolls again and the second result is final', async () => {
    const { api, onResolved } = setup(card, {
      roll: vi.fn(() => Promise.resolve(result({ dice: [5], used: 5, total: 7, result: 'setback', final: false, options: ['reroll', 'accept'], rerolls_left: 1 }))),
      reroll: vi.fn(() => Promise.resolve(result({ dice: [17], used: 17, total: 19, rerolled: true }))),
    });
    await userEvent.click(screen.getByRole('button', { name: 'Roll' }));
    await userEvent.click(await screen.findByRole('button', { name: /Second Look/ }));
    expect(api.reroll).toHaveBeenCalledWith('r1');
    expect(await screen.findByTestId('dice-sum')).toHaveTextContent('17 + 2 = 19 against 12');
    expect(onResolved).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole('button', { name: 'Continue' }));
    expect(onResolved).toHaveBeenCalledWith(expect.objectContaining({ rerolled: true }));
  });

  it('Accept setback keeps the setback and resolves', async () => {
    const accepted = result({ dice: [5], used: 5, total: 7, result: 'setback' });
    const { api, onResolved } = setup(card, {
      roll: vi.fn(() => Promise.resolve(result({ dice: [5], used: 5, total: 7, result: 'setback', final: false, options: ['reroll', 'accept'], rerolls_left: 1 }))),
      accept: vi.fn(() => Promise.resolve(accepted)),
    });
    await userEvent.click(screen.getByRole('button', { name: 'Roll' }));
    await userEvent.click(await screen.findByRole('button', { name: 'Accept setback' }));
    expect(api.accept).toHaveBeenCalledWith('r1');
    await vi.waitFor(() => expect(onResolved).toHaveBeenCalledWith(accepted));
  });

  it('a natural 20 is a Success whatever the difficulty and is labelled', async () => {
    setup({ ...card, dc: 18 }, { roll: vi.fn(() => Promise.resolve(result({ dice: [20], used: 20, total: 22, dc: 18 }))) });
    await userEvent.click(screen.getByRole('button', { name: 'Roll' }));
    expect(await screen.findByText('Natural 20')).toBeInTheDocument();
    expect(screen.getByTestId('dice-sum')).toHaveTextContent('20 + 2 = 22 against 18');
    expect(screen.getByTestId('dice-verdict')).toHaveTextContent('Success');
  });

  it('a natural 1 is a Setback and is labelled', async () => {
    setup(card, { roll: vi.fn(() => Promise.resolve(result({ dice: [1], used: 1, total: 3, result: 'setback' }))) });
    await userEvent.click(screen.getByRole('button', { name: 'Roll' }));
    expect(await screen.findByText('Natural 1')).toBeInTheDocument();
    expect(screen.getByTestId('dice-verdict')).toHaveTextContent('Setback');
  });

  it('shows a retry message when the roll fails', async () => {
    setup(card, { roll: vi.fn(() => Promise.reject(new Error('x'))) });
    await userEvent.click(screen.getByRole('button', { name: 'Roll' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('The dice would not roll');
    expect(screen.getByRole('button', { name: 'Roll' })).toBeInTheDocument();
  });
});

describe('DiceMoment tumble', () => {
  beforeEach(() => {
    vi.unstubAllGlobals();
    vi.useFakeTimers({ shouldAdvanceTime: true });
  });
  afterEach(() => vi.useRealTimers());

  it('tumbles for about a second before the result shows', async () => {
    setup(card, {});
    await userEvent.click(screen.getByRole('button', { name: 'Roll' }));
    const die = screen.getByRole('status', { name: 'Rolling' });
    expect(die).toHaveClass('animate-tumble');
    expect(screen.queryByTestId('dice-verdict')).not.toBeInTheDocument();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(TUMBLE_MS);
    });
    expect(await screen.findByTestId('dice-verdict')).toBeInTheDocument();
  });
});
