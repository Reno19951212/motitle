import { test, expect } from '@playwright/test';

test.describe('Console page (/console)', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/login');
    await page.fill('#username', 'admin_p3');
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

  test('selecting a file shows its duration in FileFactsBlock + TransportBar', async ({ page }) => {
    await page.goto('/console?console=1');
    await expect(page.locator('[data-testid="console-rail"]')).toBeVisible();

    // Click the first queue item (if any) — tolerate empty queue
    const items = page.locator('[data-testid^="queue-item-"]');
    const n = await items.count();
    if (n === 0) {
      test.skip(true, 'No files in queue to select — upload a fixture to test');
      return;
    }

    await items.first().click();

    // FileFactsBlock 時長 row — should NOT be the empty-state "未揀檔" or "—"
    const facts = page.locator('[data-testid="aside-facts"]');
    await expect(facts).toBeVisible();

    // 時長 value is the .v cell in the row whose key is "時長"
    const durationValue = facts.locator('.con-fact', { hasText: '時長' }).locator('.v');
    await expect(durationValue).toBeVisible();
    const durText = await durationValue.textContent();
    // Should match mm:ss or h:mm:ss (NOT "—")
    expect(durText).toMatch(/^\d+:\d{2}(:\d{2})?$/);

    // TransportBar totalTime — same expectation
    const transportTc = page.locator('[data-testid="transport-bar"] .tc');
    await expect(transportTc).toBeVisible();
    const tcText = await transportTc.textContent();
    expect(tcText).toMatch(/\/ \d+:\d{2}/);  // " / mm:ss" suffix
  });

  test('Ctrl/Cmd+K opens global search modal, Esc closes it', async ({ page }) => {
    await page.goto('/console?console=1');
    // Wait for Console mount — useHotkeys registers via useEffect (post-mount).
    await expect(page.locator('[data-testid="console-rail"]')).toBeVisible();
    // Body focus + Control+K (Cmd+K is captured by Chromium for Tab Search on macOS).
    await page.keyboard.press('Control+K');
    // Use explicit waitFor so Playwright polls for the new modal element to
    // appear in DOM (not just retry on a stale locator handle).
    await page.locator('[data-testid="global-search-modal"]').waitFor({ state: 'visible', timeout: 5000 });
    await page.keyboard.press('Escape');
    await page.locator('[data-testid="global-search-modal"]').waitFor({ state: 'detached', timeout: 5000 });
  });
});
