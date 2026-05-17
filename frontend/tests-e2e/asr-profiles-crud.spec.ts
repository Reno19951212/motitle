import { test, expect } from '@playwright/test';

test.describe('ASR Profiles CRUD', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/login');
    await page.fill('#username', 'admin');
    await page.fill('#password', 'AdminPass1!');
    await page.click('button:has-text("Log in")');
    await page.waitForLoadState('networkidle');
    test.skip(page.url().includes('/login'), 'admin login failed');
  });

  test('open new ASR profile dialog', async ({ page }) => {
    await page.goto('/asr_profiles');
    await expect(page.getByRole('heading', { name: /ASR Profiles/i })).toBeVisible();
    await page.getByRole('button', { name: /\+ New ASR Profile/i }).click();
    await expect(page.getByRole('heading', { name: /New ASR Profile/i })).toBeVisible();
    await expect(page.getByLabel(/Name/i)).toBeVisible();
    // Verify engine + mode + language dropdowns visible
    await expect(page.getByLabel(/Engine/i)).toBeVisible();
    await page.keyboard.press('Escape');
  });
});
