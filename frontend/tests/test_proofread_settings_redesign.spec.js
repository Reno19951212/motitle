// Proofread page redesign (2026-06-04) — follows the dashboard inspector「字幕設定」
// display + two-block segment rows.
//
//   1. 字幕設定 panel renders the dashboard-style controls into #ssBody:
//      a preview box, a 字型 <select>, three range sliders (size / outline / margin),
//      and colour swatches — replacing the old text/number/color inputs.
//   2. The segment-list rail shows TWO stacked text blocks per row
//      (.rv-b-rail-text-1 = first/source, .rv-b-rail-text-2 = second/translated);
//      single-output_lang files render line 1 only (no empty second line).
//
// Auth: storageState from global-setup (cached admin session).
const { test, expect } = require('@playwright/test');

const BASE = process.env.BASE_URL || 'http://localhost:5001';

async function firstFileId(page) {
  const r = await page.request.get(BASE + '/api/files');
  const files = (await r.json()).files || [];
  return files;
}

async function openProofread(page, fid) {
  await page.setViewportSize({ width: 1512, height: 950 });
  await page.goto(`${BASE}/proofread.html?file_id=${fid}`, { waitUntil: 'networkidle' });
  await page.waitForTimeout(1500);
}

test.describe('proofread redesign — dashboard-style 字幕設定 + two-block rows', () => {

  test('字幕設定 renders dashboard-style controls (preview + select + sliders + swatches)', async ({ page }) => {
    const files = await firstFileId(page);
    test.skip(files.length === 0, 'No files in registry — upload one first');
    await openProofread(page, files[0].id);

    // New JS-rendered body container exists.
    await expect(page.locator('#ssBody')).toHaveCount(1);

    // Preview box + grouped sections.
    await expect(page.locator('#ssBody #ssPreviewText')).toHaveCount(1);
    expect(await page.locator('#ssBody .ss-group').count()).toBeGreaterThanOrEqual(3);

    // Font-family dropdown + three range sliders (size / outline / margin).
    await expect(page.locator('#ssBody select')).toHaveCount(1);
    expect(await page.locator('#ssBody input[type=range]').count()).toBe(3);

    // Size slider keeps id=ssSize + min=12 (backend cap) and is a range now.
    await expect(page.locator('#ssBody input#ssSize[type=range]')).toHaveCount(1);
    expect(await page.locator('#ssSize').getAttribute('min')).toBe('12');

    // Colour swatches (text + outline rows) present; old text/number/color inputs gone.
    expect(await page.locator('#ssBody .swatch-pick .sw').count()).toBeGreaterThanOrEqual(8);
    await expect(page.locator('#ssBody input[type=text]')).toHaveCount(0);     // no #ssFamily text box
    await expect(page.locator('#ssBody input[type=number]')).toHaveCount(0);   // no number spinners
  });

  test('segment rows render the first-language block (.rv-b-rail-text-1)', async ({ page }) => {
    const files = await firstFileId(page);
    test.skip(files.length === 0, 'No files in registry — upload one first');
    await openProofread(page, files[0].id);

    const rows = page.locator('#segList .rv-b-rail-item');
    const n = await rows.count();
    test.skip(n === 0, 'File has no segments yet');

    // Every row carries the line-1 (primary/source) block.
    expect(await page.locator('#segList .rv-b-rail-text-1').count()).toBe(n);

    // The first row's line-1 has real, non-empty text.
    const t1 = (await rows.first().locator('.rv-b-rail-text-1').textContent() || '').trim();
    expect(t1.length).toBeGreaterThan(0);
  });

});
