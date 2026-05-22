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
});
