// Comprehensive live verification of the redesigned user.html.
//
// Prerequisites — a backend serving THIS checkout's frontend + two seeded
// accounts (an admin to drive the page, a non-admin to verify access gating).
// From backend/ with the venv active and FLASK_SECRET_KEY exported:
//   python -c "from auth.users import init_db,create_user,get_user_by_username,update_password as up; import app; \
//     db=app.app.config['AUTH_DB_PATH']; init_db(db); \
//     [ (up(db,n,'PwTest1234!') if get_user_by_username(db,n) else create_user(db,n,'PwTest1234!',is_admin=a)) \
//       for n,a in [('pwtest_admin',True),('pwtest_user',False)] ]"
//
// Run with: BASE_URL=http://localhost:5001 PROBE_USER=pwtest_admin PROBE_PASS='PwTest1234!' \
//           npx playwright test tests/user-page-full.spec.js --workers=1
// Self-cleaning: temp users created during the run are deleted by the tests.
// The non-admin test logs in as `pwtest_user` (also seeded above).
const { test, expect } = require("@playwright/test");

const BASE = process.env.BASE_URL || "http://localhost:5001";
const ADMIN_USER = process.env.PROBE_USER || "pwtest_admin";
const ADMIN_PASS = process.env.PROBE_PASS || "PwTest1234!";
const SHOT = "test-results/userpage";

async function gotoUser(page) {
  await page.goto(BASE + "/user.html");
  await expect(page.locator("#navUsers")).toBeVisible({ timeout: 10000 });
}
function rowByName(page, name) {
  return page.locator('[data-testid="admin-user-row"]', { hasText: name });
}
// Robust against stacked toasts: match the specific toast by text.
function toast(page, text) {
  return page.locator(".toast", { hasText: text });
}

test.describe("identity + account pane", () => {
  test("identity card shows username, role pill, meta chips", async ({ page }) => {
    await gotoUser(page);
    await expect(page.locator("#accountUsername")).toHaveText(ADMIN_USER);
    await expect(page.locator("#accountRole")).toContainText("管理員");
    await expect(page.locator("#accountMeta")).toContainText("ID");
    await expect(page.locator("#userChipName")).toHaveText(ADMIN_USER);
    await page.screenshot({ path: `${SHOT}-account.png`, fullPage: true });
  });

  test("own-remarks box hidden when caller has no remarks", async ({ page }) => {
    await gotoUser(page);
    await expect(page.locator("#ownRemark")).toBeHidden();
  });

  test("change-password: wrong old password shows inline error (no real change)", async ({ page }) => {
    await gotoUser(page);
    await page.fill('#changePwForm input[name="old_password"]', "definitely-wrong-old");
    await page.fill('#changePwForm input[name="new_password"]', "BrandNewPass1!");
    await page.click('#changePwForm button[type="submit"]');
    await expect(page.locator("#changePwMsg")).toHaveClass(/err/);
    await expect(page.locator("#changePwMsg")).toContainText("✕");
  });
});

test.describe("user management — full CRUD lifecycle", () => {
  const NAME = "pw_e2e_user";

  test("create → reset(new icon) → toggle admin → remarks set/clear → delete", async ({ page }) => {
    await gotoUser(page);
    await page.locator("#navUsers").click();
    await expect(page.locator("#pane-users")).toBeVisible();

    // pre-clean: if a stale row exists from a prior failed run, delete it
    if (await rowByName(page, NAME).count()) {
      await rowByName(page, NAME).locator('[data-testid="admin-user-delete"]').click();
      await page.locator('[data-testid="admin-user-delete-confirm"]').click();
      await expect(rowByName(page, NAME)).toHaveCount(0);
    }

    // CREATE
    await page.fill('#adminUserCreateForm input[name="username"]', NAME);
    await page.fill('#adminUserCreateForm input[name="password"]', "PwTest1234!");
    await page.click('[data-testid="admin-user-create-submit"]');
    await expect(toast(page, "用戶已建立").first()).toBeVisible();
    await expect(rowByName(page, NAME)).toBeVisible();
    await expect(rowByName(page, NAME)).toContainText("用戶");       // role pill
    await expect(rowByName(page, NAME).locator(".remark-empty")).toBeVisible();

    // RESET PASSWORD via the NEW reset icon button
    const row = rowByName(page, NAME);
    await expect(row.locator('[data-testid="admin-user-reset"]')).toBeVisible();
    await row.locator('[data-testid="admin-user-reset"]').click();
    await expect(page.locator("#resetPwInput")).toBeVisible();
    // edge: too-short → error, no success toast
    await page.fill("#resetPwInput", "123");
    await page.click(".expand-edit .btn-primary");
    await expect(toast(page, "密碼太短").first()).toBeVisible();
    // valid reset
    await page.fill("#resetPwInput", "FreshPass9!");
    await page.click(".expand-edit .btn-primary");
    await expect(toast(page, "密碼已重設").first()).toBeVisible();

    // TOGGLE ADMIN up then down
    await rowByName(page, NAME).locator('[title="升為管理員"]').click();
    await expect(toast(page, "權限已更新").first()).toBeVisible();
    await expect(rowByName(page, NAME)).toContainText("管理員");
    await rowByName(page, NAME).locator('[title="降級為用戶"]').click();
    await expect(rowByName(page, NAME)).toContainText("用戶");

    // REMARKS set
    await rowByName(page, NAME).locator('[data-testid="admin-user-remark"]').click();
    await expect(page.locator("#remarkInput")).toBeVisible();
    await expect(page.locator("#remarkInput")).toHaveAttribute("maxlength", "500");
    await page.fill("#remarkInput", "夜更測試備註");
    await page.click('[data-testid="admin-user-remark-save"]');
    await expect(toast(page, "備註已儲存").first()).toBeVisible();
    await expect(rowByName(page, NAME)).toContainText("夜更測試備註");

    // REMARKS clear
    await rowByName(page, NAME).locator('[data-testid="admin-user-remark"]').click();
    await page.fill("#remarkInput", "");
    await page.click('[data-testid="admin-user-remark-save"]');
    await expect(toast(page, "備註已儲存").first()).toBeVisible();
    await expect(rowByName(page, NAME).locator(".remark-empty")).toBeVisible();

    await page.screenshot({ path: `${SHOT}-users.png`, fullPage: true });

    // DELETE (cancel first, then confirm)
    await rowByName(page, NAME).locator('[data-testid="admin-user-delete"]').click();
    await expect(page.locator('[data-testid="admin-user-delete-confirm"]')).toBeVisible();
    await page.locator(".expand-danger .btn-sec").click();        // cancel
    await expect(page.locator('[data-testid="admin-user-delete-confirm"]')).toHaveCount(0);
    await expect(rowByName(page, NAME)).toBeVisible();             // still there
    await rowByName(page, NAME).locator('[data-testid="admin-user-delete"]').click();
    await page.locator('[data-testid="admin-user-delete-confirm"]').click();
    await expect(toast(page, "用戶已刪除").first()).toBeVisible();
    await expect(rowByName(page, NAME)).toHaveCount(0);
  });

  test("create edge cases: weak password + duplicate username rejected", async ({ page }) => {
    await gotoUser(page);
    await page.locator("#navUsers").click();
    // weak pw (client guard fires first: <8 chars → 密碼太短)
    await page.fill('#adminUserCreateForm input[name="username"]', "pw_e2e_weak");
    await page.fill('#adminUserCreateForm input[name="password"]', "123");
    await page.click('[data-testid="admin-user-create-submit"]');
    await expect(toast(page, "密碼太短").first()).toBeVisible();
    await expect(rowByName(page, "pw_e2e_weak")).toHaveCount(0);
    // duplicate: create then create again → backend 409 → 建立失敗
    await page.fill('#adminUserCreateForm input[name="username"]', "pw_e2e_dup");
    await page.fill('#adminUserCreateForm input[name="password"]', "PwTest1234!");
    await page.click('[data-testid="admin-user-create-submit"]');
    await expect(rowByName(page, "pw_e2e_dup")).toBeVisible();
    await page.fill('#adminUserCreateForm input[name="username"]', "pw_e2e_dup");
    await page.fill('#adminUserCreateForm input[name="password"]', "PwTest1234!");
    await page.click('[data-testid="admin-user-create-submit"]');
    await expect(toast(page, "建立失敗").first()).toBeVisible();
    // cleanup
    await rowByName(page, "pw_e2e_dup").locator('[data-testid="admin-user-delete"]').click();
    await page.locator('[data-testid="admin-user-delete-confirm"]').click();
    await expect(rowByName(page, "pw_e2e_dup")).toHaveCount(0);
  });

  test("own row: delete disabled + 你自己 marker", async ({ page }) => {
    await gotoUser(page);
    await page.locator("#navUsers").click();
    const me = rowByName(page, ADMIN_USER).first();
    await expect(me).toContainText("你自己");
    await expect(me.locator('[data-testid="admin-user-delete"]')).toBeDisabled();
  });

  test("inline panels are mutually exclusive on a row", async ({ page }) => {
    await gotoUser(page);
    await page.locator("#navUsers").click();
    const me = rowByName(page, ADMIN_USER).first();
    await me.locator('[data-testid="admin-user-remark"]').click();
    await expect(page.locator("#remarkInput")).toBeVisible();
    await me.locator('[data-testid="admin-user-reset"]').click();   // switches to reset
    await expect(page.locator("#resetPwInput")).toBeVisible();
    await expect(page.locator("#remarkInput")).toHaveCount(0);       // remark closed
    // only ONE expand-row exists in the table
    await expect(page.locator("#adminUserList tr.expand-row")).toHaveCount(1);
  });
});

test.describe("audit log", () => {
  test("rows render, expand to detail, search + filter chips work", async ({ page }) => {
    await gotoUser(page);
    await page.locator("#navAudit").click();
    await expect(page.locator("#pane-audit")).toBeVisible();
    await page.waitForSelector("#adminAuditList .audit-item", { timeout: 8000 });

    // expand first row
    const first = page.locator("#adminAuditList .audit-item").first();
    await first.click();
    await expect(page.locator("#adminAuditList .audit-detail-row").first()).toBeVisible();
    await expect(page.locator(".adetail-block-head").first()).toContainText("Summary");
    await page.screenshot({ path: `${SHOT}-audit.png`, fullPage: true });

    // filter chip 刪除 → every visible badge is a delete badge (or none)
    await page.locator('#auditFilter [data-filter="delete"]').click();
    const badges = page.locator("#adminAuditList .act-badge");
    const n = await badges.count();
    for (let i = 0; i < n; i++) {
      await expect(badges.nth(i)).toContainText("delete");
    }
    // back to 全部
    await page.locator('#auditFilter [data-filter="all"]').click();
    await expect(page.locator("#adminAuditList .audit-item").first()).toBeVisible();

    // search narrows
    await page.fill("#auditSearch", "update_remarks");
    const after = page.locator("#adminAuditList .act-badge");
    const m = await after.count();
    for (let i = 0; i < m; i++) {
      await expect(after.nth(i)).toContainText("update_remarks");
    }
  });
});

test.describe("own-remarks round trip (admin sets own remark → /api/me shows it)", () => {
  test("set own remark, reload, see it on 我的帳戶; then clear", async ({ page }) => {
    await gotoUser(page);
    await page.locator("#navUsers").click();
    const me = rowByName(page, ADMIN_USER).first();
    await me.locator('[data-testid="admin-user-remark"]').click();
    await page.fill("#remarkInput", "我的測試備註");
    await page.click('[data-testid="admin-user-remark-save"]');
    await expect(toast(page, "備註已儲存").first()).toBeVisible();

    // reload → 我的帳戶 pane shows the own-remarks box
    await page.reload();
    await expect(page.locator("#navUsers")).toBeVisible();
    await expect(page.locator("#ownRemark")).toBeVisible();
    await expect(page.locator("#ownRemarkText")).toContainText("我的測試備註");

    // clear it again (cleanup)
    await page.locator("#navUsers").click();
    await rowByName(page, ADMIN_USER).first().locator('[data-testid="admin-user-remark"]').click();
    await page.fill("#remarkInput", "");
    await page.click('[data-testid="admin-user-remark-save"]');
    await expect(toast(page, "備註已儲存").first()).toBeVisible();
  });
});

test.describe("non-admin access", () => {
  test("non-admin sees only 我的帳戶 (no admin nav/panes)", async ({ page, context }) => {
    // log out admin storageState, log in as the seeded non-admin via API
    // (shares the page's cookie jar — avoids the login-form fetch/redirect race)
    await context.clearCookies();
    const lr = await page.request.post(BASE + "/login", {
      data: { username: "pwtest_user", password: "PwTest1234!" },
    });
    expect(lr.ok()).toBeTruthy();
    await page.goto(BASE + "/user.html");
    await expect(page.locator("#navAccount")).toBeVisible();
    await expect(page.locator("#navUsers")).toBeHidden();
    await expect(page.locator("#navAudit")).toBeHidden();
    await expect(page.locator("#navAdminGroup")).toBeHidden();
    await expect(page.locator("#accountRole")).toContainText("用戶");
  });
});
