// test_output_lang_realtime_list.spec.js — Bug 2: home-page "realtime subtitle"
// transcript inspector list for output_lang files.
//
//   - single output language  → each transcript row shows ONE line (.t-en),
//     no phantom second line (.t-zh) duplicating the same language.
//   - two output languages     → each row shows BOTH lines, with DIFFERENT
//     language text (first in .t-en, second in .t-zh).
//
// Before the fix, loadFileSegments() set zh_text = _en_text = firstText for
// every output_lang segment, so the transcript list rendered two identical
// lines even for single-language files.
//
// All API calls stubbed via page.route — no real backend output_lang file
// needed. font-preview.js falls back to http://localhost:5001 for /api/fonts
// and /api/profiles/active, so those are stubbed with an any-host glob.

const { test, expect } = require('@playwright/test');

const BASE = process.env.BASE_URL || 'http://localhost:5001';
const USER = process.env.PROBE_USER || 'admin_p3';
const PASS = process.env.PROBE_PASS || 'TestPass1!';

const FID_SINGLE = 'rt-output-lang-single';
const FID_DUAL = 'rt-output-lang-dual';

const FILE_SINGLE = {
  id: FID_SINGLE, original_name: 'single.mp4', status: 'done',
  active_kind: 'output_lang', translation_status: 'done',
  languages: [{ role: 'first', lang: 'yue', label: '口語廣東話' }],
};
const FILE_DUAL = {
  id: FID_DUAL, original_name: 'dual.mp4', status: 'done',
  active_kind: 'output_lang', translation_status: 'done',
  languages: [
    { role: 'first', lang: 'yue', label: '口語廣東話' },
    { role: 'second', lang: 'en', label: '英文' },
  ],
};

const TRANS_SINGLE = {
  translations: [
    { idx: 0, start: 1.0, end: 4.0, yue_text: '今日天氣係咁㗎喎',
      by_lang: { yue: { text: '今日天氣係咁㗎喎', status: 'pending', flags: [] } },
      status: 'pending', flags: [] },
  ],
};
const TRANS_DUAL = {
  translations: [
    { idx: 0, start: 1.0, end: 4.0,
      yue_text: '今日天氣係咁㗎喎', en_text: 'The weather is like this today',
      by_lang: {
        yue: { text: '今日天氣係咁㗎喎', status: 'pending', flags: [] },
        en: { text: 'The weather is like this today', status: 'pending', flags: [] },
      }, status: 'pending', flags: [] },
  ],
};

test.use({ storageState: undefined, viewport: { width: 1512, height: 900 } });

async function stub(page, fileStub, transStub) {
  const fid = fileStub.id;
  await page.route('**/api/files', (r) => r.request().method() === 'GET'
    ? r.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ files: [fileStub] }) })
    : r.continue());
  await page.route(`**/api/files/${fid}/languages`, (r) =>
    r.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ languages: fileStub.languages }) }));
  await page.route(`**/api/files/${fid}/translations`, (r) => r.request().method() === 'GET'
    ? r.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(transStub) })
    : r.continue());
  await page.route(`**/api/files/${fid}/segments`, (r) =>
    r.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ segments: [] }) }));
  await page.route(`**/api/files/${fid}/media`, (r) =>
    r.fulfill({ status: 204, contentType: 'video/mp4', body: Buffer.alloc(0) }));
  // font-preview.js cross-origin fallbacks (any host).
  await page.route('**/api/fonts', (r) =>
    r.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify([]) }));
  await page.route('**/api/profiles/active', (r) => r.request().method() === 'GET'
    ? r.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ profile: { id: 'p', name: 'P', font: { family: 'Noto Sans TC', size: 48, color: '#ffffff', outline_color: '#000000', outline_width: 3, margin_bottom: 60 } } }) })
    : r.continue());
}

async function loadInTranscript(page, fileStub, transStub) {
  await stub(page, fileStub, transStub);
  const r = await page.request.post(BASE + '/login', { data: { username: USER, password: PASS } });
  if (!r.ok()) throw new Error(`Login failed: ${r.status()}`);
  await page.goto(BASE + '/');
  await page.waitForSelector('#inspectorBody', { timeout: 8000 });
  await page.evaluate(async (f) => {
    uploadedFiles[f.id] = f;
    activeFileId = f.id;
    currentTab = 'transcript';
    await loadFileSegments(f.id);
    switchTab('transcript');
  }, fileStub);
  await page.waitForSelector('.t-row', { timeout: 8000 });
}

test.describe.serial('output_lang home transcript list (Bug 2)', () => {

  test('single output language → one line per row (no duplicate .t-zh)', async ({ page }) => {
    await loadInTranscript(page, FILE_SINGLE, TRANS_SINGLE);
    const row = page.locator('.t-row').first();
    await expect(row.locator('.t-en')).toHaveText('今日天氣係咁㗎喎');
    expect(await row.locator('.t-zh').count()).toBe(0);   // no phantom 2nd line
  });

  test('two output languages → two lines per row with different languages', async ({ page }) => {
    await loadInTranscript(page, FILE_DUAL, TRANS_DUAL);
    const row = page.locator('.t-row').first();
    await expect(row.locator('.t-en')).toHaveText('今日天氣係咁㗎喎');             // first lang
    await expect(row.locator('.t-zh')).toHaveText('The weather is like this today'); // second lang
  });

  test('single output language → video overlay shows ONE line even in bilingual mode', async ({ page }) => {
    // Subtitle-source 'bilingual' on a single-language file used to stack the
    // first language twice (firstText\nfirstText) because the overlay fell back
    // to the first language when zh_text was empty. output_lang now passes zh
    // through unchanged → bilingual collapses to the single present language.
    const single = { ...FILE_SINGLE, id: 'rt-ol-single-bi', subtitle_source: 'bilingual' };
    await loadInTranscript(page, single, TRANS_SINGLE);
    await page.evaluate(() => updateSubtitleOverlay(2.0));   // inside segment 0 [1.0,4.0)
    const lines = await page.locator('#subtitleSvgText tspan').allTextContents();
    expect(lines.length).toBe(1);
    expect(lines[0]).toBe('今日天氣係咁㗎喎');
  });

});
