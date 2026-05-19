/**
 * Verify the user-reported "看不到實時字幕" bug is fixed.
 *
 * 1. Dashboard inspector → 實時字幕 tab → renders preview lines (not empty hint)
 * 2. Proofread page (/proofread/<id>) → SegmentTable shows N rows
 *
 * Assumes:
 *   - admin/AdminPass1! exists
 *   - file b9b9e4fad18c (HK racing clip) exists with 97 segments completed
 */
import { test, expect } from '@playwright/test';

const FID = 'b9b9e4fad18c';

test.describe('Transcript visibility (Dashboard inspector + Proofread)', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/login');
    await page.fill('#username', 'admin');
    await page.fill('#password', 'AdminPass1!');
    await page.click('button:has-text("Log in")');
    await expect(page).toHaveURL('/', { timeout: 10_000 });
  });

  test('Dashboard inspector 實時字幕 shows preview lines for selected file', async ({ page }) => {
    // Click the queue item for the HK clip
    const queueRow = page.locator('.queue-item').filter({ hasText: '袁幸堯' }).first();
    await expect(queueRow).toBeVisible({ timeout: 5000 });
    await queueRow.click();

    // Verify inspector is rendering for that file
    const inspector = page.locator('.inspector');
    await expect(inspector).toBeVisible();

    // The 實時字幕 tab is default — assert preview block is NOT showing the
    // legacy "go to proofread" empty state, and IS showing segment rows.
    const scroll = page.locator('.inspector-body.transcript-body .transcript-scroll');
    await expect(scroll).toBeVisible();

    // Wait for at least one segment line to render (not "載入中…").
    // The preview lines have a timestamp span — find one matching m:ss pattern.
    await expect(
      scroll.locator('span').filter({ hasText: /^\d+:\d{2}$/ }).first(),
    ).toBeVisible({ timeout: 5000 });

    // Count timestamp cells — should be 25 (the preview cap) or all if <25.
    const tsCount = await scroll.locator('span').filter({ hasText: /^\d+:\d{2}$/ }).count();
    console.log(`[inspector] timestamp lines visible: ${tsCount}`);
    expect(tsCount).toBeGreaterThanOrEqual(10);

    // Confirm Chinese text content present (袁幸堯 / 賽馬 / 騎師 likely keywords)
    const fullText = await scroll.innerText();
    console.log(`[inspector] first 300 chars: ${fullText.slice(0, 300)}`);
    expect(fullText.length).toBeGreaterThan(50);
  });

  test('Proofread page shows SegmentTable rows', async ({ page }) => {
    await page.goto(`/proofread/${FID}`);
    // Wait for table headers
    await expect(page.locator('th:has-text("#")')).toBeVisible({ timeout: 10_000 });

    // Wait for at least one row + count
    const rows = page.locator('tbody tr');
    await expect(rows.first()).toBeVisible({ timeout: 10_000 });
    const rowCount = await rows.count();
    console.log(`[proofread] segment rows: ${rowCount}`);
    expect(rowCount).toBeGreaterThan(10);

    // Verify header counter shows N segments
    const header = page.locator('text=/\\d+ segments/');
    await expect(header.first()).toBeVisible();
  });
});
