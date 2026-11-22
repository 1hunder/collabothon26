import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import MarketPanel from './MarketPanel';

describe('MarketPanel', () => {
  it('opens the Rumour ledger from the stall when the hero owns it (there is no chip for it)', async () => {
    const onRumours = vi.fn();
    render(<MarketPanel rows={[]} newsDay={null} onClose={vi.fn()} onRumours={onRumours} />);
    await userEvent.click(screen.getByRole('button', { name: 'Rumour ledger' }));
    expect(onRumours).toHaveBeenCalledTimes(1);
  });

  it('shows no Rumour ledger button without the ledger', () => {
    render(<MarketPanel rows={[]} newsDay={null} onClose={vi.fn()} />);
    expect(screen.queryByRole('button', { name: 'Rumour ledger' })).not.toBeInTheDocument();
  });
});
