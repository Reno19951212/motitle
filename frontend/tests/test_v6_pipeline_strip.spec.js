/**
 * V6 Pipeline strip — Playwright spec (Task 4.1)
 *
 * Covers:
 *  1. Preset menu renders two sections (Profile / Dual-ASR V6)
 *  2. Activating a V6 pipeline renders V6 columns (vad, qwen3-ctx, refiner)
 *  3. Clicking Qwen3 Context step opens the inline prompt panel
 *  4. Editing + committing inline panel PATCHes the pipeline
 *  5. Switching back to Profile restores ASR + MT columns
 *
 * Login: self-managed (admin / AdminPass1! on dev DB).
 * The global-setup.js 'admin' user exists in the dev DB (created later in
 * the test-suite lifecycle) — confirmed via DB query at task-write time.
 * If 'admin' login fails, PROBE_USER / PROBE_PASS env overrides are honoured.
 */

const { test, expect } = require("@playwright/test");
const path = require("path");
const fs = require("fs");

const BASE = process.env.BASE_URL || "http://localhost:5001";
const USER = process.env.PROBE_USER || "admin";
const PASS = process.env.PROBE_PASS || 'TestPass1!';

// Auth storage file shared across the suite. We do a single login in
// beforeAll and reuse the session to avoid hitting the 10 req/min rate
// limit on /login. Spec manages its own auth — does NOT rely on
// global-setup.js (which can use 'admin' or 'admin_p3' depending on env).
const AUTH_FILE = path.join(__dirname, ".v6-spec-auth.json");

// Remove stale auth file at module load time so the suite always starts
// fresh. (Playwright loads this module once per worker.)
try { fs.unlinkSync(AUTH_FILE); } catch (_) {}

test.use({ storageState: undefined });

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

async function restoreProfile(page) {
  // Best-effort: put global active back to dev-default Profile via direct
  // API call so we don't trigger _activatingProfile JS lock issues.
  try {
    await page.request.post(`${BASE}/api/active`, {
      data: { kind: "profile", id: "dev-default" },
    });
  } catch (_) {
    // Ignore — test isolation is best-effort.
  }
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

test.describe("V6 Pipeline strip", () => {
  // Login once before the whole describe block, save cookie to AUTH_FILE.
  test.beforeAll(async ({ browser }) => {
    const ctx = await browser.newContext({ storageState: undefined });
    const page = await ctx.newPage();
    const r = await page.request.post(`${BASE}/login`, {
      data: { username: USER, password: PASS },
    });
    if (!r.ok()) {
      await page.close();
      await ctx.close();
      throw new Error(
        `[beforeAll] Login failed for ${USER}: HTTP ${r.status()} — ${await r.text()}`
      );
    }
    await ctx.storageState({ path: AUTH_FILE });
    await page.close();
    await ctx.close();
  });

  // Each test reuses the saved cookie.
  test.beforeEach(async ({ page }) => {
    // Apply auth from the shared file
    await page.context().addCookies(
      JSON.parse(fs.readFileSync(AUTH_FILE, "utf8")).cookies || []
    );
    await page.goto(`${BASE}/`);
    // Wait for full page hydration. The init chain runs sequentially:
    //   fetchMe → fetchActiveProfile → fetchActivePipeline → fetchProfiles
    //   → fetchPipelines (populates availablePipelines) → ...
    //
    // `activeKind` is set early (in fetchMe), but `availablePipelines` is
    // populated later in the chain. We wait for BOTH to be ready, using a
    // generous 15s timeout for slow backends.
    // Wait for the full init chain to complete:
    //   fetchMe (sets activeKind) → ... → fetchPipelines (sets availablePipelines)
    // `let` vars declared in the <script> block are accessible as bare names
    // inside page.evaluate / waitForFunction — they are NOT on `window`.
    await page.waitForFunction(
      () =>
        typeof activeKind !== "undefined" &&
        typeof availablePipelines !== "undefined" &&
        availablePipelines.length > 0,
      { timeout: 15_000 }
    ).catch(() => {
      // If pipelines never arrive (e.g., empty server), tests 2-4 will
      // still skip gracefully via their own guard.
    });
  });

  test.afterEach(async ({ page }) => {
    await restoreProfile(page);
  });

  // -------------------------------------------------------------------------
  // Test 1: Preset menu renders both sections
  // -------------------------------------------------------------------------
  test("presetMenuShowsBothSections", async ({ page }) => {
    // Hover over the Pipeline preset button to open the menu.
    const wrap = page.locator(".pipeline-preset-wrap").first();
    await expect(wrap).toBeVisible({ timeout: 8_000 });
    await wrap.hover();

    const menu = wrap.locator(".preset-menu").first();
    // Menu should appear (CSS :hover shows it)
    await expect(menu).toBeVisible({ timeout: 3_000 });

    // Must contain both section headers
    await expect(
      menu.locator(".step-menu-head", { hasText: "舊有 Profile 組合" })
    ).toBeVisible();
    await expect(
      menu.locator(".step-menu-head", { hasText: "Dual-ASR Pipeline (V6)" })
    ).toBeVisible();
  });

  // -------------------------------------------------------------------------
  // Test 2: Activating a V6 pipeline renders V6-specific columns
  // -------------------------------------------------------------------------
  test("activateV6PipelineRendersV6Columns", async ({ page }) => {
    // Get the first V6 pipeline from the already-loaded page state
    const v6Pipeline = await page.evaluate(() =>
      availablePipelines.find((p) => p.pipeline_type === "v6_vad_dual_asr")
    );

    if (!v6Pipeline) {
      test.skip(true, "no V6 pipeline available in availablePipelines");
      return;
    }

    // Activate via direct API call + reload. Using page.request.post avoids
    // the JS _activatingProfile lock issue and the window.fetchMe vs
    // let-scoped fetchMe scope ambiguity that prevents activeKind from updating
    // when activatePipeline() is called inside page.evaluate().
    await page.request.post(`${BASE}/api/active`, {
      data: { kind: "pipeline_v6", id: v6Pipeline.id },
    });
    await page.reload();
    await page.waitForFunction(
      () =>
        typeof activeKind !== "undefined" &&
        typeof availablePipelines !== "undefined" &&
        availablePipelines.length > 0,
      { timeout: 15_000 }
    ).catch(() => {});

    // After activation + reload, activeKind should be pipeline_v6
    await page.waitForFunction(() => activeKind === "pipeline_v6", {
      timeout: 8_000,
    });

    // V6 columns should be visible
    await expect(page.locator('[data-step="vad"]')).toBeVisible();
    await expect(page.locator('[data-step="qwen3-ctx"]')).toBeVisible();
    await expect(page.locator('[data-step="refiner"]')).toBeVisible();

    // Legacy Profile-mode columns should NOT be visible in V6 mode
    await expect(page.locator('[data-step="asr"]')).toHaveCount(0);
    await expect(page.locator('[data-step="mt"]')).toHaveCount(0);
  });

  // -------------------------------------------------------------------------
  // Test 3: Clicking qwen3-ctx step opens the inline prompt panel
  // -------------------------------------------------------------------------
  test("clickQwen3ContextOpensInlinePanel", async ({ page }) => {
    const v6Pipeline = await page.evaluate(() =>
      availablePipelines.find((p) => p.pipeline_type === "v6_vad_dual_asr")
    );

    if (!v6Pipeline) {
      test.skip(true, "no V6 pipeline available");
      return;
    }

    // Activate via direct API + reload (same pattern as test 2)
    await page.request.post(`${BASE}/api/active`, {
      data: { kind: "pipeline_v6", id: v6Pipeline.id },
    });
    await page.reload();
    await page.waitForFunction(
      () =>
        typeof activeKind !== "undefined" &&
        typeof availablePipelines !== "undefined" &&
        availablePipelines.length > 0,
      { timeout: 15_000 }
    ).catch(() => {});
    await page.waitForFunction(() => activeKind === "pipeline_v6", {
      timeout: 8_000,
    });

    // Click the qwen3-ctx step column to open inline panel
    await page.locator('[data-step="qwen3-ctx"]').click();

    const panel = page.locator("#inlinePromptPanel");
    await expect(panel).toBeVisible({ timeout: 4_000 });

    // Title should indicate Qwen3 ASR Context
    await expect(page.locator("#ippTitle")).toHaveText("Qwen3 ASR Context");
    // Textarea should exist and be editable
    await expect(page.locator("#ippTextarea")).toBeVisible();
  });

  // -------------------------------------------------------------------------
  // Test 4: Commit inline panel PATCHes /api/pipelines/<id>
  // -------------------------------------------------------------------------
  test("commitInlinePanelPatchesPipeline", async ({ page }) => {
    const v6Pipeline = await page.evaluate(() =>
      availablePipelines.find((p) => p.pipeline_type === "v6_vad_dual_asr")
    );

    if (!v6Pipeline) {
      test.skip(true, "no V6 pipeline available");
      return;
    }

    const originalCtx = v6Pipeline.qwen3_asr?.context || "";

    // Activate via direct API + reload
    await page.request.post(`${BASE}/api/active`, {
      data: { kind: "pipeline_v6", id: v6Pipeline.id },
    });
    await page.reload();
    await page.waitForFunction(
      () =>
        typeof activeKind !== "undefined" &&
        typeof availablePipelines !== "undefined" &&
        availablePipelines.length > 0,
      { timeout: 15_000 }
    ).catch(() => {});
    await page.waitForFunction(() => activeKind === "pipeline_v6", {
      timeout: 8_000,
    });

    // Open inline panel for qwen3_context
    await page.locator('[data-step="qwen3-ctx"]').click();
    await page.locator("#inlinePromptPanel").waitFor({ state: "visible" });

    const testCtx = "PLAYWRIGHT_TEST_CTX_" + Date.now();
    await page.locator("#ippTextarea").fill(testCtx);

    // Listen for the PATCH request before clicking save
    const patchPromise = page.waitForResponse(
      (r) =>
        r.url().includes("/api/pipelines/") && r.request().method() === "PATCH",
      { timeout: 10_000 }
    );

    // Click the primary button ("儲存到當前 Pipeline")
    await page.locator("#inlinePromptPanel .btn-primary").click();

    let patch;
    try {
      patch = await patchPromise;
    } catch (e) {
      // PATCH did not arrive — note as concern but still check
      throw new Error(
        `PATCH /api/pipelines/<id> was not called after commit: ${e.message}`
      );
    }

    expect(patch.ok(), `PATCH response should be 2xx, got ${patch.status()}`).toBeTruthy();

    const body = patch.request().postDataJSON();
    expect(body).toBeTruthy();
    expect(body.qwen3_asr?.context).toBe(testCtx);

    // Restore original context value via page.request (avoids let-scope issues)
    await page.request.patch(`${BASE}/api/pipelines/${v6Pipeline.id}`, {
      data: {
        qwen3_asr: { ...(v6Pipeline.qwen3_asr || {}), context: originalCtx },
      },
    });
  });

  // -------------------------------------------------------------------------
  // Test 5: Switching back to Profile restores ASR + MT columns
  // -------------------------------------------------------------------------
  test("switchBackToProfileRestoresProfileColumns", async ({ page }) => {
    // Activate V6 first via direct API call (avoids JS _activatingProfile lock)
    const pipelines = await page.evaluate(
      () => availablePipelines || []
    );
    const v6Pipeline = pipelines.find(
      (p) => p.pipeline_type === "v6_vad_dual_asr"
    );

    if (v6Pipeline) {
      await page.request.post(`${BASE}/api/active`, {
        data: { kind: "pipeline_v6", id: v6Pipeline.id },
      });
      // Reload so the page picks up the new active state from server
      await page.reload();
      await page.waitForFunction(() => typeof activeKind !== "undefined", {
        timeout: 10_000,
      });
      // Should now be in V6 mode
      await page.waitForFunction(() => activeKind === "pipeline_v6", {
        timeout: 6_000,
      });
    }

    // Switch back to dev-default Profile via direct API call
    await page.request.post(`${BASE}/api/active`, {
      data: { kind: "profile", id: "dev-default" },
    });
    await page.reload();
    await page.waitForFunction(() => typeof activeKind !== "undefined", {
      timeout: 10_000,
    });
    await page.waitForFunction(() => activeKind === "profile", {
      timeout: 8_000,
    });

    // Profile-mode columns should be present
    await expect(page.locator('[data-step="asr"]')).toBeVisible();
    await expect(page.locator('[data-step="mt"]')).toBeVisible();

    // V6-only columns must be absent
    await expect(page.locator('[data-step="vad"]')).toHaveCount(0);
  });

});
