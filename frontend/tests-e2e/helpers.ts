import { test as base } from '@playwright/test';

/**
 * Helper called at top of seed-dependent tests.
 * If E2E_REQUIRE_SEED env is set to "1", any missing prereq throws (hard fail).
 * Otherwise, test.skip() is called (graceful skip for CI / no-seed env).
 *
 * Usage:
 *   test('something', async ({ page }) => {
 *     await requireSeedOrSkip(page);
 *     // ... rest of test
 *   });
 */
export async function requireSeedOrSkip(_page: import('@playwright/test').Page): Promise<void> {
  const requireSeed = process.env.E2E_REQUIRE_SEED === '1';
  if (!requireSeed) {
    base.skip(true, 'E2E_REQUIRE_SEED not set; skipping seed-dependent test');
  }
  // In seeded mode, no skip — tests proceed and any failure surfaces a real bug.
}

export const SEEDED_ADMIN_USERNAME = 'e2e-admin';
export const SEEDED_ADMIN_PASSWORD = 'TestPass1!';
export const SEEDED_USER2_USERNAME = 'e2e-user2';
export const SEEDED_USER2_PASSWORD = 'TestPass2!';
export const BASE_URL = process.env.BASE_URL ?? 'http://localhost:5001';
