// test_unified_progress.spec.js — Task 3+4 step-diagram integration
//
// Verifies that:
//   1. V6 file card: .step-diagram present, 5 .sd-step, labels include
//      "VAD 切段" and "Refiner 校對" (not "Stage N" hardcoded strings)
//   2. Profile file card: .step-diagram with 3 .sd-step (轉錄/翻譯/校對)
//   3. Right-side queue panel: renderStepDiagram path doesn't throw —
//      inject a synthetic pipeline_progress event and confirm no console errors
//
// Cold-start / static state is used since live processing is hard to hold.

const { test, expect } = require('@playwright/test');

const BASE = process.env.BASE_URL || 'http://localhost:5001';
const USER = process.env.PROBE_USER || 'admin_p3';
const PASS = process.env.PROBE_PASS || 'TestPass1!';

// File IDs supplied in the task
const V6_FILE_ID      = '2d4a09ac51d9';
const PROFILE_FILE_ID = '53cdfc00c9cf';

test.use({ viewport: { width: 1512, height: 982 }, storageState: undefined });

test.describe.serial('unified-progress step-diagram', () => {

  test.beforeEach(async ({ page }) => {
    const r = await page.request.post(BASE + '/login', {
      data: { username: USER, password: PASS },
    });
    if (!r.ok()) throw new Error(`Login failed: ${r.status()}`);
  });

  test('V6 file card has 5-step diagram with correct stage labels', async ({ page }) => {
    const errors = [];
    page.on('console', msg => { if (msg.type() === 'error') errors.push(msg.text()); });

    await page.goto(BASE + '/', { waitUntil: 'networkidle' });

    // Inject a V6 file into uploadedFiles so the card renders.
    // We use the backend data to verify what kind the file actually is,
    // then drive the renderQueue() client-side.
    await page.waitForFunction(() => typeof window.renderStepDiagram === 'function', { timeout: 5000 });

    // Seed a V6 file card if not already present in uploadedFiles from /api/files.
    // uploadedFiles is a let in the script closure — if the file exists in the registry
    // it'll already be populated by fetchFileList(). Force a cold-start by calling
    // renderQueue() to ensure the diagram renders from current state.
    await page.evaluate((fid) => {
      // uploadedFiles is closure-scoped; seed it only if the file is absent
      if (typeof uploadedFiles !== 'undefined' && !uploadedFiles[fid]) {
        uploadedFiles[fid] = {
          id: fid,
          original_name: 'test_v6_file.mp4',
          status: 'done',
          translation_status: null,   // realistic V6 terminal state (no separate MT job)
          active_kind: 'pipeline_v6',
          uploaded_at: Date.now() / 1000,
        };
      }
      if (typeof renderQueue === 'function') renderQueue();
    }, V6_FILE_ID);

    // Wait for the card to appear
    const card = page.locator(`.queue-item[data-file-id="${V6_FILE_ID}"]`);
    await expect(card).toBeVisible({ timeout: 3000 });

    // Step diagram should be present
    const diagram = card.locator('.step-diagram');
    await expect(diagram).toBeVisible();

    // Should have exactly 5 steps
    const steps = card.locator('.sd-step');
    await expect(steps).toHaveCount(5);

    // Check key labels are present (not generic "Stage N")
    await expect(card).toContainText('VAD 切段');
    await expect(card).toContainText('Refiner 校對');
    // Must NOT contain "Stage" as a label (would indicate hardcoded fallback)
    const text = await card.innerText();
    expect(text).not.toMatch(/Stage\s+\d/);

    // No console errors
    expect(errors.filter(e => !e.includes('favicon'))).toHaveLength(0);
  });

  test('completed V6 file (translation_status null) shows ALL 5 steps done', async ({ page }) => {
    // Regression: real completed V6 files carry status='done' but
    // translation_status=null (V6 refiner is inline — no separate MT job, so
    // _mt_handler never sets translation_status='done'). The cold-start derive
    // must treat status='done' alone as V6 completion. Previously it required
    // (st==='done' && transSt==='done') and fell through to {idx:0,'idle'},
    // rendering all 5 steps as pending ○ on a finished file.
    const errors = [];
    page.on('console', msg => { if (msg.type() === 'error') errors.push(msg.text()); });

    await page.goto(BASE + '/', { waitUntil: 'networkidle' });
    await page.waitForFunction(() => typeof window.renderStepDiagram === 'function', { timeout: 5000 });

    const FID = 'v6-done-null-regression';
    await page.evaluate((fid) => {
      // Overwrite (not guard) so the realistic terminal state is deterministic,
      // and ensure no stale live snapshot exists for this synthetic id.
      uploadedFiles[fid] = {
        id: fid,
        original_name: 'completed_v6_realistic.mp4',
        status: 'done',
        translation_status: null,        // ← real V6 terminal state
        active_kind: 'pipeline_v6',
        uploaded_at: Date.now() / 1000,
      };
      if (window.__cardProgress) delete window.__cardProgress[fid];
      renderQueue();
    }, FID);

    const card = page.locator(`.queue-item[data-file-id="${FID}"]`);
    await expect(card).toBeVisible({ timeout: 3000 });
    await expect(card.locator('.sd-step')).toHaveCount(5);
    // All 5 steps must be marked done (✓), not pending.
    await expect(card.locator('.sd-step.sd-done')).toHaveCount(5);
    await expect(card.locator('.sd-step.sd-pending')).toHaveCount(0);
    expect(errors.filter(e => !e.includes('favicon'))).toHaveLength(0);
  });

  test('Profile file card has 3-step diagram (轉錄/翻譯/校對)', async ({ page }) => {
    const errors = [];
    page.on('console', msg => { if (msg.type() === 'error') errors.push(msg.text()); });

    await page.goto(BASE + '/', { waitUntil: 'networkidle' });
    await page.waitForFunction(() => typeof window.renderStepDiagram === 'function', { timeout: 5000 });

    await page.evaluate((fid) => {
      if (typeof uploadedFiles !== 'undefined' && !uploadedFiles[fid]) {
        uploadedFiles[fid] = {
          id: fid,
          original_name: 'test_profile_file.mp4',
          status: 'done',
          translation_status: 'done',
          active_kind: 'profile',
          uploaded_at: Date.now() / 1000,
        };
      }
      if (typeof renderQueue === 'function') renderQueue();
    }, PROFILE_FILE_ID);

    const card = page.locator(`.queue-item[data-file-id="${PROFILE_FILE_ID}"]`);
    await expect(card).toBeVisible({ timeout: 3000 });

    const diagram = card.locator('.step-diagram');
    await expect(diagram).toBeVisible();

    const steps = card.locator('.sd-step');
    await expect(steps).toHaveCount(3);

    // Verify stage labels for profile kind
    await expect(card).toContainText('轉錄');
    await expect(card).toContainText('翻譯');
    await expect(card).toContainText('校對');

    expect(errors.filter(e => !e.includes('favicon'))).toHaveLength(0);
  });

  test('pipeline_progress event updates file card diagram live', async ({ page }) => {
    const errors = [];
    page.on('console', msg => { if (msg.type() === 'error') errors.push(msg.text()); });

    await page.goto(BASE + '/', { waitUntil: 'networkidle' });
    await page.waitForFunction(() => typeof window.renderStepDiagram === 'function', { timeout: 5000 });

    // Seed V6 file
    await page.evaluate((fid) => {
      if (typeof uploadedFiles !== 'undefined') {
        uploadedFiles[fid] = uploadedFiles[fid] || {
          id: fid,
          original_name: 'live_update_test.mp4',
          status: 'transcribing',
          translation_status: null,
          active_kind: 'pipeline_v6',
          uploaded_at: Date.now() / 1000,
        };
      }
      if (typeof renderQueue === 'function') renderQueue();
    }, V6_FILE_ID);

    const card = page.locator(`.queue-item[data-file-id="${V6_FILE_ID}"]`);
    await expect(card).toBeVisible({ timeout: 3000 });

    // Simulate a pipeline_progress event with stages.
    // Use __setCardProgress test hook (exposed by index.html) to inject into
    // the private cardProgress map, then re-render the card list.
    await page.waitForFunction(() => typeof window.__setCardProgress === 'function', { timeout: 5000 });
    await page.evaluate((fid) => {
      const snap = {
        stages: [
          { key: 'vad', label: 'VAD 切段' },
          { key: 'qwen3', label: 'Qwen3 識別' },
          { key: 'mlx', label: 'mlx 對齊' },
          { key: 'merge', label: '時間合併' },
          { key: 'refiner', label: 'Refiner 校對' },
        ],
        stage_index: 1,
        stage_state: 'active',
        pct: 40,
        stage_label: 'Qwen3 識別中',
      };
      // __setCardProgress writes into the private closure cardProgress map
      window.__setCardProgress(fid, snap);
      // renderQueue is a function declaration → accessible on window in non-strict inline scripts
      if (typeof renderQueue === 'function') renderQueue();
    }, V6_FILE_ID);

    // After the event, the card should show the active step (Qwen3 識別)
    await expect(card.locator('.sd-active')).toBeVisible({ timeout: 2000 });

    expect(errors.filter(e => !e.includes('favicon'))).toHaveLength(0);
  });

  test('queue panel renderStepDiagram path does not throw on cold-start', async ({ page }) => {
    const errors = [];
    page.on('console', msg => { if (msg.type() === 'error') errors.push(msg.text()); });

    await page.goto(BASE + '/', { waitUntil: 'networkidle' });
    await page.waitForFunction(() => typeof window.renderStepDiagram === 'function', { timeout: 5000 });

    // Simulate /api/queue returning a row with stages — calls renderQueueRows directly
    await page.evaluate(() => {
      const fakeJobs = [{
        id: 'fake-job-99',
        file_id: 'fake-file-99',
        file_name: 'fake_test.mp4',
        type: 'asr',
        status: 'running',
        position: 0,
        progress_pct: 30,
        stage_label: 'VAD 切段中',
        stage_state: 'active',
        pipeline_kind: 'pipeline_v6',
        stage_index: 0,
        stages: [
          { key: 'vad', label: 'VAD 切段' },
          { key: 'qwen3', label: 'Qwen3 識別' },
          { key: 'mlx', label: 'mlx 對齊' },
          { key: 'merge', label: '時間合併' },
          { key: 'refiner', label: 'Refiner 校對' },
        ],
        owner_username: 'admin_p3',
      }];
      // renderQueueRows is a function declaration in queue-panel.js → accessible globally
      if (typeof renderQueueRows === 'function') renderQueueRows(fakeJobs);
    });

    // Queue panel should show a step diagram
    const panel = page.locator('#queuePanel');
    await expect(panel.locator('.step-diagram')).toBeVisible({ timeout: 2000 });

    // Must have 5 steps for V6
    const steps = panel.locator('.sd-step');
    await expect(steps).toHaveCount(5);

    expect(errors.filter(e => !e.includes('favicon'))).toHaveLength(0);
  });

  // -------------------------------------------------------------------------
  // Bug #16 regression: stage_index=null + stage_state='done' must NOT mark
  // all steps done (false-all-done).  The null guard in step-diagram.js:8
  // prevents null >= N-1 from evaluating truthy.
  // -------------------------------------------------------------------------
  test('null stage_index with stage_state=done does NOT false-all-done', async ({ page }) => {
    const errors = [];
    page.on('console', msg => { if (msg.type() === 'error') errors.push(msg.text()); });

    await page.goto(BASE + '/', { waitUntil: 'networkidle' });
    await page.waitForFunction(() => typeof window.renderStepDiagram === 'function', { timeout: 5000 });

    const FID = 'null-idx-bug16-regression';

    // Seed a V6 file in uploadedFiles
    await page.evaluate((fid) => {
      uploadedFiles[fid] = {
        id: fid,
        original_name: 'null_idx_test.mp4',
        status: 'transcribing',
        translation_status: null,
        active_kind: 'pipeline_v6',
        uploaded_at: Date.now() / 1000,
      };
      renderQueue();
    }, FID);

    const card = page.locator(`.queue-item[data-file-id="${FID}"]`);
    await expect(card).toBeVisible({ timeout: 3000 });

    // Inject a pipeline_progress snapshot with stage_index=null + stage_state='done'
    // (simulates a backend event where stage_index is omitted/null but state is done)
    await page.waitForFunction(() => typeof window.__setCardProgress === 'function', { timeout: 5000 });
    await page.evaluate((fid) => {
      window.__setCardProgress(fid, {
        stages: [
          { key: 'vad', label: 'VAD 切段' },
          { key: 'qwen3', label: 'Qwen3 識別' },
          { key: 'mlx', label: 'mlx 對齊' },
          { key: 'merge', label: '時間合併' },
          { key: 'refiner', label: 'Refiner 校對' },
        ],
        stage_index: null,   // ← the null that triggered the bug
        stage_state: 'done',
        pct: 100,
        stage_label: '完成',
      });
      renderQueue();
    }, FID);

    await expect(card.locator('.sd-step')).toHaveCount(5);
    // With stage_index=null the guard makes allDone=false, so 0 steps are sd-done
    // (they render as sd-pending since no stageIndex to compare against).
    await expect(card.locator('.sd-step.sd-done')).toHaveCount(0);

    // No console errors
    expect(errors.filter(e => !e.includes('favicon'))).toHaveLength(0);
  });

});
