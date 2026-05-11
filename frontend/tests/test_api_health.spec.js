// API health and readiness probe tests
// Tests using { request } start with admin session (from storageState in playwright.config.js)
const { test, expect } = require("@playwright/test");

const BASE = process.env.BASE_URL || "http://localhost:5001";

test("/api/ready returns {ready:true} without auth", async ({ request }) => {
  const r = await request.get(BASE + "/api/ready");
  expect(r.status()).toBe(200);
  const body = await r.json();
  expect(body.ready).toBe(true);
});

test("/api/health returns status ok", async ({ request }) => {
  const r = await request.get(BASE + "/api/health");
  expect(r.status()).toBe(200);
  const body = await r.json();
  expect(body).toHaveProperty("status");
});

// For unauthenticated tests, pass empty storageState to override config-level storageState
test("/api/me returns 401 when not logged in", async ({ browser }) => {
  const ctx = await browser.newContext({ storageState: { cookies: [], origins: [] } });
  const r = await ctx.request.get(BASE + "/api/me");
  expect(r.status()).toBe(401);
  await ctx.close();
});

test("/api/files returns 401 when not logged in", async ({ browser }) => {
  const ctx = await browser.newContext({ storageState: { cookies: [], origins: [] } });
  const r = await ctx.request.get(BASE + "/api/files");
  expect(r.status()).toBe(401);
  await ctx.close();
});

test("/api/profiles returns 401 when not logged in", async ({ browser }) => {
  const ctx = await browser.newContext({ storageState: { cookies: [], origins: [] } });
  const r = await ctx.request.get(BASE + "/api/profiles");
  expect(r.status()).toBe(401);
  await ctx.close();
});

test("/api/asr/engines returns engine list when logged in", async ({ request }) => {
  const r = await request.get(BASE + "/api/asr/engines");
  expect(r.status()).toBe(200);
  const body = await r.json();
  // Response: {"engines": [...]}
  expect(body).toHaveProperty("engines");
  expect(Array.isArray(body.engines)).toBe(true);
  expect(body.engines.length).toBeGreaterThan(0);
  for (const eng of body.engines) {
    expect(eng).toHaveProperty("engine");
    expect(eng).toHaveProperty("available");
  }
});

test("/api/translation/engines returns engine list when logged in", async ({ request }) => {
  const r = await request.get(BASE + "/api/translation/engines");
  expect(r.status()).toBe(200);
  const body = await r.json();
  expect(body).toHaveProperty("engines");
  expect(Array.isArray(body.engines)).toBe(true);
  expect(body.engines.length).toBeGreaterThan(0);
});

test("/api/profiles/active returns active profile or 404", async ({ request }) => {
  const r = await request.get(BASE + "/api/profiles/active");
  expect([200, 404]).toContain(r.status());
  if (r.status() === 200) {
    const body = await r.json();
    // Response: {"profile": {...}}
    expect(body).toHaveProperty("profile");
  }
});

test("/api/files returns files list when logged in", async ({ request }) => {
  const r = await request.get(BASE + "/api/files");
  expect(r.status()).toBe(200);
  const body = await r.json();
  // Response: {"files": [...]}
  expect(body).toHaveProperty("files");
  expect(Array.isArray(body.files)).toBe(true);
});

test("/api/me returns user info when logged in", async ({ request }) => {
  const r = await request.get(BASE + "/api/me");
  expect(r.status()).toBe(200);
  const body = await r.json();
  expect(body).toHaveProperty("username");
  expect(body.username).toBe("admin");
  expect(body).not.toHaveProperty("password_hash");
});
