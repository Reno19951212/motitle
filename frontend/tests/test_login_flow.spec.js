// frontend/tests/test_login_flow.spec.js
// R5 Phase 1 — login → dashboard → logout flow.
// RED state: written in E3, expected to fail until E4 (user chip) ships.
// GREEN state: passes in E6 once admin user bootstrapped + server running.
const { test, expect } = require("@playwright/test");

const BASE = process.env.BASE_URL || "http://localhost:5001";

test("login then dashboard shows user chip", async ({ page }) => {
  await page.goto(BASE + "/");
  // unauth → redirected to /login
  await expect(page).toHaveURL(/login\.html/);

  await page.fill('[data-testid="login-form"] input[name="username"]', "admin");
  await page.fill('[data-testid="login-form"] input[name="password"]', "admin");
  await page.click('[data-testid="login-submit"]');

  // dashboard
  await expect(page).toHaveURL(BASE + "/");
  await expect(page.locator('[data-testid="user-chip"]')).toContainText("admin");

  // logout returns to login
  await page.click('[data-testid="logout"]');
  await expect(page).toHaveURL(/login\.html/);
});
