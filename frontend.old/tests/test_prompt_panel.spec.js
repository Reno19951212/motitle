// E2E tests for the proofread page "自訂 Prompt" panel (Tasks 10+11 of v3.18 Stage 2).
// Covers: apply template, clear via PATCH, commit triggers PATCH + POST /api/translate.
//
// Tests require a backend running at BASE_URL (default http://localhost:5001) with the
// admin account bootstrapped. If no uploaded files exist, all three tests skip gracefully.
//
// Session auth: uses storageState from global-setup.js (admin already logged in).

const { test, expect } = require("@playwright/test");

const BASE = process.env.BASE_URL || "http://localhost:5001";

/** Return the id of the first available file, or null if none exist. */
async function getAnyFileId(page) {
  return await page.evaluate(async () => {
    const r = await fetch("/api/files", { credentials: "include" });
    if (!r.ok) return null;
    const body = await r.json();
    const list = Array.isArray(body) ? body : body.files || [];
    return list.length > 0 ? list[0].id : null;
  });
}

test.describe("Prompt panel — apply template + commit + clear", () => {
  test("apply broadcast template fills textareas and enables commit button", async ({ page }) => {
    await page.goto(BASE + "/");
    const fid = await getAnyFileId(page);
    test.skip(!fid, "no test file available — skipping");

    await page.goto(`${BASE}/proofread.html?file_id=${fid}`);
    await page.waitForSelector("#promptPanel");

    // Template dropdown should have a placeholder + at least 1 real option
    const optCount = await page.locator("#promptTemplate option").count();
    expect(optCount).toBeGreaterThan(1);

    // Select the broadcast template and apply it
    await page.selectOption("#promptTemplate", "broadcast");
    const applyBtn = page.locator("#promptApplyTemplateBtn");
    await expect(applyBtn).not.toBeDisabled();
    await applyBtn.click();

    // #promptAnchor should now contain content from the broadcast template
    const anchorVal = await page.inputValue("#promptAnchor");
    expect(anchorVal.length).toBeGreaterThan(0);
    expect(anchorVal).toContain("保留原文所有修飾語");

    // #promptSingle should also be populated
    const singleVal = await page.inputValue("#promptSingle");
    expect(singleVal.length).toBeGreaterThan(0);
    expect(singleVal).toContain("廣播電視中文字幕翻譯員");

    // Commit button should become enabled (dirty state triggered by template apply)
    await expect(page.locator("#promptCommitBtn")).not.toBeDisabled();
  });

  test("clear button sends PATCH with null and empties textareas", async ({ page }) => {
    await page.goto(BASE + "/");
    const fid = await getAnyFileId(page);
    test.skip(!fid, "no test file available — skipping");

    await page.goto(`${BASE}/proofread.html?file_id=${fid}`);
    await page.waitForSelector("#promptPanel");

    // Populate textareas via template apply so there is something to clear
    await page.selectOption("#promptTemplate", "broadcast");
    await page.locator("#promptApplyTemplateBtn").click();
    // Confirm anchor is populated before clearing
    const anchorBefore = await page.inputValue("#promptAnchor");
    expect(anchorBefore.length).toBeGreaterThan(0);

    // Intercept the PATCH request triggered by the clear button
    const patchPromise = page.waitForRequest(
      (req) =>
        req.url().includes(`/api/files/${fid}`) && req.method() === "PATCH",
    );
    await page.click('button:has-text("清空")');
    const patchReq = await patchPromise;

    // PATCH body should carry prompt_overrides: null
    const body = JSON.parse(patchReq.postData() || "{}");
    expect(body.prompt_overrides).toBeNull();

    // All textareas should be empty after clear
    expect(await page.inputValue("#promptAnchor")).toBe("");
    expect(await page.inputValue("#promptSingle")).toBe("");
    expect(await page.inputValue("#promptEnrich")).toBe("");
    expect(await page.inputValue("#promptPass1")).toBe("");
  });

  test("commit button sends PATCH then POST /api/translate", async ({ page }) => {
    await page.goto(BASE + "/");
    const fid = await getAnyFileId(page);
    test.skip(!fid, "no test file available — skipping");

    await page.goto(`${BASE}/proofread.html?file_id=${fid}`);
    await page.waitForSelector("#promptPanel");

    // Type a custom override into one textarea to mark it dirty
    await page.fill("#promptSingle", "TEST_OVERRIDE_PROMPT");

    // Commit should be enabled now (onPromptDirty wired to oninput)
    await expect(page.locator("#promptCommitBtn")).not.toBeDisabled();

    // Expect both PATCH /api/files/<fid> and POST /api/translate to fire
    const patchPromise = page.waitForRequest(
      (req) =>
        req.url().includes(`/api/files/${fid}`) && req.method() === "PATCH",
    );
    const translatePromise = page.waitForRequest(
      (req) =>
        req.url().includes("/api/translate") && req.method() === "POST",
    );

    await page.click("#promptCommitBtn");
    const [patchReq, transReq] = await Promise.all([patchPromise, translatePromise]);

    // PATCH body should carry the custom prompt in single_segment_system
    const patchBody = JSON.parse(patchReq.postData() || "{}");
    expect(patchBody.prompt_overrides).not.toBeNull();
    expect(patchBody.prompt_overrides.single_segment_system).toBe("TEST_OVERRIDE_PROMPT");

    // POST /api/translate body should reference the same file_id
    const transBody = JSON.parse(transReq.postData() || "{}");
    expect(transBody.file_id).toBe(fid);
  });
});
