// test_output_lang_proofread.spec.js — T9 Proofread editor for output_lang
//
// 測試 output_lang 模式嘅 proofread 編輯器：
//   1. detail-panel 標籤顯示第一/第二語言名稱（唔係 原文·EN / 譯文·ZH）
//   2. enInput（頂部欄位）對 output_lang **唔係** readonly
//   3. 單輸出語言（冇第二語言）時，zhInput 欄位隱藏
//
// 所有 API 請求透過 page.route stub 攔截，唔需要真實 backend 有 output_lang 檔案。
//
// Auth 模式跟 test_proofread_layout.spec.js — POST /login 再 goto。

const { test, expect } = require('@playwright/test');

const BASE = process.env.BASE_URL || 'http://localhost:5001';
const USER = process.env.PROBE_USER || 'admin_p3';
const PASS = process.env.PROBE_PASS || 'TestPass1!';

// Stub file ID
const STUB_FID = 'test-output-lang-stub-001';

// Stub translations (2 rows, yue first + en second)
const STUB_TRANSLATIONS_DUAL = {
  translations: [
    {
      idx: 0,
      start: 1.0,
      end: 4.0,
      source_text: '',
      yue_text: '今日天氣係咁㗎喎',
      en_text: 'The weather is like this today',
      by_lang: {
        yue: { text: '今日天氣係咁㗎喎', status: 'pending', flags: [] },
        en:  { text: 'The weather is like this today', status: 'pending', flags: [] },
      },
      status: 'pending',
      flags: [],
      approved: false,
    },
    {
      idx: 1,
      start: 4.5,
      end: 8.0,
      source_text: '',
      yue_text: '所以帶定遮好過',
      en_text: 'So it is better to bring an umbrella',
      by_lang: {
        yue: { text: '所以帶定遮好過', status: 'pending', flags: [] },
        en:  { text: 'So it is better to bring an umbrella', status: 'pending', flags: [] },
      },
      status: 'pending',
      flags: [],
      approved: false,
    },
  ],
};

// Stub translations — single output language (yue only)
const STUB_TRANSLATIONS_SINGLE = {
  translations: [
    {
      idx: 0,
      start: 1.0,
      end: 4.0,
      source_text: '',
      yue_text: '今日天氣係咁㗎喎',
      by_lang: {
        yue: { text: '今日天氣係咁㗎喎', status: 'pending', flags: [] },
      },
      status: 'pending',
      flags: [],
      approved: false,
    },
  ],
};

// File entry for dual-language output_lang file
const STUB_FILE_DUAL = {
  id: STUB_FID,
  original_name: 'stub-output-lang-dual.mp4',
  status: 'done',
  active_kind: 'output_lang',
  translation_status: 'done',
  subtitle_source: null,
  bilingual_order: null,
  languages: [
    { role: 'first', lang: 'yue', label: '口語廣東話' },
    { role: 'second', lang: 'en', label: '英文' },
  ],
};

// File entry for single-language output_lang file
const STUB_FILE_SINGLE = {
  id: STUB_FID + '-single',
  original_name: 'stub-output-lang-single.mp4',
  status: 'done',
  active_kind: 'output_lang',
  translation_status: 'done',
  subtitle_source: null,
  bilingual_order: null,
  languages: [
    { role: 'first', lang: 'yue', label: '口語廣東話' },
  ],
};

test.use({ storageState: undefined, viewport: { width: 1512, height: 900 } });

// ——————————————————————————————————————————————————————
// Helper: stub the API routes for a given file stub
// ——————————————————————————————————————————————————————
async function stubApiForFile(page, fileStub, translationsStub) {
  const fid = fileStub.id;

  // /api/files — return single-element list containing the stub file
  await page.route('**/api/files', async (route) => {
    if (route.request().method() !== 'GET') { await route.continue(); return; }
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ files: [fileStub] }),
    });
  });

  // /api/files/<id>/languages
  await page.route(`**/api/files/${fid}/languages`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ languages: fileStub.languages }),
    });
  });

  // /api/files/<id>/translations
  await page.route(`**/api/files/${fid}/translations`, async (route) => {
    if (route.request().method() !== 'GET') { await route.continue(); return; }
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(translationsStub),
    });
  });

  // /api/files/<id>/segments  — return empty (output_lang doesn't use this)
  await page.route(`**/api/files/${fid}/segments`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ segments: [] }),
    });
  });

  // /api/files/<id>/media — stub 200 (avoid 404 console noise)
  await page.route(`**/api/files/${fid}/media`, async (route) => {
    await route.fulfill({
      status: 204,
      contentType: 'video/mp4',
      body: Buffer.alloc(0),
    });
  });

  // /api/profiles/active — return minimal profile to avoid null errors
  await page.route('**/api/profiles/active', async (route) => {
    if (route.request().method() !== 'GET') { await route.continue(); return; }
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        profile: {
          id: 'stub-profile',
          name: 'Stub Profile',
          font: { family: 'Noto Sans TC', size: 48, color: '#ffffff', outline_color: '#000000', outline_width: 3, margin_bottom: 60 },
        },
      }),
    });
  });
}

// ——————————————————————————————————————————————————————
// Helper: login + goto proofread for the stub file
// ——————————————————————————————————————————————————————
async function openProofreadWithStub(page, fileStub, translationsStub) {
  const fid = fileStub.id;
  await stubApiForFile(page, fileStub, translationsStub);

  const r = await page.request.post(BASE + '/login', { data: { username: USER, password: PASS } });
  if (!r.ok()) throw new Error(`Login failed: ${r.status()}`);

  await page.goto(`${BASE}/proofread.html?file_id=${fid}`);
  // Wait until segs is populated
  await page.waitForFunction(
    () => typeof segs !== 'undefined' && segs.length > 0,
    { timeout: 15000 }
  );
  // Ensure detail panel is rendered for segment 0
  await page.evaluate(() => {
    if (typeof setCursor === 'function') setCursor(0);
  });
  await page.waitForSelector('#enInput', { state: 'attached', timeout: 8000 });
}

test.describe.serial('output_lang proofread editor', () => {

  // ————————————————————————————
  // Test 1: detail labels show first/second language names
  // ————————————————————————————
  test('detail labels show first/second language descriptor (NOT 原文·EN / 譯文·ZH)', async ({ page }) => {
    await openProofreadWithStub(page, STUB_FILE_DUAL, STUB_TRANSLATIONS_DUAL);

    // enInput label should show the first language descriptor
    const enLabelText = await page.locator('.rv-b-detail-field:first-of-type .rv-b-detail-label').textContent();
    expect(enLabelText).toContain('口語廣東話');
    expect(enLabelText).toContain('YUE');
    // Must NOT show the old static labels
    expect(enLabelText).not.toContain('原文 · EN');

    // zhInput label should show the second language descriptor
    const zhLabelText = await page.locator('.rv-b-detail-field:nth-of-type(2) .rv-b-detail-label').textContent();
    expect(zhLabelText).toContain('英文');
    expect(zhLabelText).toContain('EN');
    expect(zhLabelText).not.toContain('譯文 · ZH');
  });

  // ————————————————————————————
  // Test 2: enInput is NOT readonly for output_lang (unlike V6 which IS readonly)
  // ————————————————————————————
  test('enInput is editable (not readonly) for output_lang files', async ({ page }) => {
    await openProofreadWithStub(page, STUB_FILE_DUAL, STUB_TRANSLATIONS_DUAL);

    const isReadOnly = await page.locator('#enInput').evaluate(el => el.readOnly);
    expect(isReadOnly).toBe(false);

    // Also verify typing is possible
    const before = await page.locator('#enInput').inputValue();
    await page.locator('#enInput').fill(before + '_TEST');
    const after = await page.locator('#enInput').inputValue();
    expect(after).toBe(before + '_TEST');
  });

  // ————————————————————————————
  // Test 3: single-output stub hides the zhInput field
  // ————————————————————————————
  test('zhInput detail-field is hidden when only one output language', async ({ page }) => {
    await openProofreadWithStub(page, STUB_FILE_SINGLE, STUB_TRANSLATIONS_SINGLE);

    // The second detail field (wrapping zhInput) should not be visible
    // The field may be hidden via display:none or not rendered at all
    const zhFieldVisible = await page.locator('#zhInput').isVisible().catch(() => false);
    expect(zhFieldVisible).toBe(false);
  });

  // ————————————————————————————
  // Test 4: saveEnIfDirty for output_lang PATCHes /translations with role:first
  // ————————————————————————————
  test('editing enInput PATCHes /translations with role:first for output_lang', async ({ page }) => {
    await openProofreadWithStub(page, STUB_FILE_DUAL, STUB_TRANSLATIONS_DUAL);

    // Intercept PATCH to /translations/0
    const patchPromise = page.waitForResponse(
      r => /\/api\/files\/.+\/translations\/0\b/.test(r.url()) && r.request().method() === 'PATCH',
      { timeout: 8000 }
    );

    // Stub the PATCH response
    await page.route(`**/api/files/${STUB_FID}/translations/0`, async (route) => {
      if (route.request().method() !== 'PATCH') { await route.continue(); return; }
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ translation: { status: 'pending' } }),
      });
    });

    const newText = '今日天氣好好睇';
    await page.locator('#enInput').fill(newText);
    await page.locator('#enInput').blur();

    const patch = await patchPromise;
    expect(patch.ok()).toBeTruthy();
    const body = patch.request().postDataJSON();
    expect(body.text).toBe(newText);
    expect(body.role).toBe('first');
  });

  // ————————————————————————————
  // Test 5: saveEditIfDirty (zhInput) for output_lang PATCHes /translations with role:second
  // ————————————————————————————
  test('editing zhInput PATCHes /translations with role:second for output_lang', async ({ page }) => {
    await openProofreadWithStub(page, STUB_FILE_DUAL, STUB_TRANSLATIONS_DUAL);

    // Intercept PATCH to /translations/0
    const patchPromise = page.waitForResponse(
      r => /\/api\/files\/.+\/translations\/0\b/.test(r.url()) && r.request().method() === 'PATCH',
      { timeout: 8000 }
    );

    // Stub the PATCH response
    await page.route(`**/api/files/${STUB_FID}/translations/0`, async (route) => {
      if (route.request().method() !== 'PATCH') { await route.continue(); return; }
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ translation: { status: 'pending' } }),
      });
    });

    const newText = 'The weather looks really nice today';
    await page.locator('#zhInput').fill(newText);
    await page.locator('#zhInput').blur();

    const patch = await patchPromise;
    expect(patch.ok()).toBeTruthy();
    const body = patch.request().postDataJSON();
    expect(body.text).toBe(newText);
    expect(body.role).toBe('second');
  });

});
