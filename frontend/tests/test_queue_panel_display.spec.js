// Queue-panel display regressions (2026-05-31)
//
//  Bug 1 — in the ~278px side panel a single-line row forced the status text
//          to wrap vertically ("進/行/中") and crushed the owner to "a…".
//          Fixed by a two-line row (identity on line 1; step-diagram + nowrap
//          status on line 2).
//  Bug 2 — re-running a file showed the *previous* job's stage because both the
//          backend adapter (per file_id) and the client _progressCache were
//          never invalidated on a new job. Client side: /api/queue is now
//          authoritative for the stage (overwrite on stage change; keep higher
//          pct within a stage).
//
// These drive the real render path by stubbing /api/queue, so no live job /
// timing is involved. Run with: PROBE_USER=admin_p3 PROBE_PASS=TestPass1!
const { test, expect } = require("@playwright/test");

const BASE = process.env.BASE_URL || "http://localhost:5001";

// A single mutable response the stubbed /api/queue returns; tests mutate it
// between steps to simulate job/stage transitions.
function makeJob(over = {}) {
  return {
    id: "job-" + (over.id || "1"),
    file_id: over.file_id || "fX",
    type: over.type || "translate",
    status: over.status || "running",
    position: 0,
    owner_username: over.owner_username || "admin_p3",
    file_name:
      over.file_name ||
      "YTDown.com_YouTube_FIFA-Club-World-Cup-Interview-Haris-Zeb_1080p.mp4",
    progress_pct: over.progress_pct != null ? over.progress_pct : 50,
    stage_label: over.stage_label || "翻譯",
    stage_state: over.stage_state || "active",
    pipeline_kind: over.pipeline_kind || "profile",
    stage_index: over.stage_index != null ? over.stage_index : 1,
    stages:
      over.stages ||
      [
        { key: "transcribe", label: "轉錄" },
        { key: "translate", label: "翻譯" },
        { key: "proofread", label: "校對" },
      ],
  };
}

async function mountWithQueue(page, getBody) {
  await page.route("**/api/queue", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(getBody()),
    });
  });
  await page.goto(BASE + "/");
  await expect(page.locator("#queuePanel")).toBeVisible({ timeout: 8000 });
}

test("Bug 1 @1512: 進行中 status renders on ONE line and owner is not crushed", async ({ page }) => {
  await page.setViewportSize({ width: 1512, height: 982 });
  let body = [makeJob()];
  await mountWithQueue(page, () => body);
  await page.evaluate(() => window.refreshQueue());
  await page.waitForSelector('[data-testid="queue-row"]', { timeout: 5000 });

  const m = await page.evaluate(() => {
    const row = document.querySelector('[data-testid="queue-row"]');
    const spans = [...row.querySelectorAll("span")];
    const statusEl = spans.find((s) => /進行中|排隊|完成/.test(s.textContent.trim()));
    const ownerEl = spans.find((s) => s.title === "admin_p3");
    const lh = parseFloat(getComputedStyle(statusEl).lineHeight) || 16;
    const r = statusEl.getBoundingClientRect();
    return {
      statusText: statusEl.textContent.trim(),
      statusHeight: Math.round(r.height),
      lineHeight: Math.round(lh),
      statusWhiteSpace: getComputedStyle(statusEl).whiteSpace,
      ownerText: ownerEl ? ownerEl.textContent.trim() : null,
    };
  });

  expect(m.statusText).toBe("進行中");
  expect(m.statusWhiteSpace).toBe("nowrap");
  // A vertically-wrapped 3-char CJK status is ~3 line-heights tall; one line
  // must be well under two line-heights.
  expect(m.statusHeight).toBeLessThan(m.lineHeight * 2);
  // Owner must render its real value, not be crushed to a single ellipsised char.
  expect(m.ownerText).toBe("admin_p3");
});

test("Bug 1 @mobile 390px: 進行中 still does not wrap vertically", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  let body = [makeJob()];
  await mountWithQueue(page, () => body);
  await page.evaluate(() => window.refreshQueue());
  await page.waitForSelector('[data-testid="queue-row"]', { timeout: 5000 });

  const h = await page.evaluate(() => {
    const row = document.querySelector('[data-testid="queue-row"]');
    const statusEl = [...row.querySelectorAll("span")].find((s) =>
      /進行中|排隊|完成/.test(s.textContent.trim())
    );
    const lh = parseFloat(getComputedStyle(statusEl).lineHeight) || 16;
    return { height: Math.round(statusEl.getBoundingClientRect().height), lineHeight: Math.round(lh) };
  });
  expect(h.height).toBeLessThan(h.lineHeight * 2);
});

test("Bug 2: /api/queue stage wins over a stale cached stage (asr after translate)", async ({ page }) => {
  await page.setViewportSize({ width: 1512, height: 982 });
  // Start empty so the page's initial poll doesn't seed anything.
  let body = [];
  await mountWithQueue(page, () => body);

  // Prime a STALE cache entry: previous translate job finished at 翻譯 100%.
  await page.evaluate(() => {
    window.__pipelineProgressHandler({
      file_id: "fX",
      pct: 100,
      stage_label: "翻譯",
      stage_state: "active",
      pipeline_kind: "profile",
      stage_index: 1,
      stages: [
        { key: "transcribe", label: "轉錄" },
        { key: "translate", label: "翻譯" },
        { key: "proofread", label: "校對" },
      ],
    });
  });

  // Now a NEW asr job for the same file reports stage 0 (轉錄) at 0%.
  body = [makeJob({ type: "asr", stage_index: 0, stage_label: "轉錄", progress_pct: 0 })];
  await page.evaluate(() => window.refreshQueue());
  await page.waitForSelector('[data-testid="queue-row"]', { timeout: 5000 });

  const activeLabel = await page.evaluate(() => {
    const row = document.querySelector('[data-testid="queue-row"]');
    const el = row.querySelector(".sd-step.sd-active .sd-label");
    return el ? el.textContent.trim() : null;
  });
  // Must reflect the new ASR job (轉錄), NOT the stale translate stage (翻譯).
  expect(activeLabel).toBe("轉錄");
});

test("Bug 2: within the same stage the poll does not drag pct backwards", async ({ page }) => {
  await page.setViewportSize({ width: 1512, height: 982 });
  let body = [];
  await mountWithQueue(page, () => body);

  // Live socket pushed translate stage to 70%.
  await page.evaluate(() => {
    window.__pipelineProgressHandler({
      file_id: "fX",
      pct: 70,
      stage_label: "翻譯",
      stage_state: "active",
      pipeline_kind: "profile",
      stage_index: 1,
      stages: [
        { key: "transcribe", label: "轉錄" },
        { key: "translate", label: "翻譯" },
        { key: "proofread", label: "校對" },
      ],
    });
  });

  // A slightly-older server snapshot (same stage, 50%) arrives via poll.
  body = [makeJob({ stage_index: 1, stage_label: "翻譯", progress_pct: 50 })];
  await page.evaluate(() => window.refreshQueue());

  const pct = await page.evaluate(() => window.__progressCacheGet("fX").pct);
  expect(pct).toBe(70); // kept the higher live value, no backward flicker
});
