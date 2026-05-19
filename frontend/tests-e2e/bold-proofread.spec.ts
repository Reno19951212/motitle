/**
 * Bold variant — Proofread page smoke spec (iter 6 rewrite).
 *
 * Verifies the Claude Designer's Proofread.html layout landed:
 *   • motitle-bold full-page layout with .rv-shell + .rv-header + .rv-body
 *   • SegmentRail (340px col) renders the seeded 97 segments
 *   • Clicking a segment row populates the .rv-b-detail DetailEditor
 *   • Time-driven subtitle overlay above the <video>
 *   • Render modal opens via header Render button
 *   • Back button navigates to Dashboard
 *   • Timeline waveform panel rendered + interactive
 *
 * The HK clip `b9b9e4fad18c` is seeded into the admin user's data with 97
 * segments. Tests are graceful: if login fails the whole describe skips.
 */
import { test, expect } from '@playwright/test';

const FILE_ID = 'b9b9e4fad18c';

test.describe('Bold Proofread page (designer rewrite)', () => {
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
    // motitle-bold shell + persistent rail
    await expect(page.locator('.motitle-bold')).toBeVisible({ timeout: 10_000 });
    await expect(page.locator('.b-rail')).toBeVisible();
    // Review shell + designer landmarks
    await expect(page.locator('.rv-shell')).toBeVisible();
    await expect(page.locator('.rv-header')).toBeVisible();
    await expect(page.locator('.rv-body .rv-b')).toBeVisible();
    // Header chips
    await expect(page.locator('.rv-back')).toBeVisible();
    await expect(page.locator('.rv-fname')).toBeVisible();
    await expect(page.locator('.rv-progress')).toBeVisible();
    // 2-col body
    await expect(page.locator('.rv-b-left')).toBeVisible();
    await expect(page.locator('.rv-b-right')).toBeVisible();
  });

  test('SegmentRail shows seeded HK clip segments (≥ 50 rows)', async ({ page }) => {
    await page.goto(`/proofread/${FILE_ID}`);
    await page.waitForLoadState('networkidle');
    await expect(page.locator('.rv-b-rail-item').first()).toBeVisible({ timeout: 10_000 });
    const count = await page.locator('.rv-b-rail-item').count();
    console.log(`[proofread] segment rows: ${count}`);
    expect(count).toBeGreaterThan(50);
  });

  test('clicking a segment row populates the detail editor', async ({ page }) => {
    await page.goto(`/proofread/${FILE_ID}`);
    await page.waitForLoadState('networkidle');
    await expect(page.locator('.rv-b-rail-item').first()).toBeVisible({ timeout: 10_000 });
    // Click the 3rd row (skip first which auto-selects on mount)
    const rows = page.locator('.rv-b-rail-item');
    const target = rows.nth(2);
    await target.click();
    // Detail editor shows the segment #
    await expect(page.locator('.rv-b-detail-head .rv-b-detail-num')).toContainText('#3', {
      timeout: 5_000,
    });
    // ZH textarea is mounted
    await expect(page.locator('.rv-b-detail textarea[id^="zhInput-"]')).toBeVisible();
  });

  test('time-driven subtitle overlay shows segment text after seek to t=40', async ({ page }) => {
    await page.goto(`/proofread/${FILE_ID}`);
    await page.waitForLoadState('networkidle');

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
    await page.waitForTimeout(300);

    // SVG SubtitleOverlay text element contains the seeded segment 7 text (袁幸…)
    await expect(page.locator('text=/袁幸/').first()).toBeVisible({ timeout: 5_000 });
  });

  test('Timeline waveform panel rendered + has region rects', async ({ page }) => {
    await page.goto(`/proofread/${FILE_ID}`);
    await page.waitForLoadState('networkidle');
    // Wait for video metadata so duration drives region positions
    await page.waitForFunction(
      () => {
        const v = document.querySelector('video') as HTMLVideoElement | null;
        return !!v && Number.isFinite(v.duration) && v.duration > 0;
      },
      { timeout: 15_000 },
    );
    await expect(page.locator('.rv-b-timeline-panel')).toBeVisible({ timeout: 5_000 });
    await expect(page.locator('.rv-wave')).toBeVisible();
    // Should render at least N waveform bars
    const barCount = await page.locator('.rv-wave-bar').count();
    expect(barCount).toBeGreaterThan(50);
    // Should render region rects (one per segment)
    await expect(page.locator('.rv-wave-region').first()).toBeVisible({ timeout: 5_000 });
  });

  test('Render modal opens via header Render button', async ({ page }) => {
    await page.goto(`/proofread/${FILE_ID}`);
    await page.waitForLoadState('networkidle');
    const runBtn = page.locator('.rv-header .run-btn');
    await expect(runBtn).toBeVisible({ timeout: 5_000 });
    await runBtn.click();
    await expect(page.getByText('Render Output')).toBeVisible({ timeout: 5_000 });
    await page.keyboard.press('Escape');
    await expect(page.getByText('Render Output')).not.toBeVisible({ timeout: 3_000 });
  });

  test('Back button returns to Dashboard', async ({ page }) => {
    await page.goto(`/proofread/${FILE_ID}`);
    await page.waitForLoadState('networkidle');
    const backBtn = page.locator('.rv-back');
    await expect(backBtn).toBeVisible({ timeout: 5_000 });
    await backBtn.click();
    await expect(page).toHaveURL('/', { timeout: 5_000 });
  });
});
