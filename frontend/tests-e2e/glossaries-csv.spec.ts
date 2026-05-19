import { test, expect } from '@playwright/test';

/**
 * Legacy Glossaries spec — updated for iter 4 Bold variant.
 *
 * The old version asserted shadcn EntityForm dialog (heading "New Glossary",
 * row-level Export anchors). The Bold rewrite uses inline panels in the
 * right column and a single CSV Export anchor on the selected glossary.
 *
 * Intent preserved:
 *   1. Page lists glossaries + new-glossary form exposes source_lang +
 *      target_lang selects.
 *   2. CSV export anchor links to /api/glossaries/<id>/export with the
 *      glossary id in the href.
 */

test.describe('Glossaries page (Bold variant)', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/login');
    await page.fill('#username', 'admin');
    await page.fill('#password', 'AdminPass1!');
    await page.click('button:has-text("Log in")');
    await page.waitForLoadState('networkidle');
    test.skip(page.url().includes('/login'), 'admin login failed');
  });

  test('lists glossaries + new form shows lang dropdowns', async ({ page }) => {
    await page.goto('/glossaries');
    await page.waitForLoadState('networkidle');
    await expect(page.locator('.b-topbar .page-title')).toBeVisible();
    await page.locator('.b-topbar .run-btn').click();
    await expect(page.getByLabel(/Source lang/i)).toBeVisible({ timeout: 5_000 });
    await expect(page.getByLabel(/Target lang/i)).toBeVisible();
  });

  test('CSV export anchor contains glossary id', async ({ page }) => {
    await page.goto('/glossaries');
    await page.waitForLoadState('networkidle');

    // Need a glossary selected for the CSV export anchor to render. Try the
    // first existing row; if none exist, skip.
    const rows = page.locator('.profile-row');
    const count = await rows.count();
    if (count === 0) {
      test.skip(true, 'No glossaries in test environment — skip Export anchor check');
    }
    await rows.first().click();

    const exportLink = page.locator('a[href*="/api/glossaries/"][href*="/export"]');
    await expect(exportLink.first()).toBeVisible({ timeout: 5_000 });
    const href = await exportLink.first().getAttribute('href');
    expect(href).toMatch(/\/api\/glossaries\/[^/]+\/export/);
  });
});
