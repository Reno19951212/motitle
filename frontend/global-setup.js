// global-setup.js — logs in once as admin and saves session state for all tests
const { chromium, request: apiRequest } = require("@playwright/test");

const BASE = process.env.BASE_URL || "http://localhost:5001";

async function globalSetup() {
  // Use API request to login (faster than browser, no rate-limit accumulation)
  const ctx = await apiRequest.newContext({ baseURL: BASE });
  const r = await ctx.post("/login", {
    data: { username: "admin", password: "AdminPass1!" },
  });
  if (!r.ok()) {
    const body = await r.text();
    throw new Error(`Global setup: admin login failed ${r.status()}: ${body}`);
  }

  // Save the API context storage state (cookies) to file
  await ctx.storageState({ path: "./playwright-auth.json" });
  await ctx.dispose();
  console.log("[global-setup] Admin session saved to playwright-auth.json");
}

module.exports = globalSetup;
