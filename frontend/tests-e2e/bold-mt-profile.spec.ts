/**
 * Bold variant — MT Profile CRUD page smoke spec.
 *
 * Verifies the iter 3 rewrite landed:
 *   • motitle-bold full-page layout landmarks (b-rail + b-topbar + b-body)
 *   • Rail MT item highlighted as active
 *   • Existing MT profiles or empty state rendered in left panel
 *   • Create + read + delete round-trip
 *   • user_message_template hint mentions {text} placeholder
 *   • Back button navigates to Dashboard
 *
 * Tests are graceful: if admin login fails the whole describe skips.
 */
import { test, expect } from '@playwright/test';

test.describe('Bold MT Profile page', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/login');
    await page.fill('#username', 'admin');
    await page.fill('#password', 'AdminPass1!');
    await page.click('button:has-text("Log in")');
    await page.waitForLoadState('networkidle');
    test.skip(page.url().includes('/login'), 'admin login failed — env credential issue');
  });

  test('Bold layout landmarks present on /mt_profiles', async ({ page }) => {
    await page.goto('/mt_profiles');
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

  test('rail MT item highlighted as active', async ({ page }) => {
    await page.goto('/mt_profiles');
    await page.waitForLoadState('networkidle');
    const mtRail = page.locator('.b-rail a.rail-btn[href="/mt_profiles"]');
    await expect(mtRail).toBeVisible();
    await expect(mtRail).toHaveClass(/\bon\b/);
  });

  test('lists existing MT profiles or empty state', async ({ page }) => {
    await page.goto('/mt_profiles');
    await page.waitForLoadState('networkidle');
    // Wait for at least one profile-row OR an empty-state to appear
    await page.waitForSelector('.profile-row, .empty-title', { timeout: 5_000 });
    const hasContent =
      (await page.locator('.profile-row').count()) +
      (await page.locator('.empty-title').count());
    expect(hasContent).toBeGreaterThan(0);
  });

  test('user_message_template hint mentions {text}', async ({ page }) => {
    await page.goto('/mt_profiles');
    await page.waitForLoadState('networkidle');
    await page.locator('.b-topbar .run-btn').click();
    await expect(page.locator('#user_message_template')).toBeVisible({ timeout: 5_000 });
    // Hint text + the inline <code> {text} chip should be visible
    await expect(page.locator('.field-code', { hasText: '{text}' })).toBeVisible();
  });

  test('create + read + delete round-trip', async ({ page }) => {
    const uniqName = `e2e-mt-${Date.now()}`;
    await page.goto('/mt_profiles');
    await page.waitForLoadState('networkidle');

    // Click + 新增 Profile
    await page.locator('.b-topbar .run-btn').click();
    await expect(page.locator('#name')).toBeVisible({ timeout: 5_000 });

    // Fill name (defaults are valid otherwise — en/en + valid prompts)
    await page.fill('#name', uniqName);
    await page.locator('#input_lang').selectOption('en');
    // output_lang is auto-mirrored by the form; assert it tracks
    await expect(page.locator('#output_lang')).toHaveValue('en');

    // Save
    await page.locator('button[type="submit"]:has-text("Save")').click();

    // Wait for the new row to appear in the list
    await expect(page.locator('.profile-row', { hasText: uniqName })).toBeVisible({
      timeout: 10_000,
    });

    // Click the row to re-load — form should populate
    await page.locator('.profile-row', { hasText: uniqName }).click();
    await expect(page.locator('#name')).toHaveValue(uniqName);

    // Delete via the row's profile-del button
    const row = page.locator('.profile-row', { hasText: uniqName });
    await row.hover();
    await row.locator('.profile-del').click();

    // ConfirmDialog should appear — click Delete
    await page.locator('button:has-text("Delete")').last().click();

    // Row should disappear
    await expect(page.locator('.profile-row', { hasText: uniqName })).toHaveCount(0, {
      timeout: 5_000,
    });
  });

  test('back button returns to Dashboard', async ({ page }) => {
    await page.goto('/mt_profiles');
    await page.waitForLoadState('networkidle');
    await page.locator('.b-topbar .back-btn').click();
    await expect(page).toHaveURL('/', { timeout: 5_000 });
  });
});
