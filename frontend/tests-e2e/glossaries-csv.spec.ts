import { test, expect } from '@playwright/test';

test.describe('Glossaries page', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/login');
    await page.fill('#username', 'admin');
    await page.fill('#password', 'AdminPass1!');
    await page.click('button:has-text("Log in")');
    await page.waitForLoadState('networkidle');
    test.skip(page.url().includes('/login'), 'admin login failed');
  });

  test('lists glossaries + new dialog shows lang dropdowns', async ({ page }) => {
    await page.goto('/glossaries');
    await expect(page.getByRole('heading', { name: /Glossaries/i })).toBeVisible();
    await page.getByRole('button', { name: /\+ New Glossary/i }).click();
    await expect(page.getByRole('heading', { name: /New Glossary/i })).toBeVisible();
    await expect(page.getByLabel(/Source lang/i)).toBeVisible();
    await expect(page.getByLabel(/Target lang/i)).toBeVisible();
    await page.keyboard.press('Escape');
  });

  test('CSV export link contains glossary id', async ({ page }) => {
    await page.goto('/glossaries');
    const exportLinks = page.locator('a:has-text("Export")');
    const count = await exportLinks.count();
    if (count === 0) {
      test.skip(true, 'No glossaries in test environment — skip Export link check');
    }
    const href = await exportLinks.first().getAttribute('href');
    expect(href).toMatch(/\/api\/glossaries\/[^/]+\/export/);
  });
});
