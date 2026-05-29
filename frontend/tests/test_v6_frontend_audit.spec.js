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

  // Tasks 2, 3, 4 will append further tests to this describe block.
});
