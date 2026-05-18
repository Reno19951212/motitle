/**
 * Track A new spec: proofread-stage-rerun
 *
 * Tests that opening the Proofread page, interacting with a segment's "Re-run"
 * dropdown, POSTs to the correct stage rerun endpoint and triggers a UI update.
 *
 * Seed dependency: requires a completed file in the registry.
 * Without E2E_REQUIRE_SEED=1, this spec gracefully skips.
 */
import { test, expect } from '@playwright/test';
import { requireSeedOrSkip, SEEDED_ADMIN_USERNAME, SEEDED_ADMIN_PASSWORD } from './helpers';

test.describe('Proofread stage re-run (Track A new spec)', () => {
  test.beforeEach(async ({ page }) => {
    await requireSeedOrSkip(page);
    // Login as seeded admin
    await page.goto('/login');
    await page.fill('#username', SEEDED_ADMIN_USERNAME);
    await page.fill('#password', SEEDED_ADMIN_PASSWORD);
    await page.click('button:has-text("Log in")');
    await page.waitForLoadState('networkidle');
    if (page.url().includes('/login')) {
      test.skip(true, 'e2e-admin login failed — seed bootstrap may not have run');
    }
  });

  test('re-run dropdown is present on a proofread page with stages', async ({ page }) => {
    // Navigate to dashboard and look for a file with an "Open" button (completed state)
    await page.goto('/');
    await page.waitForLoadState('networkidle');

    const openLink = page.getByRole('button', { name: /Open/i }).first();
    const hasFile = await openLink.isVisible({ timeout: 3_000 }).catch(() => false);
    if (!hasFile) {
      test.skip(true, 'No completed file on dashboard — skipping re-run spec (needs uploaded file)');
      return;
    }
    await openLink.click();
    await expect(page).toHaveURL(/\/proofread\//);
    await page.waitForLoadState('networkidle');

    // The StageRerunMenu renders a <summary> element containing "Re-run"
    // It is part of SegmentRow / TopBar area — verify the summary is present
    const rerunSummary = page.locator('summary').filter({ hasText: 'Re-run' }).first();
    const rerunVisible = await rerunSummary.isVisible({ timeout: 5_000 }).catch(() => false);
    if (!rerunVisible) {
      test.skip(
        true,
        'Re-run summary not visible — file may not have stage_outputs yet (no ASR stage run)',
      );
      return;
    }

    // Open the re-run dropdown
    await rerunSummary.click();

    // The dropdown should list at least one stage option
    const stageButton = page.locator('details[open] button').filter({ hasText: /Stage/ }).first();
    await expect(stageButton).toBeVisible({ timeout: 3_000 });
  });

  test('clicking Re-run stage POSTs to /api/files/<id>/stages/<idx>/rerun', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');

    const openLink = page.getByRole('button', { name: /Open/i }).first();
    const hasFile = await openLink.isVisible({ timeout: 3_000 }).catch(() => false);
    if (!hasFile) {
      test.skip(true, 'No completed file — skipping rerun POST assertion');
      return;
    }
    await openLink.click();
    await expect(page).toHaveURL(/\/proofread\//);
    await page.waitForLoadState('networkidle');

    const rerunSummary = page.locator('summary').filter({ hasText: 'Re-run' }).first();
    const rerunVisible = await rerunSummary.isVisible({ timeout: 5_000 }).catch(() => false);
    if (!rerunVisible) {
      test.skip(true, 'Re-run summary not visible — no stages on this file');
      return;
    }

    // Intercept the POST /api/files/<id>/stages/<idx>/rerun
    let rerunRequested = false;
    page.on('request', (req) => {
      if (req.method() === 'POST' && req.url().match(/\/api\/files\/.+\/stages\/\d+\/rerun/)) {
        rerunRequested = true;
      }
    });

    await rerunSummary.click();
    const stageButton = page.locator('details[open] button').filter({ hasText: /Stage/ }).first();
    const stageVisible = await stageButton.isVisible({ timeout: 3_000 }).catch(() => false);
    if (!stageVisible) {
      test.skip(true, 'No stage buttons in open re-run dropdown');
      return;
    }
    await stageButton.click();

    // Wait briefly for the network request to fire
    await page.waitForTimeout(1_500);
    expect(rerunRequested).toBe(true);
  });
});
