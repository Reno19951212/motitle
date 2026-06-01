// Sequence file card realtime — live stage-label + streaming caption (2026-06-01).
// Drives page globals (classic <script>): uploadedFiles / activeFileId / renderAll /
// _updateCardCaption / window.__setCardProgress / window.__setCardSubtitle.
// Run with PROBE_USER=admin_p3 PROBE_PASS=TestPass1!
const { test, expect } = require("@playwright/test");
const BASE = process.env.BASE_URL || "http://localhost:5001";

async function seed(page, status) {
  await page.evaluate((st) => {
    uploadedFiles["f-rt"] = { id: "f-rt", original_name: "rt.mp4", status: st,
      active_kind: "pipeline_v6", _local: false };
    activeFileId = "f-rt";
    renderAll();
  }, status);
}

test("card shows live stage-label (name + %) while processing", async ({ page }) => {
  await page.goto(BASE + "/");
  await page.waitForSelector("#queueList", { timeout: 8000 });
  await seed(page, "transcribing");
  await page.evaluate(() => {
    window.__setCardProgress("f-rt", { stages: [{ key: "qwen3", label: "Qwen3 識別" }],
      stage_index: 0, stage_state: "active", pct: 40, stage_label: "Qwen3 識別" });
    renderAll();
  });
  const txt = await page.locator('.queue-item[data-file-id="f-rt"] .card-stage-label').textContent();
  expect(txt).toContain("Qwen3 識別");
  expect(txt).toContain("40%");
});

test("card renders streaming caption from cardSubtitle while processing", async ({ page }) => {
  await page.goto(BASE + "/");
  await page.waitForSelector("#queueList", { timeout: 8000 });
  await seed(page, "transcribing");
  await page.evaluate(() => {
    window.__setCardSubtitle("f-rt", { text: "今晚第五場賽事" });
    renderAll();
  });
  const cap = await page.locator('.queue-item[data-file-id="f-rt"] .card-live-caption').textContent();
  expect(cap).toContain("今晚第五場賽事");
});

test("_updateCardStageLabel creates the stage-label node on demand (live, no re-render)", async ({ page }) => {
  await page.goto(BASE + "/");
  await page.waitForSelector("#queueList", { timeout: 8000 });
  await seed(page, "transcribing");
  // No cardProgress at render time → no .card-stage-label node yet; the live
  // updater must create it (mirrors the pipeline_progress listener path).
  const before = await page.locator('.queue-item[data-file-id="f-rt"] .card-stage-label').count();
  await page.evaluate(() => _updateCardStageLabel("f-rt", "VAD 切段 10%"));
  const txt = await page.locator('.queue-item[data-file-id="f-rt"] .card-stage-label').textContent();
  expect(before).toBe(0);
  expect(txt).toContain("VAD 切段");
  expect(txt).toContain("10%");
});

test("_updateCardCaption live-updates the caption without a full re-render", async ({ page }) => {
  await page.goto(BASE + "/");
  await page.waitForSelector("#queueList", { timeout: 8000 });
  await seed(page, "transcribing");
  await page.evaluate(() => _updateCardCaption("f-rt", "live 串流文字"));
  const cap = await page.locator('.queue-item[data-file-id="f-rt"] .card-live-caption').textContent();
  expect(cap).toContain("live 串流文字");
});

test("caption is NOT shown once the file is done", async ({ page }) => {
  await page.goto(BASE + "/");
  await page.waitForSelector("#queueList", { timeout: 8000 });
  await seed(page, "done");
  await page.evaluate(() => {
    window.__setCardSubtitle("f-rt", { text: "唔應該顯示" });
    renderAll();
  });
  const n = await page.locator('.queue-item[data-file-id="f-rt"] .card-live-caption').count();
  expect(n).toBe(0);
});
