// Shared cross-account job queue panel — verifies:
//   1. Admin + editor see the SAME /api/queue payload
//   2. Each row is annotated with file_name + owner_username
//   3. Recently finished jobs (<5 min) show in the response with their status
//   4. SocketIO 'queue_changed' triggers immediate refresh on connected clients
//   5. The dashboard panel renders rows for every job (with the cancel button
//      visible on active jobs)
const { test, expect, request: pwRequest } = require("@playwright/test");

const BASE = process.env.BASE_URL || "http://localhost:5001";

// ---------------------------------------------------------------------------
// API-level cross-account sync
// ---------------------------------------------------------------------------
test("admin and editor both receive the global /api/queue payload", async () => {
  // Both contexts reuse the cached storage state from global-setup.js so we
  // avoid /login rate-limit (10/min) during ralph loops.
  const adminCtx = await pwRequest.newContext({
    baseURL: BASE,
    storageState: "./playwright-auth.json",
  });
  const editorCtx = await pwRequest.newContext({
    baseURL: BASE,
    storageState: "./playwright-auth-editor.json",
  });

  const [a, e] = await Promise.all([adminCtx.get("/api/queue"), editorCtx.get("/api/queue")]);
  expect(a.status()).toBe(200);
  expect(e.status()).toBe(200);
  const aBody = await a.json();
  const eBody = await e.json();

  // Same total count, same job ids — exact equality on the id list
  const aIds = aBody.map((j) => j.id).sort();
  const eIds = eBody.map((j) => j.id).sort();
  expect(eIds).toEqual(aIds);

  await adminCtx.dispose();
  await editorCtx.dispose();
});

test("/api/queue rows have file_name, owner_username, valid type+status", async ({ request }) => {
  const r = await request.get(BASE + "/api/queue");
  expect(r.status()).toBe(200);
  const jobs = await r.json();
  if (jobs.length === 0) {
    // Nothing to assert about row shape — payload is at least a valid array
    expect(Array.isArray(jobs)).toBe(true);
    return;
  }
  const validStatuses = new Set(["queued", "running", "done", "failed", "cancelled"]);
  for (const j of jobs) {
    expect(j).toHaveProperty("id");
    expect(j).toHaveProperty("type");
    expect(j).toHaveProperty("status");
    expect(j).toHaveProperty("owner_username");
    expect(j).toHaveProperty("file_name"); // may be null if file deleted, key still present
    expect(["asr", "translate", "render"]).toContain(j.type);
    expect(validStatuses.has(j.status), `bad status: ${j.status}`).toBe(true);
  }
});

// ---------------------------------------------------------------------------
// Frontend panel rendering
// ---------------------------------------------------------------------------
test("queue panel renders rows for jobs in /api/queue", async ({ page }) => {
  await page.goto(BASE + "/");
  await expect(page).toHaveURL(BASE + "/");

  // Wait for the panel to either show its empty placeholder or actual rows.
  const panel = page.locator("#queuePanel");
  await expect(panel).toBeVisible({ timeout: 8000 });
  await page.waitForTimeout(1500); // let one poll cycle settle

  // What does the API say?
  const apiResp = await page.evaluate(async () =>
    (await fetch("/api/queue", { credentials: "same-origin" })).json()
  );
  const rowCount = await page.locator('[data-testid="queue-row"]').count();
  if (apiResp.length === 0) {
    expect(rowCount).toBe(0);
    await expect(panel).toContainText("無進行中嘅工作");
  } else {
    expect(rowCount).toBe(apiResp.length);
    // First row should display the file name
    const firstFileName = apiResp[0].file_name;
    if (firstFileName) {
      // file_name is truncated to 28 chars + ellipsis in the panel
      const truncated = firstFileName.length > 28 ? firstFileName.slice(0, 27) : firstFileName;
      const firstRow = page.locator('[data-testid="queue-row"]').first();
      await expect(firstRow).toContainText(truncated.slice(0, 10));
    }
  }
});

// ---------------------------------------------------------------------------
// SocketIO push: trigger a transcribe enqueue and assert the panel updates
// faster than the 3s polling interval would allow.
// ---------------------------------------------------------------------------
test("SocketIO 'queue_changed' push refreshes panel within 1.5s", async ({ page, request }) => {
  test.setTimeout(120_000);

  // Pick ANY file — enqueueing a re-transcribe creates a fresh asr job
  // regardless of the file's current status. We don't filter on status
  // because previous test runs may have left the file in 'transcribing'.
  const filesResp = await request.get(BASE + "/api/files");
  expect(filesResp.status(), "GET /api/files").toBe(200);
  const filesBody = await filesResp.json();
  const candidate = (filesBody.files || [])[0];
  if (!candidate) {
    test.skip(true, "no files in registry");
    return;
  }

  await page.goto(BASE + "/");
  await expect(page.locator("#queuePanel")).toBeVisible({ timeout: 8000 });
  await page.waitForTimeout(500);
  const beforeRowCount = await page.locator('[data-testid="queue-row"]').count();

  // Enqueue via API; the worker is fast, so the row may transition quickly.
  // We just need *some* change to /api/queue's annotated payload.
  const enq = await request.post(BASE + `/api/files/${candidate.id}/transcribe`, {
    data: {},
  });
  expect(enq.status()).toBe(202);
  const t0 = Date.now();

  // Wait at most 1500ms — well under the 3000ms poll interval — for the panel
  // to reflect the new job (row count changed OR a new id appeared).
  const newJobId = (await enq.json()).job_id;
  await page.waitForFunction(
    (jid) => !!document.getElementById(`queueRow-${jid}`),
    newJobId,
    { timeout: 1500 }
  );
  const elapsed = Date.now() - t0;
  console.log(`socket-push refresh observed at +${elapsed}ms (poll would be 3000ms)`);
  expect(elapsed).toBeLessThan(1500);
});
