// E2E flow-coverage gaps — fills the holes identified in the deep-sweep audit:
//   1. Upload happy path (no spec hits POST /api/transcribe before this one)
//   2. Upload validation: bad extension, missing file param
//   3. Render approval gate: file with no segments/translations
//   4. Render input validation: invalid format, unknown file
//   5. Render permission boundary: non-owner non-admin gets 403 (the fix
//      we shipped in commit 14d5000 — verifies the regression won't return)
//   6. Session expiry → auth.js fetch interceptor redirects to /login

const { test, expect, request: pwRequest } = require("@playwright/test");

const BASE = process.env.BASE_URL || "http://localhost:5001";
const EDITOR_AUTH = "./playwright-auth-editor.json";
const ADMIN_AUTH = "./playwright-auth.json";

// Minimal RIFF WAV header — backend's upload route only checks file extension,
// not decodability, so this passes through validation and lands in the registry.
// The ASR worker will fail to decode it, but our tests never wait for ASR to
// complete; we clean up the file before any ASR work matters.
const _WAV_HEADER = Buffer.from([
  0x52, 0x49, 0x46, 0x46, 0x24, 0x00, 0x00, 0x00,
  0x57, 0x41, 0x56, 0x45, 0x66, 0x6d, 0x74, 0x20,
  0x10, 0x00, 0x00, 0x00, 0x01, 0x00, 0x01, 0x00,
  0x44, 0xac, 0x00, 0x00, 0x88, 0x58, 0x01, 0x00,
  0x02, 0x00, 0x10, 0x00, 0x64, 0x61, 0x74, 0x61,
  0x00, 0x00, 0x00, 0x00,
]);

function _wavMultipart(name = "test.wav") {
  return {
    file: { name, mimeType: "audio/wav", buffer: _WAV_HEADER },
  };
}

// ---------------------------------------------------------------------------
// Upload — Stage 1 of the pipeline. Zero specs covered this before today.
// ---------------------------------------------------------------------------

test("Upload happy path — POST /api/transcribe returns 202 + file_id + job_id", async () => {
  const ctx = await pwRequest.newContext({ baseURL: BASE, storageState: EDITOR_AUTH });
  try {
    const r = await ctx.post("/api/transcribe", { multipart: _wavMultipart("e2e_happy.wav") });
    expect(r.status()).toBe(202);
    const body = await r.json();
    expect(body.file_id, "response should expose file_id").toBeTruthy();
    expect(body.job_id, "response should expose job_id").toBeTruthy();
    expect(body.status).toBe("queued");
    expect(typeof body.queue_position).toBe("number");
    // Cleanup so the registry doesn't accumulate test files across ralph runs.
    await ctx.delete(`/api/files/${body.file_id}`);
  } finally {
    await ctx.dispose();
  }
});

test("Upload rejection — unsupported extension (.txt) → 400", async () => {
  const ctx = await pwRequest.newContext({ baseURL: BASE, storageState: EDITOR_AUTH });
  try {
    const r = await ctx.post("/api/transcribe", {
      multipart: { file: { name: "notes.txt", mimeType: "text/plain", buffer: Buffer.from("hello") } },
    });
    expect(r.status()).toBe(400);
    const body = await r.json();
    expect(body.error).toMatch(/不支持|format|extension/i);
  } finally {
    await ctx.dispose();
  }
});

test("Upload rejection — missing file part → 400", async () => {
  const ctx = await pwRequest.newContext({ baseURL: BASE, storageState: EDITOR_AUTH });
  try {
    const r = await ctx.post("/api/transcribe", { multipart: {} });
    expect(r.status()).toBe(400);
    const body = await r.json();
    expect(body.error).toMatch(/未找到|file/i);
  } finally {
    await ctx.dispose();
  }
});

// ---------------------------------------------------------------------------
// Render — Stage 5. Approval gate + format/file validation.
// ---------------------------------------------------------------------------

test("Render rejection — fresh file with no segments yet → 400 (transcription/translation/approval gate)", async () => {
  const ctx = await pwRequest.newContext({ baseURL: BASE, storageState: EDITOR_AUTH });
  let file_id = null;
  try {
    const upR = await ctx.post("/api/transcribe", { multipart: _wavMultipart("e2e_gate.wav") });
    expect(upR.status()).toBe(202);
    ({ file_id } = await upR.json());

    const r = await ctx.post("/api/render", { data: { file_id, format: "mp4" } });
    expect(r.status()).toBe(400);
    const body = await r.json();
    // Any of three valid messages depending on resolver state:
    //   "File has no transcription segments to render"
    //   "File has no translations to render"
    //   "N segment(s) not yet approved..."
    expect(body.error).toMatch(/transcription|translation|approved|segment/i);
  } finally {
    if (file_id) await ctx.delete(`/api/files/${file_id}`);
    await ctx.dispose();
  }
});

test("Render rejection — invalid format → 400", async () => {
  const ctx = await pwRequest.newContext({ baseURL: BASE, storageState: EDITOR_AUTH });
  try {
    const r = await ctx.post("/api/render", {
      data: { file_id: "any12345abcd", format: "tiff" },
    });
    expect(r.status()).toBe(400);
    const body = await r.json();
    expect(body.error).toMatch(/format/i);
  } finally {
    await ctx.dispose();
  }
});

test("Render rejection — missing file_id → 400", async () => {
  const ctx = await pwRequest.newContext({ baseURL: BASE, storageState: EDITOR_AUTH });
  try {
    const r = await ctx.post("/api/render", { data: { format: "mp4" } });
    expect(r.status()).toBe(400);
    const body = await r.json();
    expect(body.error).toMatch(/file_id/i);
  } finally {
    await ctx.dispose();
  }
});

test("Render rejection — unknown file_id → 404", async () => {
  const ctx = await pwRequest.newContext({ baseURL: BASE, storageState: EDITOR_AUTH });
  try {
    const r = await ctx.post("/api/render", {
      data: { file_id: "doesnotexist1234", format: "mp4" },
    });
    expect(r.status()).toBe(404);
  } finally {
    await ctx.dispose();
  }
});

// ---------------------------------------------------------------------------
// Permission boundary — the regression we fixed in commit 14d5000.
// Without the @login_required + body-file_id ownership check, a non-owner
// non-admin could spawn a render against any file in the system.
// ---------------------------------------------------------------------------

test("Render permission boundary — non-owner non-admin gets 403", async () => {
  const adminCtx = await pwRequest.newContext({ baseURL: BASE, storageState: ADMIN_AUTH });

  // Spin up a temporary non-admin user for the negative case. We can't reuse
  // "editor" because we need a *third* user (editor owns the file, admin
  // bypasses the check, so neither covers "authed-but-not-owner").
  const uname = `e2e_perm_${Date.now().toString(36)}`;
  const password = "TempPass1!";
  const createR = await adminCtx.post("/api/admin/users", {
    data: { username: uname, password, is_admin: false },
  });
  if (!createR.ok()) {
    await adminCtx.dispose();
    test.skip(true, `admin user-create failed: ${createR.status()}`);
    return;
  }

  let editorFileId = null;
  let editorCtx = null;
  let otherCtx = null;
  try {
    // Editor uploads a file
    editorCtx = await pwRequest.newContext({ baseURL: BASE, storageState: EDITOR_AUTH });
    const upR = await editorCtx.post("/api/transcribe", {
      multipart: _wavMultipart("e2e_perm.wav"),
    });
    expect(upR.status()).toBe(202);
    ({ file_id: editorFileId } = await upR.json());

    // Third user logs in and tries to render editor's file
    otherCtx = await pwRequest.newContext({ baseURL: BASE });
    const loginR = await otherCtx.post("/login", { data: { username: uname, password } });
    expect(loginR.ok(), `login of temp user must succeed: ${loginR.status()}`).toBeTruthy();

    const r = await otherCtx.post("/api/render", {
      data: { file_id: editorFileId, format: "mp4" },
    });
    expect(r.status(), "non-owner non-admin must get 403, not 4xx-leak").toBe(403);
    const body = await r.json();
    expect(body.error).toMatch(/forbidden|permission|权限|權限/i);
  } finally {
    if (editorFileId && editorCtx) {
      try { await editorCtx.delete(`/api/files/${editorFileId}`); } catch (_) {}
    }
    if (editorCtx) await editorCtx.dispose();
    if (otherCtx) await otherCtx.dispose();

    // Tear down the temp user
    try {
      const list = await adminCtx.get("/api/admin/users");
      if (list.ok()) {
        const body = await list.json();
        const found = (body.users || []).find((u) => u.username === uname);
        if (found) await adminCtx.delete(`/api/admin/users/${found.id}`);
      }
    } catch (_) {}
    await adminCtx.dispose();
  }
});

// ---------------------------------------------------------------------------
// Session expiry — verifies the auth.js global fetch wrapper redirects on
// 401. Pre-fix, a stale-cookie user would get silent fetch failures and
// stuck spinners; post-fix the page lands on /login.html?next=… cleanly.
// ---------------------------------------------------------------------------

test("Session expiry → 401 fetch triggers redirect to /login.html", async ({ page, context }) => {
  // playwright.config.js loads admin storageState by default, so this lands
  // directly on the dashboard.
  await page.goto(BASE + "/");
  await page.waitForLoadState("domcontentloaded");

  // Nuke cookies to simulate session expiry.
  await context.clearCookies();

  // Trigger a non-whitelisted fetch (auth.js excludes /api/me + /api/health
  // + /api/ready from the redirect, but /api/files is covered).
  const redirectPromise = page.waitForURL(/\/login\.html/, { timeout: 5000 });
  await page.evaluate(() => {
    return fetch("/api/files", { credentials: "same-origin" }).catch(() => {});
  });
  await redirectPromise;
  expect(page.url()).toMatch(/\/login\.html/);
  // The next-param preserves the user's intended destination so post-login
  // they don't lose their place.
  expect(page.url()).toMatch(/next=/);
});
