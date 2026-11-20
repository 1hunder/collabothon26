import { render, screen } from '@testing-library/react';
import { createMemoryRouter, RouterProvider } from 'react-router-dom';
import TopBar from './TopBar';

function setup(handle?: object): void {
  const router = createMemoryRouter([{ path: '/', element: <TopBar />, handle }]);
  render(<RouterProvider router={router} />);
}

describe('TopBar', () => {
  it('shows the logo and no back arrow on the overview', () => {
    setup();
    expect(screen.getByAltText('Commerzbank')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Back' })).not.toBeInTheDocument();
  });

  it('shows the title instead of the logo, without back by default', () => {
    setup({ title: 'Payments' });
    expect(screen.getByRole('heading', { name: 'Payments' })).toBeInTheDocument();
    expect(screen.queryByAltText('Commerzbank')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Back' })).not.toBeInTheDocument();
  });

  it('shows the back arrow only when requested', () => {
    setup({ title: 'StartDepot', back: true });
    expect(screen.getByRole('button', { name: 'Back' })).toBeInTheDocument();
  });
});
