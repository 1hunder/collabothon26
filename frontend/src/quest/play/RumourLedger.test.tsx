import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it } from 'vitest';
import DialogueBox from './DialogueBox';
import RumourLedger from './RumourLedger';
import { hasRumourLedger, rumoursHeard } from './rumours';

afterEach(cleanup);

describe('Rumour ledger', () => {
  it('shows only for a hero with the item', () => {
    expect(hasRumourLedger(['ratio-lens'], undefined)).toBe(false);
    expect(hasRumourLedger(['rumour_ledger'], undefined)).toBe(true);
    expect(hasRumourLedger([], ['x'])).toBe(true);
  });
  it('prefers the server list, else what Ren Tal said', () => {
    const backlog = [
      { seq: 1, speaker: 'Ren Tal', text: 'The foreman sold early.' },
      { seq: 2, speaker: 'Campaign Master', text: 'Narration.' },
    ];
    expect(rumoursHeard(undefined, backlog)).toEqual(['The foreman sold early.']);
    expect(rumoursHeard(['From the server'], backlog)).toEqual(['From the server']);
  });
  it('lists each rumour in a sheet', async () => {
    render(<RumourLedger rumours={['A', 'B']} onClose={() => undefined} />);
    expect(screen.getByRole('dialog', { name: 'Rumour ledger' })).toHaveTextContent('A');
    await userEvent.click(screen.getByRole('button', { name: 'Close Rumour ledger' }));
  });
});

describe('Backlog swipe', () => {
  it('a downward swipe on the dialogue box asks for the backlog', () => {
    let opened = 0;
    render(<DialogueBox speaker="Campaign Master" text="Hello." onAdvance={() => undefined} onSwipeDown={() => (opened += 1)} />);
    const box = screen.getByTestId('dialogue-box');
    fireEvent.touchStart(box, { touches: [{ clientY: 100 }] });
    fireEvent.touchEnd(box, { changedTouches: [{ clientY: 260 }] });
    expect(opened).toBe(1);
  });
});
