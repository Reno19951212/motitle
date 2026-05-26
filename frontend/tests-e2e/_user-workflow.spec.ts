/**
 * Comprehensive user-workflow spec — exercise the full Console UX as a
 * real user would, from upload through preview. Reports a structured
 * findings table at the end via console.log.
 *
 * Pipeline 'e62b6a58' is pre-seeded (preset_slot=1) but references a
 * bogus asr_profile_id, so pipeline_run will fail at ASR stage. We
 * document the resulting UX (does WorkerStatus show error? does the
 * stage bar flip to err?) as a finding.
 *
 * File under test: ~/Downloads/【#賽馬娛樂新聞】25:26 #26 新見習騎師🏇袁幸堯不日登場🔥 1080p.mp4
 * (265 second video, ~91 MB, mp4 container)
 */
import { test, expect } from '@playwright/test';
import * as os from 'node:os';
import * as path from 'node:path';
import * as fs from 'node:fs';

const FILE_PATH = path.join(
  os.homedir(),
  'Downloads',
  '【#賽馬娛樂新聞】25:26 #26 新見習騎師🏇袁幸堯不日登場🔥 1080p.mp4',
);

type Finding = {
  step: string;
  status: '✓ works' | '✗ broken' | '⚠ partial' | '— skipped';
  detail: string;
};
const findings: Finding[] = [];
function record(step: string, status: Finding['status'], detail: string) {
  findings.push({ step, status, detail });
  console.log(`[WORKFLOW] ${status}  ${step} — ${detail}`);
}

test('comprehensive user workflow', async ({ page }) => {
  test.setTimeout(180_000);  // 3 min — allow ASR start
  // Skip in CI / when fixture is unavailable — this spec exists for
  // local UX validation and requires a specific video + seeded pipeline.
  test.skip(!fs.existsSync(FILE_PATH), `Fixture not at ${FILE_PATH} — manual local-only spec`);

  // ─── Step 1: Login ──────────────────────────────────────────────────
  await test.step('1. Login as admin_p3', async () => {
    await page.goto('/login');
    await page.fill('#username', 'admin_p3');
    await page.fill('#password', 'AdminPass1!');
    await page.click('button:has-text("Log in")');
    try {
      await expect(page).toHaveURL('/', { timeout: 8_000 });
      record('1. Login', '✓ works', 'admin_p3 → redirected to /');
    } catch {
      record('1. Login', '✗ broken', `still on ${page.url()}`);
      throw new Error('login failed, abort');
    }
  });

  // ─── Step 2: Console renders ────────────────────────────────────────
  await test.step('2. /console?console=1 renders 4-column layout', async () => {
    await page.goto('/console?console=1');
    try {
      await expect(page.locator('[data-testid="console-rail"]')).toBeVisible({ timeout: 5_000 });
      await expect(page.locator('[data-testid="console-queue"]')).toBeVisible();
      await expect(page.locator('[data-testid="console-workbench"]')).toBeVisible();
      await expect(page.locator('[data-testid="console-aside"]')).toBeVisible();
      record('2. Console layout', '✓ works', '4 columns visible (rail/queue/workbench/aside)');
    } catch (e) {
      record('2. Console layout', '✗ broken', String(e).slice(0, 200));
      throw e;
    }
  });

  // ─── Step 3: Pipeline preset ⌘1 ────────────────────────────────────
  await test.step('3. Preset pill ⌘1 shows seeded pipeline', async () => {
    const pill1 = page.locator('[data-testid="preset-pill-1"]');
    const text = (await pill1.textContent()) ?? '';
    if (text.includes('未設定')) {
      record('3. Preset ⌘1', '⚠ partial', 'pill shows "未設定" — pipelines store not populated');
    } else if (/賽馬|mlx|test/.test(text)) {
      record('3. Preset ⌘1', '✓ works', `pill text: "${text.trim()}"`);
    } else {
      record('3. Preset ⌘1', '⚠ partial', `unexpected pill text: "${text.trim()}"`);
    }
  });

  // ─── Step 4: ⌘1 hotkey selects ──────────────────────────────────────
  await test.step('4. ⌘1 hotkey switches active pipeline', async () => {
    await page.keyboard.press('Control+1');
    await page.waitForTimeout(300);
    const pill1Active = await page.locator('[data-testid="preset-pill-1"]').getAttribute('data-active');
    if (pill1Active === 'true') {
      record('4. ⌘1 hotkey', '✓ works', 'preset-pill-1 data-active=true after Ctrl+1');
    } else {
      record('4. ⌘1 hotkey', '✗ broken', `data-active="${pill1Active}" (expected "true")`);
    }
  });

  // ─── Step 5: File picker upload ─────────────────────────────────────
  let queueItemCount = 0;
  await test.step('5. Upload file via drop zone file input', async () => {
    if (!fs.existsSync(FILE_PATH)) {
      record('5. Upload file', '— skipped', `file not found at ${FILE_PATH}`);
      return;
    }

    // Capture network for the upload request
    const reqs: Array<{ url: string; status: number; body: string }> = [];
    page.on('response', async (resp) => {
      const url = resp.url();
      if (url.includes('/api/transcribe') || url.includes('/api/files/upload')) {
        let body = '';
        try { body = (await resp.text()).slice(0, 200); } catch {}
        reqs.push({ url, status: resp.status(), body });
      }
    });

    const dropInput = page.locator('[data-testid="console-drop"] input[type="file"]');
    await dropInput.setInputFiles(FILE_PATH);

    // Wait for either a request to fire OR queue count to grow
    const before = await page.locator('[data-testid^="queue-item-"]').count();
    try {
      await expect.poll(
        async () => {
          const count = await page.locator('[data-testid^="queue-item-"]').count();
          return count > before || reqs.length > 0;
        },
        { timeout: 10_000 }
      ).toBeTruthy();
    } catch {}

    await page.waitForTimeout(2000);
    queueItemCount = await page.locator('[data-testid^="queue-item-"]').count();

    if (queueItemCount > before) {
      record('5. Upload file', '✓ works', `queue grew ${before}→${queueItemCount}. Requests: ${JSON.stringify(reqs.map(r => `${r.status} ${r.url.split('/').pop()}`))}`);
    } else if (reqs.length > 0) {
      record('5. Upload file', '✗ broken', `upload request fired but queue did not grow. Reqs: ${reqs.map(r => `[${r.status}] ${r.body}`).join(' | ')}`);
    } else {
      record('5. Upload file', '✗ broken', `no /api/transcribe or /api/files/upload request fired after setInputFiles — react-dropzone may have rejected the file (accept filter / size)`);
    }
  });

  // ─── Step 6: New queue item shows correct meta ──────────────────────
  let newFileId: string | null = null;
  await test.step('6. New queue item has duration + size + filename', async () => {
    if (queueItemCount === 0) {
      record('6. Queue item meta', '— skipped', 'no queue items present');
      return;
    }
    const firstItem = page.locator('[data-testid^="queue-item-"]').first();
    const testid = await firstItem.getAttribute('data-testid');
    newFileId = testid?.replace('queue-item-', '') ?? null;

    const nameEl = firstItem.locator('.nm');
    const metaEl = firstItem.locator('.con-q-meta');
    const nameText = (await nameEl.textContent()) ?? '';
    const metaText = (await metaEl.textContent()) ?? '';

    const hasName = /賽馬|袁幸堯|1080p/.test(nameText);
    const hasMmSs = /\d+:\d{2}/.test(metaText);
    const hasMB = /MB|GB/.test(metaText);

    if (hasName && hasMmSs && hasMB) {
      record('6. Queue meta', '✓ works', `name="${nameText.slice(0, 30)}" meta="${metaText.trim()}"`);
    } else {
      record('6. Queue meta', '⚠ partial', `name=${hasName} duration=${hasMmSs} size=${hasMB} text="${metaText.trim()}"`);
    }
  });

  // ─── Step 7: 4-segment stage bar shape ──────────────────────────────
  await test.step('7. Stage bar has exactly 4 cells', async () => {
    if (!newFileId) {
      record('7. Stage bar', '— skipped', 'no file');
      return;
    }
    const cells = page.locator(`[data-testid="queue-item-${newFileId}"] [data-testid="queue-stage-bar"] i`);
    const count = await cells.count();
    if (count === 4) {
      record('7. Stage bar', '✓ works', `4 cells render correctly`);
    } else {
      record('7. Stage bar', '✗ broken', `found ${count} cells (expected 4)`);
    }
  });

  // ─── Step 8: Click queue item → workbench updates ───────────────────
  await test.step('8. Click queue item → video + transcript update', async () => {
    if (!newFileId) {
      record('8. Click selects', '— skipped', 'no file');
      return;
    }
    await page.locator(`[data-testid="queue-item-${newFileId}"]`).click();
    await page.waitForTimeout(500);

    const videoEl = page.locator('[data-testid="video-element"]');
    const count = await videoEl.count();
    if (count === 0) {
      record('8. Video preview', '✗ broken', 'video-element NOT in DOM (selectedFile probably null)');
    } else {
      const src = (await videoEl.getAttribute('src')) ?? '';
      const box = await videoEl.boundingBox();
      const valid = src.includes('/api/files/') && src.includes('/media');
      // ≥100×100 hard threshold — previously the layout collapsed video to
      // 0×N even with valid src + readyState=4, because .con-bottom flex-shrink:0
      // grew to transcript scrollHeight and squeezed .con-video to 0. The fix
      // (grid-template-rows 1fr auto minmax(0,40vh) on .con-stage) prevents
      // regression. If height ever drops back under 100px, fail loudly.
      const sized = box && box.width > 100 && box.height > 100;
      if (valid && sized) {
        record('8. Video preview', '✓ works', `<video src="${src.split('/').slice(-3).join('/')}" ${Math.round(box!.width)}x${Math.round(box!.height)}>`);
      } else if (valid && box) {
        record('8. Video preview', '✗ broken', `layout collapse — box=${JSON.stringify(box)} (regression in .con-stage grid)`);
        throw new Error(`Video element in DOM with src ${src} but layout collapsed to ${box.width}x${box.height}. Check .con-stage grid-template-rows + .con-bottom min-height/overflow.`);
      } else {
        record('8. Video preview', '⚠ partial', `video in DOM but src="${src}"`);
      }

      // ─── 8b: Broadcast-grade subtitle overlay (Option C wire) ──────────
      // Seek into the first segment so an active translation is picked.
      // /api/files/<id>/translations is the data source — if the file
      // hasn't been transcribed yet this step gracefully degrades to skip.
      const transResp = await page.request.get(`/api/files/${newFileId}/translations`);
      if (transResp.ok()) {
        const raw = await transResp.json();
        const trans: Array<{ start?: number; end?: number; zh_text?: string; en_text?: string }> =
          Array.isArray(raw) ? raw : (raw?.translations ?? []);
        const first = trans.find((t) => Number.isFinite(t.start) && Number.isFinite(t.end));
        if (first && first.start !== undefined && first.end !== undefined) {
          const mid = (first.start + first.end) / 2;
          await videoEl.evaluate((v, t) => {
            (v as HTMLVideoElement).currentTime = t as number;
            v.dispatchEvent(new Event('timeupdate'));
          }, mid);
          await page.waitForTimeout(500);
          const overlay = page.locator('[data-testid="subtitle-overlay"]');
          const overlayCount = await overlay.count();
          if (overlayCount > 0) {
            const tspanText = await overlay.locator('tspan').allTextContents();
            const joined = tspanText.join(' ').trim();
            if (joined.length > 0) {
              record('8b. Subtitle overlay', '✓ works', `tspan="${joined.slice(0, 40)}" at t=${mid.toFixed(1)}s`);
            } else {
              record('8b. Subtitle overlay', '⚠ partial', `overlay in DOM but tspans empty`);
            }
          } else {
            record('8b. Subtitle overlay', '✗ broken', `no [data-testid="subtitle-overlay"] in DOM (Workbench wire missing?)`);
            throw new Error('Subtitle overlay not rendered — check VideoPanel.tsx + Workbench.tsx wire to useFileTranslations + useFilePipeline.');
          }
        } else {
          record('8b. Subtitle overlay', '— skipped', 'no segments with start/end');
        }
      } else {
        record('8b. Subtitle overlay', '— skipped', `translations fetch ${transResp.status()}`);
      }
    }
  });

  // ─── Step 9: FileFactsBlock duration ────────────────────────────────
  await test.step('9. Right aside FileFactsBlock shows duration', async () => {
    if (!newFileId) {
      record('9. Facts duration', '— skipped', 'no file');
      return;
    }
    const facts = page.locator('[data-testid="aside-facts"]');
    const durRow = facts.locator('.con-fact', { hasText: '時長' }).locator('.v');
    const durText = (await durRow.textContent()) ?? '';
    if (/\d+:\d{2}/.test(durText)) {
      record('9. Facts duration', '✓ works', `時長 = ${durText.trim()}`);
    } else {
      record('9. Facts duration', '✗ broken', `時長 = "${durText.trim()}" (expected mm:ss)`);
    }
  });

  // ─── Step 10: TransportBar totalTime ────────────────────────────────
  await test.step('10. TransportBar shows total time', async () => {
    if (!newFileId) {
      record('10. Transport time', '— skipped', 'no file');
      return;
    }
    const tc = page.locator('[data-testid="transport-bar"] .tc');
    const tcText = (await tc.textContent()) ?? '';
    if (/\/ \d+:\d{2}/.test(tcText)) {
      record('10. Transport time', '✓ works', `transport tc = "${tcText.trim()}"`);
    } else {
      record('10. Transport time', '✗ broken', `transport tc = "${tcText.trim()}"`);
    }
  });

  // ─── Step 11: WorkerStatus shows processing or failed ──────────────
  await test.step('11. WorkerStatus reflects pipeline activity', async () => {
    if (!newFileId) {
      record('11. WorkerStatus', '— skipped', 'no file');
      return;
    }
    // Pipeline was seeded with bogus asr_profile_id → expect failure within 10s
    await page.waitForTimeout(8000);
    const worker = page.locator('[data-testid="worker-status"]');
    const text = (await worker.textContent()) ?? '';
    const hasActive = /處理中|進行/.test(text) && /[1-9]\d* 進行/.test(text);
    const hasQueued = /待處理.*[1-9]/.test(text);
    const hasError = /重試|錯誤|fail/i.test(text);
    const isEmpty = /沒有處理中/.test(text);

    if (hasActive) {
      record('11. WorkerStatus', '✓ works', `shows active processing: "${text.replace(/\s+/g, ' ').slice(0, 80)}"`);
    } else if (hasError) {
      record('11. WorkerStatus', '⚠ partial', `shows error state (expected for bogus pipeline)`);
    } else if (hasQueued) {
      record('11. WorkerStatus', '✓ works', `shows queued`);
    } else if (isEmpty) {
      record('11. WorkerStatus', '⚠ partial', `shows empty — job may have failed silently or finished too fast`);
    } else {
      record('11. WorkerStatus', '⚠ partial', `state unclear: "${text.replace(/\s+/g, ' ').slice(0, 100)}"`);
    }
  });

  // ─── Step 12: Stage bar update after time ──────────────────────────
  await test.step('12. Stage bar shows queued/starting/warn (not idle) shortly after enqueue', async () => {
    if (!newFileId) {
      record('12. Stage bar update', '— skipped', 'no file');
      return;
    }
    const cells = page.locator(`[data-testid="queue-item-${newFileId}"] [data-testid="queue-stage-bar"] i`);

    // Within 5 seconds, the first cell should be NOT idle (queued, starting, or warn).
    // Allows for pipeline_stage_start latency.
    await expect.poll(
      async () => {
        const cls = await cells.nth(0).getAttribute('class');
        return cls ?? '';
      },
      { timeout: 5_000 }
    ).not.toMatch(/^idle$/);

    const cls = await cells.nth(0).getAttribute('class');
    if (cls === 'queued' || cls === 'starting' || cls === 'warn') {
      record('12. Stage bar update', '✓ works', `cell 0 class="${cls}" within 5s of enqueue`);
    } else if (cls === 'err') {
      record('12. Stage bar update', '⚠ partial', `cell 0 went to err (pipeline failed)`);
    } else if (cls === 'done') {
      record('12. Stage bar update', '✓ works', `cell 0 went to done (pipeline was fast)`);
    } else {
      record('12. Stage bar update', '✗ broken', `unexpected cell 0 class: "${cls}"`);
    }
  });

  // ─── Step 13: ⌘K modal ────────────────────────────────────────────
  await test.step('13. ⌘K opens global search modal', async () => {
    await page.keyboard.press('Control+K');
    try {
      await page.locator('[data-testid="global-search-modal"]').waitFor({ state: 'visible', timeout: 3000 });
      record('13. ⌘K modal', '✓ works', 'modal opens');
      await page.keyboard.press('Escape');
      await page.locator('[data-testid="global-search-modal"]').waitFor({ state: 'detached', timeout: 3000 });
    } catch {
      record('13. ⌘K modal', '✗ broken', 'modal did not appear within 3s');
    }
  });

  // ─── Step 14: Space key on video ───────────────────────────────────
  await test.step('14. Space toggles real video play/pause', async () => {
    if (!newFileId) {
      record('14. Space play', '— skipped', 'no file');
      return;
    }
    // Ensure focus is on the page root, not on inputs (useHotkeys filter).
    // page.mouse.click on a safe coordinate avoids the body-outside-viewport error.
    await page.mouse.click(100, 100);
    await page.waitForTimeout(200);

    const videoEl = page.locator('[data-testid="video-element"]');
    const beforePaused = await videoEl.evaluate((v: HTMLVideoElement) => v.paused).catch(() => null);

    await page.keyboard.press('Space');
    // play() is async — give the browser a moment to flip paused state
    await page.waitForTimeout(500);

    const afterPaused = await videoEl.evaluate((v: HTMLVideoElement) => v.paused).catch(() => null);

    if (beforePaused === true && afterPaused === false) {
      record('14. Space play', '✓ works', 'video.paused: true → false after Space');
    } else if (beforePaused === null) {
      record('14. Space play', '— skipped', 'video element not found');
    } else {
      record('14. Space play', '✗ broken', `video.paused before=${beforePaused} after=${afterPaused} (expected true→false)`);
    }
  });

  // ─── Step 15: Render cell (known limitation: always idle) ──────────
  await test.step('15. Render cell (4th stage cell) — MVP limitation', async () => {
    if (!newFileId) {
      record('15. Render cell', '— skipped', 'no file');
      return;
    }
    const cells = page.locator(`[data-testid="queue-item-${newFileId}"] [data-testid="queue-stage-bar"] i`);
    const renderCellClass = await cells.nth(3).getAttribute('class');
    if (renderCellClass === 'idle') {
      record('15. Render cell', '⚠ partial', 'always idle (MVP: render does not emit socket events, only file.status reflects state)');
    } else {
      record('15. Render cell', '✓ works', `render cell class="${renderCellClass}"`);
    }
  });

  // ─── Step 16: Open proofread link (known: missing) ─────────────────
  await test.step('16. "Open in Proofread" link/button on queue item', async () => {
    if (!newFileId) {
      record('16. Proofread link', '— skipped', 'no file');
      return;
    }
    const item = page.locator(`[data-testid="queue-item-${newFileId}"]`);
    const hasProofreadLink = await item
      .locator('a[href*="/proofread/"], button:has-text("校對"), button:has-text("proofread")')
      .count();
    if (hasProofreadLink > 0) {
      record('16. Proofread link', '✓ works', `found ${hasProofreadLink} link/button`);
    } else {
      record('16. Proofread link', '✗ broken', 'no proofread link on queue item (must type URL manually)');
    }
  });

  // ─── Final report ────────────────────────────────────────────────
  console.log('\n\n=================================================================');
  console.log('USER WORKFLOW EXPERIENCE FINDINGS');
  console.log('=================================================================\n');

  const counts = { works: 0, broken: 0, partial: 0, skipped: 0 };
  for (const f of findings) {
    if (f.status.includes('works')) counts.works++;
    else if (f.status.includes('broken')) counts.broken++;
    else if (f.status.includes('partial')) counts.partial++;
    else counts.skipped++;
    console.log(`${f.status}  ${f.step.padEnd(40)} ${f.detail}`);
  }
  console.log(`\nSummary: ${counts.works} works · ${counts.partial} partial · ${counts.broken} broken · ${counts.skipped} skipped`);
});
