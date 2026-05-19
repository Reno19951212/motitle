import { test, expect } from '@playwright/test';

test.describe('Auth flow', () => {
  test('login → dashboard → logout', async ({ page }) => {
    // Start at login (whether redirected from / or visited directly)
    await page.goto('/login');
    await expect(page.locator('h1:has-text("MoTitle Login")')).toBeVisible();

    await page.fill('#username', 'admin');
    await page.fill('#password', 'AdminPass1!');
    await page.click('button:has-text("Log in")');

    // Land on Bold Dashboard at root — .b-topbar replaces <header>
    await expect(page).toHaveURL('/', { timeout: 10_000 });
    await expect(page.locator('.b-topbar')).toBeVisible();
    const logoutBtn = page.locator('.b-topbar .health-cluster button:has-text("Logout")');
    await expect(logoutBtn).toBeVisible();

    // Logout returns to /login
    await logoutBtn.click();
    await expect(page).toHaveURL(/\/login/);
  });

  test('unauthenticated visit to /pipelines redirects to /login', async ({ page }) => {
    await page.context().clearCookies();
    await page.goto('/pipelines');
    await expect(page).toHaveURL(/\/login/);
  });
});
