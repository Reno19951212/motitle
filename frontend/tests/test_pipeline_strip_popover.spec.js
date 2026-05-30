const { test, expect } = require('@playwright/test');
const BASE = process.env.BASE_URL || 'http://localhost:5001';
const USER = process.env.PROBE_USER || 'admin_p3';
const PASS = process.env.PROBE_PASS || 'TestPass1!';
const V6_PIPE = '4696bbaa-b988-49bd-859c-e742cb365634';

test.use({ storageState: undefined });

test.describe('pipeline strip popover', () => {
  test.beforeEach(async ({ page }) => {
    const r = await page.request.post(BASE + '/login', { data: { username: USER, password: PASS } });
    if (!r.ok()) throw new Error('login ' + r.status());
    await page.setViewportSize({ width: 1512, height: 982 });
  });

  async function gotoMode(page, kind, id) {
    await page.request.post(BASE + '/api/active', { data: { kind, id } });
    await page.goto(BASE + '/', { waitUntil: 'networkidle' });
    await page.waitForTimeout(1500);
  }

  for (const [label, kind, id] of [['profile', 'profile', 'dev-default'], ['v6', 'pipeline_v6', V6_PIPE]]) {
    test(`${label}: popover hides then expands without overlap`, async ({ page }) => {
      await gotoMode(page, kind, id);

      // popover hidden by default
      await expect(page.locator('.pipeline-steps-popover')).toBeHidden();

      // open it
      await page.locator('.pipeline-steps-toggle').click();
      await expect(page.locator('.pipeline-steps-popover')).toBeVisible();

      // each .step .v shows fully (not clipped)
      const valuesFull = await page.evaluate(() =>
        [...document.querySelectorAll('.pipeline-steps-popover .step .v')]
          .every(v => v.scrollWidth <= v.clientWidth + 2));
      expect(valuesFull).toBe(true);

      // adjacent steps don't overlap horizontally
      const noOverlap = await page.evaluate(() => {
        const steps = [...document.querySelectorAll('.pipeline-steps-popover .step')];
        for (let i = 1; i < steps.length; i++) {
          if (steps[i].getBoundingClientRect().left < steps[i - 1].getBoundingClientRect().right - 2) return false;
        }
        return true;
      });
      expect(noOverlap).toBe(true);

      // click outside closes
      await page.mouse.click(5, 500);
      await expect(page.locator('.pipeline-steps-popover')).toBeHidden();
    });
  }
});
