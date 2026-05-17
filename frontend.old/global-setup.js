// global-setup.js — logs in once as admin (+ editor) and saves session state.
// Subsequent test runs reuse the cookie files until the session expires,
// which keeps /login under its 10/min rate limit during back-to-back ralph
// loops.
const fs = require("fs");
const { request: apiRequest } = require("@playwright/test");

const BASE = process.env.BASE_URL || "http://localhost:5001";

async function _loginAndSave(username, password, outPath) {
  // If we already have a valid session cookie file from a recent run, reuse
  // it. Hitting /login N times per minute trips the rate limiter (10/min).
  if (fs.existsSync(outPath)) {
    try {
      const probe = await apiRequest.newContext({ baseURL: BASE, storageState: outPath });
      const me = await probe.get("/api/me");
      if (me.ok()) {
        await probe.dispose();
        console.log(`[global-setup] reused cached session for ${username} at ${outPath}`);
        return;
      }
      await probe.dispose();
    } catch {}
  }
  const ctx = await apiRequest.newContext({ baseURL: BASE });
  const r = await ctx.post("/login", { data: { username, password } });
  if (!r.ok()) {
    const body = await r.text();
    throw new Error(`Global setup: ${username} login failed ${r.status()}: ${body}`);
  }
  await ctx.storageState({ path: outPath });
  await ctx.dispose();
  console.log(`[global-setup] ${username} session saved to ${outPath}`);
}

async function globalSetup() {
  await _loginAndSave("admin", "AdminPass1!", "./playwright-auth.json");
  await _loginAndSave("editor", "Editor2026!", "./playwright-auth-editor.json");
}

module.exports = globalSetup;
