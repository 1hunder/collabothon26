import { test, expect, type Locator, type Page } from '@playwright/test';

test('page loads and shows Welcome', async ({ page }) => {
  await page.goto('/');
  await expect(page).toHaveTitle('Commerzbank — Demo');
  await expect(page.getByRole('heading', { name: 'Welcome back, Lena' })).toBeVisible();
});

test('guarded route redirects to Welcome while locked', async ({ page }) => {
  await page.goto('/overview');
  await expect(page).toHaveURL(/\/$/);
  await expect(page.getByRole('heading', { name: 'Welcome back, Lena' })).toBeVisible();
});

test('Face ID unlock lands on Overview without camera or credential APIs', async ({ page }) => {
  // Browser-context script, kept as a string because the e2e tsconfig has no DOM lib.
  await page.addInitScript(`
    window.__apiCalls = [];
    const record = (name) => () => { window.__apiCalls.push(name); return Promise.reject(new Error('blocked')); };
    if (navigator.mediaDevices) navigator.mediaDevices.getUserMedia = record('getUserMedia');
    if (navigator.credentials) {
      navigator.credentials.get = record('credentials.get');
      navigator.credentials.create = record('credentials.create');
    }
  `);
  await page.goto('/');
  await expect(page.locator('input')).toHaveCount(0);
  await page.getByRole('button', { name: 'Unlock with Face ID' }).click();
  await expect(page.getByRole('button', { name: 'Unlock with Face ID' })).toBeDisabled();
  await expect(page).toHaveURL(/\/overview$/);
  await expect(page.getByRole('heading', { name: 'Hello, Lena' })).toBeVisible();
  expect(await page.evaluate('window.__apiCalls')).toEqual([]);
});

test('placeholder tabs show the demo text with the tab bar visible', async ({ page }) => {
  await page.goto('/');
  await page.getByRole('button', { name: 'Unlock with Face ID' }).click();
  await expect(page).toHaveURL(/\/overview$/);
  for (const name of ['Payments', 'Service', 'Profile']) {
    await page.getByRole('navigation', { name: 'Main' }).getByRole('button', { name }).click();
    await expect(page.getByRole('heading', { name, level: 1 })).toBeVisible();
    await expect(page.getByText("This area isn't part of the demo.")).toBeVisible();
    await expect(page.getByRole('navigation', { name: 'Main' })).toBeVisible();
  }
});

async function unlock(page: Page): Promise<void> {
  await page.goto('/');
  await page.getByRole('button', { name: 'Unlock with Face ID' }).click();
  await expect(page).toHaveURL(/\/overview$/);
}

async function top(locator: Locator): Promise<number> {
  const box = await locator.boundingBox();
  if (box === null) throw new Error('element has no bounding box');
  return box.y;
}

test('Overview shows its content in order', async ({ page }) => {
  await unlock(page);
  const main = page.getByRole('main');
  const ordered = [
    page.getByRole('heading', { name: 'Hello, Lena' }),
    main.getByText('€1,240.50').first(),
    page.getByRole('button', { name: /StartKonto/ }),
    page.getByText('DE00 0000 0000 0000 0000 00'),
    page.getByRole('button', { name: /StartDepot/ }),
    page.getByText('No investments yet'),
    page.getByRole('button', { name: 'Transfer' }),
    page.getByRole('button', { name: 'Cards' }),
    page.getByRole('button', { name: 'Postbox' }),
    page.getByRole('heading', { name: 'Finance Quest' }),
  ];
  const ys: number[] = [];
  for (const l of ordered) ys.push(await top(l));
  // Transfer, Cards and Postbox share a row; every other step must be strictly lower.
  const rowIdx = [6, 7, 8];
  ys.forEach((y, i) => {
    if (i === 0) return;
    const prev = rowIdx.includes(i) && rowIdx.includes(i - 1) ? ys[i - 1] : ys[i - 1] + 1;
    expect(y, `element ${i}`).toBeGreaterThanOrEqual(prev);
  });
  await expect(page.getByRole('button', { name: /StartDepot/ })).toContainText('€0.00');
  await expect(page.getByText('New', { exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Start', exact: true })).toBeVisible();
});

test('quick action shows one toast that disappears', async ({ page }) => {
  await unlock(page);
  await page.getByRole('button', { name: 'Transfer' }).click();
  const toast = page.getByText('Not available in this demo.');
  await expect(toast).toHaveCount(1);
  await expect(toast).toBeVisible();
  await expect(toast).toHaveCount(0, { timeout: 5000 });
});

test('quest card is reachable within one viewport of scrolling', async ({ page }) => {
  await unlock(page);
  const vh = page.viewportSize()?.height ?? 0;
  const title = page.getByRole('heading', { name: 'Finance Quest' });
  const start = page.getByRole('button', { name: 'Start', exact: true });
  const startBox = await start.boundingBox();
  if (startBox === null) throw new Error('no Start box');
  // Within one viewport height of scrolling means the button bottom is at most 2 viewports down.
  expect(startBox.y + startBox.height).toBeLessThanOrEqual(2 * vh);
  await page.mouse.move(10, vh / 2);
  await page.mouse.wheel(0, vh);
  await expect(title).toBeInViewport({ ratio: 1 });
  await expect(start).toBeInViewport({ ratio: 1 });
});

const tabBar = (page: Page): Locator => page.getByRole('navigation', { name: 'Main' });
const investmentsTab = (page: Page): Locator => tabBar(page).getByRole('button', { name: 'Investments' });

async function openStartDepotFromOverview(page: Page): Promise<void> {
  await unlock(page);
  await page.getByRole('button', { name: /StartDepot/ }).click();
  await expect(page).toHaveURL(/\/investments\/startdepot$/);
}

test('StartDepot from the Overview card shows content, highlights Investments, back returns', async ({ page }) => {
  await openStartDepotFromOverview(page);
  const main = page.getByRole('main');
  await expect(main.getByText('€0.00')).toBeVisible();
  await expect(page.getByText("You don't have any investments yet.")).toBeVisible();
  await expect(page.getByText('No custody fees up to €20,000 depot value')).toBeVisible();
  await expect(page.getByText('Savings plans from €25 a month')).toBeVisible();
  await expect(page.getByText('For pupils, students and trainees')).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Practise before you invest' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Start your first quest' })).toBeVisible();
  await expect(investmentsTab(page)).toHaveAttribute('aria-current', 'page');
  await page.getByRole('button', { name: 'Back' }).click();
  await expect(page).toHaveURL(/\/overview$/);
  await expect(page.getByRole('heading', { name: 'Hello, Lena' })).toBeVisible();
});

test('Investments to StartDepot and back arrow returns to Investments', async ({ page }) => {
  await unlock(page);
  await investmentsTab(page).click();
  await expect(page).toHaveURL(/\/investments$/);
  await page.getByRole('button', { name: /StartDepot/ }).click();
  await expect(page).toHaveURL(/\/investments\/startdepot$/);
  await page.getByRole('button', { name: 'Back' }).click();
  await expect(page).toHaveURL(/\/investments$/);
});

test('Investments tab on StartDepot goes to Investments; savings plan shows toast', async ({ page }) => {
  await openStartDepotFromOverview(page);
  await page.getByRole('button', { name: 'Set up savings plan' }).click();
  await expect(page.getByText('Not available in this demo.')).toBeVisible();
  await investmentsTab(page).click();
  await expect(page).toHaveURL(/\/investments$/);
  await expect(page.getByRole('button', { name: /StartDepot/ })).toContainText('€0.00');
});

test('browser back returns to the previous shell screen', async ({ page }) => {
  await openStartDepotFromOverview(page);
  await page.goBack();
  await expect(page).toHaveURL(/\/overview$/);
  await page.getByRole('navigation', { name: 'Main' }).getByRole('button', { name: 'Payments' }).click();
  await expect(page).toHaveURL(/\/payments$/);
  await page.goBack();
  await expect(page).toHaveURL(/\/overview$/);
});

const leaveText = 'Leave the quest? You can continue where you left off.';

test('Overview Start opens the quest without shell chrome; close dialog Stay and Leave work', async ({ page }) => {
  await unlock(page);
  await page.getByRole('button', { name: 'Start', exact: true }).click();
  await expect(page).toHaveURL(/\/quest\/hero\/new$/);
  await expect(page.getByRole('heading', { name: 'Create your hero' })).toBeVisible();
  await expect(page.getByRole('navigation')).toHaveCount(0);
  await page.getByRole('button', { name: 'Close quest' }).click();
  await expect(page.getByText(leaveText)).toBeVisible();
  await expect(page.getByRole('button', { name: 'Leave' })).toBeVisible();
  await page.getByRole('button', { name: 'Stay' }).click();
  await expect(page.getByText(leaveText)).toHaveCount(0);
  await expect(page).toHaveURL(/\/quest\/hero\/new$/);
  await page.getByRole('button', { name: 'Close quest' }).click();
  await page.getByRole('button', { name: 'Leave' }).click();
  await expect(page).toHaveURL(/\/overview$/);
  await expect(tabBar(page)).toBeVisible();
});

test('StartDepot quest entry: browser back shows the leave dialog, Leave returns to StartDepot', async ({ page }) => {
  await openStartDepotFromOverview(page);
  await page.getByRole('button', { name: 'Start your first quest' }).click();
  await expect(page).toHaveURL(/\/quest\/hero\/new$/);
  await expect(page.getByRole('heading', { name: 'Create your hero' })).toBeVisible();
  // The router registers its blocker in an effect after the first paint; let two frames pass before going back.
  await page.evaluate('new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)))');
  await page.goBack();
  await expect(page.getByText(leaveText)).toBeVisible();
  await page.getByRole('button', { name: 'Leave' }).click();
  await expect(page).toHaveURL(/\/investments\/startdepot$/);
  await expect(page.getByRole('button', { name: 'Continue' })).toBeVisible();
});

async function leaveQuest(page: Page): Promise<void> {
  await expect(page.getByRole('heading', { name: 'Create your hero' })).toBeVisible();
  await page.getByRole('button', { name: 'Close quest' }).click();
  await page.getByRole('button', { name: 'Leave' }).click();
  await expect(page).toHaveURL(/\/overview$/);
}

test('unfinished quest: Overview and StartDepot cards show Continue, balances unchanged', async ({ page }) => {
  await unlock(page);
  await page.getByRole('button', { name: 'Start', exact: true }).click();
  await leaveQuest(page);
  await expect(page.getByText('Quest in progress')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Start', exact: true })).toHaveCount(0);
  await page.getByRole('button', { name: /StartDepot/ }).click();
  await expect(page).toHaveURL(/\/investments\/startdepot$/);
  await expect(page.getByRole('main').getByText('€0.00')).toBeVisible();
  await expect(page.getByText("You don't have any investments yet.")).toBeVisible();
  await expect(page.getByText('Quest in progress')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Start your first quest' })).toHaveCount(0);
  await page.getByRole('button', { name: 'Continue' }).click();
  await expect(page).toHaveURL(/\/quest\/hero\/new$/);
  await expect(page.getByRole('heading', { name: 'Create your hero' })).toBeVisible();
});

test('unfinished quest survives a reload; corrupt storage falls back to Start', async ({ page }) => {
  const errors: string[] = [];
  page.on('pageerror', (e) => errors.push(e.message));
  await unlock(page);
  await page.getByRole('button', { name: 'Start', exact: true }).click();
  await leaveQuest(page);
  await page.reload();
  await unlock(page);
  await expect(page.getByText('Quest in progress')).toBeVisible();
  await page.getByRole('button', { name: 'Continue' }).click();
  await expect(page.getByRole('heading', { name: 'Create your hero' })).toBeVisible();
  await leaveQuest(page);
  await page.evaluate("localStorage.setItem('fq.quest.v2', '{bad')");
  await page.reload();
  await unlock(page);
  await expect(page.getByRole('button', { name: 'Start', exact: true })).toBeVisible();
  await expect(page.getByText('Quest in progress')).toHaveCount(0);
  expect(errors).toEqual([]);
});

test('new player: hero creation, interests, disclosure note, then play', async ({ page }) => {
  await unlock(page);
  await page.getByRole('button', { name: 'Start', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Begin' })).toBeDisabled();
  await page.getByRole('radio', { name: /Analyst/ }).click();
  await page.getByRole('button', { name: 'Begin' }).click();
  await expect(page).toHaveURL(/\/quest\/interests$/);
  await expect(page.getByRole('button', { name: 'Find my quest' })).toBeDisabled();
  await page.getByRole('button', { name: 'Tech' }).click();
  await page.getByRole('button', { name: 'Find my quest' }).click();
  await page.getByRole('button', { name: 'Got it' }).click();
  await expect(page).toHaveURL(/\/quest\/play$/);
  await expect(page.getByRole('navigation', { name: 'Quest dock' })).toBeVisible();
});
