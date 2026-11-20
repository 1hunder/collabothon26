import { defineConfig, devices } from '@playwright/test';

const port = 4173;

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
  webServer: {
    command: `npm run build && npm run preview`,
    url: `http://localhost:${port}`,
    reuseExistingServer: false,
    // Fixture mode: a new player has no hero, so Start opens "Create your hero" without a backend.
    env: { VITE_API_MODE: 'fixture' },
    timeout: 120_000,
  },
});
