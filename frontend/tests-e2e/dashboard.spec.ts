import { test, expect } from '@playwright/test';

test.describe('Dashboard', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/login');
    await page.fill('#username', 'admin');
    await page.fill('#password', 'AdminPass1!');
    await page.click('button:has-text("Log in")');
    await expect(page).toHaveURL('/');
  });

  test('shows Pipeline picker + Upload zone', async ({ page }) => {
    await expect(page.locator('label:has-text("Pipeline")')).toBeVisible();
    await expect(page.locator('text=Drag video/audio file')).toBeVisible();
  });
});
