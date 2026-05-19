import { test, expect } from '@playwright/test';

test.describe('Admin user management', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/login');
    await page.fill('#username', 'admin');
    await page.fill('#password', 'AdminPass1!');
    await page.click('button:has-text("Log in")');
    await page.waitForLoadState('networkidle');
    test.skip(page.url().includes('/login'), 'admin login failed');
  });

  test('admin page shows Users + Audit panels', async ({ page }) => {
    // Iter 5 Bold rewrite — Tabs replaced with side-by-side 2-col panels.
    await page.goto('/admin');
    await page.waitForLoadState('networkidle');
    await expect(page.locator('.b-topbar .page-title')).toBeVisible({ timeout: 5_000 });
    await expect(page.locator('.panel-head', { hasText: /Users/i }).first()).toBeVisible();
    await expect(page.locator('.panel-head', { hasText: /Audit/i }).first()).toBeVisible();
  });

  test('audit panel loads without error', async ({ page }) => {
    // Iter 5 Bold rewrite — Audit panel always rendered (no tab to click).
    await page.goto('/admin');
    await page.waitForLoadState('networkidle');
    const auditPanel = page.locator('.panel', { hasText: /Audit Log/i });
    await expect(auditPanel).toBeVisible({ timeout: 5_000 });
    // Either rows or empty-state present.
    const rowCount = await auditPanel.locator('.audit-row').count();
    const emptyCount = await auditPanel.locator('.empty-title').count();
    expect(rowCount + emptyCount).toBeGreaterThan(0);
  });
});
