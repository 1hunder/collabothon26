import { test, expect, type Page } from '@playwright/test';

async function unlock(page: Page): Promise<void> {
  await page.goto('/');
  await page.getByRole('button', { name: 'Unlock with Face ID' }).click();
  await expect(page).toHaveURL(/\/overview$/);
}

async function expectNoHorizontalOverflow(page: Page): Promise<void> {
  const [scrollWidth, innerWidth] = (await page.evaluate(
    '[document.documentElement.scrollWidth, window.innerWidth]',
  )) as [number, number];
  expect(scrollWidth).toBeLessThanOrEqual(innerWidth);
}

const tab = (page: Page, name: string) =>
  page.getByRole('navigation', { name: 'Main' }).getByRole('button', { name });

test('no horizontal overflow on any shell screen at 360 px', async ({ page }) => {
  await page.setViewportSize({ width: 360, height: 740 });
  await page.goto('/');
  await expectNoHorizontalOverflow(page);
  await unlock(page);
  await expectNoHorizontalOverflow(page);
  for (const name of ['Payments', 'Investments', 'Service', 'Profile']) {
    await tab(page, name).click();
    await expect(page.getByRole('heading', { name, level: 1 })).toBeVisible();
    await expectNoHorizontalOverflow(page);
  }
  await tab(page, 'Investments').click();
  await page.getByRole('button', { name: /StartDepot/ }).click();
  await expect(page).toHaveURL(/\/investments\/startdepot$/);
  await expectNoHorizontalOverflow(page);
  await page.getByRole('button', { name: 'Start your first quest' }).click();
  await expect(page.getByRole('heading', { name: 'Create your hero' })).toBeVisible();
  await expectNoHorizontalOverflow(page);
  await page.getByRole('radio', { name: /Guardian/ }).click();
  await page.getByRole('button', { name: 'Begin' }).click();
  await expect(page.getByText(/This story is real market history/)).toBeVisible();
  await expectNoHorizontalOverflow(page);
});

test('at 1280 px the app column is at most 430 px wide and centred', async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  await unlock(page);
  const box = await page.getByRole('navigation', { name: 'Main' }).boundingBox();
  if (box === null) throw new Error('tab bar has no bounding box');
  expect(box.width).toBeLessThanOrEqual(430);
  expect(Math.abs(box.x + box.width / 2 - 640)).toBeLessThanOrEqual(1);
  const header = await page.getByRole('banner').boundingBox();
  if (header === null) throw new Error('header has no bounding box');
  expect(header.width).toBeLessThanOrEqual(430);
  expect(Math.abs(header.x + header.width / 2 - 640)).toBeLessThanOrEqual(1);
});

test('Overview computed styles match the spec colours and shapes', async ({ page }) => {
  await unlock(page);
  const quest = page.locator('section', { has: page.getByRole('heading', { name: 'Finance Quest' }) });
  await expect(quest).toHaveCSS('background-color', 'rgb(255, 255, 255)');
  const start = page.getByRole('button', { name: 'Start', exact: true });
  await expect(start).toHaveCSS('background-color', 'rgb(255, 215, 0)');
  await expect(page.locator('body')).toHaveCSS('background-color', 'rgb(241, 239, 237)');
  await expect(page.getByRole('button', { name: /StartKonto/ })).toHaveCSS('border-radius', '0px');
  const box = await start.boundingBox();
  if (box === null) throw new Error('Start has no bounding box');
  const radius = parseFloat(await start.evaluate((el) => (globalThis as unknown as { getComputedStyle(e: unknown): { borderTopLeftRadius: string } }).getComputedStyle(el).borderTopLeftRadius));
  expect(radius).toBeGreaterThanOrEqual(box.height / 2);
});
