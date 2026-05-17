const { defineConfig } = require('@playwright/test');
module.exports = defineConfig({
  testDir: './tests',
  timeout: 30000,
  globalSetup: './global-setup.js',
  workers: 3,
  use: {
    headless: true,
    storageState: './playwright-auth.json',
  },
});
