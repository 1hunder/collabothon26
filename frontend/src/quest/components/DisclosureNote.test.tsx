import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import DisclosureNote from './DisclosureNote';

it('shows the exact note and Got it dismisses', async () => {
  const onDismiss = vi.fn();
  render(<DisclosureNote onDismiss={onDismiss} />);
  expect(
    screen.getByText(
      "This story is real market history. We've hidden the company's name, the dates and the price level. You'll find out who it was at the end.",
    ),
  ).toBeInTheDocument();
  await userEvent.click(screen.getByRole('button', { name: 'Got it' }));
  expect(onDismiss).toHaveBeenCalledTimes(1);
});
