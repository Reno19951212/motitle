// E2E regression for the proofread panel layout fix (2026-05-30).
// Guards: (1) 自訂 Prompt panel fully removed; (2) 詞彙表 + 字幕設定 share one
// row at proper height (not crushed to ~88px by a stray 3rd grid child).
const { test, expect } = require('@playwright/test');

const BASE = process.env.BASE_URL || 'http://localhost:5001';
const USER = process.env.PROBE_USER || 'admin_p3';
const PASS = process.env.PROBE_PASS || 'AdminPass1!';

test.use({ storageState: undefined });

test.describe('proofread panel layout', () => {
  test.beforeEach(async ({ page }) => {
    const r = await page.request.post(BASE + '/login', { data: { username: USER, password: PASS } });
    if (!r.ok()) throw new Error(`Login failed: ${r.status()}`);
  });

  async function openProofread(page) {
    const filesR = await page.request.get(BASE + '/api/files');
    const files = (await filesR.json()).files || [];
    test.skip(files.length === 0, 'No files in registry — upload one first');
    const fid = files[0].id;
    await page.setViewportSize({ width: 1512, height: 900 }); // MacBook 14"
    await page.goto(`${BASE}/proofread.html?file_id=${fid}`);
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(1500);
    return fid;
  }

  test('自訂 Prompt panel is fully removed', async ({ page }) => {
    await openProofread(page);
    await expect(page.locator('#promptPanel')).toHaveCount(0);
    await expect(page.locator('#promptTemplate')).toHaveCount(0);
    await expect(page.locator('#promptCommitBtn')).toHaveCount(0);
  });

  test('詞彙表 + 字幕設定 fill one row at proper height', async ({ page }) => {
    await openProofread(page);
    const glo = await page.locator('#glossaryPanel').boundingBox();
    const sub = await page.locator('#subtitleSettingsPanel').boundingBox();
    expect(glo).not.toBeNull();
    expect(sub).not.toBeNull();
    expect(glo.height).toBeGreaterThan(180);
    expect(sub.height).toBeGreaterThan(180);
    expect(Math.abs(glo.height - sub.height)).toBeLessThan(24);
    expect(Math.abs(glo.y - sub.y)).toBeLessThan(8);
    expect(sub.x).toBeGreaterThan(glo.x);
  });
});
