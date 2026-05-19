import { test, expect } from '@playwright/test';

test.describe('Dashboard (Bold variant)', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/login');
    await page.fill('#username', 'admin');
    await page.fill('#password', 'AdminPass1!');
    await page.click('button:has-text("Log in")');
    await expect(page).toHaveURL('/', { timeout: 10_000 });
  });

  test('shows Bold layout — rail, topbar, pipeline-strip, drop-hero', async ({ page }) => {
    await expect(page.locator('.b-rail')).toBeVisible();
    await expect(page.locator('.b-topbar')).toBeVisible();
    await expect(page.locator('.pipeline-strip')).toBeVisible();
    await expect(page.locator('.drop-hero')).toBeVisible();
    await expect(page.locator('.drop-hero .t')).toHaveText('拖放影片上傳');
  });

  test('topbar exposes ASR + MT + socket status pills', async ({ page }) => {
    // 3 status div-pills + 1 logout button-pill — assert by label, not count
    const cluster = page.locator('.b-topbar .health-cluster');
    await expect(cluster.locator('.health-pill .hk').filter({ hasText: /^ASR$/ })).toBeVisible();
    await expect(cluster.locator('.health-pill .hk').filter({ hasText: /^MT$/ })).toBeVisible();
    await expect(cluster.locator('.health-pill .hk').filter({ hasText: /^即時$/ })).toBeVisible();
  });

  test('pipeline preset chip is interactive (hover reveals menu)', async ({ page }) => {
    const presetWrap = page.locator('.pipeline-preset-wrap');
    await expect(presetWrap).toBeVisible();
    // Bold dropdowns use CSS hover/:focus-within — Playwright hover triggers menu
    await presetWrap.hover();
    const menu = page.locator('.pipeline-preset-wrap .preset-menu');
    await expect(menu).toBeVisible({ timeout: 2000 });
  });
});
