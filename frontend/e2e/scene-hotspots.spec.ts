import { test, expect, type Page } from '@playwright/test';

// Scene hotspots (fixture mode): the glowing object painted into each constant background is a button.
test.setTimeout(90_000);

test.beforeEach(() => {
  test.skip(!['chromium-430x932', 'chromium-360x740'].includes(test.info().project.name), 'phone viewports on chromium only');
});

const shotsDir = process.env.HOTSPOT_SHOTS_DIR;
async function shot(page: Page, name: string, projectName: string): Promise<void> {
  if (shotsDir && projectName === 'chromium-430x932') await page.screenshot({ path: `${shotsDir}/${name}.png` });
}

async function startQuest(page: Page): Promise<void> {
  await page.goto('/');
  await page.getByRole('button', { name: 'Unlock with Face ID' }).click();
  await page.getByRole('button', { name: 'Start', exact: true }).click();
  await page.getByLabel('Name').fill('Mira');
  await page.getByRole('radio', { name: /Analyst/ }).click();
  await page.getByRole('button', { name: 'Begin' }).click();
  await expect(page).toHaveURL(/\/quest\/play$/);
  await readUntilChoices(page);
}

async function readUntilChoices(page: Page): Promise<void> {
  for (let i = 0; i < 60; i++) {
    if ((await page.getByRole('region', { name: 'Choices' }).count()) > 0 && (await page.getByTestId('title-card').count()) === 0) return;
    const title = page.getByTestId('title-card');
    if ((await title.count()) > 0) await title.click({ timeout: 2000 }).catch(() => undefined);
    const box = page.getByTestId('dialogue-box');
    if ((await box.count()) > 0) await box.click({ timeout: 2000 }).catch(() => undefined);
    await page.waitForTimeout(120);
  }
  throw new Error('choices never appeared');
}

async function goTo(page: Page, place: string): Promise<void> {
  await page.getByRole('button', { name: 'Map', exact: true }).click();
  await page.getByRole('dialog', { name: 'The map' }).getByRole('button', { name: new RegExp(place) }).click();
  await readUntilChoices(page);
}

/** The hotspot is on screen and is the topmost element at its own centre (nothing covers it). */
async function expectReachable(page: Page, name: string): Promise<void> {
  const btn = page.getByRole('button', { name });
  await expect(btn).toBeVisible();
  // Evaluated in the page as a string: the e2e tsconfig has no DOM lib.
  const top = (await page.evaluate(`(() => {
    const el = [...document.querySelectorAll('button')].find((b) => b.getAttribute('aria-label') === ${JSON.stringify(name)});
    const r = el.getBoundingClientRect();
    const hit = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
    return { isSelf: hit === el, vw: window.innerWidth, vh: window.innerHeight, r: { l: r.left, t: r.top, w: r.width, h: r.height } };
  })()`)) as { isSelf: boolean; vw: number; vh: number; r: { l: number; t: number; w: number; h: number } };
  expect(top.isSelf, `hotspot "${name}" is covered at its centre`).toBe(true);
  expect(top.r.w).toBeGreaterThan(44);
  expect(top.r.h).toBeGreaterThan(44);
  expect(top.r.l).toBeGreaterThanOrEqual(0);
  expect(top.r.l + top.r.w).toBeLessThanOrEqual(top.vw + 0.5);
}

test('Tavern: the notice board opens the pinned notice', async ({ page }, testInfo) => {
  await startQuest(page);
  await expectReachable(page, 'Read the notice board');
  await shot(page, 'tavern-scene', testInfo.project.name);
  await page.getByRole('button', { name: 'Read the notice board' }).click();
  const notice = page.getByRole('dialog', { name: 'Notice board' });
  await expect(notice).toBeVisible();
  await expect(notice).toContainText('No news posted yet');
  await shot(page, 'tavern-notice', testInfo.project.name);
  await notice.getByRole('button', { name: 'Close Notice board' }).click();
  await expect(notice).toHaveCount(0);
});

test('Library: the glowing books open the parchment, which pages', async ({ page }, testInfo) => {
  await startQuest(page);
  await goTo(page, 'Library');
  await expectReachable(page, "Read the guild's records");
  await shot(page, 'library-scene', testInfo.project.name);
  await page.getByRole('button', { name: "Read the guild's records" }).click();
  const lib = page.getByRole('dialog', { name: 'Library' });
  await expect(lib).toBeVisible();
  await expect(lib.getByText(/^Page 1 of \d+$/)).toBeVisible();
  // One close control only: the quest layout's own is hidden while the parchment is open.
  await expect(page.getByRole('button', { name: 'Close quest' })).toHaveCount(0);
  await shot(page, 'library-parchment', testInfo.project.name);
  await lib.getByRole('button', { name: 'Next page' }).click();
  await expect(lib.getByText(/^Page 2 of \d+$/)).toBeVisible();
  await shot(page, 'library-parchment-page2', testInfo.project.name);
  await lib.getByRole('button', { name: 'Close Library' }).click();
  await expect(lib).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Close quest' })).toHaveCount(1);
});

test('Market Square: the stall opens the panel with the price chart', async ({ page }, testInfo) => {
  await startQuest(page);
  await goTo(page, 'Market Square');
  await expectReachable(page, 'Visit the market stall');
  await shot(page, 'market-scene', testInfo.project.name);
  await page.getByRole('button', { name: 'Visit the market stall' }).click();
  const panel = page.getByRole('dialog', { name: 'Market stall' });
  await expect(panel).toBeVisible();
  await expect(panel.getByRole('tab', { name: 'Price chart', selected: true })).toBeVisible();
  await expect(panel.locator('canvas').first()).toBeVisible();
  await shot(page, 'market-stall', testInfo.project.name);
  await panel.getByRole('button', { name: 'Close Market stall' }).click();
  await expect(panel).toHaveCount(0);
});
