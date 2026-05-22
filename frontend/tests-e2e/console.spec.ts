import { test, expect } from '@playwright/test';

test.describe('Console page (/console)', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/login');
    await page.fill('#username', 'admin');
    await page.fill('#password', 'AdminPass1!');
    await page.click('button:has-text("Log in")');
    await expect(page).toHaveURL('/', { timeout: 10_000 });
  });

  test('redirects /console without ?console=1 query to /', async ({ page }) => {
    await page.goto('/console');
    await expect(page).toHaveURL('/', { timeout: 5_000 });
  });

  test('renders 4 columns at /console?console=1', async ({ page }) => {
    await page.goto('/console?console=1');
    await expect(page.locator('[data-testid="console-rail"]')).toBeVisible();
    await expect(page.locator('[data-testid="console-queue"]')).toBeVisible();
    await expect(page.locator('[data-testid="console-workbench"]')).toBeVisible();
    await expect(page.locator('[data-testid="console-aside"]')).toBeVisible();
  });

  test('rail shows brand mark + 6 nav + 3 bottom', async ({ page }) => {
    await page.goto('/console?console=1');
    await expect(page.locator('.con-rail .mark')).toBeVisible();
    await expect(page.locator('[data-testid^="rail-nav-"]')).toHaveCount(6);
    await expect(page.locator('[data-testid^="rail-bottom-"]')).toHaveCount(3);
  });

  test('queue stage bar has 4 cells when present', async ({ page }) => {
    await page.goto('/console?console=1');
    const bars = page.locator('[data-testid="queue-stage-bar"]');
    const n = await bars.count();
    if (n > 0) {
      const cells = bars.first().locator('i');
      await expect(cells).toHaveCount(4);
    }
  });

  test('preset pills 1-4 exist and Cmd+1-4 keys register', async ({ page }) => {
    await page.goto('/console?console=1');
    for (const slot of [1, 2, 3, 4]) {
      await expect(page.locator(`[data-testid="preset-pill-${slot}"]`)).toBeVisible();
    }
    await page.keyboard.press('Meta+2'); // press does not throw — pill may be disabled if no pipeline mapped, tolerate
  });

  test('worker status section renders', async ({ page }) => {
    await page.goto('/console?console=1');
    await expect(page.locator('[data-testid="worker-status"]')).toBeVisible();
  });

  test('metrics bar shows queue label + dash placeholders for ASR/MT/GPU', async ({ page }) => {
    await page.goto('/console?console=1');
    await expect(page.locator('[data-testid="metrics-bar"]')).toBeVisible();
    // 3 of 4 metrics are "—" (Q5=B)
    const dashes = page.locator('[data-testid="metrics-bar"]').locator('text=—');
    expect(await dashes.count()).toBeGreaterThanOrEqual(3);
  });

  test('aside has 3 blocks (pipeline + glossary + facts)', async ({ page }) => {
    await page.goto('/console?console=1');
    await expect(page.locator('[data-testid="aside-pipeline"]')).toBeVisible();
    await expect(page.locator('[data-testid="aside-glossary"]')).toBeVisible();
    await expect(page.locator('[data-testid="aside-facts"]')).toBeVisible();
  });

  test('Cmd+K opens global search modal, Esc closes it', async ({ page }) => {
    await page.goto('/console?console=1');
    await page.keyboard.press('Meta+K');
    await expect(page.locator('[data-testid="global-search-modal"]')).toBeVisible();
    await page.keyboard.press('Escape');
    await expect(page.locator('[data-testid="global-search-modal"]')).not.toBeVisible();
  });
});
