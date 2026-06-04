// Unified 5-item left rail across all pages (Task A).
const { test, expect } = require('@playwright/test');
const BASE = process.env.BASE_URL || 'http://localhost:5001';
const USER = process.env.PROBE_USER || 'admin_p3';
const PASS = process.env.PROBE_PASS || 'TestPass1!';
const EXPECTED = ['主頁', '檔案', '校對', '術語表', 'User'];

test.use({ storageState: undefined });

async function login(page) {
  const r = await page.request.post(BASE + '/login', { data: { username: USER, password: PASS } });
  if (!r.ok()) throw new Error(`Login failed: ${r.status()}`);
}

const PAGES = [
  ['/', '主頁'],
  ['/proofread.html', '校對'],
  ['/Glossary.html', '術語表'],
  ['/user.html', 'User'],
  ['/admin.html', 'User'],
];

for (const [url, active] of PAGES) {
  test(`rail on ${url} = exactly 5 items`, async ({ page }) => {
    await login(page);
    await page.goto(BASE + url, { waitUntil: 'domcontentloaded' });
    const rail = page.locator('.b-rail');
    await expect(rail).toBeVisible();
    const labels = await rail.locator('.rail-btn .tt').allInnerTexts();
    expect(labels.map(s => s.trim())).toEqual(EXPECTED);
    const text = await rail.innerText();
    expect(text).not.toContain('Pipeline');
    expect(text).not.toContain('語言');
    expect(text).not.toContain('服務狀態');
  });
}

test('user.html reachable (200) after login', async ({ page }) => {
  await login(page);
  const r = await page.request.get(BASE + '/user.html');
  expect(r.status()).toBe(200);
});

test('index topbar 設定 gear is removed (per Ka Lok design)', async ({ page }) => {
  await login(page);
  await page.goto(BASE + '/', { waitUntil: 'domcontentloaded' });
  expect(await page.locator('#settingsGearBtn').count()).toBe(0);   // settings button removed
});
