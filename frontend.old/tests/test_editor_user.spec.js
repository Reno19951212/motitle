// Regular (non-admin) user flow tests
// Verifies that the editor account can use the system but has no admin access.
const { test, expect } = require("@playwright/test");

const BASE = process.env.BASE_URL || "http://localhost:5001";
const FRESH = { storageState: { cookies: [], origins: [] } };

test.describe("Editor user flow", () => {
  // Login once for the whole describe block to avoid rate-limit hits.
  let editorState;

  test.beforeAll(async ({ browser }) => {
    const ctx = await browser.newContext(FRESH);
    const page = await ctx.newPage();
    await page.goto(BASE + "/login.html");
    await page.fill('[data-testid="login-form"] input[name="username"]', "editor");
    await page.fill('[data-testid="login-form"] input[name="password"]', "Editor2026!");
    await page.click('[data-testid="login-submit"]');
    await expect(page).toHaveURL(BASE + "/", { timeout: 10000 });
    editorState = await ctx.storageState();
    await ctx.close();
  });

  test("editor can log in and sees dashboard", async ({ browser }) => {
    const ctx = await browser.newContext({ storageState: editorState });
    const page = await ctx.newPage();
    await page.goto(BASE + "/");
    await expect(page).toHaveURL(BASE + "/");
    await expect(page.locator('[data-testid="user-chip"]')).toContainText("editor");
    await ctx.close();
  });

  test("editor does not see admin link", async ({ browser }) => {
    const ctx = await browser.newContext({ storageState: editorState });
    const page = await ctx.newPage();
    await page.goto(BASE + "/");
    await expect(page.locator('[data-testid="admin-link"]')).not.toBeVisible();
    await ctx.close();
  });

  test("editor can log out", async ({ browser }) => {
    const ctx = await browser.newContext({ storageState: editorState });
    const page = await ctx.newPage();
    await page.goto(BASE + "/");
    await page.click('[data-testid="logout"]');
    await expect(page).toHaveURL(/login\.html/);
    await ctx.close();
  });

  test("editor API: /api/me returns editor info", async ({ browser }) => {
    const ctx = await browser.newContext({ storageState: editorState });
    const r = await ctx.request.get(BASE + "/api/me");
    expect(r.status()).toBe(200);
    const body = await r.json();
    expect(body.username).toBe("editor");
    expect(body.is_admin).toBe(false);
    await ctx.close();
  });

  test("editor API: /api/admin/users returns 403", async ({ browser }) => {
    const ctx = await browser.newContext({ storageState: editorState });
    const r = await ctx.request.get(BASE + "/api/admin/users");
    expect(r.status()).toBe(403);
    await ctx.close();
  });

  test("editor can access /api/files", async ({ browser }) => {
    const ctx = await browser.newContext({ storageState: editorState });
    const r = await ctx.request.get(BASE + "/api/files");
    expect(r.status()).toBe(200);
    const body = await r.json();
    expect(body).toHaveProperty("files");
    await ctx.close();
  });

  test("editor can access /api/profiles", async ({ browser }) => {
    const ctx = await browser.newContext({ storageState: editorState });
    const r = await ctx.request.get(BASE + "/api/profiles");
    expect(r.status()).toBe(200);
    const body = await r.json();
    expect(body).toHaveProperty("profiles");
    await ctx.close();
  });

  test("editor visiting /admin.html gets 403 (admin-only page)", async ({ browser }) => {
    // Backend returns HTTP 403 + JSON error for non-admin authenticated users.
    // The URL stays at /admin.html but the HTML content is never sent.
    const ctx = await browser.newContext({ storageState: editorState });
    const r = await ctx.request.get(BASE + "/admin.html");
    expect(r.status()).toBe(403);
    const body = await r.json();
    expect(body).toHaveProperty("error");
    await ctx.close();
  });
});
