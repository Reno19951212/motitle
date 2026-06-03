// Topbar per-language processing-progress (#topProgress) — replaces the pipeline strip.
const { test, expect } = require('@playwright/test');
const BASE = process.env.BASE_URL || 'http://localhost:5001';
const PASS = process.env.PROBE_PASS || 'TestPass1!';
test.use({ storageState: undefined });

async function adminLogin(page) {
  await page.goto(`${BASE}/login.html`);
  await page.fill('#loginUsername', 'admin_p3'); await page.fill('#loginPassword', PASS);
  await page.click('#loginSubmit'); await page.waitForURL(`${BASE}/`);
}

test('topbar shows #topProgress and NOT the old pipeline strip', async ({ page }) => {
  await adminLogin(page);
  await expect(page.locator('#topProgress')).toBeVisible();
  expect(await page.locator('#pipelineStrip').count()).toBe(0);          // strip removed
  await expect(page.locator('#topProgress')).toContainText('處理進度');
});

test('no file selected → 未選擇檔案', async ({ page }) => {
  await adminLogin(page);
  await page.evaluate(() => { activeFileId = null; renderStatusCard(); });
  await expect(page.locator('#topProgress')).toContainText('未選擇檔案');
});

test('selected output_lang file → per-target-language bars (第一/第二)', async ({ page }) => {
  await adminLogin(page);
  await page.waitForFunction(() => typeof renderStatusCard === 'function', { timeout: 10000 });
  await page.evaluate(() => {
    const FID = '__tp_test__';
    uploadedFiles[FID] = {
      id: FID, original_name: 't.mp4', status: 'done', translation_status: 'done',
      active_kind: 'output_lang',
      languages: [
        { role: 'first',  lang: 'yue', label: '口語廣東話' },
        { role: 'second', lang: 'en',  label: '英文' },
      ],
    };
    activeFileId = FID;
    renderStatusCard();
  });
  const bars = page.locator('#topProgress .tp-lang');
  await expect(bars).toHaveCount(2);                                     // first + second
  await expect(bars.nth(0)).toContainText('第一');
  await expect(bars.nth(1)).toContainText('第二');
  await expect(page.locator('#topProgress .tp-fill')).toHaveCount(2);    // progress fills
});
