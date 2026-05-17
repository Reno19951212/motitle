// Verifies the queue-cancel flow end-to-end after fixing two bugs:
//   1. File-card cancel button condition: was checking f.status === 'translating'
//      (a value that never occurs) instead of f.translation_status === 'translating'
//   2. cancelJob() previously asked `confirm("取消呢個工作？")` whose own
//      Cancel button is labeled 取消 — users reflexively dismissed the action
const { test, expect } = require("@playwright/test");

const BASE = process.env.BASE_URL || "http://localhost:5001";

async function pickDoneFile(request) {
  const r = await request.get(BASE + "/api/files");
  const files = (await r.json()).files || [];
  // Prefer a 'done' file but accept any file with segments — across ralph
  // runs all files often end up mid-transcribe, but a re-transcribe enqueue
  // works fine on any state (backend resets pipeline state).
  return (
    files.find((f) => f.status === "done") ||
    files.find((f) => (f.segment_count || 0) > 0) ||
    files[0] ||
    null
  );
}

// Pick a file we can run /api/translate on (needs non-zero segments)
async function pickTranslatableFile(request) {
  const r = await request.get(BASE + "/api/files");
  const files = (await r.json()).files || [];
  return files.find((f) => (f.segment_count || 0) > 0) || null;
}

// ---------------------------------------------------------------------------
// 1. Cancel a queued ASR job via the queue panel × button
// ---------------------------------------------------------------------------
test("cancel queued ASR job via queue-panel × button — no confirm, job removed", async ({ page, request }) => {
  test.setTimeout(60_000);
  const target = await pickDoneFile(request);
  if (!target) { test.skip(true, "no done file"); return; }

  const enq = await request.post(BASE + `/api/files/${target.id}/transcribe`, { data: {} });
  expect(enq.status()).toBe(202);
  const { job_id } = await enq.json();

  // No `page.on('dialog')` — the fix removes the confirm() dialog entirely.
  // If a confirm still fires, Playwright auto-dismisses it which would
  // make this test fail.
  await page.goto(BASE + "/");
  await page.waitForSelector(`#queueRow-${job_id}`, { timeout: 10000 });
  await page.locator(`#queuePanel #queueCancelBtn-${job_id}`).click();

  // Poll for removal (queued cancel is synchronous; usually <500ms)
  let removed = false;
  for (let i = 0; i < 20; i++) {
    await new Promise((r) => setTimeout(r, 200));
    const q = await (await request.get(BASE + "/api/queue")).json();
    if (!q.find((j) => j.id === job_id)) { removed = true; break; }
  }
  expect(removed, "queued job should be removed from /api/queue").toBe(true);
});

// ---------------------------------------------------------------------------
// 2. File-card cancel button must appear while MT translation is running
// ---------------------------------------------------------------------------
test("file-card cancel button: regression check for translation_status condition", async ({ page }) => {
  // Pure UI test — doesn't trigger live MT (which puts files into transcribing
  // state and breaks subsequent ralph iters). Directly stages a synthetic
  // file entry with translation_status='translating' + job_id, then asks the
  // dashboard's renderQueue() to render. The cancel button must appear.
  await page.goto(BASE + "/");
  await page.waitForTimeout(500);

  const visible = await page.evaluate(() => {
    // Stash a fake "MT translating" file into uploadedFiles via the window-
    // exposed register helpers. selectFile is a function declaration so it's
    // on window; uploadedFiles itself is `let`-scoped, but we can inject via
    // the same socket file_added handler the backend would normally fire.
    const fakeId = "__bug_test_mt__";
    const fakeFile = {
      id: fakeId,
      original_name: "fake.mp4",
      status: "done",
      translation_status: "translating",
      segment_count: 10,
      approved_count: 0,
      job_id: "fake-job-12345",
    };
    // Use the dashboard's own socket file_added path
    if (window.socket && typeof window.socket.emit === "function") {
      // Fire a synthetic event onto the socket's local handlers
      const handlers = (window.socket._callbacks && window.socket._callbacks["$file_added"]) || [];
      handlers.forEach((h) => h(fakeFile));
    }
    // Trigger render
    if (typeof window.renderQueue === "function") window.renderQueue();
    // Look for the cancel button on the fake file's card
    return !!document.querySelector(`#queueCancelBtn-${fakeFile.job_id}`);
  });

  expect(
    visible,
    "File card should render a cancel button when translation_status='translating' (pre-fix this was missing)"
  ).toBe(true);
});
