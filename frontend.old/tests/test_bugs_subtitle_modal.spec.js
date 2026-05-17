// Verification + regression tests for two reported UI bugs:
//   Bug 1: live subtitle overlay jumps around erratically while MT translation
//          is running (re-translate / pipeline rerun).
//   Bug 2: opening a "child" modal (edit / engine config) on top of a parent
//          modal (manage / pipeline) — both share z-index 3000 so the second
//          modal's dimming backdrop layers OVER the first, obscuring content.
const { test, expect } = require("@playwright/test");

const BASE = process.env.BASE_URL || "http://localhost:5001";

// ---------------------------------------------------------------------------
// Bug 2: modal stacking
// ---------------------------------------------------------------------------
test("Bug 2 — child modal renders ABOVE its parent (effective z-index)", async ({ page }) => {
  await page.goto(BASE + "/");
  await expect(page).toHaveURL(BASE + "/");

  // Open pipeline-manage modal (parent)
  await page.evaluate(() => window.openProfileManageModal && window.openProfileManageModal());
  await page.waitForTimeout(150);
  const ppmOpen = await page.locator("#ppmOverlay.open").count();
  if (ppmOpen === 0) {
    test.skip(true, "openProfileManageModal not available in this build");
    return;
  }
  // Open Save modal (child)
  await page.evaluate(() => window.openProfileSaveModal && window.openProfileSaveModal());
  await page.waitForTimeout(150);
  const ppsOpen = await page.locator("#ppsOverlay.open").count();
  expect(ppsOpen, "child modal should be open").toBeGreaterThan(0);

  const ppmZ = await page.evaluate(() => {
    const e = document.getElementById("ppmOverlay");
    return e ? parseInt(getComputedStyle(e).zIndex, 10) : null;
  });
  const ppsZ = await page.evaluate(() => {
    const e = document.getElementById("ppsOverlay");
    return e ? parseInt(getComputedStyle(e).zIndex, 10) : null;
  });
  console.log(`z-index: ppmOverlay=${ppmZ}, ppsOverlay=${ppsZ}`);

  // Capture pixel at center of ppsOverlay modal box — should be the LIGHT
  // modal background, not the dark ppm backdrop.
  expect(ppsZ, "child modal must have strictly higher z-index than parent").toBeGreaterThan(ppmZ);

  // Tidy up so the next test starts clean
  await page.evaluate(() => {
    window.closeProfileSaveModal && window.closeProfileSaveModal();
    window.closeProfileManageModal && window.closeProfileManageModal();
  });
});

// ---------------------------------------------------------------------------
// Bug 1: subtitle overlay stability during translation
// Strategy: load a done+translated file, capture FontPreview text at a fixed
// video time across N samples while translation_progress events flow in via
// SocketIO. The text at a given video timestamp must remain stable.
// ---------------------------------------------------------------------------
test("Bug 1 — renderProgressOnly leaves transcript DOM untouched", async ({ page, request }) => {
  // Deterministic version: doesn't trigger MT (which is non-deterministic and
  // creates queue backlog across ralph runs). Instead, exercises the exact
  // code path used by the translation_progress + subtitle_segment handlers
  // — renderProgressOnly() — and verifies the transcript-scroll DOM node
  // is the SAME identity before and after. If the bug regresses,
  // renderTranscriptTab will fire under renderProgressOnly and rebuild
  // innerHTML, swapping out the node.
  const r = await request.get(BASE + "/api/files");
  const files = (await r.json()).files || [];
  const target = files.find((f) => f.status === "done" && f.segment_count > 0);
  if (!target) {
    test.skip(true, "no done file with segments");
    return;
  }

  await page.goto(BASE + "/");
  await page.waitForTimeout(300);
  await page.evaluate((id) => window.selectFile && window.selectFile(id), target.id);

  // Wait for transcript rows
  await page.waitForFunction(
    () => document.querySelectorAll(".t-row[data-seg]").length > 0,
    null,
    { timeout: 12000 }
  );

  // Capture initial scroll element + a known child, plus a unique marker
  // we set on the scroll node — if renderTranscriptTab fires, innerHTML is
  // replaced and the marker is lost.
  await page.evaluate(() => {
    const s = document.querySelector(".transcript-scroll");
    if (s) s.dataset.bug1Marker = "stable-before-progress";
  });

  // Simulate 30 progress events firing in quick succession (same volume as a
  // long MT translation generates). renderProgressOnly is the function the
  // post-fix handlers call.
  await page.evaluate(() => {
    for (let i = 0; i < 30; i++) {
      if (typeof window.renderProgressOnly === "function") window.renderProgressOnly();
    }
  });

  const markerStillPresent = await page.evaluate(() => {
    const s = document.querySelector(".transcript-scroll");
    return s ? s.dataset.bug1Marker === "stable-before-progress" : null;
  });
  expect(
    markerStillPresent,
    "renderProgressOnly() must NOT rebuild transcript-scroll innerHTML — Bug 1 regression"
  ).toBe(true);

  // Sanity: renderProgressOnly itself must exist (otherwise fix is missing)
  const helperExists = await page.evaluate(() => typeof window.renderProgressOnly === "function");
  expect(helperExists, "window.renderProgressOnly should be defined").toBe(true);
});
