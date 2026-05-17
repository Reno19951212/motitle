// Regression test for the "subtitle settings can't be saved" bug.
//
// Root cause: profiles.py _validate_font rejected non-int values for
// font.size / outline_width / margin_bottom, but the dashboard slider
// for outline_width uses step="0.5" and posts e.g. 2.5 (a float). The
// PATCH then 400'd, the frontend showed a generic "儲存失敗" and the
// user had no way to tell why.
const { test, expect, request: pwRequest } = require("@playwright/test");

const BASE = process.env.BASE_URL || "http://localhost:5001";

async function activeProfileId(req) {
  const r = await req.get(BASE + "/api/profiles/active");
  expect(r.status()).toBe(200);
  const body = await r.json();
  return body.profile?.id;
}

test("PATCH /api/profiles/<id> accepts float outline_width (slider step=0.5)", async ({ request }) => {
  const pid = await activeProfileId(request);
  expect(pid).toBeTruthy();
  const r = await request.patch(BASE + `/api/profiles/${pid}`, {
    data: { font: { outline_width: 2.5, size: 36, margin_bottom: 40 } },
  });
  expect(r.status(), `outline_width=2.5 should be accepted, got ${r.status()} ${await r.text()}`).toBe(200);
  const body = await r.json();
  expect(body.profile.font.outline_width).toBe(2.5);
});

test("PATCH still rejects bool + out-of-range numeric font fields", async ({ request }) => {
  const pid = await activeProfileId(request);
  // bool (isinstance(True, int) is True in Python — easy to slip through)
  const rBool = await request.patch(BASE + `/api/profiles/${pid}`, {
    data: { font: { outline_width: true } },
  });
  expect(rBool.status()).toBe(400);
  // out of range
  const rRange = await request.patch(BASE + `/api/profiles/${pid}`, {
    data: { font: { size: 999 } },
  });
  expect(rRange.status()).toBe(400);
});

test("dashboard outline slider can save without 儲存失敗 toast", async ({ page }) => {
  // The dashboard's '儲存為預設' button calls saveFontAsProfile() which
  // PATCH'es {font: fontConfig}. Pre-fix, dragging the outline slider to a
  // 0.5 step (e.g. 2.5) made fontConfig.outline_width float; backend 400'd
  // and the user saw "儲存失敗".
  await page.goto(BASE + "/");
  await page.waitForTimeout(500);

  // Capture toasts so we can assert against them
  const toasts = [];
  await page.exposeFunction("__testToast", (msg, kind) => toasts.push({ msg, kind }));
  await page.evaluate(() => {
    const orig = window.showToast;
    window.showToast = (msg, kind) => { window.__testToast(msg, kind); if (orig) orig(msg, kind); };
  });

  const result = await page.evaluate(async () => {
    // Look up active profile via the API directly (activeProfile is a
    // script-scoped `let`, not window-bound)
    const ap = await (await fetch("/api/profiles/active", { credentials: "same-origin" })).json();
    const pid = ap.profile?.id;
    // Set a fractional outline_width — what the slider would produce
    if (typeof window.updateFontConfig === "function") {
      window.updateFontConfig("outline_width", 2.5);
    }
    // Trigger the same PATCH the save button does
    const r = await fetch(`/api/profiles/${pid}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ font: { outline_width: 2.5, size: 36, margin_bottom: 40 } }),
      credentials: "same-origin",
    });
    return { status: r.status, body: await r.text() };
  });

  expect(result.status, `PATCH should succeed; got ${result.status}: ${result.body}`).toBe(200);
  // Make sure no "儲存失敗" toast was raised
  const fails = toasts.filter((t) => t.msg && t.msg.startsWith("儲存失敗"));
  expect(fails, `unexpected save-failed toasts: ${JSON.stringify(fails)}`).toEqual([]);
});
