// V6 frontend audit — Playwright spec covering 4 V6-mode UX flows.
// Reproducer file: registry entry d159d9dbd309 (賽馬娛樂新聞).
// Tests self-handle login (admin_p3 / AdminPass1!) and skip cleanly when
// no V6 file is present in the dev registry.
const { test, expect } = require('@playwright/test');

const BASE = process.env.BASE_URL || 'http://localhost:5001';
const USER = process.env.PROBE_USER || 'admin_p3';
const PASS = process.env.PROBE_PASS || 'AdminPass1!';

const PRIMARY_V6_FID = process.env.V6_TEST_FID || 'd159d9dbd309';

test.use({ storageState: undefined });

test.describe.serial('V6 frontend audit', () => {
  let v6FileId = null;

  test.beforeAll(async ({ browser }) => {
    const ctx = await browser.newContext();
    const page = await ctx.newPage();
    const r = await page.request.post(BASE + '/login', { data: { username: USER, password: PASS } });
    if (!r.ok()) throw new Error(`Login failed: ${r.status()}`);
    const filesRes = await page.request.get(BASE + '/api/files');
    const files = (await filesRes.json()).files || [];
    const v6Done = files.find(f => f.id === PRIMARY_V6_FID && f.active_kind === 'pipeline_v6' && f.status === 'done')
                || files.find(f => f.active_kind === 'pipeline_v6' && f.status === 'done');
    v6FileId = v6Done ? v6Done.id : null;
    await ctx.close();
  });

  test.beforeEach(async ({ page }) => {
    await page.request.post(BASE + '/login', { data: { username: USER, password: PASS } });
    test.skip(!v6FileId, 'No V6 file in registry — upload a V6 file via Dashboard with V6 pipeline active first');
  });

  test('proofread_v6_file_renders_segments_and_overlay', async ({ page }) => {
    await page.goto(`${BASE}/proofread.html?file_id=${v6FileId}`);
    await page.waitForLoadState('networkidle');

    const segCount = await page.evaluate(() => (typeof segs !== 'undefined' ? segs.length : 0));
    expect(segCount).toBeGreaterThan(0);

    const firstZh = await page.evaluate(() => (typeof segs !== 'undefined' && segs[0]) ? segs[0].zh : '');
    expect(firstZh.length).toBeGreaterThan(0);
    expect(firstZh).not.toContain('source_text');

    const firstStart = await page.evaluate(() => (typeof segs !== 'undefined' && segs[0]) ? segs[0].in : 0);
    await page.evaluate((t) => {
      const v = document.querySelector('video');
      if (v) { v.currentTime = (t / 1000) + 0.5; v.pause(); }
    }, firstStart);
    await page.waitForTimeout(800);

    const overlayText = await page.evaluate(() => {
      const t = document.querySelector('#subtitleSvg text') || document.querySelector('svg text');
      return t ? (t.textContent || '').trim() : '';
    });
    expect(overlayText.length).toBeGreaterThan(0);
  });

  test('proofread_v6_en_textarea_is_readonly', async ({ page }) => {
    await page.goto(`${BASE}/proofread.html?file_id=${v6FileId}`);
    await page.waitForLoadState('networkidle');

    await page.waitForFunction(() => typeof segs !== 'undefined' && segs.length > 0);

    await page.evaluate(() => {
      if (typeof selectSegment === 'function') selectSegment(0);
      else if (typeof setCursor === 'function') setCursor(0);
    });
    await page.waitForSelector('#enInput', { state: 'attached' });

    const isReadOnly = await page.locator('#enInput').evaluate(el => el.readOnly === true);
    expect(isReadOnly).toBe(true);

    const tooltip = await page.locator('#enInput').getAttribute('title');
    expect(tooltip || '').toContain('V6');

    const before = await page.locator('#enInput').inputValue();
    await page.locator('#enInput').focus();
    await page.keyboard.type('XYZ_test_mutate_attempt');
    const after = await page.locator('#enInput').inputValue();
    expect(after).toBe(before);
  });

  test('dashboard_v6_file_inspector_and_overlay_populated', async ({ page }) => {
    await page.goto(BASE + '/');
    await page.waitForLoadState('networkidle');
    await page.waitForFunction(() => typeof activeKind !== 'undefined');

    // Click the V6 file in the file list to load it into the inspector
    await page.evaluate((fid) => {
      if (typeof selectFile === 'function') {
        selectFile(fid);
      } else {
        const card = document.querySelector(`[data-file-id="${fid}"]`);
        if (card) card.click();
      }
    }, v6FileId);

    // loadFileSegments should populate `segments` global
    await page.waitForFunction(
      () => typeof segments !== 'undefined' && segments && segments.length > 0,
      null,
      { timeout: 10000 }
    );

    const firstZh = await page.evaluate(() => segments[0].zh_text || '');
    expect(firstZh.length).toBeGreaterThan(0);

    // Seek video into first segment range; overlay should show text
    const firstStart = await page.evaluate(() => segments[0].start);
    await page.evaluate((t) => {
      const v = document.querySelector('video');
      if (v) { v.currentTime = t + 0.5; v.pause(); }
    }, firstStart);
    await page.waitForTimeout(800);

    const overlayText = await page.evaluate(() => {
      const t = document.querySelector('#subtitleSvg text') || document.querySelector('svg text');
      return t ? (t.textContent || '').trim() : '';
    });
    expect(overlayText.length).toBeGreaterThan(0);
  });

  // Tasks 3, 4 will append further tests to this describe block.

  test('proofread_v6_zh_edit_patches_translations', async ({ page }) => {
    await page.goto(`${BASE}/proofread.html?file_id=${v6FileId}`);
    await page.waitForLoadState('networkidle');
    await page.waitForFunction(() => typeof segs !== 'undefined' && segs.length > 0);

    await page.evaluate(() => {
      if (typeof selectSegment === 'function') selectSegment(0);
      else if (typeof setCursor === 'function') setCursor(0);
    });
    await page.waitForSelector('#zhInput', { state: 'attached' });

    const originalZh = await page.locator('#zhInput').inputValue();
    const probeText = originalZh + ' V6-PATCH-PROBE-' + Date.now();

    const patchPromise = page.waitForResponse(r =>
      /\/api\/files\/.+\/translations\/0\b/.test(r.url()) && r.request().method() === 'PATCH'
    );

    await page.locator('#zhInput').fill(probeText);
    await page.locator('#zhInput').blur();

    const patch = await patchPromise;
    expect(patch.ok()).toBeTruthy();
    const body = patch.request().postDataJSON();
    expect(body.zh_text).toBe(probeText);

    // Restore original to avoid contaminating the fixture
    await page.evaluate(async ([fid, original]) => {
      await fetch(`/api/files/${fid}/translations/0`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ zh_text: original }),
      });
    }, [v6FileId, originalZh]);
  });
});
