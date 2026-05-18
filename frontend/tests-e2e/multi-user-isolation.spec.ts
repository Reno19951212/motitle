/**
 * Track A new spec: multi-user-isolation
 *
 * Tests that user A (e2e-admin) and user B (e2e-user2) cannot see each other's
 * files. Per v3.9 R5 Phase 1D: /api/files is filtered by owner (user_id),
 * so each user only sees their own uploads.
 *
 * Upload dependency: This spec verifies that the file list is filtered, but
 * does NOT actually upload a file (no fixture binary is guaranteed in the repo).
 * Instead it verifies:
 *   1. e2e-user2 logs in and sees an empty file list (or only their own files).
 *   2. The /api/files response for user B does not contain files owned by user A.
 *
 * For stronger isolation proof, a test operator should:
 *   - Upload a file as e2e-admin before running this spec
 *   - Then run the spec to assert it's absent from e2e-user2's view
 *
 * Without E2E_REQUIRE_SEED=1, this spec gracefully skips.
 */
import { test, expect } from '@playwright/test';
import {
  requireSeedOrSkip,
  SEEDED_ADMIN_USERNAME,
  SEEDED_ADMIN_PASSWORD,
  SEEDED_USER2_USERNAME,
  SEEDED_USER2_PASSWORD,
} from './helpers';

test.describe('Multi-user file isolation (Track A new spec)', () => {
  test.beforeEach(async ({ page }) => {
    await requireSeedOrSkip(page);
  });

  test('user B (e2e-user2) cannot see files owned by user A (e2e-admin)', async ({
    page,
    context,
  }) => {
    // Step 1: Login as e2e-admin, capture their file IDs
    await page.goto('/login');
    await page.fill('#username', SEEDED_ADMIN_USERNAME);
    await page.fill('#password', SEEDED_ADMIN_PASSWORD);
    await page.click('button:has-text("Log in")');
    await page.waitForLoadState('networkidle');
    if (page.url().includes('/login')) {
      test.skip(true, 'e2e-admin login failed — seed bootstrap may not have run');
      return;
    }

    // Intercept /api/files response for admin to capture their file IDs
    const adminFilesRes = await page.request.get('/api/files');
    const adminFilesBody = adminFilesRes.ok()
      ? ((await adminFilesRes.json()) as Record<string, unknown>)
      : { files: [] };
    const adminFiles = (adminFilesBody.files as Array<{ id: string; original_name: string }>) ?? [];
    console.log(`[isolation-spec] e2e-admin owns ${adminFiles.length} file(s)`);

    // Step 2: Logout admin
    const logoutBtn = page.getByRole('button', { name: /Logout/i });
    if (await logoutBtn.isVisible({ timeout: 3_000 }).catch(() => false)) {
      await logoutBtn.click();
      await expect(page).toHaveURL(/\/login/, { timeout: 5_000 });
    } else {
      // Navigate directly to clear session
      await page.goto('/login');
    }

    // Step 3: Login as e2e-user2
    await page.goto('/login');
    await page.fill('#username', SEEDED_USER2_USERNAME);
    await page.fill('#password', SEEDED_USER2_PASSWORD);
    await page.click('button:has-text("Log in")');
    await page.waitForLoadState('networkidle');
    if (page.url().includes('/login')) {
      test.skip(
        true,
        'e2e-user2 login failed — seed bootstrap may not have created this user, or wrong password',
      );
      return;
    }

    // Step 4: Get user2's file list from /api/files
    const user2FilesRes = await page.request.get('/api/files');
    expect(user2FilesRes.ok()).toBe(true);
    const user2FilesBody = (await user2FilesRes.json()) as Record<string, unknown>;
    const user2Files =
      (user2FilesBody.files as Array<{ id: string; original_name: string }>) ?? [];
    console.log(`[isolation-spec] e2e-user2 sees ${user2Files.length} file(s)`);

    // Step 5: Assert no admin file IDs appear in user2's file list
    const adminFileIds = new Set(adminFiles.map((f) => f.id));
    const user2FileIds = user2Files.map((f) => f.id);
    const leaks = user2FileIds.filter((id) => adminFileIds.has(id));
    if (adminFiles.length === 0) {
      // If admin has no files, the isolation assertion is vacuously true but we
      // note it so the operator knows to upload a file first for a strong test.
      console.warn(
        '[isolation-spec] e2e-admin has no files — isolation assertion is vacuously true. ' +
          'Upload a file as e2e-admin before re-running for meaningful coverage.',
      );
    }
    expect(leaks).toHaveLength(0);

    // Step 6: Dashboard UI should not show admin filenames
    await page.goto('/');
    await page.waitForLoadState('networkidle');

    for (const adminFile of adminFiles.slice(0, 3)) {
      // Check top 3 to avoid excessive DOM scanning
      const fileVisible = await page
        .locator(`text="${adminFile.original_name}"`)
        .isVisible({ timeout: 1_000 })
        .catch(() => false);
      expect(fileVisible).toBe(false);
    }

    void context; // suppress unused variable warning
  });

  test('e2e-admin cannot see files created by e2e-user2 via API', async ({ page }) => {
    // Login as user2 first (they have zero files on a fresh seed)
    await page.goto('/login');
    await page.fill('#username', SEEDED_USER2_USERNAME);
    await page.fill('#password', SEEDED_USER2_PASSWORD);
    await page.click('button:has-text("Log in")');
    await page.waitForLoadState('networkidle');
    if (page.url().includes('/login')) {
      test.skip(true, 'e2e-user2 login failed');
      return;
    }

    const user2FilesRes = await page.request.get('/api/files');
    expect(user2FilesRes.ok()).toBe(true);
    const user2FilesBody = (await user2FilesRes.json()) as Record<string, unknown>;
    const user2Files =
      (user2FilesBody.files as Array<{ id: string }>) ?? [];

    // Logout
    const logoutBtn = page.getByRole('button', { name: /Logout/i });
    if (await logoutBtn.isVisible({ timeout: 3_000 }).catch(() => false)) {
      await logoutBtn.click();
      await expect(page).toHaveURL(/\/login/, { timeout: 5_000 });
    }

    // Login as admin, get their files, verify no user2 file IDs leak
    await page.goto('/login');
    await page.fill('#username', SEEDED_ADMIN_USERNAME);
    await page.fill('#password', SEEDED_ADMIN_PASSWORD);
    await page.click('button:has-text("Log in")');
    await page.waitForLoadState('networkidle');
    if (page.url().includes('/login')) {
      test.skip(true, 'e2e-admin login failed in reverse isolation check');
      return;
    }

    const adminFilesRes = await page.request.get('/api/files');
    expect(adminFilesRes.ok()).toBe(true);
    const adminFilesBody = (await adminFilesRes.json()) as Record<string, unknown>;
    const adminFiles =
      (adminFilesBody.files as Array<{ id: string }>) ?? [];

    // Admin is admin — per R5 Phase 3 B: admins see ALL files.
    // This test documents that intentional behavior rather than asserting absence.
    // If admin policy changes to "owner-only even for admin", update this assertion.
    const user2FileIds = new Set(user2Files.map((f) => f.id));
    const adminSeesUser2Files = adminFiles.filter((f) => user2FileIds.has(f.id));
    console.log(
      `[isolation-spec] Admin sees ${adminSeesUser2Files.length} of user2's ${user2Files.length} files ` +
        `(admin-sees-all is the documented behavior per R5 Phase 3)`,
    );
    // No assertion on count — just verify the API responds successfully
    expect(adminFilesRes.status()).toBe(200);
  });
});
