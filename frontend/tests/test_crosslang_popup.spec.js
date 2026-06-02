const { test, expect } = require('@playwright/test');
const BASE = process.env.BASE_URL || 'http://localhost:5001';
const USER = process.env.PROBE_USER || 'admin_p3';
const PASS = process.env.PROBE_PASS || 'TestPass1!';
test.use({ storageState: undefined });

test('popup has 粵語/普通話 source + 普通話 output + 繁簡 toggle, confirm sends them', async ({ page }) => {
  await page.route('**/api/fonts', r => r.fulfill({ status: 200, contentType: 'application/json', body: '[]' }));
  let posted = null;
  await page.route('**/api/transcribe', async (route) => {
    posted = route.request().postData();
    await route.fulfill({ status: 202, contentType: 'application/json',
      body: JSON.stringify({ file_id: 'x', job_id: 'j', status: 'queued', queue_position: 0 }) });
  });
  const r = await page.request.post(BASE + '/login', { data: { username: USER, password: PASS } });
  if (!r.ok()) throw new Error('login ' + r.status());
  await page.goto(BASE + '/');
  await page.waitForFunction(() => typeof openOutputLangModal === 'function');
  const srcOpts = await page.$$eval('#olSourceLang option', os => os.map(o => o.value));
  expect(srcOpts).toEqual(expect.arrayContaining(['yue', 'cmn', 'en', 'ja']));
  const outOpts = await page.$$eval('#olFirstLang option', os => os.map(o => o.value));
  expect(outOpts).toEqual(expect.arrayContaining(['yue', 'zh', 'cmn', 'en', 'ja']));
  expect(await page.locator('#olScript').count()).toBeGreaterThan(0);
  await page.evaluate(() => {
    selectedFile = new File([new Uint8Array([1])], 'clip.mp4', { type: 'video/mp4' });
    document.getElementById('olSourceLang').value = 'cmn';
    document.getElementById('olFirstLang').value = 'yue';
    document.getElementById('olScript').value = 'simp';
    openOutputLangModal(selectedFile);
    confirmOutputLangModal();
  });
  await expect.poll(() => posted, { timeout: 3000 }).not.toBeNull();
  expect(posted).toContain('source_language');
});
