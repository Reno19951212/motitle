// frontend/tests/test_admin_flow.spec.js
const { test, expect } = require("@playwright/test");

const BASE = process.env.BASE_URL || "http://localhost:5001";

test("admin can create + delete a user via dashboard", async ({ page }) => {
  // Login as admin
  await page.goto(BASE + "/login.html");
  await page.fill('[data-testid="login-form"] input[name="username"]', "admin");
  await page.fill('[data-testid="login-form"] input[name="password"]', "admin");
  await page.click('[data-testid="login-submit"]');

  // Admin link visible
  await expect(page.locator('[data-testid="admin-link"]')).toBeVisible();
  await page.click('[data-testid="admin-link"]');
  await expect(page).toHaveURL(/admin\.html/);

  // Create user
  await page.fill('[data-testid="admin-user-create-form"] input[name="username"]', "playwright_user");
  await page.fill('[data-testid="admin-user-create-form"] input[name="password"]', "pw");
  await page.click('[data-testid="admin-user-create-submit"]');

  // Wait for the new row to appear
  await expect(page.locator('[data-testid="admin-user-row"]', { hasText: "playwright_user" })).toBeVisible();

  // Delete it (confirm dialog auto-accept)
  page.on("dialog", d => d.accept());
  await page.locator('[data-testid="admin-user-row"]', { hasText: "playwright_user" })
            .locator('[data-testid="admin-user-delete"]')
            .click();
  await expect(page.locator('[data-testid="admin-user-row"]', { hasText: "playwright_user" })).toHaveCount(0);
});
