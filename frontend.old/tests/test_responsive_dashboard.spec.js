// Responsive dashboard and proofread tests
// Uses storageState (pre-logged in as admin)
const { test, expect } = require("@playwright/test");

const BASE = process.env.BASE_URL || "http://localhost:5001";

test.describe("Mobile dashboard (375x667)", () => {
  test.use({ viewport: { width: 375, height: 667 } });

  test("hamburger button visible on mobile", async ({ page }) => {
    await page.goto(BASE + "/");
    await expect(page).toHaveURL(BASE + "/");
    await expect(page.locator('[data-testid="mobile-hamburger"]')).toBeVisible();
  });

  test("hamburger opens drawer with overlay", async ({ page }) => {
    await page.goto(BASE + "/");
    await expect(page).toHaveURL(BASE + "/");

    await page.click('[data-testid="mobile-hamburger"]');
    await expect(page.locator('[data-testid="mobile-sidebar-drawer"]')).toBeVisible();
    await expect(page.locator('[data-testid="mobile-sidebar-overlay"]')).toBeVisible();

    // Tap overlay closes drawer
    await page.click('[data-testid="mobile-sidebar-overlay"]');
    await expect(page.locator('[data-testid="mobile-sidebar-drawer"]')).not.toBeVisible();
  });
});

test.describe("Desktop dashboard (1920x1080)", () => {
  test.use({ viewport: { width: 1920, height: 1080 } });

  test("hamburger button hidden on desktop", async ({ page }) => {
    await page.goto(BASE + "/");
    await expect(page).toHaveURL(BASE + "/");
    await expect(page.locator('[data-testid="mobile-hamburger"]')).not.toBeVisible();
  });
});

test.describe("Proofread mobile (375x667)", () => {
  test.use({ viewport: { width: 375, height: 667 } });

  test("mobile tabs visible + segments tab visible", async ({ page }) => {
    await page.goto(BASE + "/proofread.html?file_id=nonexistent");
    await expect(page.locator('[data-testid="proofread-mobile-tab-video"]')).toBeVisible();
    await expect(page.locator('[data-testid="proofread-mobile-tab-segments"]')).toBeVisible();
  });
});
