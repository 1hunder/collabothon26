import { test, expect, type Page } from '@playwright/test';

/** True when the element matching the selector is the topmost element at its own centre. */
async function isTopAtCentre(page: Page, label: string): Promise<boolean> {
  return (await page.evaluate(`(() => {
    const el = [...document.querySelectorAll('button')].find((b) => b.textContent.trim() === ${JSON.stringify(label)} || b.getAttribute('aria-label') === ${JSON.stringify(label)});
    if (!el) return false;
    const r = el.getBoundingClientRect();
    const top = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
    return !!top && el.contains(top);
  })()`)) as boolean;
}

test('play screen: voice, hero status and close each own their hit area', async ({ page }) => {
  await page.goto('/');
  await page.getByRole('button', { name: 'Unlock with Face ID' }).click();
  await page.getByRole('button', { name: /Investments/ }).click();
  await page.getByRole('button', { name: /StartDepot/ }).click();
  await page.getByRole('button', { name: 'Start your first quest' }).click();
  await page.getByRole('radio', { name: /Guardian/ }).click();
  await page.getByRole('button', { name: 'Begin' }).click();
  await page.getByRole('button', { name: 'Gaming' }).click();
  await page.getByRole('button', { name: 'Find my quest' }).click();
  await expect(page.getByText(/This story is real market history/)).toBeVisible();
  await page.getByRole('button', { name: 'Got it' }).click();
  await expect(page).toHaveURL(/\/quest\/play$/);
  await expect(page.getByRole('button', { name: 'Hero status' })).toBeVisible();
  // The Tavern title card covers the stage for a moment; skip it.
  await page.getByTestId('title-card').click();
  await expect(page.getByTestId('title-card')).toHaveCount(0);
  expect(await isTopAtCentre(page, 'Hero status')).toBe(true);
  expect(await isTopAtCentre(page, 'Close quest')).toBe(true);
  expect(await isTopAtCentre(page, 'Voice')).toBe(true);
  // Exactly one voice control on this screen.
  await expect(page.getByRole('button', { name: /^Voice( on| off)?$/ })).toHaveCount(1);
});
