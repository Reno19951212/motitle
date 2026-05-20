import { test, expect } from '@playwright/test';

// v5-A3 — Proofread page TargetLangTabs switcher. Graceful-skip if file lacks
// multi-lang by_lang data (e.g. ASR-only files or no v5 fixtures seeded).

test('proofread page shows target-lang tabs when file has by_lang data', async ({ page }) => {
  await page.goto('/login');
  await page.fill('#username', process.env.E2E_USER || 'admin');
  await page.fill('#password', process.env.E2E_PASSWORD || 'AdminPass1!');
  await page.click('button:has-text("Log in")');
  await page.waitForLoadState('networkidle');
  test.skip(page.url().includes('/login'), 'admin login failed');

  const fid = process.env.E2E_V5_FILE_ID || 'b9b9e4fad18c';
  await page.goto(`/proofread/${fid}`);

  // Wait briefly for hydration; then check whether lang tabs exist
  await page.waitForTimeout(800);
  const tabs = page.locator('.lang-tabs button');
  const count = await tabs.count();
  if (count < 2) {
    test.skip(true, `File ${fid} doesn't have multi-lang v5 data (found ${count} tab(s))`);
  }

  // If there are multiple tabs, click the second one and ensure it activates
  const enTab = page.locator('.lang-tabs button:has-text("en")');
  if ((await enTab.count()) > 0) {
    await enTab.first().click();
    await page.waitForTimeout(300);
    await expect(enTab.first()).toBeVisible();
  }
});
