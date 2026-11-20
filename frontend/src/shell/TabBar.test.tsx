import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { createMemoryRouter, RouterProvider } from 'react-router-dom';
import TabBar from './TabBar';

function setup(path: string, initial: string[] = [path]) {
  const router = createMemoryRouter([{ path: '*', element: <TabBar /> }], {
    initialEntries: initial,
    initialIndex: initial.length - 1,
  });
  render(<RouterProvider router={router} />);
  return router;
}

function activeLabel(): string | undefined {
  return screen
    .getAllByRole('button')
    .find((b) => b.getAttribute('aria-current') === 'page')
    ?.textContent?.trim();
}

describe('TabBar', () => {
  it('lists tabs in order', () => {
    setup('/overview');
    expect(screen.getAllByRole('button').map((b) => b.textContent)).toEqual([
      'Overview',
      'Payments',
      'Investments',
      'Service',
      'Profile',
    ]);
  });

  it.each([
    ['/overview', 'Overview'],
    ['/payments', 'Payments'],
    ['/investments', 'Investments'],
    ['/investments/startdepot', 'Investments'],
    ['/service', 'Service'],
    ['/profile', 'Profile'],
  ])('highlights the right tab for %s', (path, label) => {
    setup(path);
    expect(activeLabel()).toBe(label);
  });

  it('inactive tab pushes its root', async () => {
    const router = setup('/overview');
    await userEvent.click(screen.getByRole('button', { name: 'Payments' }));
    expect(router.state.location.pathname).toBe('/payments');
    expect(router.state.historyAction).toBe('PUSH');
  });

  it('active tab replaces with its root', async () => {
    const router = setup('/investments/startdepot', ['/overview', '/investments/startdepot']);
    await userEvent.click(screen.getByRole('button', { name: 'Investments' }));
    expect(router.state.location.pathname).toBe('/investments');
    expect(router.state.historyAction).toBe('REPLACE');
  });
});
