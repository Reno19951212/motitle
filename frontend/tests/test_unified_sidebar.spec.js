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

// Regression (2026-06-05): the rail 主頁 link used href="index.html" on Glossary/Files/
// user, which 404s (backend serves "/", not "/index.html"). And proofread's 檔案 link
// pointed at "/" instead of Files.html. The home link must be "/" on every cross-page rail.
test('rail 主頁 points to / (not the 404 index.html) on every cross-page rail', async ({ page }) => {
  await login(page);
  for (const url of ['/proofread.html', '/Glossary.html', '/Files.html', '/user.html']) {
    await page.goto(BASE + url, { waitUntil: 'domcontentloaded' });
    const home = await page.locator('.b-rail a.rail-btn', { hasText: '主頁' }).first().getAttribute('href');
    expect(home, `${url} 主頁 link`).toBe('/');
  }
});

test('proofread rail 檔案 points to Files.html (not home)', async ({ page }) => {
  await login(page);
  await page.goto(BASE + '/proofread.html', { waitUntil: 'domcontentloaded' });
  const files = await page.locator('.b-rail a.rail-btn', { hasText: '檔案' }).first().getAttribute('href');
  expect(files).toBe('/Files.html');
});
