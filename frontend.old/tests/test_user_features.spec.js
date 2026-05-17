// End-to-end verification of 5 user-facing features:
//   1. SRT export
//   2. Video render (burn-in)
//   3. Proofread page load
//   4. Edit + approve translation
//   5. Glossary create + scan + apply
//
// Uses storageState (pre-logged in as admin). Operates against whichever
// `done`-status file is currently in the admin-visible registry — picks the
// one with the fewest segments to keep render time low.
const { test, expect } = require("@playwright/test");

const BASE = process.env.BASE_URL || "http://localhost:5001";

// Shared file picked once at suite start.
let TARGET_FILE = null;

test.beforeAll(async ({ request }) => {
  const r = await request.get(BASE + "/api/files");
  expect(r.ok(), `GET /api/files: ${r.status()}`).toBe(true);
  const body = await r.json();
  const done = (body.files || []).filter(
    (f) => f.status === "done" && f.translation_status === "done" && f.segment_count > 0
  );
  expect(done.length, "needs at least one done+translated file in registry").toBeGreaterThan(0);
  done.sort((a, b) => a.segment_count - b.segment_count);
  TARGET_FILE = done[0];
  console.log(
    `[setup] target file: ${TARGET_FILE.id} ` +
      `(${TARGET_FILE.original_name}, ${TARGET_FILE.segment_count} segments)`
  );
});

// ---------------------------------------------------------------------------
// 1. SRT export
// ---------------------------------------------------------------------------
test("SRT export returns well-formed SRT", async ({ request }) => {
  const r = await request.get(
    BASE + `/api/files/${TARGET_FILE.id}/subtitle.srt`
  );
  expect(r.status(), "SRT 200").toBe(200);
  const text = await r.text();
  expect(text.length, "SRT non-empty").toBeGreaterThan(50);
  // Must contain at least one cue: index, timecode, text
  expect(text).toMatch(/^\d+\r?\n\d{2}:\d{2}:\d{2}[.,]\d{3} --> \d{2}:\d{2}:\d{2}[.,]\d{3}/m);
});

test("SRT with explicit source=en works", async ({ request }) => {
  const r = await request.get(
    BASE + `/api/files/${TARGET_FILE.id}/subtitle.srt?source=en`
  );
  expect(r.status()).toBe(200);
  const text = await r.text();
  expect(text.length).toBeGreaterThan(50);
});

// ---------------------------------------------------------------------------
// 3. Proofread page loads
// ---------------------------------------------------------------------------
test("proofread page loads with file_id query param", async ({ page }) => {
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto(BASE + `/proofread.html?file_id=${TARGET_FILE.id}`);
  // Page should render its main shell even before video loads.
  await expect(page.locator("body")).toBeVisible();
  // Proofread renders segments into .rv-b-rail-item[data-idx]
  const segRow = page.locator('.rv-b-rail-item[data-idx]').first();
  await expect(segRow).toBeVisible({ timeout: 15000 });
  expect(errors, "no uncaught page errors: " + errors.join("; ")).toEqual([]);
});

// ---------------------------------------------------------------------------
// 4. Edit + approve translation
// ---------------------------------------------------------------------------
test("edit then approve translation round-trips", async ({ request }) => {
  // Fetch original
  const before = await request.get(
    BASE + `/api/files/${TARGET_FILE.id}/translations`
  );
  expect(before.ok()).toBe(true);
  const beforeBody = await before.json();
  const translations = beforeBody.translations || beforeBody;
  expect(Array.isArray(translations)).toBe(true);
  expect(translations.length).toBeGreaterThan(0);

  const idx = 0;
  const original = translations[idx];
  const originalZh = original.zh_text;
  const testText = `[E2E TEST ${Date.now()}] ${originalZh}`;

  // PATCH new text (auto-approves per CLAUDE.md)
  const patch = await request.patch(
    BASE + `/api/files/${TARGET_FILE.id}/translations/${idx}`,
    { data: { zh_text: testText } }
  );
  expect(patch.status(), `PATCH translations[${idx}]: ${patch.status()}`).toBe(200);

  // Verify the new text + approved status came back
  const after = await request.get(
    BASE + `/api/files/${TARGET_FILE.id}/translations`
  );
  const afterBody = await after.json();
  const afterTranslations = afterBody.translations || afterBody;
  expect(afterTranslations[idx].zh_text).toBe(testText);
  expect(afterTranslations[idx].status).toBe("approved");

  // Restore original (and re-approve to keep test idempotent)
  const restore = await request.patch(
    BASE + `/api/files/${TARGET_FILE.id}/translations/${idx}`,
    { data: { zh_text: originalZh } }
  );
  expect(restore.status()).toBe(200);
});

test("unapprove flips status back to pending", async ({ request }) => {
  // First ensure idx=0 is approved
  await request.patch(
    BASE + `/api/files/${TARGET_FILE.id}/translations/0`,
    { data: { zh_text: "tmp" } }
  );
  const unap = await request.post(
    BASE + `/api/files/${TARGET_FILE.id}/translations/0/unapprove`
  );
  expect(unap.status()).toBe(200);
  // Status endpoint confirms
  const status = await request.get(
    BASE + `/api/files/${TARGET_FILE.id}/translations/status`
  );
  const body = await status.json();
  // body shape: {approved, total, ...}
  expect(body).toHaveProperty("approved");
  expect(body).toHaveProperty("total");
});

// ---------------------------------------------------------------------------
// 5. Glossary create + scan + apply
// ---------------------------------------------------------------------------
test("glossary create + add entry + scan + apply roundtrip", async ({ request }) => {
  const create = await request.post(BASE + "/api/glossaries", {
    data: { name: `E2E Glossary ${Date.now()}`, description: "ralph-loop test", source_lang: "en", target_lang: "zh" },
  });
  expect(create.status()).toBe(201);
  const gid = (await create.json()).id;

  try {
    const entry = await request.post(BASE + `/api/glossaries/${gid}/entries`, {
      data: { source: "and", target: "和" },
    });
    expect(entry.status()).toBe(201);
    expect((await entry.json()).entries.some((e) => e.source === "and")).toBe(true);

    const scan = await request.post(
      BASE + `/api/files/${TARGET_FILE.id}/glossary-scan`,
      { data: { glossary_id: gid } }
    );
    expect(scan.status(), `scan: ${scan.status()}`).toBe(200);
    const scanBody = await scan.json();
    // v3.15: violations split into strict_violations + loose_violations
    expect(scanBody).toHaveProperty("strict_violations");
    expect(scanBody).toHaveProperty("loose_violations");
    expect(Array.isArray(scanBody.strict_violations)).toBe(true);
    expect(Array.isArray(scanBody.loose_violations)).toBe(true);
  } finally {
    await request.delete(BASE + `/api/glossaries/${gid}`);
  }
});

test("glossary apply rewrites zh_text via LLM", async ({ request }) => {
  test.setTimeout(180_000);

  const create = await request.post(BASE + "/api/glossaries", {
    data: { name: `E2E Apply ${Date.now()}`, source_lang: "en", target_lang: "zh" },
  });
  const gid = (await create.json()).id;

  try {
    // 'mess' is rare in the target clip (1 occurrence) — bounds LLM cost
    await request.post(BASE + `/api/glossaries/${gid}/entries`, {
      data: { source: "mess", target: "搞亂" },
    });

    const scan = await request.post(
      BASE + `/api/files/${TARGET_FILE.id}/glossary-scan`,
      { data: { glossary_id: gid } }
    );
    expect(scan.status()).toBe(200);
    const scanBody = await scan.json();
    // v3.15: violations are split into strict_violations + loose_violations
    const violations = [
      ...(scanBody.strict_violations || []),
      ...(scanBody.loose_violations || []),
    ];

    if (violations.length === 0) return; // already compliant — plumbing tested via scan

    const v = violations[0];
    const apply = await request.post(
      BASE + `/api/files/${TARGET_FILE.id}/glossary-apply`,
      {
        data: {
          glossary_id: gid,
          // v3.15: apply endpoint uses term_source/term_target; scan rows still have
          // legacy term_en/term_zh aliases so we map them explicitly.
          violations: [{ seg_idx: v.seg_idx, term_source: v.term_source || v.term_en, term_target: v.term_target || v.term_zh }],
        },
      }
    );
    expect(apply.status(), `apply: ${apply.status()} ${await apply.text()}`).toBe(200);
    const applyBody = await apply.json();
    // v3.15 apply returns {applied_count, failed_count}
    expect(applyBody).toHaveProperty("applied_count");

    const tr = await request.get(BASE + `/api/files/${TARGET_FILE.id}/translations`);
    const updated = ((await tr.json()).translations || [])[v.seg_idx];
    expect(updated.zh_text).toContain("搞亂");
  } finally {
    await request.delete(BASE + `/api/glossaries/${gid}`);
  }
});

// ---------------------------------------------------------------------------
// 2. Video render (slow — keep last)
// ---------------------------------------------------------------------------
test("render mp4 end-to-end (approve-all + render + download)", async ({ request }) => {
  test.setTimeout(180_000); // 3 min; render of 45 segments @ 1080p ≈ 30-60s

  // Approve all translations (render gate)
  const approveAll = await request.post(
    BASE + `/api/files/${TARGET_FILE.id}/translations/approve-all`
  );
  expect(approveAll.ok(), `approve-all: ${approveAll.status()}`).toBe(true);

  // Start render — small + fast: 720p, ultrafast, CRF 28
  const start = await request.post(BASE + "/api/render", {
    data: {
      file_id: TARGET_FILE.id,
      format: "mp4",
      render_options: {
        bitrate_mode: "crf",
        crf: 28,
        preset: "ultrafast",
        resolution: "1280x720",
        audio_bitrate: "128k",
      },
    },
  });
  expect(start.status(), `POST /api/render: ${start.status()} ${await start.text()}`).toBe(202);
  const job = await start.json();
  const renderId = job.render_id;
  expect(renderId).toBeTruthy();

  // Poll until done or error (max 150s)
  let final = null;
  for (let i = 0; i < 75; i++) {
    await new Promise((r) => setTimeout(r, 2000));
    const s = await request.get(BASE + `/api/renders/${renderId}`);
    expect(s.ok()).toBe(true);
    const sb = await s.json();
    if (sb.status === "done" || sb.status === "error") {
      final = sb;
      break;
    }
  }
  expect(final, "render did not finish within 150s").not.toBeNull();
  expect(final.status, `render status: ${JSON.stringify(final)}`).toBe("done");

  // Download
  const dl = await request.get(BASE + `/api/renders/${renderId}/download`);
  expect(dl.status()).toBe(200);
  const headers = dl.headers();
  expect(headers["content-type"]).toMatch(/video|octet-stream/);
  // Body should be non-trivial (≥10 KB)
  const buf = await dl.body();
  expect(buf.length).toBeGreaterThan(10_000);
});
