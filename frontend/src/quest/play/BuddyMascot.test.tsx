import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import BuddyMascot from './BuddyMascot';

describe('BuddyMascot', () => {
  it('opens the chat on tap while awake with a learning moment waiting', async () => {
    const onOpenChat = vi.fn();
    render(<BuddyMascot onOpenChat={onOpenChat} pending={[{ id: 'm1', concept_key: 'news_reaction', title: 'Reacting to news' }]} />);
    await userEvent.click(screen.getByRole('button', { name: /Chat with CommerzBuddy/ }));
    expect(onOpenChat).toHaveBeenCalledTimes(1);
  });
});
