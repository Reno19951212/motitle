/**
 * Bold variant — Glossary CRUD page smoke spec.
 *
 * Verifies the iter 4 rewrite landed:
 *   • motitle-bold full-page layout landmarks (b-rail + b-topbar + b-body)
 *   • Rail Glossary item highlighted as active
 *   • Existing glossaries or empty state rendered in left panel
 *   • Create + read + delete round-trip
 *   • Entries panel + CSV export anchor present after selection
 *   • Back button navigates to Dashboard
 *
 * Tests are graceful: if admin login fails the whole describe skips.
 */
import { test, expect } from '@playwright/test';

test.describe('Bold Glossary page', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/login');
    await page.fill('#username', 'admin');
    await page.fill('#password', 'AdminPass1!');
    await page.click('button:has-text("Log in")');
    await page.waitForLoadState('networkidle');
    test.skip(page.url().includes('/login'), 'admin login failed — env credential issue');
  });

  test('Bold layout landmarks present on /glossaries', async ({ page }) => {
    await page.goto('/glossaries');
    await page.waitForLoadState('networkidle');
    await expect(page.locator('.motitle-bold')).toBeVisible({ timeout: 10_000 });
    await expect(page.locator('.b-rail')).toBeVisible();
    await expect(page.locator('.b-topbar')).toBeVisible();
    await expect(page.locator('.b-body.b-body-entity')).toBeVisible();
    await expect(page.locator('.b-topbar .back-btn')).toBeVisible();
    await expect(page.locator('.b-topbar .page-title')).toBeVisible();
    await expect(page.locator('.b-topbar .run-btn')).toBeVisible();
    await expect(page.locator('.b-topbar .health-cluster')).toBeVisible();
  });

  test('rail Glossary item highlighted as active', async ({ page }) => {
    await page.goto('/glossaries');
    await page.waitForLoadState('networkidle');
    const glossRail = page.locator('.b-rail a.rail-btn[href="/glossaries"]');
    await expect(glossRail).toBeVisible();
    await expect(glossRail).toHaveClass(/\bon\b/);
  });

  test('lists existing glossaries or empty state', async ({ page }) => {
    await page.goto('/glossaries');
    await page.waitForLoadState('networkidle');
    await page.waitForSelector('.profile-row, .empty-title', { timeout: 5_000 });
    const hasContent =
      (await page.locator('.profile-row').count()) +
      (await page.locator('.empty-title').count());
    expect(hasContent).toBeGreaterThan(0);
  });

  test('create + read + delete round-trip', async ({ page }) => {
    const uniqName = `e2e-gloss-${Date.now()}`;
    await page.goto('/glossaries');
    await page.waitForLoadState('networkidle');

    // Click + 新增 Glossary
    await page.locator('.b-topbar .run-btn').click();
    await expect(page.locator('#name')).toBeVisible({ timeout: 5_000 });

    // Fill name + verify lang defaults (en + zh)
    await page.fill('#name', uniqName);
    await expect(page.locator('#source_lang')).toHaveValue('en');
    await expect(page.locator('#target_lang')).toHaveValue('zh');

    // Save — create button labelled 建立
    await page.locator('button[type="submit"]').first().click();

    // Wait for the new row to appear in the list
    await expect(page.locator('.profile-row', { hasText: uniqName })).toBeVisible({
      timeout: 10_000,
    });

    // Click the row to re-load — meta form should populate
    await page.locator('.profile-row', { hasText: uniqName }).click();
    await expect(page.locator('#name')).toHaveValue(uniqName, { timeout: 5_000 });

    // Delete via the row's profile-del button
    const row = page.locator('.profile-row', { hasText: uniqName });
    await row.hover();
    await row.locator('.profile-del').click();

    // ConfirmDialog should appear — click Delete (last button matches the dialog
    // confirm, not the row's hidden one).
    await page.locator('button:has-text("Delete")').last().click();

    // Row should disappear
    await expect(page.locator('.profile-row', { hasText: uniqName })).toHaveCount(0, {
      timeout: 5_000,
    });
  });

  test('selecting a glossary reveals entries panel + CSV export anchor', async ({ page }) => {
    await page.goto('/glossaries');
    await page.waitForLoadState('networkidle');

    // We need at least one glossary — create an ephemeral one for this test
    const uniqName = `e2e-gloss-entries-${Date.now()}`;
    await page.locator('.b-topbar .run-btn').click();
    await expect(page.locator('#name')).toBeVisible({ timeout: 5_000 });
    await page.fill('#name', uniqName);
    await page.locator('button[type="submit"]').first().click();

    // Reload glossary in list view + select it
    const row = page.locator('.profile-row', { hasText: uniqName });
    await expect(row).toBeVisible({ timeout: 10_000 });
    await row.click();

    // Entries panel header should be visible
    await expect(page.locator('text=/Entries/i').first()).toBeVisible({ timeout: 5_000 });

    // CSV export anchor for this glossary
    const exportLink = page.locator('a[href*="/api/glossaries/"][href*="/export"]');
    await expect(exportLink.first()).toBeVisible({ timeout: 5_000 });

    // Cleanup: delete the ephemeral glossary
    await row.hover();
    await row.locator('.profile-del').click();
    await page.locator('button:has-text("Delete")').last().click();
    await expect(row).toHaveCount(0, { timeout: 5_000 });
  });

  test('back button returns to Dashboard', async ({ page }) => {
    await page.goto('/glossaries');
    await page.waitForLoadState('networkidle');
    await page.locator('.b-topbar .back-btn').click();
    await expect(page).toHaveURL('/', { timeout: 5_000 });
  });
});
