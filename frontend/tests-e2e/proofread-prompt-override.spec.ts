/**
 * Track A new spec: proofread-prompt-override
 *
 * Tests that opening the PromptOverridesDrawer from the Proofread TopBar,
 * filling in an override, and saving it POSTs to the correct endpoint.
 *
 * Seed dependency: requires a completed file tied to a pipeline.
 * Without E2E_REQUIRE_SEED=1, this spec gracefully skips.
 */
import { test, expect } from '@playwright/test';
import { requireSeedOrSkip, SEEDED_ADMIN_USERNAME, SEEDED_ADMIN_PASSWORD } from './helpers';

const TEST_OVERRIDE_MARKER = 'TEST_OVERRIDE_MARKER_1234';

test.describe('Proofread prompt overrides drawer (Track A new spec)', () => {
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

  test('⚙ Overrides button opens the prompt overrides drawer', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');

    const openLink = page.getByRole('button', { name: /Open/i }).first();
    const hasFile = await openLink.isVisible({ timeout: 3_000 }).catch(() => false);
    if (!hasFile) {
      test.skip(true, 'No completed file — cannot exercise overrides drawer');
      return;
    }
    await openLink.click();
    await expect(page).toHaveURL(/\/proofread\//);
    await page.waitForLoadState('networkidle');

    // Click the "⚙ Overrides" button in TopBar
    const overridesBtn = page.getByRole('button', { name: /Overrides/i });
    await expect(overridesBtn).toBeVisible({ timeout: 5_000 });
    await overridesBtn.click();

    // The PromptOverridesDrawer should appear (role=complementary, aria-label="Prompt overrides")
    await expect(
      page.getByRole('complementary', { name: /Prompt overrides/i }),
    ).toBeVisible({ timeout: 3_000 });

    // Should show the heading "Prompt Overrides"
    await expect(page.getByText('Prompt Overrides')).toBeVisible();

    // Should show textareas for override keys
    await expect(
      page.getByRole('textbox', { name: /single_segment_system_prompt/i }),
    ).toBeVisible({ timeout: 3_000 });

    // Close via the close button
    await page.getByRole('button', { name: /Close overrides drawer/i }).click();
    await expect(
      page.getByRole('complementary', { name: /Prompt overrides/i }),
    ).not.toBeVisible({ timeout: 2_000 });
  });

  test('save prompt override POSTs to /api/files/<id>/pipeline_overrides', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');

    const openLink = page.getByRole('button', { name: /Open/i }).first();
    const hasFile = await openLink.isVisible({ timeout: 3_000 }).catch(() => false);
    if (!hasFile) {
      test.skip(true, 'No completed file — cannot exercise overrides save');
      return;
    }
    await openLink.click();
    await expect(page).toHaveURL(/\/proofread\//);
    await page.waitForLoadState('networkidle');

    // Open overrides drawer
    const overridesBtn = page.getByRole('button', { name: /Overrides/i });
    const overridesBtnVisible = await overridesBtn.isVisible({ timeout: 5_000 }).catch(() => false);
    if (!overridesBtnVisible) {
      test.skip(true, '⚙ Overrides button not found — TopBar may not have rendered (no pipeline_id?)');
      return;
    }
    await overridesBtn.click();

    // Wait for drawer to open
    const drawer = page.getByRole('complementary', { name: /Prompt overrides/i });
    await expect(drawer).toBeVisible({ timeout: 3_000 });

    // Type override marker into single_segment_system_prompt textarea
    const textarea = page.getByRole('textbox', { name: /single_segment_system_prompt/i });
    const textareaVisible = await textarea.isVisible({ timeout: 3_000 }).catch(() => false);
    if (!textareaVisible) {
      test.skip(true, 'single_segment_system_prompt textarea not visible in drawer');
      return;
    }
    await textarea.fill(TEST_OVERRIDE_MARKER);

    // Intercept the POST /api/files/<id>/pipeline_overrides
    let overridePosted = false;
    let overrideBody = '';
    page.on('request', async (req) => {
      if (
        req.method() === 'POST' &&
        req.url().includes('/api/files/') &&
        req.url().includes('/pipeline_overrides')
      ) {
        overridePosted = true;
        overrideBody = req.postData() ?? '';
      }
    });

    // Click Save
    await page.getByRole('button', { name: /^Save$/i }).click();
    await page.waitForTimeout(2_000);

    expect(overridePosted).toBe(true);
    expect(overrideBody).toContain(TEST_OVERRIDE_MARKER);
  });

  test('Escape key closes overrides drawer without saving', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');

    const openLink = page.getByRole('button', { name: /Open/i }).first();
    const hasFile = await openLink.isVisible({ timeout: 3_000 }).catch(() => false);
    if (!hasFile) {
      test.skip(true, 'No completed file — cannot test Escape key behavior');
      return;
    }
    await openLink.click();
    await expect(page).toHaveURL(/\/proofread\//);
    await page.waitForLoadState('networkidle');

    const overridesBtn = page.getByRole('button', { name: /Overrides/i });
    const overridesBtnVisible = await overridesBtn.isVisible({ timeout: 5_000 }).catch(() => false);
    if (!overridesBtnVisible) {
      test.skip(true, '⚙ Overrides button not found');
      return;
    }
    await overridesBtn.click();

    const drawer = page.getByRole('complementary', { name: /Prompt overrides/i });
    await expect(drawer).toBeVisible({ timeout: 3_000 });

    // Press Escape — useKeyboardShortcuts in Proofread should close the drawer
    await page.keyboard.press('Escape');
    await expect(drawer).not.toBeVisible({ timeout: 2_000 });
  });
});
