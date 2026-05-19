/**
 * Bold variant — Admin page smoke spec.
 *
 * Verifies the iter 5 rewrite landed:
 *   • motitle-bold full-page layout landmarks (b-rail + b-topbar + b-body)
 *   • Rail Admin item highlighted as active
 *   • Users panel + Audit panel both rendered simultaneously (2-col split)
 *   • Existing users visible (admin always present)
 *   • Audit panel shows rows or empty state
 *   • Create + delete user round-trip
 *   • Back button navigates to Dashboard
 *
 * Tests are graceful: if admin login fails the whole describe skips.
 */
import { test, expect } from '@playwright/test';

test.describe('Bold Admin page', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/login');
    await page.fill('#username', 'admin');
    await page.fill('#password', 'AdminPass1!');
    await page.click('button:has-text("Log in")');
    await page.waitForLoadState('networkidle');
    test.skip(page.url().includes('/login'), 'admin login failed — env credential issue');
  });

  test('Bold layout landmarks present on /admin', async ({ page }) => {
    await page.goto('/admin');
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

  test('rail Admin item highlighted as active', async ({ page }) => {
    await page.goto('/admin');
    await page.waitForLoadState('networkidle');
    const adminRail = page.locator('.b-rail a.rail-btn[href="/admin"]');
    await expect(adminRail).toBeVisible();
    await expect(adminRail).toHaveClass(/\bon\b/);
  });

  test('Users panel + Audit panel both visible (2-col split)', async ({ page }) => {
    await page.goto('/admin');
    await page.waitForLoadState('networkidle');
    // Both panels render side by side — assert each title is present
    await expect(page.locator('.panel-head', { hasText: /Users/i }).first()).toBeVisible({
      timeout: 5_000,
    });
    await expect(page.locator('.panel-head', { hasText: /Audit/i }).first()).toBeVisible({
      timeout: 5_000,
    });
    // Audit filter selects rendered
    await expect(page.locator('select[aria-label="Filter by actor"]')).toBeVisible();
    await expect(page.locator('select[aria-label="Limit"]')).toBeVisible();
  });

  test('lists existing users (admin always present)', async ({ page }) => {
    await page.goto('/admin');
    await page.waitForLoadState('networkidle');
    await page.waitForSelector('.profile-row.user-row, .empty-title', { timeout: 5_000 });
    // admin user always present
    await expect(
      page.locator('.profile-row.user-row .profile-name', { hasText: 'admin' }).first(),
    ).toBeVisible({ timeout: 5_000 });
  });

  test('audit panel shows rows or empty state', async ({ page }) => {
    await page.goto('/admin');
    await page.waitForLoadState('networkidle');
    // Scoped to audit panel only — either audit-row or empty-title within it
    const auditPanel = page.locator('.panel', { hasText: /Audit Log/i });
    await expect(auditPanel).toBeVisible({ timeout: 5_000 });
    const rowCount = await auditPanel.locator('.audit-row').count();
    const emptyCount = await auditPanel.locator('.empty-title').count();
    expect(rowCount + emptyCount).toBeGreaterThan(0);
  });

  test('create + delete user round-trip', async ({ page }) => {
    const uniqName = `e2e-user-${Date.now()}`;
    await page.goto('/admin');
    await page.waitForLoadState('networkidle');

    // Click + 新增用戶
    await page.locator('.b-topbar .run-btn').click();
    await expect(page.locator('#username')).toBeVisible({ timeout: 5_000 });

    // Fill form
    await page.fill('#username', uniqName);
    await page.fill('#password', 'TestPass1!');

    // Submit — form submit button labelled 建立 Create
    await page.locator('button[type="submit"]').first().click();

    // Wait for the new row to appear
    await expect(
      page.locator('.profile-row.user-row .profile-name', { hasText: uniqName }),
    ).toBeVisible({ timeout: 10_000 });

    // Find the row + click Delete
    const row = page.locator('.profile-row.user-row', {
      has: page.locator('.profile-name', { hasText: uniqName }),
    });
    await row.locator('button:has-text("Delete")').click();

    // ConfirmDialog appears — click Delete (last on page = dialog confirm)
    await page.locator('button:has-text("Delete")').last().click();

    // Row should disappear
    await expect(
      page.locator('.profile-row.user-row .profile-name', { hasText: uniqName }),
    ).toHaveCount(0, { timeout: 5_000 });
  });

  test('back button returns to Dashboard', async ({ page }) => {
    await page.goto('/admin');
    await page.waitForLoadState('networkidle');
    await page.locator('.b-topbar .back-btn').click();
    await expect(page).toHaveURL('/', { timeout: 5_000 });
  });
});
