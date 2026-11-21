import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import ChoiceList, { ActionInput, type ChoiceListProps } from './ChoiceList';

function setup(over: Partial<ChoiceListProps> = {}) {
  const props: ChoiceListProps = {
    canDecide: false,
    onSend: vi.fn(),
    onDecide: vi.fn(),
    ...over,
  };
  render(<ChoiceList {...props} />);
  return props;
}

beforeEach(() => window.sessionStorage.clear());

describe('ChoiceList', () => {
  it('asks what you would do and offers only a text input, no answer buttons', () => {
    setup();
    expect(screen.getByText('What would you do?')).toBeInTheDocument();
    expect(screen.getByRole('textbox')).toHaveAttribute('placeholder', 'What do you do?');
    expect(screen.queryByRole('button', { name: 'Write your own action…' })).not.toBeInTheDocument();
  });

  it('asks for the reasoning while the Campaign Master waits for it', () => {
    setup({ awaitingReasoning: true });
    expect(screen.getByText('Why did you choose that?')).toBeInTheDocument();
    expect(screen.getByRole('textbox')).toHaveAttribute('placeholder', 'Your reasoning, in your own words…');
  });

  it('the text box is always there and Send stays disabled for empty or only spaces', async () => {
    const p = setup();
    const box = screen.getByRole('textbox');
    const send = screen.getByRole('button', { name: 'Send' });
    expect(send).toBeDisabled();
    await userEvent.type(box, '   ');
    expect(send).toBeDisabled();
    await userEvent.type(box, 'read the notice');
    expect(send).toBeEnabled();
    await userEvent.click(send);
    expect(p.onSend).toHaveBeenCalledWith('read the notice');
  });

  it('the own-action text box uses at least 16px text so iOS does not zoom', async () => {
    setup();
    expect(screen.getByRole('textbox')).toHaveClass('text-base');
  });

  it("shows I'm ready to decide only when the server says the player can decide", async () => {
    const { unmount } = render(
      <ChoiceList canDecide={false} onSend={vi.fn()} onDecide={vi.fn()} />,
    );
    expect(screen.queryByRole('button', { name: "I'm ready to decide" })).not.toBeInTheDocument();
    unmount();
    const onDecide = vi.fn();
    setup({ canDecide: true, onDecide });
    await userEvent.click(screen.getByRole('button', { name: "I'm ready to decide" }));
    expect(onDecide).toHaveBeenCalled();
  });

  it('offers no "Ask for a hint" and no "Chase a bonus lead"', () => {
    setup();
    expect(screen.queryByRole('button', { name: 'Ask for a hint' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Chase a bonus lead' })).not.toBeInTheDocument();
  });
});

describe('own action keyboard', () => {
  it('Enter submits, Shift+Enter does not, empty never submits', async () => {
    const onSend = vi.fn();
    render(<ActionInput busy={false} onSend={onSend} prompt="What would you do?" />);
    const box = screen.getByRole('textbox');
    await userEvent.type(box, '{Enter}');
    expect(onSend).not.toHaveBeenCalled();
    await userEvent.type(box, 'Ask the clerk{Shift>}{Enter}{/Shift}more');
    expect(onSend).not.toHaveBeenCalled();
    await userEvent.type(box, '{Enter}');
    expect(onSend).toHaveBeenCalledWith('Ask the clerk\nmore');
  });
});
