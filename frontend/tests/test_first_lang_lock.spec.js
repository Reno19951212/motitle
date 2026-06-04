// First-output-language lock: the first output language is bound to the upload's
// source language (faithful track). Hard-locked for 英文/普通話/日文; 粵語 source is the
// one exception — it may pick 口語廣東話 OR 中文書面語. The second output language stays free.
const { test, expect } = require('@playwright/test');
const BASE = process.env.BASE_URL || 'http://localhost:5001';
const USER = process.env.PROBE_USER || 'admin_p3';
const PASS = process.env.PROBE_PASS || 'TestPass1!';
test.use({ storageState: undefined });

async function openPopup(page) {
  const r = await page.request.post(BASE + '/login', { data: { username: USER, password: PASS } });
  if (!r.ok()) throw new Error('login ' + r.status());
  await page.goto(BASE + '/', { waitUntil: 'domcontentloaded' });
  await page.waitForFunction(() => typeof openOutputLangModal === 'function', { timeout: 15000 });
  await page.setInputFiles('#fileInput', { name: 'clip.mp4', mimeType: 'video/mp4', buffer: Buffer.from('fake') });
  await expect(page.locator('#olOverlay')).toHaveClass(/open/, { timeout: 5000 });
}

const firstOpts = (page) =>
  page.locator('#olFirstLang option').evaluateAll((o) => o.map((x) => x.value));

test('英文 / 普通話 / 日文 source 硬鎖第一語言 = source (select disabled)', async ({ page }) => {
  await openPopup(page);
  for (const lang of ['en', 'cmn', 'ja']) {
    await page.selectOption('#olSourceLang', lang);
    expect(await firstOpts(page)).toEqual([lang]);                 // only the source language
    expect(await page.locator('#olFirstLang').isDisabled()).toBe(true);   // hard-locked
    expect(await page.locator('#olFirstLang').inputValue()).toBe(lang);
  }
});

test('粵語 source 例外：第一語言可揀 口語廣東話 / 中文書面語 (enabled)', async ({ page }) => {
  await openPopup(page);
  await page.selectOption('#olSourceLang', 'yue');
  expect(await firstOpts(page)).toEqual(['zh', 'yue']);           // 書面語 first (default), 口語 second
  expect(await page.locator('#olFirstLang').inputValue()).toBe('zh');  // 粵語預設 = 中文書面語
  expect(await page.locator('#olFirstLang').isDisabled()).toBe(false);
  await page.selectOption('#olFirstLang', 'yue');                 // 口語 selectable
  expect(await page.locator('#olFirstLang').inputValue()).toBe('yue');
  await page.selectOption('#olFirstLang', 'zh');                  // 書面語 selectable
  expect(await page.locator('#olFirstLang').inputValue()).toBe('zh');
});

test('切換 source 即時重套鎖定（粵語→英文鎖 en，英文→粵語還原可揀）', async ({ page }) => {
  await openPopup(page);
  await page.selectOption('#olSourceLang', 'yue');
  await page.selectOption('#olFirstLang', 'zh');                   // user picks 書面語
  await page.selectOption('#olSourceLang', 'en');                  // → hard-lock en
  expect(await firstOpts(page)).toEqual(['en']);
  expect(await page.locator('#olFirstLang').isDisabled()).toBe(true);
  expect(await page.locator('#olFirstLang').inputValue()).toBe('en');
  await page.selectOption('#olSourceLang', 'yue');                 // back to 粵語
  expect(await firstOpts(page)).toEqual(['zh', 'yue']);
  expect(await page.locator('#olFirstLang').inputValue()).toBe('zh');  // 還原預設書面語
  expect(await page.locator('#olFirstLang').isDisabled()).toBe(false);
});

test('第二輸出語言排走同來源同語系（英文 source → 仍可揀中文/日文，但唔可再揀英文）', async ({ page }) => {
  await openPopup(page);
  await page.selectOption('#olSourceLang', 'en');                  // first locked = en (en 語系)
  const secondVals = await page.locator('#olSecondLang option').evaluateAll((o) => o.map((x) => x.value));
  // en 語系排走 → 仍含中文系 + 日文 + 無，但唔含 en
  expect(secondVals).toEqual(expect.arrayContaining(['', 'yue', 'zh', 'cmn', 'ja']));
  expect(secondVals).not.toContain('en');
});

test('粵語 source → 第二語言唔可揀任何中文形態（封鎖同語系雙輸出 drift）', async ({ page }) => {
  await openPopup(page);
  await page.selectOption('#olSourceLang', 'yue');                 // 中文語系
  const secondVals = await page.locator('#olSecondLang option').evaluateAll((o) => o.map((x) => x.value));
  expect(secondVals).toEqual(['', 'en', 'ja']);                   // 只剩無 + 跨語系
  for (const zh of ['yue', 'zh', 'cmn']) expect(secondVals).not.toContain(zh);
});

test('切換 source 即時重套第二語言過濾（粵語→英文 source 後可再揀中文做第二）', async ({ page }) => {
  await openPopup(page);
  await page.selectOption('#olSourceLang', 'yue');
  expect(await page.locator('#olSecondLang option').evaluateAll(o => o.map(x => x.value))).toEqual(['', 'en', 'ja']);
  await page.selectOption('#olSourceLang', 'en');                 // 切去英文 source
  const vals = await page.locator('#olSecondLang option').evaluateAll(o => o.map(x => x.value));
  expect(vals).toContain('zh');                                  // 英文 source → 第二可揀中文書面語
  expect(vals).not.toContain('en');
});
