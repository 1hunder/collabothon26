import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { createMemoryRouter, RouterProvider } from 'react-router-dom';
import QuestLayout from './QuestLayout';
import WhatAreYouInto from './screens/WhatAreYouInto';

function setup() {
  const router = createMemoryRouter(
    [
      { path: '/overview', element: <div>Overview page</div> },
      { path: '/quest', element: <QuestLayout />, children: [{ index: true, element: <WhatAreYouInto /> }] },
    ],
    { initialEntries: ['/overview', { pathname: '/quest', state: { origin: '/overview' } }], initialIndex: 1 },
  );
  render(<RouterProvider router={router} />);
  return router;
}

const text = 'Leave the quest? You can continue where you left off.';

describe('QuestLayout', () => {
  it('opens the leave dialog from the close button', async () => {
    setup();
    await userEvent.click(screen.getByRole('button', { name: 'Close quest' }));
    expect(screen.getByRole('dialog')).toHaveTextContent(text);
  });

  it('Stay keeps you on the quest', async () => {
    const router = setup();
    await userEvent.click(screen.getByRole('button', { name: 'Close quest' }));
    await userEvent.click(screen.getByRole('button', { name: 'Stay' }));
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(router.state.location.pathname).toBe('/quest');
    expect(screen.getByText('What are you into?')).toBeInTheDocument();
  });

  it('Leave navigates to the origin', async () => {
    const router = setup();
    await userEvent.click(screen.getByRole('button', { name: 'Close quest' }));
    await userEvent.click(screen.getByRole('button', { name: 'Leave' }));
    expect(router.state.location.pathname).toBe('/overview');
    expect(screen.getByText('Overview page')).toBeInTheDocument();
  });
});
