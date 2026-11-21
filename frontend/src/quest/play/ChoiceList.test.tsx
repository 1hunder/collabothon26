import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import ChoiceList, { ActionInput, type ChoiceListProps } from './ChoiceList';

const suggestions = ['Go to the Library', 'Visit the Square', 'Ask the barkeep'];

function setup(over: Partial<ChoiceListProps> = {}) {
  const props: ChoiceListProps = {
    suggestions,
    canDecide: false,
    focusLeft: 3,
    bonusLeadAvailable: true,
    onSend: vi.fn(),
    onDecide: vi.fn(),
    onHint: vi.fn(),
    onBonusLead: vi.fn(),
    ...over,
  };
  render(<ChoiceList {...props} />);
  return props;
}

beforeEach(() => window.sessionStorage.clear());

describe('ChoiceList', () => {
  it('asks what you would do and lists three suggestions and the own-action choice', () => {
    setup();
    expect(screen.getByText('What would you do?')).toBeInTheDocument();
    for (const s of suggestions) expect(screen.getByRole('button', { name: s })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Write your own action…' })).toBeInTheDocument();
  });

  it('sends a suggestion immediately, without further typing', async () => {
    const p = setup();
    await userEvent.click(screen.getByRole('button', { name: 'Visit the Square' }));
    expect(p.onSend).toHaveBeenCalledWith('Visit the Square');
  });

  it('own action: the text box opens and Send stays disabled for empty or only spaces', async () => {
    const p = setup();
    await userEvent.click(screen.getByRole('button', { name: 'Write your own action…' }));
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
    await userEvent.click(screen.getByRole('button', { name: 'Write your own action…' }));
    expect(screen.getByRole('textbox')).toHaveClass('text-base');
  });

  it("shows I'm ready to decide only when the server says the player can decide", async () => {
    const { unmount } = render(
      <ChoiceList suggestions={suggestions} canDecide={false} focusLeft={3} bonusLeadAvailable onSend={vi.fn()} onDecide={vi.fn()} onHint={vi.fn()} onBonusLead={vi.fn()} />,
    );
    expect(screen.queryByRole('button', { name: "I'm ready to decide" })).not.toBeInTheDocument();
    unmount();
    const onDecide = vi.fn();
    setup({ canDecide: true, onDecide });
    await userEvent.click(screen.getByRole('button', { name: "I'm ready to decide" }));
    expect(onDecide).toHaveBeenCalled();
  });

  it('disables both Focus actions at 0 Focus', () => {
    setup({ focusLeft: 0 });
    expect(screen.getByRole('button', { name: 'Ask for a hint' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Chase a bonus lead' })).toBeDisabled();
  });

  it('enables the Focus actions with Focus left', async () => {
    const p = setup();
    await userEvent.click(screen.getByRole('button', { name: 'Ask for a hint' }));
    await userEvent.click(screen.getByRole('button', { name: 'Chase a bonus lead' }));
    expect(p.onHint).toHaveBeenCalled();
    expect(p.onBonusLead).toHaveBeenCalled();
  });
});

describe('own action keyboard', () => {
  it('Enter submits, Shift+Enter does not, empty never submits', async () => {
    const onSend = vi.fn();
    render(<ActionInput busy={false} onSend={onSend} />);
    const box = screen.getByRole('textbox');
    await userEvent.type(box, '{Enter}');
    expect(onSend).not.toHaveBeenCalled();
    await userEvent.type(box, 'Ask the clerk{Shift>}{Enter}{/Shift}more');
    expect(onSend).not.toHaveBeenCalled();
    await userEvent.type(box, '{Enter}');
    expect(onSend).toHaveBeenCalledWith('Ask the clerk\nmore');
  });
});
