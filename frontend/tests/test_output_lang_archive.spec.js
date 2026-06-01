// test_output_lang_archive.spec.js — T10 archive MT/V6 UI hiding
//
// Verifies the conservative T10 guards added during output-lang archiving:
//
//   1. reTranslateFile() for an output_lang file shows an info toast
//      instead of calling /api/translate (the MT step is a no-op for output_lang).
//
//   2. The pipeline strip still renders without crashing when activeKind === "pipeline_v6"
//      and no file is selected (regression guard — strip must not throw).
//
//   3. The profile-strip preset-wrap is present when a profile file is selected
//      (regression guard — profile files must still see the full strip).
//
//   4. No JS errors on the dashboard after T10 guard additions.
//
// Auth: POST /login then goto. Viewport 1512×982.
//
// NOTE: The pipeline-strip V6/Profile preset-menu UI is intentionally retained
// (not hidden) per the T10 conservative approach — see
// docs/superpowers/archived/ARCHIVE_MT_V6_DESIGN.md §2.8 "Remaining UI to retire".

const { test, expect } = require('@playwright/test');

const BASE = process.env.BASE_URL || 'http://localhost:5001';
const USER = process.env.PROBE_USER || 'admin_p3';
const PASS = process.env.PROBE_PASS || 'TestPass1!';

test.use({ viewport: { width: 1512, height: 982 }, storageState: undefined });

async function login(page) {
  const r = await page.request.post(BASE + '/login', {
    data: { username: USER, password: PASS },
  });
  if (!r.ok()) throw new Error(`Login failed: ${r.status()}`);
}

test.describe.serial('output-lang archive: reTranslateFile guard + strip regression', () => {

  test.beforeEach(async ({ page }) => {
    await login(page);
  });

  // ───────────────────────────────────────────────────────────────────────────
  // T1: reTranslateFile() shows info toast for output_lang, does NOT call /api/translate
  // ───────────────────────────────────────────────────────────────────────────
  test('reTranslateFile shows info toast for output_lang, skips /api/translate', async ({ page }) => {
    let translateCalled = false;

    await page.goto(BASE + '/', { waitUntil: 'domcontentloaded' });
    await page.waitForFunction(() => typeof reTranslateFile === 'function', { timeout: 10000 });

    // Intercept /api/translate to detect if it gets called
    await page.route('**/api/translate', (route) => {
      translateCalled = true;
      route.continue();
    });

    // Inject an output_lang file into uploadedFiles
    await page.evaluate(() => {
      const FAKE_ID = '__test_retranslate_output_lang__';
      if (typeof uploadedFiles === 'undefined') return;
      uploadedFiles[FAKE_ID] = {
        id: FAKE_ID,
        original_name: 'retranslate-test.mp4',
        status: 'done',
        active_kind: 'output_lang',
        translation_status: 'done',
      };
      window.__testRetranslateId = FAKE_ID;
    });

    // Call reTranslateFile directly
    await page.evaluate(() => reTranslateFile(window.__testRetranslateId));

    // Toast should be visible with the info message
    const toast = page.locator('.toast, [class*="toast"]').first();
    await expect(toast).toBeVisible({ timeout: 3000 });

    // /api/translate must NOT have been called
    expect(translateCalled).toBe(false);
  });

  // ───────────────────────────────────────────────────────────────────────────
  // T2: renderPipelineStrip doesn't throw on dashboard without selected file
  // ───────────────────────────────────────────────────────────────────────────
  test('renderPipelineStrip renders without errors (no file selected)', async ({ page }) => {
    const errors = [];
    page.on('console', msg => { if (msg.type() === 'error') errors.push(msg.text()); });

    await page.goto(BASE + '/', { waitUntil: 'networkidle' });
    await page.waitForFunction(() => typeof renderPipelineStrip === 'function', { timeout: 10000 });

    await page.evaluate(() => {
      activeFileId = null;
      renderPipelineStrip();
    });

    const strip = page.locator('#pipelineStrip');
    await expect(strip).toBeVisible();

    // No JS errors
    expect(errors.filter(e => !e.includes('favicon') && !e.includes('Failed to load resource'))).toHaveLength(0);
  });

  // ───────────────────────────────────────────────────────────────────────────
  // T3: profile file → strip still renders preset-wrap (regression guard)
  // ───────────────────────────────────────────────────────────────────────────
  test('profile file: strip still renders preset-wrap (regression guard)', async ({ page }) => {
    const errors = [];
    page.on('console', msg => { if (msg.type() === 'error') errors.push(msg.text()); });

    await page.goto(BASE + '/', { waitUntil: 'networkidle' });
    await page.waitForFunction(() => typeof renderPipelineStrip === 'function', { timeout: 10000 });

    // Inject a synthetic profile file and select it
    await page.evaluate(() => {
      const FAKE_ID = '__test_profile_archive__';
      if (typeof uploadedFiles === 'undefined') return;
      uploadedFiles[FAKE_ID] = {
        id: FAKE_ID,
        original_name: 'test-profile.mp4',
        status: 'done',
        active_kind: 'profile',
        translation_status: 'done',
        languages: [],
      };
      activeFileId = FAKE_ID;
      activeKind = 'profile';
      renderPipelineStrip();
    });

    const strip = page.locator('#pipelineStrip');
    await expect(strip).toBeVisible();

    // Profile path should render the preset-wrap (pipeline selector)
    const presetWrap = strip.locator('.pipeline-preset-wrap');
    await expect(presetWrap).toHaveCount(1);

    // No console errors
    expect(errors.filter(e => !e.includes('favicon'))).toHaveLength(0);
  });

  // ───────────────────────────────────────────────────────────────────────────
  // T4: reTranslateFile() still works for NON-output_lang files (no guard fires)
  // ───────────────────────────────────────────────────────────────────────────
  test('reTranslateFile proceeds normally for profile files (no guard fires)', async ({ page }) => {
    let translateCalled = false;
    let translateBody = null;

    await page.goto(BASE + '/', { waitUntil: 'domcontentloaded' });
    await page.waitForFunction(() => typeof reTranslateFile === 'function', { timeout: 10000 });

    // Intercept /api/translate
    await page.route('**/api/translate', async (route) => {
      translateCalled = true;
      translateBody = route.request().postDataJSON();
      // Return a fake success so the function completes
      await route.fulfill({
        status: 202,
        contentType: 'application/json',
        body: JSON.stringify({ file_id: translateBody?.file_id, job_id: 'test-job', status: 'queued' }),
      });
    });

    // Inject a profile file
    await page.evaluate(() => {
      const FAKE_ID = '__test_profile_translate__';
      if (typeof uploadedFiles === 'undefined') return;
      uploadedFiles[FAKE_ID] = {
        id: FAKE_ID,
        original_name: 'profile-test.mp4',
        status: 'done',
        active_kind: 'profile',  // NOT output_lang → guard must not fire
        translation_status: 'done',
      };
      window.__testProfileId = FAKE_ID;
    });

    await page.evaluate(() => reTranslateFile(window.__testProfileId));

    // Wait briefly for the fetch to be intercepted
    await page.waitForTimeout(500);

    // /api/translate SHOULD have been called for a profile file
    expect(translateCalled).toBe(true);
    expect(translateBody?.file_id).toBe('__test_profile_translate__');
  });

});
