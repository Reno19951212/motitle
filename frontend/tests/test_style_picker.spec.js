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

test('upload confirm sends mt_style in FormData with no ReferenceError', async ({ page }) => {
  const errors = [];
  page.on('pageerror', e => errors.push(e.message));
  await page.goto(`${BASE}/login.html`);
  await page.fill('#loginUsername', 'admin_p3');
  await page.fill('#loginPassword', PROBE_PASS);
  await page.click('#loginSubmit');
  await page.waitForURL(`${BASE}/`);

  // intercept the transcribe POST so we capture FormData without real processing
  let captured = null;
  await page.route('**/api/transcribe', async route => {
    captured = route.request().postData() || '';
    await route.fulfill({ status: 202, contentType: 'application/json',
      body: JSON.stringify({ file_id: 'test', job_id: 'j', queue_position: 1 }) });
  });

  // pick a fake file -> opens the output-lang popup
  await page.setInputFiles('#fileInput', { name: 'clip.mp4', mimeType: 'video/mp4', buffer: Buffer.from('fake') });
  await page.waitForSelector('#olStartBtn', { state: 'visible' });
  await page.selectOption('#olSourceLang', 'en');
  // First-language lock: 英文 source auto-locks first output = 英文 (select disabled);
  // no manual selectOption('#olFirstLang') — it would fail on the disabled element.
  await page.selectOption('#olSecondLang', 'zh').catch(() => {});
  await page.selectOption('#mtStyle', 'racing');
  await page.click('#olStartBtn');
  await page.waitForTimeout(800);

  expect(errors).toEqual([]);              // no ReferenceError from pendingMtStyle scope
  expect(captured).not.toBeNull();          // the POST fired (FormData assembled OK)
  expect(captured).toContain('mt_style');   // mt_style sent
  expect(captured).toContain('racing');     // the selected style value
});
