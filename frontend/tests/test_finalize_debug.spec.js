// finalize-debug — regression tests for two production bugs.
//
// Issue 1: hardcoded "index.html" navigation triggers 404 because backend
//   only exposes `@app.get("/")` — there is no /index.html route.
//   Affected: proofread.html backToDashboard() + 6 rail buttons + Glossary.html 6 hrefs.
//
// Issue 2: js/auth.js declares its own `async function fetchMe()` and loads
//   AFTER the inline fetchMe in index.html, overwriting `window.fetchMe`.
//   activateProfile/activatePipeline call the auth.js version, which doesn't
//   update activeKind/activeId — so Pipeline strip layout stays stuck on the
//   previous mode after switching.
//
// All tests self-handle login. Sets backend to dev-default Profile in beforeEach
// to ensure a known starting state.

const { test, expect } = require('@playwright/test');

const BASE = process.env.BASE_URL || 'http://localhost:5001';
const USER = process.env.PROBE_USER || 'admin_p3';
const PASS = process.env.PROBE_PASS || 'TestPass1!';

test.use({ storageState: undefined });

test.describe.serial('finalize-debug', () => {

  test.beforeEach(async ({ page }) => {
    const r = await page.request.post(BASE + '/login', { data: { username: USER, password: PASS } });
    if (!r.ok()) throw new Error(`Login failed: ${r.status()}`);
    // Reset to a known Profile so Issue 2 tests start from profile mode.
    await page.request.post(BASE + '/api/active', {
      data: { kind: 'profile', id: 'dev-default' },
    });
  });

  // -----------------------------------------------------------------
  // Issue 1: navigation to / not /index.html
  // -----------------------------------------------------------------

  test('proofread_home_button_goes_to_root_not_index_html', async ({ page }) => {
    // Need any file id to open proofread — picks the first one in registry
    const filesR = await page.request.get(BASE + '/api/files');
    const files = (await filesR.json()).files || [];
    test.skip(files.length === 0, 'No files in registry — upload one first');
    const fid = files[0].id;

    await page.goto(`${BASE}/proofread.html?file_id=${fid}`);
    await page.waitForLoadState('networkidle');

    // Click the 主頁 rail button (first .rail-btn with title="主頁")
    await page.locator('.rail-btn[title="主頁"]').first().click();
    await page.waitForLoadState('networkidle');

    // After navigation, URL must be / (or BASE + '/') and the page must be 200.
    const url = page.url();
    expect(url).toBe(BASE + '/');

    // Confirm dashboard loaded (look for any dashboard-only landmark)
    await page.waitForFunction(() => typeof activeKind !== 'undefined', { timeout: 10000 });
  });

  test('proofread_back_arrow_goes_to_root_not_index_html', async ({ page }) => {
    const filesR = await page.request.get(BASE + '/api/files');
    const files = (await filesR.json()).files || [];
    test.skip(files.length === 0, 'No files in registry');
    const fid = files[0].id;

    await page.goto(`${BASE}/proofread.html?file_id=${fid}`);
    await page.waitForLoadState('networkidle');

    await page.locator('.rv-back').first().click();
    await page.waitForLoadState('networkidle');

    expect(page.url()).toBe(BASE + '/');
  });

  test('glossary_home_button_goes_to_root_not_index_html', async ({ page }) => {
    await page.goto(BASE + '/Glossary.html');
    await page.waitForLoadState('networkidle');

    await page.locator('.rail-btn[title="主頁"]').first().click();
    await page.waitForLoadState('networkidle');

    expect(page.url()).toBe(BASE + '/');
  });

  test('glossary_back_link_goes_to_root_not_index_html', async ({ page }) => {
    await page.goto(BASE + '/Glossary.html');
    await page.waitForLoadState('networkidle');

    await page.locator('.gl-back').first().click();
    await page.waitForLoadState('networkidle');

    expect(page.url()).toBe(BASE + '/');
  });

  // -----------------------------------------------------------------
  // Issue 2: activateProfile/activatePipeline updates activeKind
  // -----------------------------------------------------------------

  test('activateProfile_updates_activeKind_after_v6_was_active', async ({ page }) => {
    await page.goto(BASE + '/');
    await page.waitForFunction(() => typeof activeKind !== 'undefined');
    await page.waitForTimeout(500);

    // Step 1: switch to V6 first
    await page.evaluate(async () => {
      await activatePipeline('4696bbaa-b988-49bd-859c-e742cb365634');
    });
    const afterV6 = await page.evaluate(() => ({ activeKind, activeId }));
    expect(afterV6.activeKind).toBe('pipeline_v6');

    // Step 2: switch back to Profile — THIS is the regression we're guarding
    await page.evaluate(async () => {
      await activateProfile('dev-default');
    });
    const afterProfile = await page.evaluate(() => ({ activeKind, activeId }));
    expect(afterProfile.activeKind).toBe('profile');
    expect(afterProfile.activeId).toBe('dev-default');
  });

  test('pipeline_strip_renders_profile_layout_after_switching_back', async ({ page }) => {
    await page.goto(BASE + '/');
    await page.waitForFunction(() => typeof activeKind !== 'undefined');

    // Go V6
    await page.evaluate(async () => {
      await activatePipeline('4696bbaa-b988-49bd-859c-e742cb365634');
    });
    await page.waitForTimeout(300);

    // Go back to Profile
    await page.evaluate(async () => {
      await activateProfile('dev-default');
    });
    await page.waitForTimeout(300);

    // Profile-mode pipeline strip should show ASR + MT + 術語表 step columns,
    // NOT VAD + Qwen3 Context + Refiner.
    const layout = await page.evaluate(() => ({
      hasVad: !!document.querySelector('[data-step="vad"]'),
      hasQwen3: !!document.querySelector('[data-step="qwen3-ctx"]'),
      hasRefiner: !!document.querySelector('[data-step="refiner"]'),
      hasAsr: !!document.querySelector('[data-step="asr"]'),
      hasMt: !!document.querySelector('[data-step="mt"]'),
      hasGloss: !!document.querySelector('[data-step="gloss"]'),
      presetKText: document.querySelector('.pp-k')?.textContent || '',
    }));

    expect(layout.hasVad).toBe(false);
    expect(layout.hasQwen3).toBe(false);
    expect(layout.hasRefiner).toBe(false);
    expect(layout.hasAsr).toBe(true);
    expect(layout.hasMt).toBe(true);
    expect(layout.presetKText).not.toContain('V6');
  });
});
