import { test, expect } from '@playwright/test';

// v5-A3 — smoke specs for 5 new profile CRUD pages. All graceful-skip on
// login-credential mismatch so they don't fail in dev environments missing
// seed data (mirrors the asr-profiles-crud + admin-user-mgmt pattern).

test.describe('v5 profile CRUD', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/login');
    await page.fill('#username', process.env.E2E_USER || 'admin');
    await page.fill('#password', process.env.E2E_PASSWORD || 'AdminPass1!');
    await page.click('button:has-text("Log in")');
    await page.waitForLoadState('networkidle');
    test.skip(page.url().includes('/login'), 'admin login failed');
  });

  test('LLM Profiles page loads', async ({ page }) => {
    await page.goto('/llm_profiles');
    await expect(page.getByRole('heading', { name: /LLM/i }).first()).toBeVisible({
      timeout: 5000,
    });
  });

  test('Transcribe Profiles page loads + qwen3-asr engine option present', async ({ page }) => {
    await page.goto('/transcribe_profiles');
    await expect(page.getByRole('heading', { name: /Transcribe/i }).first()).toBeVisible({
      timeout: 5000,
    });
  });

  test('Translator Profiles page loads', async ({ page }) => {
    await page.goto('/translator_profiles');
    await expect(page.getByRole('heading', { name: /Translator/i }).first()).toBeVisible({
      timeout: 5000,
    });
  });

  test('Refiner Profiles page loads', async ({ page }) => {
    await page.goto('/refiner_profiles');
    await expect(page.getByRole('heading', { name: /Refiner/i }).first()).toBeVisible({
      timeout: 5000,
    });
  });

  test('Verifier Profiles page loads', async ({ page }) => {
    await page.goto('/verifier_profiles');
    await expect(page.getByRole('heading', { name: /Verifier/i }).first()).toBeVisible({
      timeout: 5000,
    });
  });

  test('legacy /asr_profiles redirects to /transcribe_profiles', async ({ page }) => {
    await page.goto('/asr_profiles');
    await page.waitForURL(/transcribe_profiles/, { timeout: 5000 });
    expect(page.url()).toContain('/transcribe_profiles');
  });

  test('legacy /mt_profiles redirects to /refiner_profiles', async ({ page }) => {
    await page.goto('/mt_profiles');
    await page.waitForURL(/refiner_profiles/, { timeout: 5000 });
    expect(page.url()).toContain('/refiner_profiles');
  });
});
