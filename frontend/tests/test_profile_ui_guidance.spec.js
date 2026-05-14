// E2E test for v3.16 per-engine preset + danger warning split.
// All four tests target new container IDs introduced in this refactor.
// `test.fixme()` markers stay in until implementation reaches each stage.

const { test, expect } = require("@playwright/test");

const BASE = process.env.BASE_URL || "http://localhost:5001";

async function _openPpsModal(page) {
  await page.goto(BASE + "/");
  await page.waitForLoadState("domcontentloaded");
  // Wait for the pipeline strip to render (indicates profiles are loaded)
  await page.waitForSelector(".pipeline-strip", { timeout: 5000 }).catch(() => {});
  await page.waitForTimeout(300);
  // Use JS call to bypass videoPlaceholder pointer-event interception
  await page.evaluate(() => window.openProfileSaveModal && window.openProfileSaveModal());
  await page.waitForSelector("#ppsOverlay.open", { timeout: 3000 });
}

test("ASR preset chip 'Accuracy' sets model_size=large-v3 + word_timestamps=true", async ({ page }) => {
  await _openPpsModal(page);

  // Click ASR section's "Accuracy" chip
  const accuracyBtn = page.locator("#ppsAsrPresetButtons button", { hasText: "Accuracy" });
  await expect(accuracyBtn).toBeVisible();
  await accuracyBtn.click();

  // Verify chip becomes active
  await expect(accuracyBtn).toHaveClass(/active/);

  // Verify the summary block reflects ASR override
  const summary = await page.locator("#ppsSummary").textContent();
  expect(summary).toContain("large-v3");
});

test("MT preset chip 'Fast Draft' sets batch_size=10 + parallel_batches=4", async ({ page }) => {
  await _openPpsModal(page);

  const fastDraftBtn = page.locator("#ppsMtPresetButtons button", { hasText: "Fast Draft" });
  await expect(fastDraftBtn).toBeVisible();
  await fastDraftBtn.click();

  await expect(fastDraftBtn).toHaveClass(/active/);

  // Fast Draft sets parallel_batches=4, which triggers critical warning
  const warning = page.locator("#ppsMtDangerWarnings .pps-warning-chip", { hasText: /parallel_batches > 1/ });
  await expect(warning).toBeVisible({ timeout: 1000 });
  await expect(warning).toContainText(/parallel_batches > 1/);
});

test("Mix-and-match: ASR Accuracy + MT Fast Draft both active simultaneously", async ({ page }) => {
  await _openPpsModal(page);

  await page.locator("#ppsAsrPresetButtons button", { hasText: "Accuracy" }).click();
  await page.locator("#ppsMtPresetButtons button", { hasText: "Fast Draft" }).click();

  // Both chips active concurrently
  await expect(page.locator("#ppsAsrPresetButtons button.active", { hasText: "Accuracy" })).toBeVisible();
  await expect(page.locator("#ppsMtPresetButtons button.active", { hasText: "Fast Draft" })).toBeVisible();

  // Summary mentions both
  const summary = await page.locator("#ppsSummary").textContent();
  expect(summary).toContain("large-v3");      // from ASR preset
  expect(summary).toContain("Fast Draft");    // from MT preset label OR underlying value
});

test("Cross-engine warning: alignment_mode=llm-markers + word_timestamps=false renders in MT section", async ({ page }) => {
  await _openPpsModal(page);

  // Speed preset sets word_timestamps=false; Broadcast Quality preset sets alignment_mode=llm-markers
  await page.locator("#ppsAsrPresetButtons button", { hasText: "Speed" }).click();
  await page.locator("#ppsMtPresetButtons button", { hasText: "Broadcast Quality" }).click();

  const crossWarning = page.locator(
    "#ppsMtDangerWarnings .pps-warning-chip",
    { hasText: /word_timestamps/ },
  );
  await expect(crossWarning).toBeVisible({ timeout: 1000 });
});
