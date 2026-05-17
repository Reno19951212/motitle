// Page navigation and page-load smoke tests
// Uses storageState — all tests start logged in as admin
const { test, expect } = require("@playwright/test");

const BASE = process.env.BASE_URL || "http://localhost:5001";

test("login page loads without JS errors", async ({ browser }) => {
  const ctx = await browser.newContext();
  const page = await ctx.newPage();
  const errors = [];
  page.on("pageerror", e => errors.push(e.message));
  await page.goto(BASE + "/login.html");
  await page.waitForLoadState("domcontentloaded");
  expect(errors.filter(e => !e.includes("favicon"))).toHaveLength(0);
  await ctx.close();
});

test("dashboard loads without JS errors after login", async ({ page }) => {
  const errors = [];
  page.on("pageerror", e => errors.push(e.message));
  await page.goto(BASE + "/");
  await expect(page).toHaveURL(BASE + "/");
  await page.waitForLoadState("domcontentloaded");
  const critical = errors.filter(e =>
    !e.includes("favicon") && !e.includes("socket") && !e.includes("WebSocket")
  );
  expect(critical).toHaveLength(0);
});

test("admin page loads without JS errors", async ({ page }) => {
  const errors = [];
  page.on("pageerror", e => errors.push(e.message));
  await page.goto(BASE + "/admin.html");
  await page.waitForLoadState("domcontentloaded");
  const critical = errors.filter(e =>
    !e.includes("favicon") && !e.includes("socket") && !e.includes("WebSocket")
  );
  expect(critical).toHaveLength(0);
});

test("proofread page loads without JS errors (no file)", async ({ page }) => {
  const errors = [];
  page.on("pageerror", e => errors.push(e.message));
  await page.goto(BASE + "/proofread.html?file_id=nonexistent");
  // Use domcontentloaded — networkidle times out due to open WebSocket
  await page.waitForLoadState("domcontentloaded");
  const critical = errors.filter(e =>
    !e.includes("favicon") && !e.includes("socket") && !e.includes("WebSocket") &&
    !e.includes("404") && !e.includes("nonexistent")
  );
  expect(critical).toHaveLength(0);
});

test("admin link navigates to admin page", async ({ page }) => {
  await page.goto(BASE + "/");
  await expect(page).toHaveURL(BASE + "/");
  await expect(page.locator('[data-testid="admin-link"]')).toBeVisible();
  await page.click('[data-testid="admin-link"]');
  await expect(page).toHaveURL(/admin\.html/);
});

test("logout button on dashboard works", async ({ page }) => {
  await page.goto(BASE + "/");
  await expect(page).toHaveURL(BASE + "/");
  await page.click('[data-testid="logout"]');
  await expect(page).toHaveURL(/login\.html/);
});

test("back link on admin page returns to dashboard", async ({ page }) => {
  await page.goto(BASE + "/admin.html");
  const backLink = page.locator('a', { hasText: /dashboard|返回|back/i }).first();
  await expect(backLink).toBeVisible();
  await backLink.click();
  await expect(page).toHaveURL(BASE + "/");
});
