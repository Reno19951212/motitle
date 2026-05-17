// Regression tests for the four frontend/backend type-mismatch fixes
// surfaced by the audit (follow-up to commit 7ac3d23).
const { test, expect } = require("@playwright/test");

const BASE = process.env.BASE_URL || "http://localhost:5001";

// ---------------------------------------------------------------------------
// HIGH 1: language_config.update() must deep-merge — saving the dashboard
// modal (which only sends max_words_per_segment + max_segment_duration +
// simplified_to_traditional) must NOT wipe merge_short_* fields.
// ---------------------------------------------------------------------------
test("language config save preserves merge_short_max_words / max_gap", async ({ request }) => {
  // Seed EN with explicit values
  const seed = await request.patch(BASE + "/api/languages/en", {
    data: {
      asr: {
        max_words_per_segment: 18,
        max_segment_duration: 14,
        merge_short_max_words: 2,
        merge_short_max_gap: 0.5,
      },
      translation: { batch_size: 1, temperature: 0.1 },
    },
  });
  expect(seed.status(), `seed: ${await seed.text()}`).toBe(200);

  // Now PATCH the way the dashboard modal does — only the 3 fields it renders
  const r = await request.patch(BASE + "/api/languages/en", {
    data: {
      asr: {
        max_words_per_segment: 16,
        max_segment_duration: 15,
        simplified_to_traditional: false,
      },
      translation: { batch_size: 1, temperature: 0.1 },
    },
  });
  expect(r.status()).toBe(200);

  const afterResp = await (await request.get(BASE + "/api/languages/en")).json();
  const after = afterResp.language || afterResp;
  expect(after.asr.merge_short_max_words, "merge_short_max_words wiped by partial save").toBe(2);
  expect(after.asr.merge_short_max_gap).toBe(0.5);
  // And the values the modal DID send were applied
  expect(after.asr.max_words_per_segment).toBe(16);
  expect(after.asr.simplified_to_traditional).toBe(false);
});

// ---------------------------------------------------------------------------
// HIGH 2: proofread ssSize input range now matches backend (min=12 not 8)
// ---------------------------------------------------------------------------
test("proofread font size input has min=12 (matches backend cap)", async ({ page }) => {
  await page.goto(BASE + "/proofread.html?file_id=nonexistent");
  await page.waitForTimeout(300);
  const min = await page.locator("#ssSize").getAttribute("min");
  expect(min).toBe("12");
});

// ---------------------------------------------------------------------------
// MEDIUM 1: language_config validator now bool-guards max_words_per_segment
// + batch_size + temperature (Python isinstance(True, int) is True, so the
// previous code accepted bools as numeric values).
// ---------------------------------------------------------------------------
test("language config rejects bool for max_words_per_segment / batch_size / temperature", async ({ request }) => {
  for (const patch of [
    { asr: { max_words_per_segment: true } },
    { translation: { batch_size: true } },
    { translation: { temperature: false } },
  ]) {
    const r = await request.patch(BASE + "/api/languages/en", { data: patch });
    expect(r.status(), `bool should be rejected for ${JSON.stringify(patch)}`).toBe(400);
  }
});

// ---------------------------------------------------------------------------
// MEDIUM 2: update_segment_text is null-safe (was crashing on text: null)
// ---------------------------------------------------------------------------
test("PATCH /api/files/<id>/segments/<seg_id> handles text:null without 500", async ({ request }) => {
  const files = (await (await request.get(BASE + "/api/files")).json()).files || [];
  const f = files.find((x) => (x.segment_count || 0) > 0);
  if (!f) { test.skip(true, "no file with segments"); return; }
  // Pick a real segment id
  const segs = (await (await request.get(BASE + `/api/files/${f.id}/segments`)).json()).segments || [];
  if (segs.length === 0) { test.skip(true, "no segments"); return; }
  const sid = segs[0].id;
  const r = await request.patch(BASE + `/api/files/${f.id}/segments/${sid}`, {
    data: { text: null },
  });
  // Pre-fix: 500 AttributeError. Post-fix: 200 (treated as empty string).
  expect([200, 400]).toContain(r.status());
  expect(r.status()).not.toBe(500);
});
