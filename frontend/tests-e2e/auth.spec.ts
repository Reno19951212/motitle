import { test, expect } from '@playwright/test';

test.describe('Auth flow', () => {
  test('login → dashboard → logout', async ({ page }) => {
    // Start at login (whether redirected from / or visited directly)
    await page.goto('/login');
    await expect(page.locator('h1:has-text("MoTitle Login")')).toBeVisible();

    await page.fill('#username', 'admin');
    await page.fill('#password', 'AdminPass1!');
    await page.click('button:has-text("Log in")');

    // Land on dashboard (root) — TopBar visible
    await expect(page).toHaveURL('/', { timeout: 10_000 });
    await expect(page.locator('header').getByText('MoTitle')).toBeVisible();
    await expect(page.getByRole('button', { name: 'Logout' })).toBeVisible();

    // Logout returns to /login
    await page.getByRole('button', { name: 'Logout' }).click();
    await expect(page).toHaveURL(/\/login/);
  });

  test('unauthenticated visit to /pipelines redirects to /login', async ({ page }) => {
    await page.context().clearCookies();
    await page.goto('/pipelines');
    await expect(page).toHaveURL(/\/login/);
  });
});
