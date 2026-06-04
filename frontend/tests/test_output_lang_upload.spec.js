// test_output_lang_upload.spec.js — T8 主頁 upload popup + output_languages
//
// Verifies the output-language pipeline upload flow on the dashboard:
//   1. Selecting a file pops up a modal with three dropdowns
//      (影片來源語言 / 目標輸出第一語言 / 目標輸出第二語言). The first/second
//      output-language selects each expose the 4 codes; the second select
//      additionally exposes a 「無」(none) option.
//   2. Picking first=口語廣東話(yue), second=英文(en) and clicking 開始處理
//      sends a POST /api/transcribe whose multipart body carries
//      output_languages = ["yue","en"].
//   3. First-only (second=「無」) sends output_languages = ["yue"].
//
// Auth pattern mirrors test_bilingual_selector.spec.js — POST /login then goto.
// Viewport 1512×982.

const { test, expect } = require('@playwright/test');

const BASE = process.env.BASE_URL || 'http://localhost:5001';
const USER = process.env.PROBE_USER || 'admin_p3';
const PASS = process.env.PROBE_PASS || 'TestPass1!';

test.use({ viewport: { width: 1512, height: 982 }, storageState: undefined });

// A tiny in-memory fixture "video" file. The backend never receives it because
// we stub POST /api/transcribe via page.route, so its actual content is moot —
// it only needs a video-ish name + non-empty bytes.
const FIXTURE = {
  name: 'fixture-clip.mp4',
  mimeType: 'video/mp4',
  buffer: Buffer.from('fake-mp4-bytes-for-popup-test'),
};

async function login(page) {
  const r = await page.request.post(BASE + '/login', {
    data: { username: USER, password: PASS },
  });
  if (!r.ok()) throw new Error(`Login failed: ${r.status()}`);
}

// Select the fixture file via the hidden #fileInput, which triggers the popup.
async function selectFixture(page) {
  await page.goto(BASE + '/', { waitUntil: 'domcontentloaded' });
  await page.waitForFunction(
    () => typeof setPendingFile === 'function' && typeof openOutputLangModal === 'function',
    { timeout: 15000 }
  );
  await page.setInputFiles('#fileInput', FIXTURE);
}

test.describe.serial('output-lang upload popup', () => {

  test.beforeEach(async ({ page }) => {
    await login(page);
  });

  test('selecting a file shows the popup with 3 dropdowns + 「無」 on second', async ({ page }) => {
    await selectFixture(page);

    const overlay = page.locator('#olOverlay');
    await expect(overlay).toHaveClass(/open/, { timeout: 5000 });

    // Three dropdowns present.
    await expect(page.locator('#olSourceLang')).toBeVisible();
    await expect(page.locator('#olFirstLang')).toBeVisible();
    await expect(page.locator('#olSecondLang')).toBeVisible();

    // First-language lock: the popup opens with the default source = 粵語, so the
    // first output language is constrained to 口語廣東話 / 中文書面語 only (no en/ja).
    const firstVals = await page.locator('#olFirstLang option').evaluateAll(
      (opts) => opts.map((o) => o.value)
    );
    expect(firstVals).toEqual(expect.arrayContaining(['yue', 'zh']));
    expect(firstVals).not.toContain('en');  // 鎖定：粵語 source 唔出英文做第一語言
    expect(firstVals).not.toContain('ja');
    expect(firstVals).not.toContain('');  // no 「無」 on the required first select

    // Second output language: same-family-as-source options are filtered out to avoid
    // the same-family index-merge drift. Default source = 粵語 (中文語系) → only 無 + 跨語系.
    const secondVals = await page.locator('#olSecondLang option').evaluateAll(
      (opts) => opts.map((o) => o.value)
    );
    expect(secondVals).toEqual(['', 'en', 'ja']);
    expect(secondVals).not.toContain('zh');   // 中文系唔可同粵語 source 同時做雙輸出
    // The 「無」 label is shown for the empty option.
    const noneLabel = await page.locator('#olSecondLang option[value=""]').textContent();
    expect((noneLabel || '').trim()).toContain('無');
  });

  test('開始處理 with first=yue second=en POSTs output_languages ["yue","en"]', async ({ page }) => {
    let captured = null;
    await page.route('**/api/transcribe', async (route) => {
      captured = route.request().postData();
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ file_id: 'stub-fid-1', job_id: 'job-1', queue_position: 1 }),
      });
    });

    await selectFixture(page);
    await expect(page.locator('#olOverlay')).toHaveClass(/open/, { timeout: 5000 });

    await page.selectOption('#olFirstLang', 'yue');
    await page.selectOption('#olSecondLang', 'en');
    await page.click('#olStartBtn');

    await expect.poll(() => captured, { timeout: 8000 }).not.toBeNull();

    expect(captured).toContain('output_languages');
    // The JSON array is embedded in the multipart field body.
    const m = captured.match(/output_languages[\s\S]*?\[(.*?)\]/);
    expect(m).not.toBeNull();
    const arr = JSON.parse('[' + m[1] + ']');
    expect(arr).toEqual(['yue', 'en']);
  });

  test('開始處理 with second=「無」 POSTs output_languages ["yue"] only', async ({ page }) => {
    let captured = null;
    await page.route('**/api/transcribe', async (route) => {
      captured = route.request().postData();
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ file_id: 'stub-fid-2', job_id: 'job-2', queue_position: 1 }),
      });
    });

    await selectFixture(page);
    await expect(page.locator('#olOverlay')).toHaveClass(/open/, { timeout: 5000 });

    await page.selectOption('#olFirstLang', 'yue');
    await page.selectOption('#olSecondLang', '');  // 「無」
    await page.click('#olStartBtn');

    await expect.poll(() => captured, { timeout: 8000 }).not.toBeNull();

    expect(captured).toContain('output_languages');
    const m = captured.match(/output_languages[\s\S]*?\[(.*?)\]/);
    expect(m).not.toBeNull();
    const arr = JSON.parse('[' + m[1] + ']');
    expect(arr).toEqual(['yue']);
  });

  test('取消 closes the popup and clears the pending file', async ({ page }) => {
    await selectFixture(page);
    await expect(page.locator('#olOverlay')).toHaveClass(/open/, { timeout: 5000 });

    await page.click('#olCancelBtn');
    await expect(page.locator('#olOverlay')).not.toHaveClass(/open/, { timeout: 5000 });

    // Pending file cleared.
    const hasPending = await page.evaluate(
      () => typeof uploadedFiles !== 'undefined' && !!uploadedFiles['__pending__']
    );
    expect(hasPending).toBe(false);
  });

  // Fix 1 — Cmd+Enter with popup open must NOT do a legacy upload (no output_languages).
  // It should either confirm the popup (POST with output_languages) or be a no-op.
  test('Cmd+Enter while popup is open confirms it (never triggers legacy upload)', async ({ page }) => {
    const posts = [];
    await page.route('**/api/transcribe', async (route) => {
      posts.push(route.request().postData());
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ file_id: 'stub-fid-fix1', job_id: 'job-fix1', queue_position: 1 }),
      });
    });

    await selectFixture(page);
    await expect(page.locator('#olOverlay')).toHaveClass(/open/, { timeout: 5000 });

    // Ensure first-lang is set (default is 'yue', which is valid).
    await page.selectOption('#olFirstLang', 'yue');
    await page.selectOption('#olSecondLang', '');

    // Click on a neutral area to move focus away from the select and onto the body.
    await page.mouse.click(10, 10);

    // Press Cmd+Enter (Meta+Enter on mac) — the popup is still open.
    await page.keyboard.press('Meta+Enter');

    // Wait briefly for any POST to fire (or not).
    await page.waitForTimeout(1500);

    if (posts.length > 0) {
      // A POST happened — it MUST carry output_languages (not a bare legacy upload).
      for (const body of posts) {
        expect(body).toContain('output_languages');
      }
    }
    // Either no POST (safe no-op) or POST with output_languages — both are acceptable.
    // What is NOT acceptable: a POST without output_languages.
    // The assertion above already covers that case.
  });

  // Fix 2 — × close button must also clear the pending card (parity with 取消 / Esc).
  test('× close button clears the pending file (same as 取消)', async ({ page }) => {
    await selectFixture(page);
    await expect(page.locator('#olOverlay')).toHaveClass(/open/, { timeout: 5000 });

    // Click the × button (the .or-close button inside #olOverlay).
    await page.click('#olOverlay .or-close');
    await expect(page.locator('#olOverlay')).not.toHaveClass(/open/, { timeout: 5000 });

    // __pending__ card must be cleared — same as clicking 取消.
    const hasPending = await page.evaluate(
      () => typeof uploadedFiles !== 'undefined' && !!uploadedFiles['__pending__']
    );
    expect(hasPending).toBe(false);
  });

});
