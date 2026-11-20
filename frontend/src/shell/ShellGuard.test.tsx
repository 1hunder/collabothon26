import { render, screen } from '@testing-library/react';
import { createMemoryRouter, RouterProvider } from 'react-router-dom';
import ShellGuard from './ShellGuard';
import { SessionProvider, resetSession, unlockSession } from './lib/session';

function setup(): void {
  const router = createMemoryRouter(
    [
      { path: '/', element: <div>Welcome</div> },
      {
        path: '/overview',
        element: (
          <ShellGuard>
            <div>Secret</div>
          </ShellGuard>
        ),
      },
    ],
    { initialEntries: ['/overview'] },
  );
  render(
    <SessionProvider>
      <RouterProvider router={router} />
    </SessionProvider>,
  );
}

describe('ShellGuard', () => {
  beforeEach(() => resetSession());

  it('redirects to / while locked', () => {
    setup();
    expect(screen.getByText('Welcome')).toBeInTheDocument();
    expect(screen.queryByText('Secret')).not.toBeInTheDocument();
  });

  it('renders children when unlocked', () => {
    unlockSession();
    setup();
    expect(screen.getByText('Secret')).toBeInTheDocument();
  });
});
