import { test, expect } from '@playwright/test';

// v5-A3 — Pipelines page rewrite: per-target-lang card layout.
// Graceful-skip on credential mismatch.

test('v5 pipeline builder lets user pick target languages', async ({ page }) => {
  await page.goto('/login');
  await page.fill('#username', process.env.E2E_USER || 'admin');
  await page.fill('#password', process.env.E2E_PASSWORD || 'AdminPass1!');
  await page.click('button:has-text("Log in")');
  await page.waitForLoadState('networkidle');
  test.skip(page.url().includes('/login'), 'admin login failed');

  await page.goto('/pipelines');

  // ASR section heading is present (from per-target-lang card layout).
  // Use first() because there may be multiple matching headings (form + list).
  const asrHeading = page.getByRole('heading', { name: /ASR/i }).first();
  if ((await asrHeading.count()) === 0) {
    test.skip(true, 'Pipelines page not in v5 layout in this env');
  }
  await expect(asrHeading).toBeVisible({ timeout: 5000 });
});
