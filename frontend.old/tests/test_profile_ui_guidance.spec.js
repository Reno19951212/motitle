// E2E test for v3.16 per-engine preset + danger warning split.
// All four tests target new container IDs introduced in this refactor.
// `test.fixme()` markers stay in until implementation reaches each stage.

const { test, expect } = require("@playwright/test");

const BASE = process.env.BASE_URL || "http://localhost:5001";

// ID of a known shared profile that always exists in the test environment.
// openProfileSaveModal() clones the activeProfile, so an active profile is required.
const _FIXTURE_PROFILE_ID = "prod-default";

async function _openPpsModal(page) {
  // Ensure a profile is active before loading the page.
  // openProfileSaveModal() has an early-return guard `if (!src) return;` where
  // src = activeProfile (loaded by async fetchActiveProfile()). Without an active
  // profile the modal silently does nothing and shows a toast instead.
  await page.request.post(`${BASE}/api/profiles/${_FIXTURE_PROFILE_ID}/activate`);

  await page.goto(BASE + "/");
  await page.waitForLoadState("domcontentloaded");

  // Poll until fetchActiveProfile() has run and openProfileSaveModal() can actually
  // open the overlay. openProfileSaveModal is a function declaration → lives on window.
  await page.waitForFunction(
    () => {
      if (typeof window.openProfileSaveModal !== "function") return false;
      const overlay = document.getElementById("ppsOverlay");
      if (!overlay) return false;
      if (overlay.classList.contains("open")) return true; // already opened
      window.openProfileSaveModal();
      return overlay.classList.contains("open");
    },
    null,
    { timeout: 10000, polling: 300 }
  );
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

test("Custom MT + JS-set parallel_batches=4 triggers parallel-disables-context warning", async ({ page }) => {
  await _openPpsModal(page);

  // Click MT Custom (deactivates any pending), then JS-mutate _pendingMtPreset to set parallel_batches=4
  await page.locator("#ppsMtPresetButtons button", { hasText: "Custom" }).click();
  await page.evaluate(() => {
    // _pendingMtPreset is module-scoped; try window first, then eval fallback
    if ("_pendingMtPreset" in window) {
      window._pendingMtPreset = { config: { parallel_batches: 4 } };
    } else {
      // eval into script scope
      // eslint-disable-next-line no-eval
      eval("_pendingMtPreset = { config: { parallel_batches: 4 } }");
    }
    if (typeof window._scheduleDangerEval === "function") {
      window._scheduleDangerEval();
    } else if (typeof _scheduleDangerEval === "function") {
      // eslint-disable-next-line no-eval
      eval("_scheduleDangerEval()");
    }
  });

  const warning = page.locator(
    "#ppsMtDangerWarnings .pps-warning-chip",
    { hasText: /parallel_batches > 1/ },
  );
  await expect(warning).toBeVisible({ timeout: 3000 });
});

test("Mix-and-match: ASR Accuracy + MT Broadcast Quality both active simultaneously", async ({ page }) => {
  await _openPpsModal(page);

  await page.locator("#ppsAsrPresetButtons button", { hasText: "Accuracy" }).click();
  await page.locator("#ppsMtPresetButtons button", { hasText: "Broadcast Quality" }).click();

  await expect(page.locator("#ppsAsrPresetButtons button.active", { hasText: "Accuracy" })).toBeVisible();
  await expect(page.locator("#ppsMtPresetButtons button.active", { hasText: "Broadcast Quality" })).toBeVisible();

  const summary = await page.locator("#ppsSummary").textContent();
  expect(summary).toContain("large-v3");
  expect(summary).toContain("Broadcast Quality");
});

test("Cross-engine warning: Custom-set word_timestamps=false + Broadcast Quality MT triggers warning", async ({ page }) => {
  await _openPpsModal(page);

  await page.locator("#ppsAsrPresetButtons button", { hasText: "Custom" }).click();
  await page.evaluate(() => {
    if ("_pendingAsrPreset" in window) {
      window._pendingAsrPreset = { config: { word_timestamps: false } };
    } else {
      // eslint-disable-next-line no-eval
      eval("_pendingAsrPreset = { config: { word_timestamps: false } }");
    }
  });
  await page.locator("#ppsMtPresetButtons button", { hasText: "Broadcast Quality" }).click();

  const crossWarning = page.locator(
    "#ppsMtDangerWarnings .pps-warning-chip",
    { hasText: /word_timestamps/ },
  );
  await expect(crossWarning).toBeVisible({ timeout: 3000 });
});
