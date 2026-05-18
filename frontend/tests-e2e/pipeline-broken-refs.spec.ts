/**
 * Track A new spec: pipeline-broken-refs
 *
 * Tests that after deleting an ASR profile that a pipeline references,
 * the Pipelines page shows a "broken ref" badge on that pipeline row.
 *
 * Per Pipelines.tsx line 144:
 *   <Badge variant="destructive">{brokenRefCount(r.broken_refs)} broken ref</Badge>
 *
 * Seed dependency: requires the seeded ASR Profile + Pipeline from global-setup.
 * Without E2E_REQUIRE_SEED=1, this spec gracefully skips.
 *
 * DESTRUCTIVE NOTE: This test deletes the seeded ASR profile. Re-run global-setup
 * or seed-e2e.sh to restore seed state before running other seed-dependent specs.
 */
import { test, expect } from '@playwright/test';
import { requireSeedOrSkip, SEEDED_ADMIN_USERNAME, SEEDED_ADMIN_PASSWORD } from './helpers';

test.describe('Pipeline broken-refs indicator (Track A new spec)', () => {
  test.beforeEach(async ({ page }) => {
    await requireSeedOrSkip(page);
    await page.goto('/login');
    await page.fill('#username', SEEDED_ADMIN_USERNAME);
    await page.fill('#password', SEEDED_ADMIN_PASSWORD);
    await page.click('button:has-text("Log in")');
    await page.waitForLoadState('networkidle');
    if (page.url().includes('/login')) {
      test.skip(true, 'e2e-admin login failed — seed bootstrap may not have run');
    }
  });

  test('pipeline shows broken ref badge after its ASR profile is deleted', async ({ page }) => {
    // Step 1: Navigate to /asr_profiles and find the seeded "E2E Whisper Profile"
    await page.goto('/asr_profiles');
    await page.waitForLoadState('networkidle');

    const profileRow = page.locator('tr, [role="row"]').filter({
      hasText: 'E2E Whisper Profile',
    });
    const profileRowVisible = await profileRow.isVisible({ timeout: 5_000 }).catch(() => false);
    if (!profileRowVisible) {
      test.skip(
        true,
        'Seeded "E2E Whisper Profile" not found on /asr_profiles — seed may not have run',
      );
      return;
    }

    // Step 2: Click the Delete button for this profile
    // EntityTable renders a "Delete" button per row
    const deleteBtn = profileRow.getByRole('button', { name: /Delete/i });
    const deleteBtnVisible = await deleteBtn.isVisible({ timeout: 3_000 }).catch(() => false);
    if (!deleteBtnVisible) {
      test.skip(true, 'Delete button not found for E2E Whisper Profile row');
      return;
    }
    await deleteBtn.click();

    // Confirm deletion dialog — ConfirmDialog renders a "Confirm" or "Delete" button
    const confirmBtn = page
      .getByRole('button', { name: /Confirm|Delete|Yes/i })
      .last();
    const confirmVisible = await confirmBtn.isVisible({ timeout: 3_000 }).catch(() => false);
    if (confirmVisible) {
      await confirmBtn.click();
    }
    await page.waitForLoadState('networkidle');

    // Step 3: Navigate to /pipelines
    await page.goto('/pipelines');
    await page.waitForLoadState('networkidle');

    // Step 4: The seeded "E2E Test Pipeline" row should now show a broken ref badge
    const pipelineRow = page.locator('tr, [role="row"]').filter({
      hasText: 'E2E Test Pipeline',
    });
    const pipelineRowVisible = await pipelineRow.isVisible({ timeout: 5_000 }).catch(() => false);
    if (!pipelineRowVisible) {
      test.skip(
        true,
        'Seeded "E2E Test Pipeline" not found on /pipelines — seed may not have run or pipeline was not created due to 409 on ASR/MT profiles',
      );
      return;
    }

    // The Badge with "broken ref" text should be visible in that row
    // Pipelines.tsx: <Badge variant="destructive">{brokenRefCount} broken ref</Badge>
    await expect(pipelineRow.locator('text=/broken ref/i')).toBeVisible({ timeout: 5_000 });
  });
});
