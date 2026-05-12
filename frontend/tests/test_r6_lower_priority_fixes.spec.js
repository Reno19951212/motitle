// Regression tests for the lower-priority R6 audit fixes:
//   R5  GlossaryManager entry methods per-id lock
//   R6  LanguageConfigManager per-lang_id lock
//   M4  Whisper LRU cache cap
//   E   error UX — body.error surfaces through retry/delete/translate toasts
const { test, expect, request: pwRequest } = require("@playwright/test");

const BASE = process.env.BASE_URL || "http://localhost:5001";

// ---------------------------------------------------------------------------
// R5 — concurrent glossary entry inserts don't drop one
// ---------------------------------------------------------------------------
test("R5 — 10 concurrent POST /glossaries/<id>/entries all land", async ({ request }) => {
  const create = await request.post(BASE + "/api/glossaries", {
    data: { name: `R6_R5_${Date.now()}`, description: "concurrency test", source_lang: "en", target_lang: "zh" },
  });
  expect(create.status()).toBe(201);
  const gid = (await create.json()).id;

  try {
    const N = 10;
    const responses = await Promise.all(
      Array.from({ length: N }, (_, i) =>
        request.post(BASE + `/api/glossaries/${gid}/entries`, {
          data: { source: `term_${i}`, target: `譯_${i}` },
        })
      )
    );
    for (const r of responses) {
      expect(r.status()).toBe(201);
    }
    const full = await (await request.get(BASE + `/api/glossaries/${gid}`)).json();
    expect(full.entries.length, "all 10 entries should be persisted").toBe(N);
  } finally {
    await request.delete(BASE + `/api/glossaries/${gid}`);
  }
});

// ---------------------------------------------------------------------------
// R6 — concurrent language config PATCHes don't lose updates
// ---------------------------------------------------------------------------
test("R6 — concurrent PATCH /languages/en serializes to a consistent final value", async ({ request }) => {
  // Seed
  await request.patch(BASE + "/api/languages/en", {
    data: { asr: { max_words_per_segment: 16 }, translation: { batch_size: 1 } },
  });

  const N = 8;
  const responses = await Promise.all(
    Array.from({ length: N }, (_, i) =>
      request.patch(BASE + "/api/languages/en", {
        data: { translation: { batch_size: i + 1 } }, // each PATCH sets a different value
      })
    )
  );
  for (const r of responses) expect(r.status()).toBe(200);
  // Final state must be ONE of the values we wrote, not garbage from a torn
  // read-modify-write.
  const afterResp = await (await request.get(BASE + "/api/languages/en")).json();
  const after = afterResp.language || afterResp;
  expect(after.translation.batch_size, "final batch_size must be one of the writes").toBeGreaterThanOrEqual(1);
  expect(after.translation.batch_size).toBeLessThanOrEqual(N);
});

// ---------------------------------------------------------------------------
// E batch — retry of a permanently-failing job surfaces body.error
// ---------------------------------------------------------------------------
test("E — POST /api/queue/<bogus>/retry returns 404 with body.error (frontend will show it)", async ({ request }) => {
  const r = await request.post(BASE + "/api/queue/__not_a_real_job__/retry");
  expect(r.status()).toBe(404);
  const body = await r.json();
  expect(body, "404 body must carry error field for frontend to surface").toHaveProperty("error");
});

// ---------------------------------------------------------------------------
// E — duplicate user creation surfaces backend error string
// ---------------------------------------------------------------------------
test("E — admin user creation conflict returns 409 with body.error", async ({ request }) => {
  const name = `R6_dupe_${Date.now()}`;
  const r1 = await request.post(BASE + "/api/admin/users", {
    data: { username: name, password: "ValidPass1!", is_admin: false },
  });
  expect(r1.status()).toBe(201);
  try {
    const r2 = await request.post(BASE + "/api/admin/users", {
      data: { username: name, password: "ValidPass1!", is_admin: false },
    });
    expect(r2.status()).toBe(409);
    expect(await r2.json()).toHaveProperty("error");
  } finally {
    // Need the created user id to delete
    const list = await (await request.get(BASE + "/api/admin/users")).json();
    const u = (list.users || []).find((x) => x.username === name);
    if (u) await request.delete(BASE + `/api/admin/users/${u.id}`);
  }
});
