import { QueryClientProvider } from '@tanstack/react-query';
import { render } from '@testing-library/react';
import { createMemoryRouter, RouterProvider, type RouteObject } from 'react-router-dom';
import { createQueryClient } from '../api/queryClient';

/** Render routes in a memory router with a fresh QueryClient. */
export function renderRoutes(routes: RouteObject[], initialEntries: string[]): ReturnType<typeof createMemoryRouter> {
  const router = createMemoryRouter(routes, { initialEntries });
  render(
    <QueryClientProvider client={createQueryClient()}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );
  return router;
}
