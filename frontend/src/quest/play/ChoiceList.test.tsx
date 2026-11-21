import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import ChoiceList, { ActionInput, type ChoiceListProps } from './ChoiceList';

function setup(over: Partial<ChoiceListProps> = {}) {
  const props: ChoiceListProps = { canDecide: false, onSend: vi.fn(), onDecide: vi.fn(), ...over };
  render(<ChoiceList {...props} />);
  return props;
}

beforeEach(() => window.sessionStorage.clear());

describe('ChoiceList', () => {
  it('shows only the text box: no preset options, no hint and no bonus lead', () => {
    setup();
    expect(screen.getByLabelText('What would you do?')).toBeInTheDocument();
    expect(screen.getByRole('textbox')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Write your own action…' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Ask for a hint' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Chase a bonus lead' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Back' })).not.toBeInTheDocument();
  });

  it('Send stays disabled for empty or only spaces, then sends the typed action', async () => {
    const p = setup();
    const box = screen.getByRole('textbox');
    const send = screen.getByRole('button', { name: 'Send' });
    expect(send).toBeDisabled();
    await userEvent.type(box, '   ');
    expect(send).toBeDisabled();
    await userEvent.type(box, 'read the ledger');
    expect(send).toBeEnabled();
    await userEvent.click(send);
    expect(p.onSend).toHaveBeenCalledWith('read the ledger');
  });

  it('the text box uses at least 16px text so iOS does not zoom', () => {
    setup();
    expect(screen.getByRole('textbox')).toHaveClass('text-base');
  });

  it('a decision scene asks about the coins and shows the purse', () => {
    setup({ prompt: 'What do you do with your coins?', purse: { cash_eur: 700, position_eur: 300, total_eur: 1000 } });
    expect(screen.getByLabelText('What do you do with your coins?')).toBeInTheDocument();
    expect(screen.getByLabelText('Your purse')).toHaveTextContent('€700.00');
  });

  it("shows I'm ready to decide only when the server says the player can decide", async () => {
    const { unmount } = render(<ChoiceList canDecide={false} onSend={vi.fn()} onDecide={vi.fn()} />);
    expect(screen.queryByRole('button', { name: "I'm ready to decide" })).not.toBeInTheDocument();
    unmount();
    const onDecide = vi.fn();
    setup({ canDecide: true, onDecide });
    await userEvent.click(screen.getByRole('button', { name: "I'm ready to decide" }));
    expect(onDecide).toHaveBeenCalled();
  });
});

describe('own action keyboard', () => {
  it('Enter submits, Shift+Enter does not, empty never submits', async () => {
    const onSend = vi.fn();
    render(<ActionInput busy={false} onSend={onSend} onCancel={() => undefined} />);
    const box = screen.getByRole('textbox');
    await userEvent.type(box, '{Enter}');
    expect(onSend).not.toHaveBeenCalled();
    await userEvent.type(box, 'Ask the clerk{Shift>}{Enter}{/Shift}more');
    expect(onSend).not.toHaveBeenCalled();
    await userEvent.type(box, '{Enter}');
    expect(onSend).toHaveBeenCalledWith('Ask the clerk\nmore');
  });
});
