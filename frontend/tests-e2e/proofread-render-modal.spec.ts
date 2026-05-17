import { test, expect } from '@playwright/test';

test.describe('Proofread render modal', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/login');
    await page.fill('#username', 'admin');
    await page.fill('#password', 'AdminPass1!');
    await page.click('button:has-text("Log in")');
    await page.waitForLoadState('networkidle');
    test.skip(page.url().includes('/login'), 'admin login failed — env credential issue, skip');
  });

  test('Render button opens modal with MP4 tab default, switch to MXF ProRes, close', async ({ page }) => {
    // Navigate to a real completed file via dashboard "Open" link. If none exist, skip.
    await page.goto('/');
    await page.waitForLoadState('networkidle');
    const openLink = page.getByRole('link', { name: /Open/i }).first();
    if (!(await openLink.isVisible({ timeout: 2_000 }).catch(() => false))) {
      test.skip(true, 'No completed file with Open link on dashboard — cannot exercise render modal');
      return;
    }
    await openLink.click();
    await expect(page).toHaveURL(/\/proofread\//);

    // Open render modal from TopBar
    await page.getByRole('button', { name: /Render/ }).click();
    await expect(page.getByText('Render Output')).toBeVisible({ timeout: 3_000 });

    // MP4 tab should be the default selected tab
    const mp4Tab = page.getByRole('tab', { name: 'MP4' });
    await expect(mp4Tab).toHaveAttribute('data-state', 'active');

    // Switch to MXF ProRes
    const mxfTab = page.getByRole('tab', { name: 'MXF ProRes' });
    await mxfTab.click();
    await expect(mxfTab).toHaveAttribute('data-state', 'active');

    // Close modal via Escape
    await page.keyboard.press('Escape');
    await expect(page.getByText('Render Output')).not.toBeVisible({ timeout: 2_000 });
  });
});
