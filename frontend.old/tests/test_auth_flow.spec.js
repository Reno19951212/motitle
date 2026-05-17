// Auth flow edge cases: wrong creds, missing fields, non-admin access guard
const { test, expect } = require("@playwright/test");

const BASE = process.env.BASE_URL || "http://localhost:5001";

// Use { storageState: { cookies: [], origins: [] } } to override config-level storageState
const FRESH = { storageState: { cookies: [], origins: [] } };

// Test protection at the API level (fast, reliable)
test("protected API returns 401 when not logged in", async ({ browser }) => {
  const ctx = await browser.newContext(FRESH);
  const r = await ctx.request.get(BASE + "/api/me");
  expect(r.status()).toBe(401);
  await ctx.close();
});

test("admin API returns 401 when not logged in", async ({ browser }) => {
  const ctx = await browser.newContext(FRESH);
  const r = await ctx.request.get(BASE + "/api/admin/users");
  expect(r.status()).toBe(401);
  await ctx.close();
});

test("wrong credentials returns 401", async ({ browser }) => {
  const ctx = await browser.newContext(FRESH);
  const r = await ctx.request.post(BASE + "/login", {
    data: { username: "admin", password: "wrongpassword_xy7z" },
  });
  expect(r.status()).toBe(401);
  await ctx.close();
});

test("missing password field returns 400", async ({ browser }) => {
  const ctx = await browser.newContext(FRESH);
  const r = await ctx.request.post(BASE + "/login", {
    data: { username: "admin" },
  });
  expect(r.status()).toBe(400);
  await ctx.close();
});

test("wrong credentials browser stays on login page", async ({ browser }) => {
  const ctx = await browser.newContext(FRESH); // fresh, no session
  const page = await ctx.newPage();
  await page.goto(BASE + "/login.html");
  await page.fill('[data-testid="login-form"] input[name="username"]', "admin");
  await page.fill('[data-testid="login-form"] input[name="password"]', "wrongpassword");
  await page.click('[data-testid="login-submit"]');
  // Should stay on login page
  await expect(page).toHaveURL(/login\.html/, { timeout: 8000 });
  await ctx.close();
});

test("non-admin user does not see admin-link", async ({ browser }) => {
  // Create non-admin user via API (using pre-authenticated request)
  const adminCtx = await browser.newContext({ storageState: "./playwright-auth.json" });
  const r = await adminCtx.request.post(BASE + "/api/admin/users", {
    data: { username: "pw_nonadmin_test", password: "TestPass1!", is_admin: false },
  });
  expect([201, 409]).toContain(r.status());
  await adminCtx.close();

  // Login as non-admin in fresh context
  const userCtx = await browser.newContext(FRESH);
  const userPage = await userCtx.newPage();
  await userPage.goto(BASE + "/login.html");
  await userPage.fill('[data-testid="login-form"] input[name="username"]', "pw_nonadmin_test");
  await userPage.fill('[data-testid="login-form"] input[name="password"]', "TestPass1!");
  await userPage.click('[data-testid="login-submit"]');
  await expect(userPage).toHaveURL(BASE + "/", { timeout: 10000 });

  // admin-link should not be visible
  await expect(userPage.locator('[data-testid="admin-link"]')).not.toBeVisible();
  await userCtx.close();

  // Cleanup non-admin user
  const cleanupCtx = await browser.newContext({ storageState: "./playwright-auth.json" });
  const users = await cleanupCtx.request.get(BASE + "/api/admin/users");
  const list = await users.json();
  const target = list.find(u => u.username === "pw_nonadmin_test");
  if (target) {
    await cleanupCtx.request.delete(BASE + `/api/admin/users/${target.id}`);
  }
  await cleanupCtx.close();
});

test("user chip shows logged-in username", async ({ page }) => {
  // Already logged in as admin via storageState
  await page.goto(BASE + "/");
  await expect(page).toHaveURL(BASE + "/");
  const chip = page.locator('[data-testid="user-chip"]');
  await expect(chip).toBeVisible();
  await expect(chip).toContainText("admin");
});
