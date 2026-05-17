// Regression tests for the R6 deep-audit fixes (commit batch following the
// audit agents — race conditions, security, memory, error UX).
const { test, expect, request: pwRequest } = require("@playwright/test");

const BASE = process.env.BASE_URL || "http://localhost:5001";

// ---------------------------------------------------------------------------
// SECURITY
// ---------------------------------------------------------------------------
test("S2 — /api/restart requires admin (was @login_required, trivial DoS)", async () => {
  const editorCtx = await pwRequest.newContext({
    baseURL: BASE,
    storageState: "./playwright-auth-editor.json",
  });
  const r = await editorCtx.post("/api/restart");
  expect(r.status(), `editor should not be able to restart, got ${r.status()}`).toBe(403);
  await editorCtx.dispose();
});

test("S4 — PATCH /api/profiles strips user_id (mass-assignment guard)", async ({ request }) => {
  const created = await request.post(BASE + "/api/profiles", {
    data: {
      name: `R6_mass_assign_${Date.now()}`,
      asr: { engine: "whisper" },
      translation: { engine: "mock" },
    },
  });
  expect(created.status()).toBe(201);
  const pid = (await created.json()).profile.id;
  try {
    // Try to chown the profile to user 99999 — backend MUST drop the field
    const patch = await request.patch(BASE + `/api/profiles/${pid}`, {
      data: { name: "renamed", user_id: 99999 },
    });
    expect(patch.status()).toBe(200);
    const after = (await patch.json()).profile;
    expect(after.user_id, "user_id should NOT have been mass-assigned").not.toBe(99999);
  } finally {
    await request.delete(BASE + `/api/profiles/${pid}`);
  }
});

test("S3 — profile GET strips translation.api_key for non-owner non-admin", async ({ request }) => {
  // Find an admin-owned/shared profile and confirm the editor sees no api_key
  const editorCtx = await pwRequest.newContext({
    baseURL: BASE,
    storageState: "./playwright-auth-editor.json",
  });
  const list = await (await editorCtx.get("/api/profiles")).json();
  for (const p of list.profiles || []) {
    const tx = p.translation || {};
    expect(tx, `api_key leaked for profile ${p.id} (${p.name})`).not.toHaveProperty("api_key");
  }
  await editorCtx.dispose();
});

// ---------------------------------------------------------------------------
// RACE
// ---------------------------------------------------------------------------
test("R10 — _save_registry writes atomically (no half-flushed JSON)", async ({ request }) => {
  // We can only verify indirectly that the file ends in valid JSON after a
  // PATCH that triggers save. (A power-cut crash is hard to simulate from
  // Playwright; this is a smoke check.)
  const files = (await (await request.get(BASE + "/api/files")).json()).files || [];
  const f = files.find((x) => (x.segment_count || 0) > 0);
  if (!f) { test.skip(true, "no file with segments"); return; }
  const ts = (await (await request.get(BASE + `/api/files/${f.id}/translations`)).json()).translations || [];
  if (ts.length === 0) { test.skip(true, "no translations"); return; }
  const r = await request.post(BASE + `/api/files/${f.id}/translations/0/approve`);
  expect(r.status()).toBe(200);
  // Confirm we can read the file back (registry.json deserialized fine)
  const reread = await request.get(BASE + "/api/files");
  expect(reread.status()).toBe(200);
});

test("R2 — DELETE /api/queue/<queued_id> uses atomic UPDATE-WHERE", async ({ request }) => {
  const files = (await (await request.get(BASE + "/api/files")).json()).files || [];
  const f = files.find((x) => (x.segment_count || 0) > 0) || files[0];
  if (!f) { test.skip(true, "no file"); return; }
  const enq = await request.post(BASE + `/api/files/${f.id}/transcribe`, { data: {} });
  expect(enq.status()).toBe(202);
  const { job_id } = await enq.json();

  const del = await request.delete(BASE + `/api/queue/${job_id}`);
  // 200 (was queued, cancelled) OR 202 (worker grabbed it first, cancelling) — both acceptable.
  // Pre-fix the queued path could clobber a worker that had just flipped to running.
  expect([200, 202]).toContain(del.status());
});

// ---------------------------------------------------------------------------
// UX
// ---------------------------------------------------------------------------
test("E2 — 401 on data endpoints redirects to /login.html?next=…", async ({ page }) => {
  // Load the dashboard, then simulate an expired session by calling logout
  // and re-attempting a data endpoint; the auth interceptor should redirect.
  await page.goto(BASE + "/");
  await expect(page).toHaveURL(BASE + "/");
  await page.evaluate(() => fetch("/logout", { method: "POST", credentials: "same-origin" }));
  // Wait a beat for the cookie to clear
  await page.waitForTimeout(200);
  // Trigger a fetch via the interceptor and watch where we end up.
  await page.evaluate(() => fetch("/api/files", { credentials: "same-origin" }));
  await page.waitForURL(/\/login\.html/, { timeout: 5000 });
  expect(page.url()).toContain("/login.html");
  expect(page.url()).toContain("next=");
});
