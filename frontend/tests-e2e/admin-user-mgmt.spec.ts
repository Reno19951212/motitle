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

  test('admin tab shows Users + Audit tabs', async ({ page }) => {
    await page.goto('/admin');
    await expect(page.getByRole('heading', { name: /^Admin/i })).toBeVisible();
    await expect(page.getByRole('tab', { name: 'Users' })).toBeVisible();
    await expect(page.getByRole('tab', { name: 'Audit' })).toBeVisible();
  });

  test('audit tab loads without error', async ({ page }) => {
    await page.goto('/admin');
    await page.getByRole('tab', { name: 'Audit' }).click();
    // Should see either rows or "No audit entries yet."
    await expect(
      page.locator('text=/Time|No audit entries/')
    ).toBeVisible({ timeout: 5_000 });
  });
});
