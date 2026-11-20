import { render, screen } from '@testing-library/react';
import { createMemoryRouter, RouterProvider } from 'react-router-dom';
import Placeholder from './Placeholder';

describe('Placeholder', () => {
  it('shows the exact demo text', () => {
    const router = createMemoryRouter([{ path: '/', element: <Placeholder title="Payments" /> }]);
    render(<RouterProvider router={router} />);
    expect(screen.getByText("This area isn't part of the demo.")).toBeInTheDocument();
  });
});
