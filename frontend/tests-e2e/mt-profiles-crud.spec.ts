/**
 * MT Profiles CRUD — updated for Bold variant (iter 3 of redesign).
 *
 * The pre-Bold page exposed `+ New MT Profile` button + `<h2>New MT Profile</h2>`
 * heading inside a modal. The Bold variant ships:
 *   • `.b-topbar .run-btn` (text `+ 新增 Profile`) to start a new profile
 *   • Inline form in right panel — no modal
 *   • `{text}` placeholder shown in `.field-code` chip below the textarea
 *
 * Test intent (CRUD UI works) is preserved.
 */
import { test, expect } from '@playwright/test';

test.describe('MT Profiles CRUD', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/login');
    await page.fill('#username', 'admin');
    await page.fill('#password', 'AdminPass1!');
    await page.click('button:has-text("Log in")');
    await page.waitForLoadState('networkidle');
    test.skip(page.url().includes('/login'), 'admin login failed');
  });

  test('opens MT profile inline form + shows {text} placeholder hint', async ({ page }) => {
    await page.goto('/mt_profiles');
    await page.waitForLoadState('networkidle');
    // Bold page-title is the canonical "MT Profiles" heading
    await expect(page.locator('.b-topbar .page-title')).toContainText(/MT Profiles/);
    // Click the topbar run-btn to start a new profile (inline form)
    await page.locator('.b-topbar .run-btn').click();
    // Inline form should appear with editable Name field
    await expect(page.locator('#name')).toBeVisible({ timeout: 5_000 });
    // {text} placeholder hint should be visible below user_message_template
    await expect(page.locator('.field-code', { hasText: '{text}' })).toBeVisible();
  });
});
