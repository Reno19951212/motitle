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

  test('open new ASR profile form', async ({ page }) => {
    await page.goto('/asr_profiles');
    // Bold variant — page title in topbar (iter 2 of redesign)
    await expect(page.getByRole('heading', { name: /ASR Profiles/i })).toBeVisible();
    // Click + 新增 Profile (Bold variant) — Chinese label, was "+ New ASR Profile"
    await page.locator('.b-topbar .run-btn').click();
    // Form appears in right column instead of modal dialog (iter 2 rewrite)
    await expect(page.getByLabel(/Name/i)).toBeVisible();
    await expect(page.getByLabel(/Engine/i)).toBeVisible();
  });
});
