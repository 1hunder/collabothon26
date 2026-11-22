import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import ChoiceList from './ChoiceList';

describe('ChoiceList: leaving a decision scene', () => {
  it('shows "Leave without trading" in a decision scene and calls onLeave', async () => {
    const onLeave = vi.fn();
    render(<ChoiceList prompt="What do you do with your coins?" canDecide={false} onSend={vi.fn()} onDecide={vi.fn()} onLeave={onLeave} />);
    await userEvent.click(screen.getByRole('button', { name: /Leave without trading/ }));
    expect(onLeave).toHaveBeenCalledTimes(1);
  });

  it('has no leave button outside a decision scene', () => {
    render(<ChoiceList canDecide={false} onSend={vi.fn()} onDecide={vi.fn()} />);
    expect(screen.queryByRole('button', { name: /Leave without trading/ })).not.toBeInTheDocument();
  });
});
