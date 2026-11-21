import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { createMemoryRouter, RouterProvider } from 'react-router-dom';
import QuestLayout from './QuestLayout';
import { useReportSheetOpen } from './sheetOpen';

function Sheeted(): React.JSX.Element {
  useReportSheetOpen(true);
  return <h1>Sheet</h1>;
}

function setup() {
  const router = createMemoryRouter(
    [
      { path: '/overview', element: <div>Overview page</div> },
      { path: '/quest', element: <QuestLayout />, children: [{ index: true, element: <h1>Quest screen</h1> }] },
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
    expect(screen.getByText('Quest screen')).toBeInTheDocument();
  });

  it('Leave navigates to the origin', async () => {
    const router = setup();
    await userEvent.click(screen.getByRole('button', { name: 'Close quest' }));
    await userEvent.click(screen.getByRole('button', { name: 'Leave' }));
    expect(router.state.location.pathname).toBe('/overview');
    expect(screen.getByText('Overview page')).toBeInTheDocument();
  });
});

describe('QuestLayout with a sheet open', () => {
  it('hides its own close button so the sheet has the only one', () => {
    const router = createMemoryRouter([{ path: '/quest', element: <QuestLayout />, children: [{ index: true, element: <Sheeted /> }] }], { initialEntries: ['/quest'] });
    render(<RouterProvider router={router} />);
    expect(screen.queryByRole('button', { name: 'Close quest' })).not.toBeInTheDocument();
  });
});
