import { render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { ApiError, api } from '../api/client';
import RevealGuard from './RevealGuard';

function setup(): void {
  render(
    <MemoryRouter initialEntries={['/quest/reveal']}>
      <Routes>
        <Route
          path="/quest/reveal"
          element={
            <RevealGuard scenarioId="s1" fallbackPath="/quest/debrief">
              {(d) => <p>revealed {d.real_name}</p>}
            </RevealGuard>
          }
        />
        <Route path="/quest/debrief" element={<p>debrief</p>} />
      </Routes>
    </MemoryRouter>,
  );
}

afterEach(() => vi.restoreAllMocks());

it('redirects to the fallback on 403', async () => {
  vi.spyOn(api, 'reveal').mockRejectedValue(new ApiError('RevealLocked', 403));
  setup();
  expect(await screen.findByText('debrief')).toBeInTheDocument();
});

it('renders children with data on success', async () => {
  vi.spyOn(api, 'reveal').mockResolvedValue({ real_name: 'X' } as never);
  setup();
  expect(await screen.findByText('revealed X')).toBeInTheDocument();
});
