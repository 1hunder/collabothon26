import { test, expect, type Locator, type Page, type Browser } from '@playwright/test';

// Acceptance suite for the whole feature. One describe per functional requirement (2.1 - 2.10),
// one test per acceptance criterion. Every test carries the tags below.
const TAGS = ['@spec:001-commerzbank-mock-app-shell', '@regression'];
const tag = { tag: TAGS };

const TOAST = 'Not available in this demo.';
const LEAVE = 'Leave the quest? You can continue where you left off.';

const tabBar = (page: Page): Locator => page.getByRole('navigation', { name: 'Main' });
const tab = (page: Page, name: string): Locator => tabBar(page).getByRole('button', { name });
const toastLoc = (page: Page): Locator => page.getByRole('status').getByRole('button');
const startBtn = (page: Page): Locator => page.getByRole('button', { name: 'Start', exact: true });

async function unlock(page: Page): Promise<void> {
  await page.goto('/');
  await page.getByRole('button', { name: 'Unlock with Face ID' }).click();
  await expect(page).toHaveURL(/\/overview$/);
}

async function box(locator: Locator): Promise<{ x: number; y: number; width: number; height: number }> {
  const b = await locator.boundingBox();
  if (b === null) throw new Error('element has no bounding box');
  return b;
}

async function leaveQuest(page: Page): Promise<void> {
  await page.getByRole('button', { name: 'Close quest' }).click();
  await page.getByRole('button', { name: 'Leave' }).click();
}

async function openStartDepotFromOverview(page: Page): Promise<void> {
  await unlock(page);
  await page.getByRole('button', { name: /StartDepot/ }).click();
  await expect(page).toHaveURL(/\/investments\/startdepot$/);
}

async function openStartDepotFromInvestments(page: Page): Promise<void> {
  await unlock(page);
  await tab(page, 'Investments').click();
  await page.getByRole('button', { name: /StartDepot/ }).click();
  await expect(page).toHaveURL(/\/investments\/startdepot$/);
}

type ScreenName = 'Overview' | 'Payments' | 'Investments' | 'Service' | 'Profile' | 'StartDepot';
const screens: ScreenName[] = ['Overview', 'Payments', 'Investments', 'Service', 'Profile', 'StartDepot'];

// Navigates client-side (no reload, so the session stays unlocked) to a shell screen.
async function goToScreen(page: Page, screen: ScreenName): Promise<void> {
  if (new URL(page.url()).pathname.startsWith('/quest')) await leaveQuest(page);
  if (screen === 'StartDepot') {
    await tab(page, 'Investments').click();
    await page.getByRole('button', { name: /StartDepot/ }).click();
    await expect(page).toHaveURL(/\/investments\/startdepot$/);
    return;
  }
  await tab(page, screen).click();
  await expect(page).toHaveURL(new RegExp(`/${screen.toLowerCase()}$`));
}

test.describe('2.1 Opening the demo', () => {
  test('2.1-AC1 Welcome shows logo, greeting and a single unlock button', tag, async ({ page }) => {
    await page.goto('/');
    await expect(page.getByRole('img', { name: 'Commerzbank' })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Welcome back, Lena' })).toBeVisible();
    await expect(page.getByRole('button')).toHaveCount(1);
    await expect(page.getByRole('button', { name: 'Unlock with Face ID' })).toBeVisible();
  });

  test('2.1-AC2 Welcome has no input fields', tag, async ({ page }) => {
    await page.goto('/');
    await expect(page.locator('input, textarea, select, [contenteditable="true"]')).toHaveCount(0);
  });

  test('2.1-AC3 Unlock plays about 1.5 s of animation, ends in a check mark, shows Overview', tag, async ({ page }) => {
    await page.goto('/');
    const t0 = Date.now();
    await page.getByRole('button', { name: 'Unlock with Face ID' }).click();
    await expect(page.getByRole('img', { name: 'Scanning face' })).toBeVisible();
    await expect(page.getByRole('img', { name: 'Face ID successful' })).toBeVisible();
    await expect(page).toHaveURL(/\/overview$/);
    const elapsed = Date.now() - t0;
    expect(elapsed).toBeGreaterThanOrEqual(1200);
    expect(elapsed).toBeLessThanOrEqual(2600);
    await expect(page.getByRole('heading', { name: 'Hello, Lena' })).toBeVisible();
  });

  test('2.1-AC4 No camera or credential API is called and no permission is requested', tag, async ({ page }) => {
    // Browser-context script kept as a string: the e2e tsconfig has no DOM lib.
    await page.addInitScript(`
      window.__calls = [];
      const rec = (n) => () => { window.__calls.push(n); return Promise.reject(new Error('blocked')); };
      if (navigator.mediaDevices) navigator.mediaDevices.getUserMedia = rec('getUserMedia');
      if (navigator.credentials) { navigator.credentials.get = rec('credentials.get'); navigator.credentials.create = rec('credentials.create'); }
      if (navigator.permissions) navigator.permissions.query = rec('permissions.query');
    `);
    const requests: string[] = [];
    page.on('dialog', (d) => requests.push(d.message()));
    await unlock(page);
    await expect(page.getByRole('heading', { name: 'Hello, Lena' })).toBeVisible();
    expect(await page.evaluate('window.__calls')).toEqual([]);
    expect(requests).toEqual([]);
  });

  test('2.1-AC5 Reloading any shell screen returns to Welcome', tag, async ({ page }) => {
    await unlock(page);
    for (const screen of screens) {
      await goToScreen(page, screen);
      await page.reload();
      await expect(page).toHaveURL(/\/$/);
      await expect(page.getByRole('heading', { name: 'Welcome back, Lena' })).toBeVisible();
      await unlock(page);
    }
  });
});

test.describe('2.2 Demo labelling', () => {
  test('2.2-AC1 No demo strip is shown', tag, async ({ page }) => {
    const strip = page.getByText('Demo — Collabothon 2026');
    await page.goto('/');
    await expect(page.getByRole('heading', { name: 'Welcome back, Lena' })).toBeVisible();
    await expect(strip).toHaveCount(0);
    await page.getByRole('button', { name: 'Unlock with Face ID' }).click();
    await expect(page).toHaveURL(/\/overview$/);
    await expect(strip).toHaveCount(0);
    // Top bar sits at the very top of the viewport (no safe-area inset in the test browser).
    expect((await box(page.getByRole('banner'))).y).toBeCloseTo(0, 0);
    await goToScreen(page, 'StartDepot');
    await expect(strip).toHaveCount(0);
    await page.getByRole('button', { name: 'Start your first quest' }).click();
    await expect(page.getByRole('heading', { name: 'What are you into?' })).toBeVisible();
    await expect(strip).toHaveCount(0);
  });
});

test.describe('2.3 Top bar', () => {
  test('2.3-AC1 Overview top bar has the logo and no back arrow', tag, async ({ page }) => {
    await unlock(page);
    const bar = page.getByRole('banner');
    await expect(bar.getByRole('img', { name: 'Commerzbank' })).toBeVisible();
    await expect(bar.getByRole('button')).toHaveCount(0);
    await expect(page.getByRole('button', { name: 'Back' })).toHaveCount(0);
  });

  test('2.3-AC2 Investments and placeholder top bars show the title and no back arrow', tag, async ({ page }) => {
    await unlock(page);
    for (const name of ['Investments', 'Payments', 'Service', 'Profile'] as const) {
      await tab(page, name).click();
      const bar = page.getByRole('banner');
      await expect(bar.getByRole('heading', { name, level: 1 })).toBeVisible();
      await expect(bar.getByRole('button')).toHaveCount(0);
      await expect(page.getByRole('button', { name: 'Back' })).toHaveCount(0);
    }
  });

  test('2.3-AC3 StartDepot top bar shows its title and a back arrow on the left', tag, async ({ page }) => {
    await openStartDepotFromOverview(page);
    const bar = page.getByRole('banner');
    await expect(bar.getByRole('heading', { name: 'StartDepot', level: 1 })).toBeVisible();
    const back = await box(bar.getByRole('button', { name: 'Back' }));
    const title = await box(bar.getByRole('heading', { name: 'StartDepot' }));
    expect(back.x).toBeLessThan(title.x);
    await expect(bar.getByRole('button')).toHaveCount(1);
  });
});

test.describe('2.4 Overview', () => {
  test('2.4-AC1 Overview shows all content in order with correct values', tag, async ({ page }) => {
    await unlock(page);
    const main = page.getByRole('main');
    const konto = page.getByRole('button', { name: /StartKonto/ });
    const depot = page.getByRole('button', { name: /StartDepot/ });
    await expect(konto).toContainText('€1,240.50');
    await expect(konto).toContainText('DE00 0000 0000 0000 0000 00');
    await expect(depot).toContainText('€0.00');
    await expect(depot).toContainText('No investments yet');
    const questSection = page.locator('section', { has: page.getByRole('heading', { name: 'Finance Quest' }) });
    await expect(questSection).toContainText('New');
    await expect(questSection).toContainText('Learn to invest with real market history — risk-free');
    await expect(questSection.getByRole('button', { name: 'Start', exact: true })).toBeVisible();
    const ys = [
      (await box(page.getByRole('heading', { name: 'Hello, Lena' }))).y,
      (await box(main.getByText('€1,240.50').first())).y,
      (await box(konto)).y,
      (await box(depot)).y,
      (await box(page.getByRole('button', { name: 'Transfer' }))).y,
      (await box(questSection)).y,
    ];
    for (let i = 1; i < ys.length; i++) expect(ys[i], `order step ${i}`).toBeGreaterThan(ys[i - 1]);
    // Total balance is the figure right below the "Total balance" label and above the cards.
    await expect(main.getByText('Total balance')).toBeVisible();
    const cardsRow = await box(konto);
    expect((await box(main.getByText('€1,240.50').first())).y).toBeLessThan(cardsRow.y);
    // Quick actions are Transfer, Cards, Postbox, left to right.
    const xs = [
      (await box(page.getByRole('button', { name: 'Transfer' }))).x,
      (await box(page.getByRole('button', { name: 'Cards' }))).x,
      (await box(page.getByRole('button', { name: 'Postbox' }))).x,
    ];
    expect(xs[0]).toBeLessThan(xs[1]);
    expect(xs[1]).toBeLessThan(xs[2]);
    // Quest card is full width and taller than either account card; accounts are white.
    const q = await box(questSection);
    expect(q.height).toBeGreaterThan((await box(konto)).height);
    expect(q.height).toBeGreaterThan((await box(depot)).height);
    expect(q.width).toBeGreaterThanOrEqual((await box(konto)).width - 1);
    await expect(konto).toHaveCSS('background-color', 'rgb(255, 255, 255)');
  });

  test('2.4-AC2 On a 360-430 px phone the quest title and Start are visible within one screen of scrolling', tag, async ({ page }) => {
    const vp = page.viewportSize();
    test.skip(vp === null || vp.width > 430, 'phone widths only');
    await unlock(page);
    await page.evaluate('window.scrollTo(0, window.innerHeight)');
    await expect(page.getByRole('heading', { name: 'Finance Quest' })).toBeInViewport({ ratio: 1 });
    await expect(startBtn(page)).toBeInViewport({ ratio: 1 });
  });

  test('2.4-AC3 Quick actions show the toast and stay on the Overview', tag, async ({ page }) => {
    await unlock(page);
    for (const name of ['Transfer', 'Cards', 'Postbox']) {
      await page.getByRole('button', { name }).click();
      await expect(toastLoc(page)).toHaveText(TOAST);
      await expect(page).toHaveURL(/\/overview$/);
    }
  });
});

test.describe('2.5 Bottom navigation', () => {
  test('2.5-AC1 Tab bar lists the five tabs in order on every shell screen', tag, async ({ page }) => {
    await unlock(page);
    for (const screen of screens) {
      await goToScreen(page, screen);
      await expect(tabBar(page).getByRole('button')).toHaveText(['Overview', 'Payments', 'Investments', 'Service', 'Profile']);
      const b = await box(tabBar(page));
      const vh = page.viewportSize()?.height ?? 0;
      expect(Math.round(b.y + b.height)).toBe(vh);
    }
  });

  test('2.5-AC2 Investments tab opens Investments and is highlighted', tag, async ({ page }) => {
    await unlock(page);
    await tab(page, 'Investments').click();
    await expect(page).toHaveURL(/\/investments$/);
    await expect(page.getByRole('banner').getByRole('heading', { name: 'Investments' })).toBeVisible();
    await expect(tab(page, 'Investments')).toHaveAttribute('aria-current', 'page');
    await expect(tabBar(page).locator('[aria-current="page"]')).toHaveCount(1);
  });

  test('2.5-AC3 Payments, Service and Profile show their title and the placeholder line', tag, async ({ page }) => {
    await unlock(page);
    for (const name of ['Payments', 'Service', 'Profile'] as const) {
      await tab(page, name).click();
      await expect(page.getByRole('heading', { name, level: 1 })).toBeVisible();
      await expect(page.getByText("This area isn't part of the demo.")).toBeVisible();
      await expect(tab(page, name)).toHaveAttribute('aria-current', 'page');
    }
  });

  test('2.5-AC4 Overview tab from any other tab opens the highlighted Overview', tag, async ({ page }) => {
    await unlock(page);
    for (const from of ['Payments', 'Investments', 'Service', 'Profile'] as const) {
      await tab(page, from).click();
      await tab(page, 'Overview').click();
      await expect(page).toHaveURL(/\/overview$/);
      await expect(page.getByRole('heading', { name: 'Hello, Lena' })).toBeVisible();
      await expect(tab(page, 'Overview')).toHaveAttribute('aria-current', 'page');
    }
  });

  test('2.5-AC5 StartDepot opened from the Overview highlights Investments', tag, async ({ page }) => {
    await openStartDepotFromOverview(page);
    await expect(tab(page, 'Investments')).toHaveAttribute('aria-current', 'page');
    await expect(tab(page, 'Overview')).not.toHaveAttribute('aria-current', 'page');
  });

  test('2.5-AC6 Investments tab on StartDepot shows the Investments screen', tag, async ({ page }) => {
    await openStartDepotFromOverview(page);
    await tab(page, 'Investments').click();
    await expect(page).toHaveURL(/\/investments$/);
    await expect(page.getByRole('banner').getByRole('heading', { name: 'Investments' })).toBeVisible();
    await expect(page.getByRole('button', { name: /StartDepot/ })).toBeVisible();
  });
});

test.describe('2.6 Investments and StartDepot', () => {
  const assertStartDepotContent = async (page: Page): Promise<void> => {
    await expect(page.getByRole('banner').getByRole('heading', { name: 'StartDepot' })).toBeVisible();
    await expect(page.getByRole('main').getByText('€0.00')).toBeVisible();
    await expect(page.getByText("You don't have any investments yet.")).toBeVisible();
    await expect(page.getByText('No custody fees up to €20,000 depot value')).toBeVisible();
    await expect(page.getByText('Savings plans from €25 a month')).toBeVisible();
    await expect(page.getByText('For pupils, students and trainees')).toBeVisible();
    await expect(page.getByRole('button', { name: 'Start your first quest' })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Set up savings plan' })).toBeVisible();
  };

  test('2.6-AC1 Overview StartDepot card opens the full StartDepot screen', tag, async ({ page }) => {
    await openStartDepotFromOverview(page);
    await assertStartDepotContent(page);
  });

  test('2.6-AC2 Investments then StartDepot entry opens the same screen', tag, async ({ page }) => {
    await unlock(page);
    await tab(page, 'Investments').click();
    await expect(page.getByRole('button', { name: /StartDepot/ })).toContainText('€0.00');
    await page.getByRole('button', { name: /StartDepot/ }).click();
    await expect(page).toHaveURL(/\/investments\/startdepot$/);
    await assertStartDepotContent(page);
  });

  test('2.6-AC3 Set up savings plan shows the toast and stays on StartDepot', tag, async ({ page }) => {
    await openStartDepotFromOverview(page);
    await page.getByRole('button', { name: 'Set up savings plan' }).click();
    await expect(toastLoc(page)).toHaveText(TOAST);
    await expect(page).toHaveURL(/\/investments\/startdepot$/);
  });

  test('2.6-AC4 Back arrow from an Overview-opened StartDepot returns to Overview', tag, async ({ page }) => {
    await openStartDepotFromOverview(page);
    await page.getByRole('button', { name: 'Back' }).click();
    await expect(page).toHaveURL(/\/overview$/);
    await expect(page.getByRole('heading', { name: 'Hello, Lena' })).toBeVisible();
  });

  test('2.6-AC5 Back arrow from an Investments-opened StartDepot returns to Investments', tag, async ({ page }) => {
    await openStartDepotFromInvestments(page);
    await page.getByRole('button', { name: 'Back' }).click();
    await expect(page).toHaveURL(/\/investments$/);
  });

  test('2.6-AC6 After leaving a quest StartDepot is unchanged and its card says Continue', tag, async ({ page }) => {
    await openStartDepotFromOverview(page);
    await page.getByRole('button', { name: 'Start your first quest' }).click();
    await expect(page.getByRole('heading', { name: 'What are you into?' })).toBeVisible();
    await leaveQuest(page);
    await expect(page).toHaveURL(/\/investments\/startdepot$/);
    await expect(page.getByRole('main').getByText('€0.00')).toBeVisible();
    await expect(page.getByText("You don't have any investments yet.")).toBeVisible();
    await expect(page.getByRole('button', { name: 'Continue' })).toBeVisible();
  });
});

test.describe('2.7 Entering and leaving Finance Quest', () => {
  test('2.7-AC1 Overview Start opens the quest without top bar or tab bar', tag, async ({ page }) => {
    await unlock(page);
    await startBtn(page).click();
    await expect(page.getByRole('heading', { name: 'What are you into?' })).toBeVisible();
    await expect(page.getByRole('banner')).toHaveCount(0);
    await expect(tabBar(page)).toHaveCount(0);
    await expect(page.getByRole('button', { name: 'Close quest' })).toBeVisible();
    const close = await box(page.getByRole('button', { name: 'Close quest' }));
    expect(close.x + close.width / 2).toBeGreaterThan(((page.viewportSize()?.width ?? 0) >= 430 ? 430 : (page.viewportSize()?.width ?? 0)) / 2);
  });

  test('2.7-AC2 StartDepot Start your first quest opens What are you into?', tag, async ({ page }) => {
    await openStartDepotFromOverview(page);
    await page.getByRole('button', { name: 'Start your first quest' }).click();
    await expect(page.getByRole('heading', { name: 'What are you into?' })).toBeVisible();
  });

  test('2.7-AC3 Close shows the leave confirmation with Leave and Stay', tag, async ({ page }) => {
    await unlock(page);
    await startBtn(page).click();
    await page.getByRole('button', { name: 'Close quest' }).click();
    const dlg = page.getByRole('dialog');
    await expect(dlg).toContainText(LEAVE);
    await expect(dlg.getByRole('button')).toHaveText(['Leave', 'Stay']);
  });

  test('2.7-AC4 Browser back inside the quest shows the same confirmation', tag, async ({ page }) => {
    await unlock(page);
    await startBtn(page).click();
    await expect(page.getByRole('heading', { name: 'What are you into?' })).toBeVisible();
    // The router registers its blocker after first paint; let two frames pass before going back.
    await page.evaluate('new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)))');
    await page.goBack();
    await expect(page.getByRole('dialog')).toContainText(LEAVE);
  });

  test('2.7-AC5 Leave returns to the origin with the chrome visible again', tag, async ({ page }) => {
    await unlock(page);
    await tab(page, 'Investments').click();
    await page.getByRole('button', { name: /StartDepot/ }).click();
    await page.getByRole('button', { name: 'Start your first quest' }).click();
    await leaveQuest(page);
    await expect(page).toHaveURL(/\/investments\/startdepot$/);
    await expect(page.getByRole('banner')).toBeVisible();
    await expect(tabBar(page)).toBeVisible();
  });

  test('2.7-AC6 Stay closes the dialog and keeps the same quest screen', tag, async ({ page }) => {
    await unlock(page);
    await startBtn(page).click();
    await page.getByRole('button', { name: 'Close quest' }).click();
    await page.getByRole('button', { name: 'Stay' }).click();
    await expect(page.getByRole('dialog')).toHaveCount(0);
    await expect(page).toHaveURL(/\/quest$/);
    await expect(page.getByRole('heading', { name: 'What are you into?' })).toBeVisible();
  });

  test('2.7-AC7 After leaving unfinished the Overview card shows Quest in progress and Continue', tag, async ({ page }) => {
    await unlock(page);
    await startBtn(page).click();
    await leaveQuest(page);
    await expect(page).toHaveURL(/\/overview$/);
    await expect(page.getByText('Quest in progress')).toBeVisible();
    await expect(page.getByRole('button', { name: 'Continue' })).toBeVisible();
    await expect(startBtn(page)).toHaveCount(0);
  });

  test('2.7-AC8 Continue reopens the last quest screen', tag, async ({ page }) => {
    await unlock(page);
    await startBtn(page).click();
    await leaveQuest(page);
    await page.getByRole('button', { name: 'Continue' }).click();
    await expect(page).toHaveURL(/\/quest$/);
    await expect(page.getByRole('heading', { name: 'What are you into?' })).toBeVisible();
  });

  test('2.7-AC9 Unfinished quest survives reload and unlock', tag, async ({ page }) => {
    await unlock(page);
    await startBtn(page).click();
    await leaveQuest(page);
    await page.reload();
    await unlock(page);
    await expect(page.getByText('Quest in progress')).toBeVisible();
    await expect(page.getByRole('button', { name: 'Continue' })).toBeVisible();
  });
});

test.describe('2.8 Unavailable features', () => {
  test('2.8-AC1 StartKonto card and quick actions show the message and keep the screen', tag, async ({ page }) => {
    await unlock(page);
    for (const l of [page.getByRole('button', { name: /StartKonto/ }), page.getByRole('button', { name: 'Cards' })]) {
      await l.click();
      await expect(toastLoc(page)).toHaveText(TOAST);
      await expect(page).toHaveURL(/\/overview$/);
      await toastLoc(page).click();
    }
  });

  test('2.8-AC2 Message disappears after 3 s and when tapped', tag, async ({ page }) => {
    await unlock(page);
    await page.getByRole('button', { name: 'Transfer' }).click();
    await expect(toastLoc(page)).toBeVisible();
    const t0 = Date.now();
    await expect(toastLoc(page)).toHaveCount(0, { timeout: 5000 });
    const gone = Date.now() - t0;
    expect(gone).toBeGreaterThanOrEqual(2000);
    expect(gone).toBeLessThanOrEqual(3600);
    await page.getByRole('button', { name: 'Transfer' }).click();
    await toastLoc(page).click();
    await expect(toastLoc(page)).toHaveCount(0);
  });

  test('2.8-AC3 Two quick taps leave exactly one message and restart the timer', tag, async ({ page }) => {
    await unlock(page);
    await page.getByRole('button', { name: 'Transfer' }).click();
    await page.waitForTimeout(2000);
    await page.getByRole('button', { name: 'Postbox' }).click();
    await expect(page.getByText(TOAST)).toHaveCount(1);
    // 1.5 s later the first toast's 3 s would have elapsed; the restarted one must still be showing.
    await page.waitForTimeout(1500);
    await expect(page.getByText(TOAST)).toHaveCount(1);
    await expect(page.getByRole('status')).toHaveCount(1);
    await expect(toastLoc(page)).toHaveCount(0, { timeout: 4000 });
  });

  test('2.8-AC4 Tap sweep: every tappable element navigates or shows the message', tag, async ({ page }) => {
    test.setTimeout(180_000);
    await unlock(page);
    // Zero real links exist, so an <a> could never silently do nothing.
    await expect(page.locator('a[href]')).toHaveCount(0);
    const selector = 'button, a[href], [role="button"], [role="link"], [role="tab"]';
    const report: string[] = [];
    for (const screen of screens) {
      await goToScreen(page, screen);
      const targets = page.locator(selector).filter({ hasNot: page.locator('[role="status"] button') });
      const labels = (await targets.allInnerTexts()).map((t, i) => t.trim() || `#${i}`);
      const n = labels.length;
      expect(n, `buttons on ${screen}`).toBeGreaterThan(4);
      for (let i = 0; i < n; i++) {
        await goToScreen(page, screen);
        if ((await toastLoc(page).count()) > 0) await toastLoc(page).click();
        await expect(toastLoc(page)).toHaveCount(0);
        const target = page.locator(selector).filter({ hasNot: page.locator('[role="status"] button') }).nth(i);
        const before = page.url();
        const label = (await target.innerText()).trim() || (await target.getAttribute('aria-label')) || `#${i}`;
        const isActiveTab = (await target.getAttribute('aria-current')) === 'page';
        await target.click();
        const navigated = await expect
          .poll(async () => page.url() !== before || (await toastLoc(page).count()) > 0, { timeout: 2000 })
          .toBe(true)
          .then(() => true, () => false);
        // Tapping the highlighted tab re-opens that tab's main screen, which is a valid outcome.
        const ok = navigated || isActiveTab;
        report.push(`${screen} / ${label}: ${navigated ? 'ok' : isActiveTab ? 'active-tab' : 'NOTHING'}`);
        expect(ok, `${screen} / "${label}" did nothing`).toBe(true);
      }
    }
    expect(report.length).toBeGreaterThan(20);
  });
});

test.describe('2.9 Look and feel', () => {
  test('2.9-AC1 Colours, rounded cards and pill buttons on the Overview and Welcome', tag, async ({ page }) => {
    await page.goto('/');
    const unlockBtn = page.getByRole('button', { name: 'Unlock with Face ID' });
    await expect(unlockBtn).toHaveCSS('background-color', 'rgb(0, 46, 60)');
    const ub = await box(unlockBtn);
    const ur = parseFloat(await unlockBtn.evaluate((el) => (globalThis as unknown as { getComputedStyle(e: unknown): { borderTopLeftRadius: string } }).getComputedStyle(el).borderTopLeftRadius));
    expect(ur).toBeGreaterThanOrEqual(ub.height / 2);
    await unlockBtn.click();
    await expect(page).toHaveURL(/\/overview$/);
    const quest = page.locator('section', { has: page.getByRole('heading', { name: 'Finance Quest' }) });
    await expect(quest).toHaveCSS('background-color', 'rgb(255, 215, 0)');
    await expect(quest).toHaveCSS('border-radius', '16px');
    await expect(page.getByRole('heading', { name: 'Hello, Lena' })).toHaveCSS('color', 'rgb(0, 46, 60)');
    await expect(page.locator('body')).toHaveCSS('background-color', 'rgb(241, 239, 237)');
    await expect(page.getByRole('button', { name: /StartKonto/ })).toHaveCSS('border-radius', '16px');
    await expect(page.getByRole('button', { name: /StartDepot/ })).toHaveCSS('border-radius', '16px');
    const start = startBtn(page);
    await expect(start).toHaveCSS('background-color', 'rgb(0, 46, 60)');
    const sb = await box(start);
    const sr = parseFloat(await start.evaluate((el) => (globalThis as unknown as { getComputedStyle(e: unknown): { borderTopLeftRadius: string } }).getComputedStyle(el).borderTopLeftRadius));
    expect(sr).toBeGreaterThanOrEqual(sb.height / 2);
  });

  test('2.9-AC2 No horizontal scrolling or cut-off text on any shell screen', tag, async ({ page }) => {
    const vp = page.viewportSize();
    test.skip(vp === null || vp.width > 430, 'phone widths only');
    await page.goto('/');
    const check = async (): Promise<void> => {
      const [sw, iw] = (await page.evaluate('[document.documentElement.scrollWidth, window.innerWidth]')) as [number, number];
      expect(sw).toBeLessThanOrEqual(iw);
      // No visible text element may extend beyond the right viewport edge.
      const clipped = await page.evaluate(`Array.from(document.querySelectorAll('main *, header *, nav *')).filter((e) => e.children.length === 0 && e.textContent.trim() && e.getBoundingClientRect().right > window.innerWidth + 0.5).map((e) => e.textContent.trim())`);
      expect(clipped).toEqual([]);
      const truncated = await page.evaluate(`Array.from(document.querySelectorAll('main *, header *, nav *')).filter((e) => e.children.length === 0 && e.textContent.trim() && !e.classList.contains('sr-only') && e.scrollWidth > e.clientWidth + 1 && getComputedStyle(e).display !== 'inline').map((e) => e.textContent.trim())`);
      expect(truncated).toEqual([]);
    };
    await check();
    await unlock(page);
    for (const screen of screens) {
      await goToScreen(page, screen);
      await check();
    }
    await goToScreen(page, 'Overview');
    await page.getByRole('button', { name: 'Start', exact: true }).click();
    await check();
  });

  test('2.9-AC3 On a wide window the shell is a centred column of at most 430 px', tag, async ({ page }) => {
    const vp = page.viewportSize();
    test.skip(vp === null || vp.width <= 1000, 'wide window only');
    await unlock(page);
    const w = vp?.width ?? 0;
    for (const l of [tabBar(page), page.getByRole('banner')]) {
      const b = await box(l);
      expect(b.width).toBeLessThanOrEqual(430);
      expect(Math.abs(b.x + b.width / 2 - w / 2)).toBeLessThanOrEqual(1);
    }
    const q = await box(page.getByRole('button', { name: /StartKonto/ }));
    expect(q.x).toBeGreaterThan((w - 430) / 2 - 1);
    expect(q.x + q.width).toBeLessThan((w + 430) / 2 + 1);
  });

  test('2.9-AC4 All text is English apart from the product names', tag, async ({ page }) => {
    await page.goto('/');
    const german = /[äöüß]|\b(Willkommen|Überweisung|Karten|Konto(?!\b)|Depot(?!\b)|Zurück|Einstellungen|Hilfe|Entsperren|Sparplan|Gebühren|Nicht verfügbar|Hallo|Startseite|Zahlungen)\b/i;
    const texts: string[] = [];
    texts.push(await page.locator('body').innerText());
    await unlock(page);
    for (const screen of screens) {
      await goToScreen(page, screen);
      texts.push(await page.locator('body').innerText());
    }
    await goToScreen(page, 'Overview');
    await page.getByRole('button', { name: 'Transfer' }).click();
    texts.push(await page.locator('body').innerText());
    await page.getByRole('button', { name: 'Start', exact: true }).click();
    await page.getByRole('button', { name: 'Close quest' }).click();
    texts.push(await page.locator('body').innerText());
    const lang = await page.evaluate('document.documentElement.lang');
    expect(lang).toBe('en');
    for (const t of texts) {
      const stripped = t.replace(/StartDepot|StartKonto|Commerzbank/g, '');
      expect(stripped).not.toMatch(german);
    }
  });
});

test.describe('2.10 Fictional data only', () => {
  async function overviewFacts(browser: Browser, baseURL: string): Promise<string> {
    const ctx = await browser.newContext({ viewport: { width: 390, height: 844 }, baseURL });
    const p = await ctx.newPage();
    await unlock(p);
    const text = await p.getByRole('main').innerText();
    await ctx.close();
    return text;
  }

  test('2.10-AC1 Two separate visitors see the same persona, balances and account number', tag, async ({ browser, baseURL }) => {
    const a = await overviewFacts(browser, baseURL ?? '');
    const b = await overviewFacts(browser, baseURL ?? '');
    expect(a).toBe(b);
    expect(a).toContain('Hello, Lena');
    expect(a).toContain('€1,240.50');
    expect(a).toContain('DE00 0000 0000 0000 0000 00');
  });

  test('2.10-AC2 StartKonto card shows the fake account number; no age and no transactions anywhere', tag, async ({ page }) => {
    await unlock(page);
    await expect(page.getByRole('button', { name: /StartKonto/ })).toContainText('DE00 0000 0000 0000 0000 00');
    for (const screen of screens) {
      await goToScreen(page, screen);
      const text = await page.locator('body').innerText();
      expect(text, screen).not.toMatch(/\b16\b/);
      expect(text, screen).not.toMatch(/transaction|umsatz|IBAN\s*DE[0-9]{2}\s?[1-9]/i);
    }
  });
});
