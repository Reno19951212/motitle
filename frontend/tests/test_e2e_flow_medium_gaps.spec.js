// E2E flow-coverage — MEDIUM-risk follow-up to test_e2e_flow_gaps.spec.js.
// Three runtime regression guards for fixes that previously only had
// source-level assertions (grepping the JS file) or no test at all:
//
//   1. WebSocket rebind on socket swap (bd90a6d M5/M6). When the dashboard's
//      restartService replaces window.socket, queue-panel.js's 1s rebind
//      poll must detach from the dead instance and re-attach 'queue_changed'
//      to the new one. Pre-fix used a `_socketBound` boolean flag that
//      locked binding to the first instance ever seen.
//
//   2. Concurrent file-level PATCH consistency (R1 in 14d5000). Two parallel
//      PATCH /api/files/<id> writes (subtitle_source) must both 200 AND
//      converge to one of the written values. Adjacent registry fields
//      (status, original_name, user_id) must remain intact. Pre-fix the
//      registry RMW could lose data when two requests interleaved.
//
//   3. Glossary scan no-op (the route was added during R1 but never
//      regression-tested for the empty-violation case — verify the response
//      shape doesn't crash when there's nothing to flag).

const { test, expect, request: pwRequest } = require("@playwright/test");

const BASE = process.env.BASE_URL || "http://localhost:5001";
const EDITOR_AUTH = "./playwright-auth-editor.json";

const _WAV_HEADER = Buffer.from([
  0x52, 0x49, 0x46, 0x46, 0x24, 0x00, 0x00, 0x00,
  0x57, 0x41, 0x56, 0x45, 0x66, 0x6d, 0x74, 0x20,
  0x10, 0x00, 0x00, 0x00, 0x01, 0x00, 0x01, 0x00,
  0x44, 0xac, 0x00, 0x00, 0x88, 0x58, 0x01, 0x00,
  0x02, 0x00, 0x10, 0x00, 0x64, 0x61, 0x74, 0x61,
  0x00, 0x00, 0x00, 0x00,
]);

// ---------------------------------------------------------------------------
// 1. WebSocket rebind runtime verification
// ---------------------------------------------------------------------------

test("queue-panel re-attaches queue_changed listener after window.socket swap", async ({ page }) => {
  await page.goto(BASE + "/");
  await page.waitForLoadState("domcontentloaded");

  // queue-panel's _bindSocket polls every 1s. Give the initial bind room to fire.
  await page.waitForTimeout(1500);

  const baseline = await page.evaluate(() => {
    return {
      hasSocket: typeof window.socket === "object" && window.socket !== null,
      hasIo: typeof window.io === "function",
      listenerCount: (window.socket && typeof window.socket.listeners === "function")
        ? window.socket.listeners("queue_changed").length
        : -1,
    };
  });
  expect(baseline.hasSocket, "dashboard must initialize window.socket").toBe(true);
  expect(baseline.hasIo, "Socket.IO client lib must be loaded for the swap test").toBe(true);
  expect(baseline.listenerCount, "queue-panel should have bound queue_changed on first instance").toBeGreaterThan(0);

  // Simulate what dashboard's restartService does: kill the current socket,
  // create a new one, assign to window.socket. Pre-fix this would orphan
  // the queue panel from the new connection's events.
  await page.evaluate(() => {
    const dead = window.socket;
    if (dead && typeof dead.disconnect === "function") dead.disconnect();
    window.socket = window.io(window.location.origin, {
      transports: ["polling", "websocket"],
      withCredentials: true,
    });
  });

  // _bindRetryTimer ticks at 1s — wait long enough for at least two ticks
  // (covers timing jitter on slower CI hosts).
  await page.waitForTimeout(2500);

  const afterSwap = await page.evaluate(() => {
    const s = window.socket;
    return {
      isNewInstance: s && typeof s.id === "string",
      listenerCount: (s && typeof s.listeners === "function")
        ? s.listeners("queue_changed").length
        : -1,
    };
  });
  expect(afterSwap.isNewInstance, "swap test must produce a fresh socket instance").toBeTruthy();
  expect(
    afterSwap.listenerCount,
    "post-fix: queue-panel rebind timer must attach queue_changed to the new socket",
  ).toBeGreaterThan(0);
});

// ---------------------------------------------------------------------------
// 2. Concurrent file-level PATCH — verifies _registry_lock RMW guard
// ---------------------------------------------------------------------------

test("two parallel PATCH /api/files/<id> must converge without losing adjacent fields", async () => {
  const ctx = await pwRequest.newContext({ baseURL: BASE, storageState: EDITOR_AUTH });
  let file_id = null;
  let original_name_seen = null;
  try {
    // Use a fresh upload so we don't depend on registry state from prior runs.
    const upR = await ctx.post("/api/transcribe", {
      multipart: { file: { name: "concurrent_test.wav", mimeType: "audio/wav", buffer: _WAV_HEADER } },
    });
    expect(upR.status()).toBe(202);
    ({ file_id } = await upR.json());

    // Two concurrent PATCH calls writing different values to subtitle_source.
    // Both hit the same _registry_lock RMW path. Pre-fix the second writer's
    // staged copy of the entry could land *after* the first writer's _save_registry
    // wrote to disk, losing adjacent field updates if any concurrent writer
    // touched a different field.
    const [rA, rB] = await Promise.all([
      ctx.patch(`/api/files/${file_id}`, { data: { subtitle_source: "en" } }),
      ctx.patch(`/api/files/${file_id}`, { data: { subtitle_source: "zh" } }),
    ]);
    expect(rA.status(), "first concurrent PATCH should succeed").toBe(200);
    expect(rB.status(), "second concurrent PATCH should succeed").toBe(200);

    // Each response body is a snapshot of the entry after that writer's RMW.
    // Record what original_name we saw — both responses must agree.
    const bodyA = await rA.json();
    const bodyB = await rB.json();
    original_name_seen = bodyA.original_name;
    expect(bodyA.original_name, "PATCH-A snapshot must preserve original_name").toBe("concurrent_test.wav");
    expect(bodyB.original_name, "PATCH-B snapshot must preserve original_name").toBe("concurrent_test.wav");
    expect(bodyA.user_id, "PATCH must preserve user_id").toBeTruthy();
    expect(bodyA.user_id).toBe(bodyB.user_id);
    expect(bodyA.id).toBe(file_id);
    expect(bodyB.id).toBe(file_id);

    // subtitle_source on each writer's snapshot must be one of the two
    // written values (no concatenation, no empty string, no field drop).
    expect(["en", "zh"]).toContain(bodyA.subtitle_source);
    expect(["en", "zh"]).toContain(bodyB.subtitle_source);

    // File still appears in listing afterwards (not accidentally deleted by
    // a race between PATCH and any concurrent write path).
    const listR = await ctx.get("/api/files");
    const present = ((await listR.json()).files || []).some((f) => f.id === file_id);
    expect(present, "file must still exist in listing after concurrent PATCH").toBe(true);
  } finally {
    if (file_id) try { await ctx.delete(`/api/files/${file_id}`); } catch (_) {}
    await ctx.dispose();
  }
});

// ---------------------------------------------------------------------------
// 3. Glossary scan no-op — file with 0 translations + non-matching glossary
// ---------------------------------------------------------------------------

test("glossary-scan on freshly-uploaded file returns scanned_count=0 + violations=[]", async () => {
  const ctx = await pwRequest.newContext({ baseURL: BASE, storageState: EDITOR_AUTH });
  let file_id = null;
  let glossary_id = null;
  try {
    // Spin up a temp glossary so we don't depend on the registry having one.
    const glCreate = await ctx.post("/api/glossaries", {
      data: { name: `_e2e_noop_${Date.now()}` },
    });
    expect(glCreate.ok(), `glossary create failed: ${glCreate.status()}`).toBeTruthy();
    glossary_id = (await glCreate.json()).id;

    // Add a term that won't match anything in our fresh file (no translations).
    await ctx.post(`/api/glossaries/${glossary_id}/entries`, {
      data: { en: "zzzqqqxxx_unlikely_term", zh: "測試" },
    });

    // Fresh file — has no translations + no segments yet.
    const upR = await ctx.post("/api/transcribe", {
      multipart: { file: { name: "noop_scan.wav", mimeType: "audio/wav", buffer: _WAV_HEADER } },
    });
    expect(upR.status()).toBe(202);
    ({ file_id } = await upR.json());

    const scanR = await ctx.post(`/api/files/${file_id}/glossary-scan`, {
      data: { glossary_id },
    });
    expect(scanR.status(), `scan should succeed; got ${scanR.status()}`).toBe(200);
    const body = await scanR.json();

    expect(body.scanned_count, "no translations to scan").toBe(0);
    expect(body.violation_count, "no violations possible without translations").toBe(0);
    expect(Array.isArray(body.violations), "violations must be an array").toBe(true);
    expect(body.violations).toEqual([]);
    expect(Array.isArray(body.matches)).toBe(true);
    expect(body.matches).toEqual([]);
    expect(body.reverted_count).toBe(0);
  } finally {
    if (file_id) try { await ctx.delete(`/api/files/${file_id}`); } catch (_) {}
    if (glossary_id) try { await ctx.delete(`/api/glossaries/${glossary_id}`); } catch (_) {}
    await ctx.dispose();
  }
});

// ---------------------------------------------------------------------------
// 4. Glossary-scan input validation — bad glossary_id → 404 (not 500)
// ---------------------------------------------------------------------------

test("glossary-scan with non-existent glossary_id → 404 (not silent 500)", async () => {
  const ctx = await pwRequest.newContext({ baseURL: BASE, storageState: EDITOR_AUTH });
  let file_id = null;
  try {
    const upR = await ctx.post("/api/transcribe", {
      multipart: { file: { name: "bad_gloss.wav", mimeType: "audio/wav", buffer: _WAV_HEADER } },
    });
    expect(upR.status()).toBe(202);
    ({ file_id } = await upR.json());

    const r = await ctx.post(`/api/files/${file_id}/glossary-scan`, {
      data: { glossary_id: "does_not_exist_zzz" },
    });
    expect(r.status()).toBe(404);
    const body = await r.json();
    expect(body.error).toMatch(/glossary|not found/i);
  } finally {
    if (file_id) try { await ctx.delete(`/api/files/${file_id}`); } catch (_) {}
    await ctx.dispose();
  }
});
