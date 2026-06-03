const { test, expect } = require('@playwright/test');
const BASE = process.env.BASE_URL || 'http://localhost:5002';
const PROBE_PASS = process.env.PROBE_PASS || 'TestPass1!';

test('upload popup has 翻譯風格 style picker with 3 options default 通用', async ({ page }) => {
  await page.goto(`${BASE}/login.html`);
  await page.fill('#loginUsername', 'admin_p3');
  await page.fill('#loginPassword', PROBE_PASS);
  await page.click('#loginSubmit');
  await page.waitForURL(`${BASE}/`);
  const sel = page.locator('#mtStyle');
  await expect(sel).toHaveCount(1);
  const opts = await sel.locator('option').allTextContents();
  expect(opts).toEqual(expect.arrayContaining(['通用', '體育新聞', '馬會賽馬']));
  await expect(sel).toHaveValue('generic');
});
