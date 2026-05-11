// Job queue API tests — uses storageState (pre-logged in as admin)
const { test, expect } = require("@playwright/test");

const BASE = process.env.BASE_URL || "http://localhost:5001";

test("GET /api/queue returns array", async ({ request }) => {
  const r = await request.get(BASE + "/api/queue");
  expect(r.status()).toBe(200);
  const body = await r.json();
  expect(Array.isArray(body)).toBe(true);
});

test("DELETE non-existent queue job returns 404", async ({ request }) => {
  const r = await request.delete(BASE + "/api/queue/nonexistent-job-id");
  expect(r.status()).toBe(404);
});

test("POST retry non-existent job returns 404", async ({ request }) => {
  const r = await request.post(BASE + "/api/queue/nonexistent-job-id/retry");
  expect(r.status()).toBe(404);
});

test("queue panel present on dashboard after login", async ({ page }) => {
  // Already logged in via storageState
  await page.goto(BASE + "/");
  await expect(page).toHaveURL(BASE + "/");

  // Queue panel section should be present in the DOM
  const queueSection = page.locator('#queuePanel, .queue-panel, [id*="queue"]').first();
  await expect(queueSection).toBeAttached();
});
