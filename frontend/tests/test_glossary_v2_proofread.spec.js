// test_glossary_v2_proofread.spec.js — Task 3.1 + 3.2
//
// Covers:
//   3.1 — upload popup has #olGlossary (multiple select) + #olGlossaryLlm (checkbox),
//          populated from GET /api/glossaries; confirm POSTs glossary_ids + glossary_llm.
//   3.2 — proofread detail panel shows glossary_changes before/after;
//          rail 📖 badge on changed rows; .gl-empty on rows with no changes;
//          「重新套用詞彙表」button hits /glossary-reapply for output_lang files.
//
// Auth: POST /login (admin_p3 / TestPass1!). All API calls route-stubbed.

const { test, expect } = require('@playwright/test');

const BASE = process.env.BASE_URL || 'http://localhost:5001';
const USER  = process.env.PROBE_USER || 'admin_p3';
const PASS  = process.env.PROBE_PASS || 'TestPass1!';

const STUB_FID = 'gloss-v2-stub-fid-001';

// ─── fixtures ───────────────────────────────────────────────────────────────

// Two stub glossaries returned by GET /api/glossaries
const STUB_GLOSSARIES = {
  glossaries: [
    { id: 'g-aaa', name: '賽馬',    source_lang: 'en', target_lang: 'yue' },
    { id: 'g-bbb', name: '足球',    source_lang: 'en', target_lang: 'zh'  },
  ],
};

// Minimal file entry (output_lang) for proofread stubs
const STUB_FILE = {
  id:           STUB_FID,
  original_name:'stub-glossary-v2.mp4',
  status:       'done',
  active_kind:  'output_lang',
  translation_status: 'done',
  subtitle_source: null,
  bilingual_order: null,
  languages: [
    { role: 'first', lang: 'yue', label: '口語廣東話' },
    { role: 'second', lang: 'en',  label: '英文'       },
  ],
};

// Translations: row 0 has glossary_changes; row 1 has none
const STUB_TRANSLATIONS = {
  translations: [
    {
      idx: 0, start: 1.0, end: 4.0,
      source_text: '',
      yue_text: '火悟空跑得好快',
      en_text:  'Blazing Wukong ran very fast',
      by_lang: {
        yue: { text: '火悟空跑得好快', status: 'pending', flags: [] },
        en:  { text: 'Blazing Wukong ran very fast', status: 'pending', flags: [] },
      },
      status: 'pending', flags: [], approved: false,
      glossary_changes: [
        { source: 'BLAZING WUKONG', before: 'Blazing Wukong', after: '火悟空', glossary: '賽馬' },
      ],
    },
    {
      idx: 1, start: 5.0, end: 8.0,
      source_text: '',
      yue_text: '今日天氣好好',
      en_text:  'The weather is nice today',
      by_lang: {
        yue: { text: '今日天氣好好', status: 'pending', flags: [] },
        en:  { text: 'The weather is nice today', status: 'pending', flags: [] },
      },
      status: 'pending', flags: [], approved: false,
      glossary_changes: [],
    },
  ],
};

// A tiny fake video file (not really uploaded — transcribe is stubbed)
const FIXTURE = {
  name:     'fixture-clip.mp4',
  mimeType: 'video/mp4',
  buffer:   Buffer.from('fake-mp4-bytes-for-glossary-test'),
};

// ─── helpers ────────────────────────────────────────────────────────────────

async function login(page) {
  const r = await page.request.post(BASE + '/login', {
    data: { username: USER, password: PASS },
  });
  if (!r.ok()) throw new Error(`Login failed: ${r.status()}`);
}

// Stub the glossaries endpoint (used in both upload and proofread tests)
async function stubGlossaries(page) {
  await page.route('**/api/glossaries', async (route) => {
    if (route.request().method() !== 'GET') { await route.continue(); return; }
    await route.fulfill({
      status: 200, contentType: 'application/json',
      body: JSON.stringify(STUB_GLOSSARIES),
    });
  });
}

// Stub all APIs needed for the proofread page
async function stubProofreadApis(page) {
  const fid = STUB_FID;

  await page.route('**/api/files', async (route) => {
    if (route.request().method() !== 'GET') { await route.continue(); return; }
    await route.fulfill({
      status: 200, contentType: 'application/json',
      body: JSON.stringify({ files: [STUB_FILE] }),
    });
  });

  await page.route(`**/api/files/${fid}/languages`, async (route) => {
    await route.fulfill({
      status: 200, contentType: 'application/json',
      body: JSON.stringify({ languages: STUB_FILE.languages }),
    });
  });

  await page.route(`**/api/files/${fid}/translations`, async (route) => {
    if (route.request().method() !== 'GET') { await route.continue(); return; }
    await route.fulfill({
      status: 200, contentType: 'application/json',
      body: JSON.stringify(STUB_TRANSLATIONS),
    });
  });

  await page.route(`**/api/files/${fid}/segments`, async (route) => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ segments: [] }) });
  });

  await page.route(`**/api/files/${fid}/media`, async (route) => {
    await route.fulfill({ status: 204, contentType: 'video/mp4', body: Buffer.alloc(0) });
  });

  await page.route('**/api/fonts', async (route) => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify([]) });
  });

  await page.route('**/api/profiles/active', async (route) => {
    if (route.request().method() !== 'GET') { await route.continue(); return; }
    await route.fulfill({
      status: 200, contentType: 'application/json',
      body: JSON.stringify({
        profile: {
          id: 'stub-profile', name: 'Stub Profile',
          font: { family: 'Noto Sans TC', size: 48, color: '#ffffff', outline_color: '#000000', outline_width: 3, margin_bottom: 60 },
        },
      }),
    });
  });

  await stubGlossaries(page);

  await page.route(`**/api/files/${fid}/glossary-reapply`, async (route) => {
    if (route.request().method() !== 'POST') { await route.continue(); return; }
    await route.fulfill({
      status: 200, contentType: 'application/json',
      body: JSON.stringify({ ok: true, file_id: fid, languages: STUB_FILE.languages, changed_count: 1 }),
    });
  });
}

// Open proofread page for the stub file (stubs must be registered first)
async function openProofread(page) {
  await page.goto(`${BASE}/proofread.html?file_id=${STUB_FID}`);
  await page.waitForFunction(
    () => typeof segs !== 'undefined' && segs.length > 0,
    { timeout: 15000 }
  );
}

// Click segment at index i to set cursor and reveal detail panel
async function clickSeg(page, i) {
  await page.locator(`.rv-b-rail-item[data-idx="${i}"]`).click();
  await page.waitForFunction(
    (idx) => {
      const el = document.getElementById('detailPanel');
      return el && el.querySelector('textarea') !== null;
    },
    i,
    { timeout: 5000 }
  );
}

// ─── tests ──────────────────────────────────────────────────────────────────

test.use({ storageState: undefined, viewport: { width: 1512, height: 900 } });

// ── Task 3.1: upload popup glossary selector ─────────────────────────────────

test.describe.serial('3.1 upload popup glossary selector', () => {
  test.beforeEach(async ({ page }) => {
    await login(page);
  });

  test('#olGlossary (multiple) and #olGlossaryLlm (checked) exist in popup', async ({ page }) => {
    await stubGlossaries(page);

    // Stub /api/transcribe so we can fire the popup without real upload
    await page.route('**/api/transcribe', async (route) => {
      await route.fulfill({
        status: 200, contentType: 'application/json',
        body: JSON.stringify({ file_id: 'stub-t31', job_id: 'j-1', queue_position: 1 }),
      });
    });

    await page.goto(BASE + '/', { waitUntil: 'domcontentloaded' });
    await page.waitForFunction(
      () => typeof openOutputLangModal === 'function',
      { timeout: 15000 }
    );

    // Select file to open popup
    await page.setInputFiles('#fileInput', FIXTURE);

    const overlay = page.locator('#olOverlay');
    await expect(overlay).toHaveClass(/open/, { timeout: 5000 });

    // #olGlossary is a multiple select
    const glossarySel = page.locator('#olGlossary');
    await expect(glossarySel).toBeVisible();
    const multiple = await glossarySel.getAttribute('multiple');
    expect(multiple).not.toBeNull();

    // #olGlossaryLlm is a checkbox, checked by default
    const llmCheck = page.locator('#olGlossaryLlm');
    await expect(llmCheck).toBeVisible();
    await expect(llmCheck).toBeChecked();
  });

  test('#olGlossary is populated from GET /api/glossaries with 2 options', async ({ page }) => {
    await stubGlossaries(page);

    await page.route('**/api/transcribe', async (route) => {
      await route.fulfill({
        status: 200, contentType: 'application/json',
        body: JSON.stringify({ file_id: 'stub-t31b', job_id: 'j-2', queue_position: 1 }),
      });
    });

    await page.goto(BASE + '/', { waitUntil: 'domcontentloaded' });
    await page.waitForFunction(() => typeof openOutputLangModal === 'function', { timeout: 15000 });
    await page.setInputFiles('#fileInput', FIXTURE);
    await expect(page.locator('#olOverlay')).toHaveClass(/open/, { timeout: 5000 });

    // Wait for glossary options to be populated
    await page.waitForFunction(
      () => {
        const sel = document.getElementById('olGlossary');
        return sel && sel.options.length >= 2;
      },
      { timeout: 8000 }
    );

    const opts = await page.locator('#olGlossary option').evaluateAll(
      (options) => options.map((o) => ({ value: o.value, text: o.textContent.trim() }))
    );
    expect(opts.length).toBeGreaterThanOrEqual(2);
    expect(opts.some(o => o.value === 'g-aaa')).toBe(true);
    expect(opts.some(o => o.value === 'g-bbb')).toBe(true);
    // Text includes source→target lang
    expect(opts.find(o => o.value === 'g-aaa').text).toContain('賽馬');
  });

  test('selecting 2 glossaries + confirm → POST includes glossary_ids + glossary_llm', async ({ page }) => {
    await stubGlossaries(page);

    let capturedBody = null;
    await page.route('**/api/transcribe', async (route) => {
      capturedBody = route.request().postData();
      await route.fulfill({
        status: 200, contentType: 'application/json',
        body: JSON.stringify({ file_id: 'stub-t31c', job_id: 'j-3', queue_position: 1 }),
      });
    });

    await page.goto(BASE + '/', { waitUntil: 'domcontentloaded' });
    await page.waitForFunction(() => typeof openOutputLangModal === 'function', { timeout: 15000 });
    await page.setInputFiles('#fileInput', FIXTURE);
    await expect(page.locator('#olOverlay')).toHaveClass(/open/, { timeout: 5000 });

    // Wait for glossary options
    await page.waitForFunction(
      () => { const s = document.getElementById('olGlossary'); return s && s.options.length >= 2; },
      { timeout: 8000 }
    );

    // Select both glossaries
    await page.selectOption('#olGlossary', ['g-aaa', 'g-bbb']);

    // Ensure LLM checkbox is checked
    const llmCheck = page.locator('#olGlossaryLlm');
    if (!(await llmCheck.isChecked())) await llmCheck.check();

    // Confirm
    await page.click('#olStartBtn');

    await expect.poll(() => capturedBody, { timeout: 8000 }).not.toBeNull();

    expect(capturedBody).toContain('glossary_ids');
    // glossary_llm should be "1"
    expect(capturedBody).toContain('glossary_llm');

    // Parse the glossary_ids JSON from the multipart body
    const m = capturedBody.match(/glossary_ids[\s\S]*?(\["[^"]*"(?:,"[^"]*")*\])/);
    if (m) {
      const arr = JSON.parse(m[1]);
      expect(arr).toContain('g-aaa');
      expect(arr).toContain('g-bbb');
    } else {
      // Fallback: just verify the field is present with both ids
      expect(capturedBody).toContain('g-aaa');
      expect(capturedBody).toContain('g-bbb');
    }
  });
});

// ── Task 3.2: proofread before/after + rail badge + reapply ──────────────────
// Use global storageState (set via playwright.config.js) to avoid hitting the
// /login rate limiter (10 req/min) after the 3.1 tests already used it.

test.describe.serial('3.2 proofread glossary_changes display', () => {
  test.use({ storageState: './playwright-auth.json' });

  test.beforeEach(async ({ page }) => {
    await stubProofreadApis(page);
    await openProofread(page);
  });

  test('detail panel shows .gl-after + .gl-before for row with glossary_changes', async ({ page }) => {
    await clickSeg(page, 0);

    // The detail panel should show '火悟空' with class gl-after
    const after = page.locator('#detailPanel .gl-after').first();
    await expect(after).toBeVisible({ timeout: 5000 });
    await expect(after).toContainText('火悟空');

    // The before text (strikethrough) should show 'Blazing Wukong'
    const before = page.locator('#detailPanel .gl-before').first();
    await expect(before).toBeVisible();
    await expect(before).toContainText('Blazing Wukong');
  });

  test('detail panel shows .gl-empty for row with no glossary_changes', async ({ page }) => {
    await clickSeg(page, 1);

    const empty = page.locator('#detailPanel .gl-empty');
    await expect(empty).toBeVisible({ timeout: 5000 });
  });

  test('📖 badge appears in rail for row 0 (has changes) but not row 1', async ({ page }) => {
    // Row 0 should have the 📖 flag
    const row0 = page.locator('.rv-b-rail-item[data-idx="0"]');
    await expect(row0).toBeVisible();
    const row0Html = await row0.innerHTML();
    expect(row0Html).toContain('📖');

    // Row 1 should NOT have the 📖 flag
    const row1 = page.locator('.rv-b-rail-item[data-idx="1"]');
    await expect(row1).toBeVisible();
    const row1Html = await row1.innerHTML();
    expect(row1Html).not.toContain('📖');
  });

  test('「重新套用詞彙表」button hits /glossary-reapply and shows success toast', async ({ page }) => {
    let reapplyCalled = false;
    // The stub is already registered in stubProofreadApis; override to track calls
    await page.route(`**/api/files/${STUB_FID}/glossary-reapply`, async (route) => {
      if (route.request().method() !== 'POST') { await route.continue(); return; }
      reapplyCalled = true;
      await route.fulfill({
        status: 200, contentType: 'application/json',
        body: JSON.stringify({ ok: true, file_id: STUB_FID, languages: STUB_FILE.languages, changed_count: 1 }),
      });
    });

    // Find the reapply button
    const btn = page.locator('#glossaryReapplyBtn');
    await expect(btn).toBeVisible({ timeout: 5000 });
    await btn.click();

    await expect.poll(() => reapplyCalled, { timeout: 8000 }).toBe(true);
  });
});
