// test_v6_second_language.spec.js
//
// Verifies the file-context language selector rendered inside #pipelineStrip:
//   1. V6 single-lang file → strip shows first-lang chip + "+ 加第二語言" button
//   2. Click "+ 加第二語言" → dropdown menu opens with target language
//   3. Profile file with two languages → shows first+second chips, NO add button
//   4. (intercept) click target → translate-second POST fires, "翻譯中…" chip appears
//
// Uses window.__injectFileAndSelectForStrip to seed synthetic file entries
// without depending on live registry data.

const { test, expect } = require('@playwright/test');

const BASE = process.env.BASE_URL || 'http://localhost:5001';
const USER = process.env.PROBE_USER || 'admin_p3';
const PASS = process.env.PROBE_PASS || 'TestPass1!';

test.use({ storageState: undefined });

test.describe.serial('pipeline-strip language selector', () => {

  test.beforeEach(async ({ page }) => {
    const r = await page.request.post(BASE + '/login', { data: { username: USER, password: PASS } });
    if (!r.ok()) throw new Error(`Login failed: ${r.status()}`);
  });

  // Helper: navigate + wait for the test injection helper to be available
  async function gotoAndWait(page) {
    await page.goto(BASE + '/');
    await page.waitForFunction(
      () => typeof window.__injectFileAndSelectForStrip === 'function',
      { timeout: 15000 }
    );
  }

  // -------------------------------------------------------------------------
  // Test 1: V6 single-lang file → shows first chip + "加第二語言" button
  // -------------------------------------------------------------------------
  test('v6_single_lang_shows_first_chip_and_add_button', async ({ page }) => {
    const errors = [];
    page.on('console', m => { if (m.type() === 'error') errors.push(m.text()); });

    await gotoAndWait(page);

    await page.evaluate(() => {
      window.__injectFileAndSelectForStrip('t_v6_single', {
        id: 't_v6_single',
        active_kind: 'pipeline_v6',
        languages: [{ role: 'first', lang: 'zh', label: '粵語原文' }],
      });
    });

    // First-lang chip should appear
    const chip = page.locator('#pipelineStrip .strip-lang-chip').first();
    await expect(chip).toBeVisible({ timeout: 5000 });
    await expect(chip).toContainText('粵語原文');
    await expect(chip).toContainText('ZH');

    // Add-lang button should appear
    const addBtn = page.locator('#pipelineStrip .strip-add-lang');
    await expect(addBtn).toBeVisible();
    await expect(addBtn).toContainText('加第二語言');

    expect(errors.filter(e => !e.includes('favicon'))).toHaveLength(0);
  });

  // -------------------------------------------------------------------------
  // Test 2: Click add button → dropdown opens with EN target
  // -------------------------------------------------------------------------
  test('click_add_button_opens_menu_with_en_target', async ({ page }) => {
    await gotoAndWait(page);

    await page.evaluate(() => {
      window.__injectFileAndSelectForStrip('t_v6_menu', {
        id: 't_v6_menu',
        active_kind: 'pipeline_v6',
        languages: [{ role: 'first', lang: 'zh', label: '粵語原文' }],
      });
    });

    const addBtn = page.locator('#pipelineStrip .strip-add-lang');
    await expect(addBtn).toBeVisible({ timeout: 5000 });
    await addBtn.click();

    const menu = page.locator('#pipelineStrip .strip-add-lang-menu.open');
    await expect(menu).toBeVisible({ timeout: 3000 });

    // Should contain English target button
    const enBtn = menu.locator('button', { hasText: '英文 (EN)' });
    await expect(enBtn).toBeVisible();
  });

  // -------------------------------------------------------------------------
  // Test 3: Profile file with two languages → both chips, no add button
  // -------------------------------------------------------------------------
  test('profile_two_lang_file_shows_both_chips_no_add_button', async ({ page }) => {
    await gotoAndWait(page);

    await page.evaluate(() => {
      window.__injectFileAndSelectForStrip('t_profile_bilingual', {
        id: 't_profile_bilingual',
        active_kind: 'profile',
        languages: [
          { role: 'first',  lang: 'en', label: '英文原文' },
          { role: 'second', lang: 'zh', label: '中文譯文' },
        ],
      });
    });

    // Both chips should appear
    const chips = page.locator('#pipelineStrip .strip-lang-chip');
    await expect(chips).toHaveCount(2, { timeout: 5000 });

    const firstChip = chips.nth(0);
    await expect(firstChip).toContainText('英文原文');
    await expect(firstChip).toContainText('EN');

    const secondChip = chips.nth(1);
    await expect(secondChip).toContainText('中文譯文');
    await expect(secondChip).toContainText('ZH');

    // No add button — profile files don't show the add-lang CTA
    const addBtn = page.locator('#pipelineStrip .strip-add-lang');
    await expect(addBtn).toHaveCount(0);
  });

  // -------------------------------------------------------------------------
  // Test 4: Click EN target → POST intercepted, "翻譯中…" chip appears
  // -------------------------------------------------------------------------
  test('click_en_target_fires_translate_second_and_shows_spinner', async ({ page }) => {
    // Intercept the translate-second POST before navigation
    await page.route('**/translate-second', route => {
      route.fulfill({
        status: 202,
        contentType: 'application/json',
        body: JSON.stringify({ file_id: 't_v6_spin', job_id: 'j_test_1', target_lang: 'en' }),
      });
    });

    await gotoAndWait(page);

    await page.evaluate(() => {
      window.__injectFileAndSelectForStrip('t_v6_spin', {
        id: 't_v6_spin',
        active_kind: 'pipeline_v6',
        languages: [{ role: 'first', lang: 'zh', label: '粵語原文' }],
      });
    });

    // Open menu
    const addBtn = page.locator('#pipelineStrip .strip-add-lang');
    await expect(addBtn).toBeVisible({ timeout: 5000 });
    await addBtn.click();

    const menu = page.locator('#pipelineStrip .strip-add-lang-menu.open');
    await expect(menu).toBeVisible({ timeout: 3000 });

    // Click the EN target button
    const enBtn = menu.locator('button', { hasText: '英文 (EN)' });
    await enBtn.click();

    // "翻譯中…" spinner chip should appear
    const spinnerChip = page.locator('#pipelineStrip .strip-lang-adding');
    await expect(spinnerChip).toBeVisible({ timeout: 5000 });
    await expect(spinnerChip).toContainText('翻譯中');
  });
});
