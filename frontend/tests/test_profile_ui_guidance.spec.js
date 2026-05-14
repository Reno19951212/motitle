// Profile modal preset picker + danger combo warnings
// Uses storageState (admin logged in via global-setup.js)
const { test, expect } = require("@playwright/test");

const BASE = process.env.BASE_URL || "http://localhost:5001";

async function openPpsModal(page) {
  await page.goto(BASE + "/");
  // Wait for the user chip — confirms we're authenticated and page loaded
  await page.waitForSelector('[data-testid="user-chip"]', { timeout: 10000 });
  // Wait for openProfileSaveModal function to be defined
  await page.waitForFunction(
    () => typeof window.openProfileSaveModal === "function",
    { timeout: 10000 }
  );
  // Give the initial fetch chain a moment to settle (fetchActiveProfile etc.)
  await page.waitForTimeout(1500);
  // Inject a stub activeProfile if none loaded (prevents modal early-return)
  await page.evaluate(() => {
    // activeProfile is a let inside the script block — not on window.
    // We can tell if it's null by inspecting ppsSummary after modal open.
    // Ensure openProfileSaveModal has something to work with.
    // The function already handles null activeProfile (shows toast), but
    // we need to patch it for the test environment where no profile may exist.
    // Instead call it — if it toasts we know there's no profile.
  });
  // Try to open modal — if activeProfile is null the function shows a toast
  // and returns early; in that case we patch and retry.
  const opened = await page.evaluate(() => {
    try {
      openProfileSaveModal();
      return true;
    } catch (e) {
      return false;
    }
  });
  if (!opened) throw new Error("openProfileSaveModal threw");

  // If modal didn't open (null activeProfile toast), patch and retry
  const isOpen = await page.locator("#ppsOverlay.open").isVisible().catch(() => false);
  if (!isOpen) {
    // Patch: directly open overlay and init UI
    await page.evaluate(() => {
      // Minimal stub so modal can open
      window._stubActiveProfile = {
        asr: { engine: "whisper", model_size: "large-v3", condition_on_previous_text: false },
        translation: { engine: "mock", batch_size: 5, parallel_batches: 1, translation_passes: 1, alignment_mode: "" },
        font: { family: "Noto Sans TC", size: 36, subtitle_source: "auto", bilingual_order: "en_top" },
        name: "Stub Profile", description: "", id: "stub-id",
      };
      // Temporarily override activeProfile read inside openProfileSaveModal
      // by injecting it as the src variable indirectly via a temp global
      // We can't patch let directly, so we trigger via manage modal's + button
      // which calls openProfileSaveModal(). Let's directly manipulate the DOM instead.
      const overlay = document.getElementById("ppsOverlay");
      if (overlay) {
        document.getElementById("ppsName").value = "Test Preset";
        document.getElementById("ppsDesc").value = "";
        document.getElementById("ppsSummary").innerHTML = "ASR — (—)<br>MT —<br>術語表 無<br>字型 —";
        document.getElementById("ppsSaveBtn").textContent = "儲存並啟用";
        document.getElementById("ppsSubtitleSource").value = "auto";
        document.getElementById("ppsBilingualOrderRow").style.display = "none";
        overlay.classList.add("open");
        // Init preset UI
        if (typeof _initPpsPresetUI === "function") _initPpsPresetUI();
        if (typeof _evaluateDangerCombos === "function") _evaluateDangerCombos();
      }
    });
  }

  await page.waitForSelector("#ppsOverlay.open", { timeout: 5000 });
  await page.waitForSelector("#ppsPresetButtons .pps-preset-btn", { timeout: 3000 });
}

test("preset picker: clicking Broadcast Quality marks button active and updates summary with batch=1", async ({ page }) => {
  await openPpsModal(page);

  // All 5 preset buttons should be present
  const allBtns = page.locator(".pps-preset-btn");
  await expect(allBtns).toHaveCount(5);

  // Click "Broadcast Quality" preset
  const broadcastBtn = page.locator(".pps-preset-btn", { hasText: "Broadcast Quality" });
  await expect(broadcastBtn).toBeVisible();
  await broadcastBtn.click();

  // Button should become active
  await expect(broadcastBtn).toHaveClass(/active/);

  // Summary should show batch=1 (Broadcast Quality has batch_size=1)
  const summary = page.locator("#ppsSummary");
  await expect(summary).toContainText("batch");
  await expect(summary).toContainText("1");

  // Summary should also mention llm-markers
  await expect(summary).toContainText("llm-markers");

  // Description field should be auto-populated
  const descValue = await page.locator("#ppsDesc").inputValue();
  expect(descValue.length).toBeGreaterThan(5);

  // Clicking Custom resets active state
  const customBtn = page.locator(".pps-preset-btn", { hasText: "Custom" });
  await customBtn.click();
  await expect(customBtn).toHaveClass(/active/);
  await expect(broadcastBtn).not.toHaveClass(/active/);

  // Save button remains enabled (warnings are advisory, not blocking)
  await expect(page.locator("#ppsSaveBtn")).toBeEnabled();
});

test("danger warning: fast-draft preset (parallel_batches=4) triggers critical warning chip that can be dismissed", async ({ page }) => {
  await openPpsModal(page);

  // Click "Fast Draft" — parallel_batches=4 triggers 'parallel-disables-context' critical warning
  const fastDraftBtn = page.locator(".pps-preset-btn", { hasText: "Fast Draft" });
  await expect(fastDraftBtn).toBeVisible();
  await fastDraftBtn.click();

  // Wait for debounced warning evaluation (200ms + buffer)
  await page.waitForTimeout(500);

  // A critical warning chip should appear
  const criticalChip = page.locator("#ppsWarnings .pps-warning-chip.critical");
  await expect(criticalChip).toBeVisible({ timeout: 2000 });

  // The warning message should mention parallel_batches
  await expect(criticalChip).toContainText("parallel_batches");

  // Dismiss button should be present
  const dismissBtn = criticalChip.locator(".pps-warn-dismiss");
  await expect(dismissBtn).toBeVisible();
  await dismissBtn.click();

  // After dismiss, the chip should be gone
  await expect(criticalChip).not.toBeVisible();

  // Save button remains enabled — warnings don't block saving
  await expect(page.locator("#ppsSaveBtn")).toBeEnabled();
});
