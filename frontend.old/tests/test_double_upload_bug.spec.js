// Regression guard for the "second upload doesn't fire without page reload" bug.
//
// Root cause (fixed): startTranscription() set isProcessing=true on entry, then
// relied on the async socket event 'transcription_complete' to reset it. If the
// user uploaded a second file BEFORE that socket event arrived, the guard
// `if (!selectedFile || isProcessing) return` at the top of startTranscription()
// silently blocked the second click.
//
// Post-fix: isProcessing resets synchronously after HTTP 202 is confirmed,
// so a second upload can start immediately after the first HTTP round-trip.
//
// Test strategy: `startTranscription` is declared with `function` keyword inside
// a classic (non-module) <script> tag, so it IS accessible as window.startTranscription.
// However, `isProcessing` is declared with `let` at the same scope — it is NOT on
// window. We therefore verify the fix through observable side-effects:
//   - Mock POST /api/transcribe to return a fake 202 immediately (avoids real ASR work).
//   - Select a file via #fileInput → runBtn becomes enabled.
//   - Click runBtn to trigger startTranscription().
//   - Verify the mock was called the expected number of times.
// For the double-upload test: do this twice in sequence without waiting for socket
// events. Both uploads must reach the mocked endpoint, proving isProcessing was
// reset after the first HTTP 202.

const { test, expect } = require("@playwright/test");

const BASE = process.env.BASE_URL || "http://localhost:5001";

// Minimal valid WAV file header — passes extension + mime validation.
const _WAV_BUF = Buffer.from([
  0x52, 0x49, 0x46, 0x46, 0x24, 0x00, 0x00, 0x00,
  0x57, 0x41, 0x56, 0x45, 0x66, 0x6d, 0x74, 0x20,
  0x10, 0x00, 0x00, 0x00, 0x01, 0x00, 0x01, 0x00,
  0x44, 0xac, 0x00, 0x00, 0x88, 0x58, 0x01, 0x00,
  0x02, 0x00, 0x10, 0x00, 0x64, 0x61, 0x74, 0x61,
  0x00, 0x00, 0x00, 0x00,
]);

/**
 * Helper: Install a fake route for POST /api/transcribe that returns a 202
 * with a synthetic file_id. Tracks how many times the handler fired.
 * Returns a getter function `callCount()`.
 */
async function installMockTranscribe(page, fakeFileId) {
  let count = 0;
  await page.route("**/api/transcribe", async (route) => {
    if (route.request().method() !== "POST") { await route.continue(); return; }
    count++;
    await route.fulfill({
      status: 202,
      contentType: "application/json",
      body: JSON.stringify({
        file_id: fakeFileId,
        job_id: `fake-job-${fakeFileId}`,
        status: "queued",
        queue_position: 0,
      }),
    });
  });
  return () => count;
}

// ---------------------------------------------------------------------------
// Test 1 — isProcessing resets after HTTP 202, NOT waiting for socket event
// ---------------------------------------------------------------------------
test("isProcessing flag resets synchronously after HTTP 202 (not waiting for socket)", async ({ page }) => {
  const fakeId = `fake-file-${Date.now()}`;
  const callCount = await installMockTranscribe(page, fakeId);

  await page.goto(BASE + "/");
  await page.waitForLoadState("domcontentloaded");
  // Give socket.io a moment to connect (startTranscription checks socket.connected)
  await page.waitForTimeout(800);

  // 1. Select a file via the hidden #fileInput → triggers handleFileSelect → sets selectedFile
  await page.setInputFiles("#fileInput", {
    name: "single_upload_test.wav",
    mimeType: "audio/wav",
    buffer: _WAV_BUF,
  });

  // runBtn becomes enabled once a pending file is staged
  await expect(page.locator("#runBtn")).toBeEnabled({ timeout: 3000 });

  // 2. Click runBtn → startTranscription() runs
  await page.click("#runBtn");

  // 3. Wait for the mocked 202 to be processed (the success path runs synchronously after)
  //    Give up to 3 s for the HTTP round-trip + JS success path to complete.
  await page.waitForFunction(() => {
    // After success path: selectedFile is cleared + __pending__ is deleted.
    // The runBtn should be disabled again (no pending local file any more).
    const btn = document.getElementById("runBtn");
    return btn && btn.disabled;
  }, { timeout: 3000 });

  // The mock was hit exactly once
  expect(callCount(), "mock transcribe endpoint should have been called once").toBe(1);

  // KEY: try to select a second file immediately — if isProcessing were still
  // true this would queue a file but startTranscription() would return early on
  // the next click, and the mock count would stay at 1.
  await page.setInputFiles("#fileInput", {
    name: "second_upload_test.wav",
    mimeType: "audio/wav",
    buffer: _WAV_BUF,
  });
  await expect(page.locator("#runBtn")).toBeEnabled({ timeout: 3000 });
  await page.click("#runBtn");

  // Wait for the second HTTP round-trip too
  await page.waitForTimeout(1000);

  // The mock must have been called a second time — proves isProcessing was reset
  expect(
    callCount(),
    "mock transcribe must be called TWICE; second call blocked means isProcessing was not reset",
  ).toBe(2);
});

// ---------------------------------------------------------------------------
// Test 2 — Two consecutive uploads both produce file_ids without page reload
// ---------------------------------------------------------------------------
test("two consecutive uploads both reach the transcribe endpoint (no page reload)", async ({ page }) => {
  const ids = [`fake-seq-1-${Date.now()}`, `fake-seq-2-${Date.now()}`];
  let callIdx = 0;
  const callCount = await installMockTranscribe(page, ids[0]); // first call uses ids[0]

  // Override: second call returns ids[1]
  await page.unrouteAll();
  let hitCount = 0;
  await page.route("**/api/transcribe", async (route) => {
    if (route.request().method() !== "POST") { await route.continue(); return; }
    const fid = ids[hitCount] || ids[ids.length - 1];
    hitCount++;
    await route.fulfill({
      status: 202,
      contentType: "application/json",
      body: JSON.stringify({
        file_id: fid,
        job_id: `fake-job-${hitCount}`,
        status: "queued",
        queue_position: 0,
      }),
    });
  });

  await page.goto(BASE + "/");
  await page.waitForLoadState("domcontentloaded");
  await page.waitForTimeout(800);

  for (let i = 0; i < 2; i++) {
    await page.setInputFiles("#fileInput", {
      name: `batch_upload_${i}.wav`,
      mimeType: "audio/wav",
      buffer: _WAV_BUF,
    });
    await expect(page.locator("#runBtn")).toBeEnabled({ timeout: 3000 });
    await page.click("#runBtn");

    // Wait for the success path to complete (button disabled = pending cleared)
    await page.waitForFunction(() => {
      const btn = document.getElementById("runBtn");
      return btn && btn.disabled;
    }, { timeout: 4000 });
  }

  expect(
    hitCount,
    `both uploads must reach the endpoint; hitCount=${hitCount} (expected 2). If 1, isProcessing was not reset between uploads.`,
  ).toBe(2);
});
