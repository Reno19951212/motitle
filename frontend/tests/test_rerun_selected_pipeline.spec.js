// Re-run a completed file with the currently-selected pipeline (2026-05-31).
//   1. 執行 button enables for a completed (done/error) selected file.
//   2. 執行 stays disabled while a file is still processing.
//   3. 執行 on a completed file POSTs the re-transcribe endpoint (re-run).
// The dashboard script is a classic <script>, so uploadedFiles / activeFileId /
// selectedFile / updateRunButton / startTranscription are page globals reachable
// by bare name inside page.evaluate. Run with PROBE_USER=admin_p3 PROBE_PASS=TestPass1!
const { test, expect } = require("@playwright/test");

const BASE = process.env.BASE_URL || "http://localhost:5001";

test("執行 enables for a completed selected file", async ({ page }) => {
  await page.goto(BASE + "/");
  await page.waitForSelector("#runBtn", { timeout: 8000 });
  const r = await page.evaluate(() => {
    uploadedFiles["f-done"] = { id: "f-done", status: "done", _local: false };
    activeFileId = "f-done";
    selectedFile = null;
    updateRunButton();
    const b = document.getElementById("runBtn");
    return { disabled: b.disabled, title: b.title };
  });
  expect(r.disabled).toBe(false);
  expect(r.title).toContain("重新執行");
});

test("執行 stays disabled while a file is still transcribing", async ({ page }) => {
  await page.goto(BASE + "/");
  await page.waitForSelector("#runBtn", { timeout: 8000 });
  const disabled = await page.evaluate(() => {
    uploadedFiles["f-busy"] = { id: "f-busy", status: "transcribing", _local: false };
    activeFileId = "f-busy";
    selectedFile = null;
    updateRunButton();
    return document.getElementById("runBtn").disabled;
  });
  expect(disabled).toBe(true);
});

test("執行 on a completed file POSTs the re-transcribe endpoint", async ({ page }) => {
  let hitUrl = null;
  await page.route("**/api/files/*/transcribe", (route) => {
    hitUrl = route.request().url();
    return route.fulfill({
      status: 202,
      contentType: "application/json",
      body: JSON.stringify({ file_id: "f-done", job_id: "j1", status: "queued", queue_position: 0 }),
    });
  });
  await page.goto(BASE + "/");
  await page.waitForSelector("#runBtn", { timeout: 8000 });
  page.on("dialog", (d) => d.accept()); // rerunPipeline confirm()
  await page.evaluate(async () => {
    uploadedFiles["f-done"] = { id: "f-done", status: "done", _local: false };
    activeFileId = "f-done";
    selectedFile = null;
    await startTranscription();
  });
  await page.waitForTimeout(400);
  expect(hitUrl).toContain("/api/files/f-done/transcribe");
});
