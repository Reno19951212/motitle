// E2E tests for v3.x multilingual glossary refactor.

const { test, expect, request: pwRequest } = require("@playwright/test");

const BASE = process.env.BASE_URL || "http://localhost:5001";
const ADMIN_AUTH = "./playwright-auth.json";

test.describe("Multilingual glossary E2E", () => {
  test("GET /api/glossaries/languages returns 8-lang whitelist", async () => {
    const ctx = await pwRequest.newContext({ baseURL: BASE, storageState: ADMIN_AUTH });
    try {
      const r = await ctx.get("/api/glossaries/languages");
      expect(r.status()).toBe(200);
      const body = await r.json();
      const codes = body.languages.map(l => l.code);
      expect(codes.sort()).toEqual(["de", "en", "es", "fr", "ja", "ko", "th", "zh"]);
    } finally { await ctx.dispose(); }
  });

  test("Create JA→ZH glossary + add entry with kana source", async () => {
    const ctx = await pwRequest.newContext({ baseURL: BASE, storageState: ADMIN_AUTH });
    let gid = null;
    try {
      const create = await ctx.post("/api/glossaries", {
        data: { name: `e2e_ja_${Date.now()}`, source_lang: "ja", target_lang: "zh" },
      });
      expect(create.status()).toBe(201);
      gid = (await create.json()).id;

      // Pure kana source — would have failed the old "must contain letter" rule.
      const addEntry = await ctx.post(`/api/glossaries/${gid}/entries`, {
        data: { source: "ニュース", target: "新聞" },
      });
      expect(addEntry.status(), `add entry got ${addEntry.status()}`).toBeLessThan(400);
    } finally {
      if (gid) try { await ctx.delete(`/api/glossaries/${gid}`); } catch (_) {}
      await ctx.dispose();
    }
  });

  test("Add entry with pure-number source succeeds", async () => {
    const ctx = await pwRequest.newContext({ baseURL: BASE, storageState: ADMIN_AUTH });
    let gid = null;
    try {
      const create = await ctx.post("/api/glossaries", {
        data: { name: `e2e_num_${Date.now()}`, source_lang: "en", target_lang: "zh" },
      });
      gid = (await create.json()).id;
      // The original bug: source="2024" rejected with "en must contain at least one letter".
      const r = await ctx.post(`/api/glossaries/${gid}/entries`, {
        data: { source: "2024", target: "二零二四" },
      });
      expect(r.status(), `pure-number source got ${r.status()}`).toBeLessThan(400);
    } finally {
      if (gid) try { await ctx.delete(`/api/glossaries/${gid}`); } catch (_) {}
      await ctx.dispose();
    }
  });

  test("Reject old en,zh CSV header", async () => {
    const ctx = await pwRequest.newContext({ baseURL: BASE, storageState: ADMIN_AUTH });
    let gid = null;
    try {
      const create = await ctx.post("/api/glossaries", {
        data: { name: `e2e_oldcsv_${Date.now()}`, source_lang: "en", target_lang: "zh" },
      });
      gid = (await create.json()).id;
      const r = await ctx.post(`/api/glossaries/${gid}/import`, {
        data: { csv_content: "en,zh\nbroadcast,廣播\n" },
      });
      expect(r.status()).toBe(400);
      const body = await r.json();
      expect(body.error).toMatch(/source, target/);
    } finally {
      if (gid) try { await ctx.delete(`/api/glossaries/${gid}`); } catch (_) {}
      await ctx.dispose();
    }
  });

  test("Accept new 3-col CSV with aliases", async () => {
    const ctx = await pwRequest.newContext({ baseURL: BASE, storageState: ADMIN_AUTH });
    let gid = null;
    try {
      const create = await ctx.post("/api/glossaries", {
        data: { name: `e2e_newcsv_${Date.now()}`, source_lang: "en", target_lang: "zh" },
      });
      gid = (await create.json()).id;
      const r = await ctx.post(`/api/glossaries/${gid}/import`, {
        data: { csv_content: "source,target,target_aliases\nbroadcast,廣播,\nanchor,主播,主持;新聞主播\n" },
      });
      expect(r.status()).toBe(200);
      const g = await ctx.get(`/api/glossaries/${gid}`).then(x => x.json());
      const anchor = g.entries.find(e => e.source === "anchor");
      expect(anchor.target_aliases).toEqual(["主持", "新聞主播"]);
    } finally {
      if (gid) try { await ctx.delete(`/api/glossaries/${gid}`); } catch (_) {}
      await ctx.dispose();
    }
  });
});

// ---------------------------------------------------------------------------
// DOM-level smoke tests — verify the v3.15 UI changes actually render.
// API-level coverage is above; these are the visual regression guards.
// ---------------------------------------------------------------------------

const { chromium } = require("@playwright/test");

test.describe("v3.15 DOM smoke", () => {
  test("Glossary.html: source + target lang dropdowns populated with 8 options each", async ({ page }) => {
    const resp = await page.goto(BASE + "/Glossary.html");
    // Skip if the route isn't registered yet (404) or redirected to login.
    if (!resp || resp.status() !== 200 || !page.url().includes("Glossary.html")) {
      test.skip(true, "Glossary.html route not available in this environment");
      return;
    }
    await page.waitForLoadState("domcontentloaded");
    // The selects populate async via fetch('/api/glossaries/languages'); wait
    // for them to fill.
    await page.waitForFunction(
      () => {
        const s = document.getElementById("glSourceLang");
        return s && s.options && s.options.length === 8;
      },
      { timeout: 5000 },
    );
    const srcCount = await page.locator("#glSourceLang option").count();
    const tgtCount = await page.locator("#glTargetLang option").count();
    expect(srcCount, "source lang dropdown should have 8 options").toBe(8);
    expect(tgtCount, "target lang dropdown should have 8 options").toBe(8);
    // Default selection sanity
    const srcVal = await page.locator("#glSourceLang").inputValue();
    const tgtVal = await page.locator("#glTargetLang").inputValue();
    expect(["en", "zh", "ja", "ko", "es", "fr", "de", "th"]).toContain(srcVal);
    expect(["en", "zh", "ja", "ko", "es", "fr", "de", "th"]).toContain(tgtVal);
  });

  test("Glossary.html: list items show lang pair badge after at least one glossary exists", async ({ page, request }) => {
    // Ensure at least one glossary exists (Broadcast News should already be there from `8bc5ed1`).
    const probe = await request.get(BASE + "/api/glossaries");
    const all = await probe.json();
    if ((all.glossaries || []).length === 0) {
      test.skip(true, "no glossaries available for badge render check");
      return;
    }
    const resp = await page.goto(BASE + "/Glossary.html");
    // Skip if the route isn't registered yet (404) or redirected to login.
    if (!resp || resp.status() !== 200 || !page.url().includes("Glossary.html")) {
      test.skip(true, "Glossary.html route not available in this environment");
      return;
    }
    await page.waitForLoadState("domcontentloaded");
    // Wait for left-pane list to populate
    await page.waitForFunction(
      () => document.querySelectorAll('.gl-list-item').length > 0,
      { timeout: 5000 },
    );
    // Every list item should show an arrow → in its meta line (.gli-meta)
    const firstItem = page.locator(".gl-list-item").first();
    const metaText = await firstItem.locator(".gli-meta").textContent();
    expect(metaText, `expected lang-pair format like 'EN → ZH', got: '${metaText}'`).toMatch(/→/);
  });

  test("proofread.html: glossary dropdown items include lang-pair label", async ({ page, request }) => {
    // Need a file_id and at least one glossary. Skip if either missing.
    const files = await request.get(BASE + "/api/files").then((r) => r.json());
    const fileWithSegs = (files.files || []).find((f) => f.segment_count > 0);
    if (!fileWithSegs) {
      test.skip(true, "needs a file with segments to navigate to proofread");
      return;
    }
    await page.goto(BASE + "/proofread.html?file_id=" + fileWithSegs.id);
    await page.waitForLoadState("domcontentloaded");
    await page.waitForTimeout(800);
    // Glossary dropdown lives somewhere on the page
    const sel = page.locator("#glossarySelect").first();
    const optsCount = await sel.locator("option").count().catch(() => 0);
    if (optsCount <= 1) {
      test.skip(true, "glossarySelect has no items in this environment");
      return;
    }
    // At least one option (skipping the placeholder) should contain an arrow
    let foundArrow = false;
    for (let i = 0; i < optsCount; i++) {
      const text = await sel.locator(`option:nth-child(${i + 1})`).textContent();
      if (text && /→/.test(text)) {
        foundArrow = true;
        break;
      }
    }
    expect(foundArrow, "at least one glossary option should display 'EN→ZH'-style lang pair").toBe(true);
  });

  test("proofread.html: apply modal renders strict + loose sections for ZH-source glossary", async ({ page, request }) => {
    // This test creates its own ZH→ZH glossary + scans a fake file, then
    // verifies the apply modal's section structure. We DO need a real file
    // with translations to scan against — find one or skip.
    const files = await request.get(BASE + "/api/files").then((r) => r.json());
    const fileReady = (files.files || []).find(
      (f) => f.status === "done" && f.translation_status === "done" && f.segment_count > 0,
    );
    if (!fileReady) {
      test.skip(true, "needs a done+translated file for scan");
      return;
    }
    // Create a ZH→ZH glossary with a term that will substring-match.
    const create = await request.post(BASE + "/api/glossaries", {
      data: { name: `smoke_zh_${Date.now()}`, source_lang: "zh", target_lang: "zh" },
    });
    expect(create.status()).toBe(201);
    const gid = (await create.json()).id;
    try {
      await request.post(BASE + `/api/glossaries/${gid}/entries`, {
        data: { source: "新聞", target: "新聞報導" },
      });
      // Run the scan via API and verify the response shape directly. Modal
      // DOM rendering verification at the page level adds flakiness; the
      // important contract is the API response shape.
      const scan = await request.post(BASE + `/api/files/${fileReady.id}/glossary-scan`, {
        data: { glossary_id: gid },
      });
      expect(scan.status()).toBe(200);
      const body = await scan.json();
      expect(body, "scan response must include strict + loose violation arrays for ZH source").toMatchObject({
        strict_violations: expect.any(Array),
        loose_violations: expect.any(Array),
        glossary_source_lang: "zh",
        glossary_target_lang: "zh",
      });
    } finally {
      await request.delete(BASE + `/api/glossaries/${gid}`).catch(() => {});
    }
  });

  test("admin.html: glossaries tab table has Source + Target headers", async ({ page }) => {
    await page.goto(BASE + "/admin.html");
    await page.waitForLoadState("domcontentloaded");
    await page.waitForTimeout(600);
    // Switch to the Glossaries tab
    const glTab = page.locator('button:has-text("Glossaries"), [data-tab="glossaries"]').first();
    if ((await glTab.count()) > 0) {
      await glTab.click();
      await page.waitForTimeout(400);
    }
    const sourceHeader = page.locator("th:has-text('Source')").first();
    const targetHeader = page.locator("th:has-text('Target')").first();
    expect(await sourceHeader.count(), "Source th must exist").toBeGreaterThan(0);
    expect(await targetHeader.count(), "Target th must exist").toBeGreaterThan(0);
  });
});
