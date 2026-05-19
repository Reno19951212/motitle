/**
 * Bold variant — ASR Profile CRUD page smoke spec.
 *
 * Verifies the iter 2 rewrite landed:
 *   • motitle-bold full-page layout landmarks (b-rail + b-topbar + b-body)
 *   • Existing ASR profiles listed in left panel
 *   • Create + read + delete round-trip
 *   • Back button navigates to Dashboard
 *
 * Tests are graceful: if admin login fails the whole describe skips.
 */
import { test, expect } from '@playwright/test';

test.describe('Bold ASR Profile page', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/login');
    await page.fill('#username', 'admin');
    await page.fill('#password', 'AdminPass1!');
    await page.click('button:has-text("Log in")');
    await page.waitForLoadState('networkidle');
    test.skip(page.url().includes('/login'), 'admin login failed — env credential issue');
  });

  test('Bold layout landmarks present on /asr_profiles', async ({ page }) => {
    await page.goto('/asr_profiles');
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

  test('rail ASR item highlighted as active', async ({ page }) => {
    await page.goto('/asr_profiles');
    await page.waitForLoadState('networkidle');
    // The rail item for /asr_profiles route should have the .on class
    const asrRail = page.locator('.b-rail a.rail-btn[href="/asr_profiles"]');
    await expect(asrRail).toBeVisible();
    await expect(asrRail).toHaveClass(/\bon\b/);
  });

  test('lists existing ASR profiles in left panel', async ({ page }) => {
    await page.goto('/asr_profiles');
    await page.waitForLoadState('networkidle');
    // Wait for at least one profile-row OR an empty-state to appear
    await page.waitForSelector('.profile-row, .empty-title', { timeout: 5_000 });
    // We expect at least one of the seeded profiles to be present
    const rowCount = await page.locator('.profile-row').count();
    console.log(`[asr-profile] profile rows: ${rowCount}`);
    expect(rowCount).toBeGreaterThan(0);
  });

  test('create + read + delete round-trip', async ({ page }) => {
    const uniqName = `e2e-asr-${Date.now()}`;
    await page.goto('/asr_profiles');
    await page.waitForLoadState('networkidle');

    // Click + 新增 Profile
    await page.locator('.b-topbar .run-btn').click();
    // Wait for form to render
    await expect(page.locator('#name')).toBeVisible({ timeout: 5_000 });

    // Fill name + verify selects exist
    await page.fill('#name', uniqName);
    await page.locator('#engine').selectOption('whisper');
    await page.locator('#mode').selectOption('same-lang');
    await page.locator('#language').selectOption('en');
    await page.locator('#device').selectOption('auto');

    // Save
    await page.locator('button[type="submit"]:has-text("Save")').click();

    // Wait for the new row to appear in the list
    await expect(page.locator('.profile-row', { hasText: uniqName })).toBeVisible({
      timeout: 10_000,
    });

    // Click the row to re-load
    await page.locator('.profile-row', { hasText: uniqName }).click();
    // Form should now show the saved name
    await expect(page.locator('#name')).toHaveValue(uniqName);

    // Delete via the row's profile-del button
    const row = page.locator('.profile-row', { hasText: uniqName });
    // Hover to reveal delete button
    await row.hover();
    await row.locator('.profile-del').click();

    // ConfirmDialog should appear
    await page.locator('button:has-text("Delete")').last().click();

    // Row should disappear
    await expect(page.locator('.profile-row', { hasText: uniqName })).toHaveCount(0, {
      timeout: 5_000,
    });
  });

  test('back button returns to Dashboard', async ({ page }) => {
    await page.goto('/asr_profiles');
    await page.waitForLoadState('networkidle');
    await page.locator('.b-topbar .back-btn').click();
    await expect(page).toHaveURL('/', { timeout: 5_000 });
  });
});
