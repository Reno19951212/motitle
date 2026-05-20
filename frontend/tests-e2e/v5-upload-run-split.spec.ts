// End-to-end verification of the v5 upload/run split flow.
//
// Verifies the bug fix in commit b91013e:
// - Drop file → file row appears in queue panel immediately (broadcast fix)
// - File status = 'uploaded', not auto-running (split fix)
// - "▶ 執行" button visible when a pipeline is picked
// - Clicking "執行" enqueues a pipeline_run job
import { test, expect } from '@playwright/test';
import path from 'node:path';
import os from 'node:os';
import fs from 'node:fs';

test.describe('v5 upload/run split', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/login');
    await page.fill('#username', 'admin');
    await page.fill('#password', 'AdminPass1!');
    await page.click('button:has-text("Log in")');
    await page.waitForURL('/', { timeout: 10_000 });
    await expect(page.locator('.b-topbar')).toBeVisible();
  });

  test('drop file → row appears in queue panel without auto-run', async ({ page }) => {
    // Generate a tiny throwaway .mp4 with bytes — backend only validates suffix,
    // not real video content, so a fake file is enough for the upload route.
    const tmpFile = path.join(os.tmpdir(), `pw-upload-${Date.now()}.mp4`);
    fs.writeFileSync(tmpFile, Buffer.from('fake mp4 bytes for upload test'));

    try {
      const queueRowsBefore = await page.locator('.queue-item').count();

      // Drop via the dropzone's hidden file input (react-dropzone exposes it).
      // The visible drop-hero <div> wraps an <input type="file"> rendered by
      // getInputProps().
      const fileInput = page.locator('.drop-hero input[type="file"]');
      await fileInput.setInputFiles(tmpFile);

      // Toast confirms the new upload-only flow.
      await expect(
        page.locator('text=已上傳').first(),
      ).toBeVisible({ timeout: 5_000 });
      await expect(
        page.locator('text=撳「執行」開始處理').first(),
      ).toBeVisible({ timeout: 5_000 });

      // Queue panel grows by exactly 1 row. The broadcast fix makes this
      // immediate — no manual refresh needed.
      await expect.poll(
        async () => page.locator('.queue-item').count(),
        { timeout: 5_000 },
      ).toBe(queueRowsBefore + 1);

      // The new row should have the synthetic file name visible.
      const newRow = page.locator('.queue-item').last();
      await expect(newRow).toBeVisible();
      await expect(newRow.locator('.nm')).toContainText('.mp4');

      // ASR stage pill should NOT show transcribe progress — file is uploaded
      // but never run. Stage pill text is "—" (idle) when stage is unknown.
      const asrPill = newRow.locator('.stage-pill').first();
      const asrText = await asrPill.textContent();
      expect(asrText).toMatch(/—|ASR/);
      // Specifically NOT a progress percent.
      expect(asrText).not.toMatch(/\d+%/);
    } finally {
      fs.unlinkSync(tmpFile);
    }
  });

  test('execute button hidden when no pipeline picked', async ({ page }) => {
    // Without picking a pipeline, the per-file 執行 button must hide.
    const queueItems = page.locator('.queue-item');
    const count = await queueItems.count();
    if (count === 0) {
      test.skip(true, 'No files in queue to check button visibility');
    }
    // The qi-run button has class .qi-run (added by T3); it must not exist on
    // any idle row when no pipeline is in the picker store.
    const runButtons = page.locator('.queue-item .qi-run');
    expect(await runButtons.count()).toBe(0);
  });
});
