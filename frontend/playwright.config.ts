import { defineConfig, devices } from '@playwright/test';

const port = Number(process.env.PW_PORT ?? 4173);

const viewports = [
  { name: '360x740', viewport: { width: 360, height: 740 } },
  { name: '430x932', viewport: { width: 430, height: 932 } },
  { name: '1280x800', viewport: { width: 1280, height: 800 } },
];

export default defineConfig({
  testDir: './e2e',
  fullyParallel: true,
  reporter: 'list',
  use: { baseURL: `http://localhost:${port}`, trace: 'on-first-retry' },
  projects: viewports.flatMap(({ name, viewport }) => [
    { name: `chromium-${name}`, use: { ...devices['Desktop Chrome'], viewport } },
    { name: `webkit-${name}`, use: { ...devices['Desktop Safari'], viewport } },
  ]),
  // Live-API spec (e2e/enron-live.spec.ts): the page is served separately (see that file), no webServer.
  webServer: process.env.E2E_LIVE_API
    ? undefined
    : {
    command: `npm run build && npx vite preview --port ${port} --strictPort`,
    url: `http://localhost:${port}`,
    reuseExistingServer: false,
    // Fixture mode: a new player has no hero, so Start opens "Create your hero" without a backend.
    env: { VITE_API_MODE: 'fixture' },
    timeout: 120_000,
  },
});
