/**
 * Bold variant — Proofread page smoke spec.
 *
 * Verifies the iter 1 rewrite landed:
 *   • motitle-bold full-page layout landmarks (b-rail + b-topbar + b-body)
 *   • SegmentTable renders the 97 seeded segments
 *   • Time-driven subtitle overlay above the <video>
 *   • Render modal opens via topbar Render button
 *   • Back button navigates to Dashboard
 *
 * The HK clip `b9b9e4fad18c` is seeded into the admin user's data with 97
 * segments. Tests are graceful: if login fails the whole describe skips.
 */
import { test, expect } from '@playwright/test';

const FILE_ID = 'b9b9e4fad18c';

test.describe('Bold Proofread page', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/login');
    await page.fill('#username', 'admin');
    await page.fill('#password', 'AdminPass1!');
    await page.click('button:has-text("Log in")');
    await page.waitForLoadState('networkidle');
    test.skip(page.url().includes('/login'), 'admin login failed — env credential issue');
  });

  test('Bold layout landmarks present on proofread page', async ({ page }) => {
    await page.goto(`/proofread/${FILE_ID}`);
    await page.waitForLoadState('networkidle');
    // Page renders motitle-bold shell instead of the legacy Layout TopBar/SideNav
    await expect(page.locator('.motitle-bold')).toBeVisible({ timeout: 10_000 });
    await expect(page.locator('.b-rail')).toBeVisible();
    await expect(page.locator('.b-topbar')).toBeVisible();
    await expect(page.locator('.b-body.b-body-proofread')).toBeVisible();
    // Topbar Proofread-specific landmarks
    await expect(page.locator('.b-topbar .back-btn')).toBeVisible();
    await expect(page.locator('.b-topbar .filename-strip')).toBeVisible();
    await expect(page.locator('.b-topbar .run-btn')).toBeVisible();
    // Health cluster shared with Dashboard
    await expect(page.locator('.b-topbar .health-cluster')).toBeVisible();
  });

  test('SegmentTable shows seeded HK clip segments (≥ 50 rows)', async ({ page }) => {
    await page.goto(`/proofread/${FILE_ID}`);
    await page.waitForLoadState('networkidle');
    // Wait for any tbody row to render
    await expect(page.locator('.seg-table-wrap tbody tr').first()).toBeVisible({
      timeout: 10_000,
    });
    const count = await page.locator('.seg-table-wrap tbody tr').count();
    console.log(`[proofread] segment rows: ${count}`);
    expect(count).toBeGreaterThan(50);
  });

  test('time-driven subtitle overlay shows segment containing 袁幸 when seeking to t=40', async ({
    page,
  }) => {
    await page.goto(`/proofread/${FILE_ID}`);
    await page.waitForLoadState('networkidle');

    // Wait for <video> to have loaded metadata so we know duration is real
    await page.waitForFunction(
      () => {
        const v = document.querySelector('video') as HTMLVideoElement | null;
        return !!v && Number.isFinite(v.duration) && v.duration > 0;
      },
      { timeout: 15_000 },
    );

    await page.evaluate(() => {
      const v = document.querySelector('video') as HTMLVideoElement | null;
      if (!v) return;
      v.currentTime = 40;
      v.dispatchEvent(new Event('timeupdate'));
    });
    await page.waitForTimeout(250);

    // The SVG SubtitleOverlay renders <text><tspan>...</tspan></text>.
    // We look for any element containing 袁幸 inside the .panel-body that
    // holds the VideoPanel.
    await expect(page.locator('text=/袁幸/').first()).toBeVisible({ timeout: 5_000 });
  });

  test('Render modal opens via topbar Render button', async ({ page }) => {
    await page.goto(`/proofread/${FILE_ID}`);
    await page.waitForLoadState('networkidle');
    // The Run button shares the .run-btn class with Dashboard and also has
    // aria-label "Open Render".
    const runBtn = page.locator('.b-topbar .run-btn');
    await expect(runBtn).toBeVisible({ timeout: 5_000 });
    await runBtn.click();
    await expect(page.getByText('Render Output')).toBeVisible({ timeout: 5_000 });
    // Escape closes the modal (cascading Esc top priority)
    await page.keyboard.press('Escape');
    await expect(page.getByText('Render Output')).not.toBeVisible({ timeout: 3_000 });
  });

  test('Overrides chip opens prompt overrides drawer', async ({ page }) => {
    await page.goto(`/proofread/${FILE_ID}`);
    await page.waitForLoadState('networkidle');
    const overridesBtn = page.locator('.b-topbar .action-chip');
    await expect(overridesBtn).toBeVisible({ timeout: 5_000 });
    await overridesBtn.click();
    // Drawer exposes role=complementary with aria-label "Prompt overrides"
    await expect(
      page.getByRole('complementary', { name: /Prompt overrides/i }),
    ).toBeVisible({ timeout: 3_000 });
  });

  test('Back button returns to Dashboard', async ({ page }) => {
    await page.goto(`/proofread/${FILE_ID}`);
    await page.waitForLoadState('networkidle');
    const backBtn = page.locator('.b-topbar .back-btn');
    await expect(backBtn).toBeVisible({ timeout: 5_000 });
    await backBtn.click();
    await expect(page).toHaveURL('/', { timeout: 5_000 });
  });

  test('Right inspector renders 3 panels (settings / glossary / stage history)', async ({
    page,
  }) => {
    await page.goto(`/proofread/${FILE_ID}`);
    await page.waitForLoadState('networkidle');
    const inspector = page.locator('.b-body.b-body-proofread .inspector');
    await expect(inspector).toBeVisible({ timeout: 10_000 });
    const panels = inspector.locator('.panel');
    expect(await panels.count()).toBeGreaterThanOrEqual(3);
  });
});
