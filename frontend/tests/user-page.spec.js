// user-page.spec.js — Playwright acceptance for the redesigned user.html
// Covers: left-tab nav visibility (admin), tab switching, inline delete confirm
// (no native dialog), remarks inline editor + toast, audit row expand.

const { test, expect } = require("@playwright/test");

const BASE = process.env.BASE_URL || "http://localhost:5001";

test.describe("user.html redesign", () => {
  test("admin sees three nav items", async ({ page }) => {
    await page.goto(BASE + "/user.html");
    // Wait for /api/me to resolve and admin sections to become visible
    await page.waitForLoadState("networkidle");
    await expect(page.locator("#navAccount")).toBeVisible();
    await expect(page.locator("#navUsers")).toBeVisible();
    await expect(page.locator("#navAudit")).toBeVisible();
  });

  test("tab switching shows the right pane", async ({ page }) => {
    await page.goto(BASE + "/user.html");
    await page.waitForLoadState("networkidle");

    // Click Users tab → users pane visible, account pane hidden
    await page.locator("#navUsers").click();
    await expect(page.locator("#pane-users")).toBeVisible();
    await expect(page.locator("#pane-account")).toBeHidden();

    // Click Audit tab → audit pane visible
    await page.locator("#navAudit").click();
    await expect(page.locator("#pane-audit")).toBeVisible();
  });

  test("inline delete confirm appears with no native dialog", async ({ page }) => {
    let nativeDialogFired = false;
    page.on("dialog", (d) => {
      nativeDialogFired = true;
      d.dismiss();
    });

    await page.goto(BASE + "/user.html");
    await page.waitForLoadState("networkidle");

    // Navigate to Users pane and wait for the table to render
    await page.locator("#navUsers").click();
    await page.waitForSelector("#adminUserList tr.urow", { timeout: 5000 });

    // Click an enabled (non-self) delete button
    const delBtn = page
      .locator('[data-testid="admin-user-delete"]:not([disabled])')
      .first();
    await delBtn.click();

    // Inline confirm row must appear
    await expect(
      page.locator('[data-testid="admin-user-delete-confirm"]')
    ).toBeVisible();

    // No native browser dialog should have fired
    expect(nativeDialogFired).toBe(false);

    // Cancel via the secondary button in the expand-danger row
    await page.locator(".expand-danger .btn-sec").click();
    await expect(
      page.locator('[data-testid="admin-user-delete-confirm"]')
    ).toHaveCount(0);
  });

  test("remarks inline editor saves and shows toast", async ({ page }) => {
    await page.goto(BASE + "/user.html");
    await page.waitForLoadState("networkidle");

    await page.locator("#navUsers").click();
    await page.waitForSelector("#adminUserList tr.urow", { timeout: 5000 });

    // Open the remarks editor on the first user row
    await page.locator('[data-testid="admin-user-remark"]').first().click();

    const ta = page.locator("#remarkInput");
    await expect(ta).toBeVisible();

    const note = "測試備註 " + Date.now();
    await ta.fill(note);

    // Save
    await page.locator('[data-testid="admin-user-remark-save"]').click();

    // Toast must say 備註已儲存
    await expect(page.locator(".toast")).toContainText("備註已儲存");

    // The user list must re-render with the note visible
    await expect(page.locator("#adminUserList")).toContainText(note);
  });

  test("audit row expands to detail with Summary block", async ({ page }) => {
    await page.goto(BASE + "/user.html");
    await page.waitForLoadState("networkidle");

    await page.locator("#navAudit").click();
    await page.waitForSelector("#adminAuditList .audit-item", { timeout: 5000 });

    const first = page.locator("#adminAuditList .audit-item").first();
    await first.click();

    // The detail row directly after the clicked item should become visible
    await expect(
      page.locator("#adminAuditList .audit-detail-row").first()
    ).toBeVisible();

    // The Summary block header must appear
    await expect(page.locator(".adetail-block-head").first()).toContainText(
      "Summary"
    );
  });
});
