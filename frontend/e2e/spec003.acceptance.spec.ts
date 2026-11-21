import { test, expect, type Page } from '@playwright/test';

// Acceptance flows for spec 003 (campaign engine), fixture mode (no backend, fictional company).
// Rules and maths are asserted in backend/tests/test_acceptance_003.py, component behaviour in
// src/quest/__acceptance__/spec003.acceptance.test.tsx. Here: whole user flows in a real browser.
const tag = { tag: ['@spec:003-campaign-engine', '@regression'] };
test.setTimeout(90_000);

async function unlock(page: Page): Promise<void> {
  await page.goto('/');
  await page.getByRole('button', { name: 'Unlock with Face ID' }).click();
  await expect(page).toHaveURL(/\/overview$/);
}

async function newHero(page: Page, cls: RegExp, name = 'Lena'): Promise<void> {
  await unlock(page);
  await page.getByRole('button', { name: 'Start', exact: true }).click();
  await page.getByLabel('Name').fill(name);
  await page.getByRole('radio', { name: cls }).click();
  await page.getByRole('button', { name: 'Begin' }).click();
  await page.getByRole('button', { name: 'Got it' }).click();
  await expect(page).toHaveURL(/\/quest\/play$/);
}

async function readUntilChoices(page: Page): Promise<void> {
  for (let i = 0; i < 60; i++) {
    if ((await page.getByRole('region', { name: 'Choices' }).count()) > 0) return;
    if ((await page.getByRole('dialog', { name: 'Dice check' }).count()) > 0) return;
    if ((await page.getByRole('article', { name: 'Breaking news' }).count()) > 0) return;
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

async function typeAction(page: Page, text: string): Promise<void> {
  await page.getByRole('button', { name: 'Write your own action…' }).click();
  await page.getByRole('textbox').fill(text);
  await page.getByRole('button', { name: 'Send' }).click();
  await readUntilChoices(page);
}

const dice = (page: Page) => page.getByRole('dialog', { name: 'Dice check' });

test.describe('spec 003 user flows', () => {
  test('E2E-FLOW hero, quest, investigation, dice, news, commit, reveal, debrief, XP, finish', tag, async ({ page }) => {
    const errors: string[] = [];
    page.on('pageerror', (e) => errors.push(e.message));
    await newHero(page, /Guardian/, 'Mira');
    await readUntilChoices(page);
    await expect(page.getByRole('button', { name: 'Hero status' })).toContainText('120 HP · €1,200');

    await goTo(page, 'Library');
    await typeAction(page, 'check the ledger for an odd figure');
    await expect(dice(page)).toBeVisible();
    await expect(dice(page)).toContainText('Difficulty 12');
    await dice(page).getByRole('button', { name: 'Roll', exact: true }).click();
    await expect(dice(page).getByTestId('dice-verdict')).toContainText('Success');
    await dice(page).getByRole('button', { name: 'Continue' }).click();
    await readUntilChoices(page);
    await goTo(page, 'Market Square'); // third turn at the Square: the news fires
    const news = page.getByRole('article', { name: 'Breaking news' });
    for (let i = 0; i < 20 && (await news.count()) === 0; i++) {
      await readUntilChoices(page);
      if ((await news.count()) === 0) await page.waitForTimeout(150);
    }
    await expect(news).toBeVisible();
    await news.getByRole('button', { name: 'Continue' }).click();
    await readUntilChoices(page);
    await page.getByRole('button', { name: "I'm ready to decide" }).click();

    await expect(page).toHaveURL(/\/quest\/commit$/);
    await page.getByRole('radio', { name: 'Invest', exact: true }).click();
    await page.getByLabel('Amount in euros').fill('1201');
    await expect(page.getByText('Enter an amount from €1 to €1,200.')).toBeVisible();
    await page.getByLabel('Amount in euros').fill('400');
    await page.getByLabel(/Evidence/).fill('too short');
    await expect(page.getByText('Explain your reasoning in at least 20 characters.')).toBeVisible();
    await expect(page.getByRole('button', { name: 'Lock my decision' })).toBeDisabled();
    await page.getByLabel(/Evidence/).fill('Debt is rising while cash flow is weak.');
    await page.getByRole('radio', { name: 'Medium' }).click();
    await page.getByRole('button', { name: 'Lock my decision' }).click();
    await expect(page.getByText("Once locked, you can't change it. Lock?")).toBeVisible();
    await page.getByRole('button', { name: 'Lock', exact: true }).click();
    await page.getByText('75 days later…').click({ timeout: 8000 });

    await expect(page.getByText(/Locked at .* · horizon/)).toBeVisible();
    await expect(page.getByText(/→ \d+ HP/)).toBeVisible();
    await page.getByRole('button', { name: 'See the debrief' }).click();
    for (const h of ['Sound reasoning', 'Overlooked', 'Luck', 'What if…']) await expect(page.getByRole('heading', { name: h })).toBeVisible();
    await expect(page.getByText(/Example Lantern/)).toHaveCount(0); // not before the reflection
    await page.getByRole('button', { name: 'Reflect' }).click();
    await expect(page.getByRole('button', { name: 'Submit reflection' })).toBeDisabled();
    await page.getByRole('textbox').fill('I would check the cash flow first.');
    await page.getByRole('button', { name: 'Submit reflection' }).click();
    await expect(page.getByRole('heading', { name: 'Example Lantern Co.' })).toBeVisible();
    await page.getByRole('button', { name: 'Continue to XP' }).click();
    await expect(page.getByText(/Total \d+ \/ 100/)).toBeVisible();
    await page.getByRole('button', { name: 'Finish quest' }).click();
    await expect(page.getByText(/Total XP: \d+/)).toBeVisible();
    await page.getByRole('button', { name: 'Back to the bank' }).click();
    await expect(page).toHaveURL(/\/overview$/);
    await expect(page.getByRole('button', { name: 'Start', exact: true })).toBeVisible();
    expect(errors).toEqual([]);
  });

  test('2.15-AC1 leave mid-investigation then Continue; 2.8-AC5 same backlog after a reload', tag, async ({ page }) => {
    await newHero(page, /Analyst/);
    await readUntilChoices(page);
    await goTo(page, 'Library');
    await page.getByRole('button', { name: 'Close quest' }).click();
    await page.getByRole('button', { name: 'Leave' }).click();
    await expect(page.getByText('Quest in progress')).toBeVisible();
    await page.reload();
    await unlock(page);
    await page.getByRole('button', { name: 'Continue' }).click();
    await expect(page).toHaveURL(/\/quest\/play$/);
    await expect(page.getByRole('button', { name: 'Hero status' })).toContainText('Rerolls: 1');
    await readUntilChoices(page);
    await page.getByRole('button', { name: 'Journal' }).click();
    await page.getByRole('button', { name: 'Open the backlog' }).click();
    await expect(page.getByRole('dialog', { name: 'Backlog' })).toContainText('Library');
  });

  test('2.5-AC9/AC10 Analyst setback offers Second Look and Accept; Second Look rerolls', tag, async ({ page }) => {
    await newHero(page, /Analyst/);
    await readUntilChoices(page);
    await typeAction(page, 'check the ledger for an odd figure');
    await dice(page).getByRole('button', { name: 'Roll', exact: true }).click();
    await expect(dice(page).getByTestId('dice-verdict')).toContainText('Setback');
    await expect(dice(page).getByRole('button', { name: 'Accept setback' })).toBeVisible();
    await dice(page).getByRole('button', { name: /Second Look — reroll \(1 left\)/ }).click();
    await expect(dice(page).getByTestId('dice-sum')).toContainText('17 + 2 = 19');
    await dice(page).getByRole('button', { name: 'Continue' }).click();
    await expect(page.getByRole('button', { name: 'Hero status' })).toContainText('Rerolls: 0');
  });

  test('2.5-AC3 Investigator Keen Eye rolls two dice and the status drops to Keen Eye: 0', tag, async ({ page }) => {
    await newHero(page, /Investigator/);
    await readUntilChoices(page);
    await typeAction(page, 'check the ledger for an odd figure');
    await dice(page).getByRole('button', { name: /Keen Eye — roll with advantage \(1 left\)/ }).click();
    await expect(dice(page)).toContainText('Two dice: 9 and 14');
    await expect(page.getByRole('button', { name: 'Hero status' })).toContainText('Keen Eye: 0');
  });

  test('2.10-AC5 the voice choice is remembered after a reload', tag, async ({ page }) => {
    await newHero(page, /Guardian/);
    await readUntilChoices(page);
    const voice = page.getByRole('button', { name: 'Voice', exact: true });
    await expect(voice).toHaveAttribute('aria-pressed', 'true');
    await voice.click();
    await expect(voice).toHaveAttribute('aria-pressed', 'false');
    await page.reload();
    await unlock(page);
    await page.getByRole('button', { name: 'Continue' }).click();
    await expect(page.getByRole('button', { name: 'Voice', exact: true })).toHaveAttribute('aria-pressed', 'false');
  });

  test('2.17-AC2/AC3 hint and bonus lead each cost one Focus', tag, async ({ page }) => {
    await newHero(page, /Guardian/);
    await readUntilChoices(page);
    await page.getByRole('button', { name: 'Ask for a hint' }).click();
    await readUntilChoices(page);
    await expect(page.getByRole('button', { name: 'Hero status' })).toContainText('Focus: 2');
    await page.getByRole('button', { name: 'Chase a bonus lead' }).click();
    await expect(dice(page)).toContainText('Difficulty 18');
    await expect(page.getByRole('button', { name: 'Hero status' })).toContainText('Focus: 1');
  });

  test('2.7-AC1b Buddy is reachable from the commit screen', tag, async ({ page }) => {
    await newHero(page, /Guardian/);
    await readUntilChoices(page);
    await goTo(page, 'Library');
    await typeAction(page, 'look around');
    await goTo(page, 'Market Square');
    for (let i = 0; i < 20 && (await page.getByRole('article', { name: 'Breaking news' }).count()) === 0; i++) await readUntilChoices(page);
    await page.getByRole('article', { name: 'Breaking news' }).getByRole('button', { name: 'Continue' }).click();
    await readUntilChoices(page);
    await page.getByRole('button', { name: "I'm ready to decide" }).click();
    await expect(page).toHaveURL(/\/quest\/commit$/);
    await expect(page.getByRole('button', { name: /Buddy/ })).toBeVisible({ timeout: 2000 });
  });
});
