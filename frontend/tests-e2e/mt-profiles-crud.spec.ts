import { test, expect } from '@playwright/test';

test.describe('MT Profiles CRUD', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/login');
    await page.fill('#username', 'admin');
    await page.fill('#password', 'AdminPass1!');
    await page.click('button:has-text("Log in")');
    await page.waitForLoadState('networkidle');
    test.skip(page.url().includes('/login'), 'admin login failed');
  });

  test('opens MT profile dialog + shows {text} placeholder hint', async ({ page }) => {
    await page.goto('/mt_profiles');
    await expect(page.getByRole('heading', { name: /MT Profiles/i })).toBeVisible();
    await page.getByRole('button', { name: /\+ New MT Profile/i }).click();
    await expect(page.getByRole('heading', { name: /New MT Profile/i })).toBeVisible();
    // Verify {text} placeholder hint visible
    await expect(page.getByText(/\{text\}/)).toBeVisible();
    await page.keyboard.press('Escape');
  });
});
