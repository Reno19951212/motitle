// Extended admin panel tests — uses storageState (pre-logged in as admin)
const { test, expect, request: pwRequest } = require("@playwright/test");

const BASE = process.env.BASE_URL || "http://localhost:5001";

test("admin: weak password on create user shows error", async ({ page }) => {
  await page.goto(BASE + "/admin.html");

  await page.fill('[data-testid="admin-user-create-form"] input[name="username"]', "weakpw_test");
  await page.fill('[data-testid="admin-user-create-form"] input[name="password"]', "short");
  await page.click('[data-testid="admin-user-create-submit"]');

  await page.waitForTimeout(600);
  await expect(
    page.locator('[data-testid="admin-user-row"]', { hasText: "weakpw_test" })
  ).toHaveCount(0);
});

test("admin: duplicate username on create shows only one row", async ({ page }) => {
  await page.goto(BASE + "/admin.html");

  await page.fill('[data-testid="admin-user-create-form"] input[name="username"]', "dupe_e2e");
  await page.fill('[data-testid="admin-user-create-form"] input[name="password"]', "DupePass1!");
  await page.click('[data-testid="admin-user-create-submit"]');
  await expect(
    page.locator('[data-testid="admin-user-row"]', { hasText: "dupe_e2e" })
  ).toBeVisible({ timeout: 5000 });

  await page.fill('[data-testid="admin-user-create-form"] input[name="username"]', "dupe_e2e");
  await page.fill('[data-testid="admin-user-create-form"] input[name="password"]', "DupePass1!");
  await page.click('[data-testid="admin-user-create-submit"]');
  await page.waitForTimeout(600);

  await expect(
    page.locator('[data-testid="admin-user-row"]', { hasText: "dupe_e2e" })
  ).toHaveCount(1);

  page.on("dialog", d => d.accept());
  await page.locator('[data-testid="admin-user-row"]', { hasText: "dupe_e2e" })
            .locator('[data-testid="admin-user-delete"]')
            .click();
  await expect(
    page.locator('[data-testid="admin-user-row"]', { hasText: "dupe_e2e" })
  ).toHaveCount(0, { timeout: 5000 });
});

test("admin: toggle admin button flips admin status via API", async ({ request }) => {
  const create = await request.post(BASE + "/api/admin/users", {
    data: { username: "toggle_e2e", password: "TogglePass1!", is_admin: false },
  });
  expect([201, 409]).toContain(create.status());

  const users = await request.get(BASE + "/api/admin/users");
  const list = await users.json();
  const target = list.find(u => u.username === "toggle_e2e");
  expect(target).toBeTruthy();

  const toggle = await request.post(BASE + `/api/admin/users/${target.id}/toggle-admin`);
  expect(toggle.status()).toBe(200);
  const toggled = await toggle.json();
  expect(toggled.is_admin).toBe(true);

  await request.delete(BASE + `/api/admin/users/${target.id}`);
});

test("admin: reset password changes credentials via API", async ({ request }) => {
  const create = await request.post(BASE + "/api/admin/users", {
    data: { username: "resetpw_e2e", password: "OldPass1!", is_admin: false },
  });
  expect([201, 409]).toContain(create.status());

  const users = await request.get(BASE + "/api/admin/users");
  const list = await users.json();
  const target = list.find(u => u.username === "resetpw_e2e");

  const reset = await request.post(BASE + `/api/admin/users/${target.id}/reset-password`, {
    data: { new_password: "NewPass1!" },
  });
  expect(reset.status()).toBe(200);

  await request.delete(BASE + `/api/admin/users/${target.id}`);
});

test("admin: audit log tab shows table", async ({ page }) => {
  await page.goto(BASE + "/admin.html");

  await page.locator('.tab', { hasText: /audit|Audit|審計|日誌/ }).first().click();
  await page.waitForTimeout(800);

  await expect(page.locator('#adminAuditList')).toBeVisible();
});

test("admin: failed login appears in audit log", async ({ page }) => {
  // Create a fresh unauthenticated request context to trigger failed login
  // Use pwRequest (the Playwright APIRequest module) not the `request` fixture
  const unauthCtx = await pwRequest.newContext({ baseURL: BASE });
  await unauthCtx.post("/login", {
    data: { username: "admin", password: "wrong_audit_e2e_trigger_xyz" },
  });
  await unauthCtx.dispose();

  // Already logged in as admin — check audit
  await page.goto(BASE + "/admin.html");
  await page.locator('.tab', { hasText: /audit|Audit|審計|日誌/ }).first().click();
  await page.waitForTimeout(800);

  const auditList = page.locator('#adminAuditList');
  await expect(auditList).toContainText("login_failed", { timeout: 5000 });
});
