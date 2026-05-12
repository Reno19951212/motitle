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
