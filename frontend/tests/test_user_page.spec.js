const { test, expect } = require('@playwright/test');
const BASE = process.env.BASE_URL || 'http://localhost:5001';
const USER = process.env.PROBE_USER || 'admin_p3';
const PASS = process.env.PROBE_PASS || 'TestPass1!';
test.use({ storageState: undefined });
async function login(page) {
  const r = await page.request.post(BASE + '/login', { data: { username: USER, password: PASS } });
  if (!r.ok()) throw new Error(`Login failed: ${r.status()}`);
}
test('admin sees account + user-mgmt + audit', async ({ page }) => {
  await login(page);
  await page.goto(BASE + '/user.html', { waitUntil: 'networkidle' });
  await expect(page.locator('#accountSection')).toBeVisible();
  await expect(page.locator('#accountUsername')).toHaveText('admin_p3');
  await expect(page.locator('#userMgmtSection')).toBeVisible();
  await expect(page.locator('#auditSection')).toBeVisible();
  await expect(page.locator('#adminUserList tr').first()).toBeVisible({ timeout: 5000 });
});
test('change-password wrong old shows error', async ({ page }) => {
  await login(page);
  await page.goto(BASE + '/user.html', { waitUntil: 'networkidle' });
  await page.fill('input[name="old_password"]', 'definitely-wrong');
  await page.fill('input[name="new_password"]', 'BrandNew9$');
  await page.click('#changePwForm button[type="submit"]');
  await expect(page.locator('#changePwMsg.err')).toBeVisible({ timeout: 4000 });
});
