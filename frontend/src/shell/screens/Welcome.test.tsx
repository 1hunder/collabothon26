import { act, render, screen } from '@testing-library/react';
import { createMemoryRouter, RouterProvider } from 'react-router-dom';
import { vi } from 'vitest';
import Welcome from './Welcome';
import { SessionProvider, isUnlocked, resetSession } from '../lib/session';

function setup() {
  const router = createMemoryRouter(
    [
      { path: '/', element: <Welcome /> },
      { path: '/overview', element: <div>Overview page</div> },
    ],
    { initialEntries: ['/'] },
  );
  render(
    <SessionProvider>
      <RouterProvider router={router} />
    </SessionProvider>,
  );
  return router;
}

describe('Welcome', () => {
  beforeEach(() => {
    resetSession();
    vi.useFakeTimers();
  });
  afterEach(() => vi.useRealTimers());

  it('shows greeting, one unlock button and no inputs', () => {
    setup();
    expect(screen.getByRole('heading', { name: 'Welcome back, Lena' })).toBeInTheDocument();
    const buttons = screen.getAllByRole('button');
    expect(buttons).toHaveLength(1);
    expect(buttons[0]).toHaveAccessibleName('Unlock with Face ID');
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument();
    expect(document.querySelector('input')).toBeNull();
  });

  it('disables the button when tapped', () => {
    setup();
    const button = screen.getByRole('button', { name: 'Unlock with Face ID' });
    act(() => button.click());
    expect(button).toBeDisabled();
  });

  it('navigates to /overview after 1500 ms and unlocks', () => {
    const router = setup();
    act(() => screen.getByRole('button', { name: 'Unlock with Face ID' }).click());
    act(() => vi.advanceTimersByTime(1499));
    expect(router.state.location.pathname).toBe('/');
    act(() => vi.advanceTimersByTime(1));
    expect(router.state.location.pathname).toBe('/overview');
    expect(isUnlocked()).toBe(true);
    expect(screen.getByText('Overview page')).toBeInTheDocument();
  });
});
