// R5 Phase 1 — login → dashboard → logout flow.
// Uses storageState from global-setup.js (admin already logged in)
const { test, expect } = require("@playwright/test");

const BASE = process.env.BASE_URL || "http://localhost:5001";

test("login then dashboard shows user chip", async ({ page }) => {
  // Already logged in via storageState
  await page.goto(BASE + "/");
  await expect(page).toHaveURL(BASE + "/");
  await expect(page.locator('[data-testid="user-chip"]')).toContainText("admin");

  // logout returns to login
  await page.click('[data-testid="logout"]');
  await expect(page).toHaveURL(/login\.html/);
});
