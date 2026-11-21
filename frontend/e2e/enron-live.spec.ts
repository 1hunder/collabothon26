import { test, expect, type Page } from '@playwright/test';

// Full Enron campaign against a live backend (FAKE_LLM=1, Enron reference pack approved).
// Run: E2E_LIVE_API=1 E2E_BASE_URL=http://localhost:4174 npx playwright test e2e/enron-live.spec.ts --project=chromium-430x932
// The page must be served by a build made with VITE_API_MODE=live and VITE_API_BASE_URL=<backend>.
// Skipped unless E2E_LIVE_API is set. The Playwright webServer (fixture mode) is not used for it.
test.skip(!process.env.E2E_LIVE_API, 'set E2E_LIVE_API to run against the live backend');
test.use({ baseURL: process.env.E2E_BASE_URL ?? 'http://localhost:4174' });
test.setTimeout(120_000);

const hasText = (page: Page, re: RegExp) => page.getByText(re).first();

/** Advance dialogue, dice and news until the "I'm ready to decide" choice is offered. */
async function playUntilReady(page: Page, opts: { needNews: boolean }): Promise<void> {
  let sawNews = false;
  for (let step = 0; step < 250; step++) {
    const decide = page.getByRole('button', { name: "I'm ready to decide" });
    if ((await decide.count()) > 0 && (!opts.needNews || sawNews)) return;

    if ((await page.getByRole('article', { name: 'Breaking news' }).count()) > 0) {
      sawNews = true;
      await page.getByRole('button', { name: 'Continue' }).click();
      continue;
    }
    const dice = page.getByRole('dialog', { name: 'Dice check' });
    if ((await dice.count()) > 0) {
      const roll = dice.getByRole('button', { name: 'Roll', exact: true });
      if ((await roll.count()) > 0) await roll.click();
      const cont = dice.getByRole('button', { name: 'Continue' });
      const accept = dice.getByRole('button', { name: 'Accept setback' });
      await expect(cont.or(accept)).toBeVisible({ timeout: 10_000 });
      if ((await accept.count()) > 0) await accept.click();
      else await cont.click();
      await expect(dice).toBeHidden({ timeout: 10_000 });
      continue;
    }
    const title = page.getByTestId('title-card');
    if ((await title.count()) > 0) {
      await title.click();
      continue;
    }
    const choices = page.getByRole('region', { name: 'Choices' });
    if ((await choices.count()) > 0) {
      // Prefer a suggestion that is not the Buddy/hint/decide controls.
      const first = choices.getByRole('button').first();
      await first.click();
      await page.waitForTimeout(400);
      continue;
    }
    const box = page.getByTestId('dialogue-box');
    if ((await box.count()) > 0) {
      await box.click();
      await page.waitForTimeout(150);
      continue;
    }
    await page.waitForTimeout(300);
  }
  throw new Error(`never reached the decision (news seen: ${sawNews})`);
}

async function openMapAndGo(page: Page, name: string): Promise<void> {
  await page.getByRole('button', { name: 'Map' }).click();
  await page.getByRole('dialog', { name: 'The map' }).getByRole('button', { name: new RegExp(name, 'i') }).click();
}

async function finishReading(page: Page): Promise<void> {
  for (let i = 0; i < 30; i++) {
    if ((await page.getByRole('region', { name: 'Choices' }).count()) > 0) return;
    const title = page.getByTestId('title-card');
    if ((await title.count()) > 0) await title.click();
    const box = page.getByTestId('dialogue-box');
    if ((await box.count()) > 0) await box.click();
    await page.waitForTimeout(150);
  }
  throw new Error('choices never appeared');
}

test('Enron campaign: hero to reveal to finish, all figures from the server', async ({ page }) => {
  const pageErrors: string[] = [];
  page.on('pageerror', (e) => pageErrors.push(e.message));

  await page.goto('/');
  await page.getByRole('button', { name: 'Unlock with Face ID' }).click();
  await expect(page).toHaveURL(/\/overview$/);
  await page.getByRole('button', { name: /StartDepot/ }).click();
  await page.getByRole('button', { name: /^Start/ }).click();

  // Hero + interests + disclosure
  await expect(page.getByRole('heading', { name: 'Create your hero' })).toBeVisible();
  await page.getByLabel('Name').fill('Tester');
  await page.getByRole('radio', { name: /Analyst/ }).click();
  await page.getByRole('button', { name: 'Begin' }).click();
  await expect(page.getByRole('heading', { name: 'What are you into?' })).toBeVisible();
  await page.getByRole('button', { name: 'Tech' }).click();
  await page.getByRole('button', { name: 'Find my quest' }).click();
  await expect(hasText(page, /real market history/)).toBeVisible();
  await page.getByRole('button', { name: 'Got it' }).click();

  // Tavern briefing: the first page of the Campaign Master's opening
  await expect(page).toHaveURL(/\/quest\/play$/);
  await expect(page.getByTestId('dialogue-box')).toBeVisible({ timeout: 30_000 });
  await finishReading(page);

  // Market Square: price board
  await openMapAndGo(page, 'Market Square');
  await finishReading(page);
  await page.getByRole('button', { name: 'Price board' }).click();
  await expect(page.getByRole('dialog', { name: 'Market stall' })).toBeVisible();
  await page.getByRole('dialog', { name: 'Market stall' }).getByRole('button', { name: /^Close/ }).click();

  // Library: documents
  await openMapAndGo(page, 'Library');
  await finishReading(page);
  await page.getByRole('button', { name: 'Library documents' }).click();
  await expect(page.getByRole('region', { name: 'Company card' })).toBeVisible();
  await page.getByRole('dialog', { name: 'Library' }).getByRole('button', { name: /^Close/ }).click();

  // Buddy
  await page.getByRole('button', { name: 'Buddy' }).click();
  await page.getByLabel('Your question for CommerzBuddy').fill('What is a share price?');
  await page.getByRole('button', { name: 'Ask', exact: true }).click();
  await expect(page.getByTestId('name-tab').filter({ hasText: 'CommerzBuddy' })).toBeVisible();
  await expect(page.getByTestId('dialogue-box')).toBeVisible({ timeout: 30_000 });
  await page.getByRole('button', { name: 'Close Buddy' }).click();

  // Dice check(s) and moves until the news card, then ready to decide
  await finishReading(page);
  await playUntilReady(page, { needNews: true });

  // Decide: seal
  await page.getByRole('button', { name: "I'm ready to decide" }).click();
  await expect(page).toHaveURL(/\/quest\/commit$/);
  await expect(page.getByRole('heading', { name: 'Seal your decision' })).toBeVisible();

  // Back to investigating (resume-play) and decide again
  await page.getByRole('button', { name: 'Back to investigating' }).click();
  await expect(page).toHaveURL(/\/quest\/play$/);
  // The server phase went back to play (POST resume-play), so a reload would not reopen the commit screen.
  const api = process.env.E2E_API_BASE_URL ?? 'http://localhost:8017';
  const phase = await page.evaluate(async (base) => {
    const headers = { 'X-Session-Id': localStorage.getItem('fq.session.v1') ?? '' };
    const hero = (await (await fetch(`${base}/hero`, { headers })).json()) as { active_campaign_id: string };
    const c = (await (await fetch(`${base}/campaigns/${hero.active_campaign_id}`, { headers })).json()) as { phase: string };
    return c.phase;
  }, api);
  expect(phase).toBe('play');
  await finishReading(page);
  await page.getByRole('button', { name: "I'm ready to decide" }).click();
  await expect(page).toHaveURL(/\/quest\/commit$/);

  await page.getByRole('radio', { name: /^Invest$/ }).click();
  await page.getByLabel('Amount in euros').fill('400');
  await page.getByLabel(/Evidence/).fill('Revenue grows but the debt keeps rising, so I only risk a part of my budget.');
  await page.getByRole('radio', { name: 'Medium' }).click();
  await page.getByRole('button', { name: 'Lock my decision' }).click();
  await page.getByRole('button', { name: 'Lock', exact: true }).click();
  await expect(hasText(page, /days later/)).toBeVisible({ timeout: 15_000 });

  // Outcome: € and HP from the server
  await expect(page.getByRole('heading', { name: 'The outcome' })).toBeVisible({ timeout: 15_000 });
  await expect(page.getByText('Final value')).toBeVisible();
  await expect(page.getByText(/\d+ HP → \d+ HP/)).toBeVisible();

  // Debrief + what-if
  await page.getByRole('button', { name: 'See the debrief' }).click();
  await expect(page.getByRole('heading', { name: 'Debrief' })).toBeVisible({ timeout: 30_000 });
  await expect(page.getByText(/What if/i).first()).toBeVisible();
  await expect(page.getByText('Enron')).toHaveCount(0);
  await page.getByRole('button', { name: 'Reflect' }).click();

  // Reflection, then the company reveal
  await page.locator('#reflection').fill('Next time I would check the debt and cash flow before investing anything.');
  await page.getByRole('button', { name: 'Submit reflection' }).click();
  await expect(page.getByRole('heading', { name: /Enron/ })).toBeVisible({ timeout: 15_000 });

  // XP and finish
  await page.getByRole('button', { name: 'Continue to XP' }).click();
  await expect(page.getByRole('heading', { name: 'Your XP' })).toBeVisible({ timeout: 30_000 });
  await expect(page.getByText(/Total \d+ \/ 100/)).toBeVisible();
  await page.getByRole('button', { name: 'Finish quest' }).click();
  await expect(page.getByText(/Total XP:/)).toBeVisible();
  await page.getByRole('button', { name: 'Back to the bank' }).click();

  // Back in the bank app: a new quest can start
  await expect(page).toHaveURL(/\/overview$/);
  await expect(page.getByRole('button', { name: 'Start', exact: true })).toBeVisible();
  await expect(page.getByText('Quest in progress')).toHaveCount(0);
  expect(pageErrors).toEqual([]);
});
