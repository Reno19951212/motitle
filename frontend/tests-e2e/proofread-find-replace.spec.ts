import { test, expect } from '@playwright/test';

test.describe('Proofread Find & Replace', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/login');
    await page.fill('#username', 'admin');
    await page.fill('#password', 'AdminPass1!');
    await page.click('button:has-text("Log in")');
    await page.waitForLoadState('networkidle');
    test.skip(page.url().includes('/login'), 'admin login failed — env credential issue, skip');
  });

  test('Cmd/Ctrl+F opens find toolbar, typing fills query, Esc closes', async ({ page }) => {
    // Need a real loaded file because FindReplaceToolbar only mounts after `file` loads
    await page.goto('/');
    await page.waitForLoadState('networkidle');
    const openLink = page.getByRole('link', { name: /Open/i }).first();
    if (!(await openLink.isVisible({ timeout: 2_000 }).catch(() => false))) {
      test.skip(true, 'No completed file on dashboard — cannot exercise find toolbar');
      return;
    }
    await openLink.click();
    await expect(page).toHaveURL(/\/proofread\//);

    // Wait for proofread shell to settle
    await page.waitForLoadState('networkidle');

    const isMac = process.platform === 'darwin';
    const modifier = isMac ? 'Meta' : 'Control';
    await page.keyboard.press(`${modifier}+KeyF`);

    const findInput = page.getByLabel('Find query');
    await expect(findInput).toBeVisible({ timeout: 2_000 });

    // Typing updates the input value (controlled state in FindReplaceToolbar)
    await findInput.fill('test');
    await expect(findInput).toHaveValue('test');

    // Esc closes the toolbar (handled by useKeyboardShortcuts → setFindOpen(false))
    await page.keyboard.press('Escape');
    await expect(findInput).not.toBeVisible({ timeout: 2_000 });
  });
});
