// Dashboard file-list status + #topProgress sync live from /api/queue (like the queue panel),
// not relying on the unreliable file_updated socket.
const { test, expect } = require('@playwright/test');
const BASE = process.env.BASE_URL || 'http://localhost:5001';
const PASS = process.env.PROBE_PASS || 'TestPass1!';
test.use({ storageState: undefined });

test('poll-driven: #topProgress + card badge update live from an active /api/queue row', async ({ page }) => {
  await page.goto(`${BASE}/login.html`);
  await page.fill('#loginUsername','admin_p3'); await page.fill('#loginPassword',PASS);
  await page.click('#loginSubmit'); await page.waitForURL(`${BASE}/`);
  await page.waitForFunction(() => typeof _pollCardProgress === 'function' && typeof renderQueue === 'function', { timeout: 10000 });

  // Inject a TRANSLATING output_lang file (non-transcribing → backend pct drives the bars;
  // transcribing uses the separate time-estimate, covered by the estimate test below).
  await page.evaluate(() => {
    const FID = '__sync_test__';
    uploadedFiles[FID] = {
      id: FID, original_name: 'sync.mp4', status: 'done', translation_status: 'translating',
      active_kind: 'output_lang',
      languages: [{ role:'first', lang:'yue', label:'口語廣東話' }, { role:'second', lang:'en', label:'英文' }],
    };
    activeFileId = FID; renderQueue(); renderStatusCard();
  });

  await page.route('**/api/queue', route => route.fulfill({
    status: 200, contentType: 'application/json',
    body: JSON.stringify([{
      id: 'job1', file_id: '__sync_test__', type: 'translate', status: 'running',
      progress_pct: 42, stage_label: '翻譯', stage_state: 'active',
      stages: [{key:'asr',label:'轉錄'},{key:'mt',label:'翻譯'}], stage_index: 1,
      pipeline_kind: 'output_lang',
    }]),
  }));

  await page.evaluate(() => _pollCardProgress());

  // #topProgress shows the backend pct (42%) on the per-language bars.
  await expect(page.locator('#topProgress .tp-fill').first()).toHaveAttribute('style', /width:\s*42%/);
  await expect(page.locator('#topProgress .tp-pct').first()).toContainText('42%');
  // The card badge synced to the live stage from /api/queue.
  const badge = page.locator('#queueList .queue-item[data-file-id="__sync_test__"] .qh .badge');
  await expect(badge).toContainText('翻譯');
  await expect(badge).toContainText('42%');
});

test('transcribing file → #topProgress advances via the time-estimate (mlx gives no real pct)', async ({ page }) => {
  await page.goto(`${BASE}/login.html`);
  await page.fill('#loginUsername','admin_p3'); await page.fill('#loginPassword',PASS);
  await page.click('#loginSubmit'); await page.waitForURL(`${BASE}/`);
  await page.waitForFunction(() => typeof _applyTranscribeEstimate === 'function', { timeout: 10000 });
  const pct = await page.evaluate(() => {
    const FID = '__est_test__';
    uploadedFiles[FID] = { id: FID, original_name: 'e.mp4', status: 'transcribing', active_kind: 'output_lang',
      languages: [{ role:'first', lang:'yue', label:'口語廣東話' }] };
    activeFileId = FID;
    _asrStartAt[FID] = Date.now() - 20000;   // pretend 20s elapsed (mlx reports 0%)
    _applyTranscribeEstimate(FID); renderStatusCard();
    return parseInt(document.querySelector('#topProgress .tp-pct').textContent, 10);
  });
  // 20s @ T=45s → ~34% — non-zero (moving) and capped well under 100.
  expect(pct).toBeGreaterThan(5);
  expect(pct).toBeLessThan(95);
});

test('poll loads missing languages descriptor → #topProgress shows bars for in-flight upload', async ({ page }) => {
  await page.goto(`${BASE}/login.html`);
  await page.fill('#loginUsername','admin_p3'); await page.fill('#loginPassword',PASS);
  await page.click('#loginSubmit'); await page.waitForURL(`${BASE}/`);
  await page.waitForFunction(() => typeof _pollCardProgress === 'function', { timeout: 10000 });

  // A just-uploaded file: present in uploadedFiles but WITHOUT a languages descriptor yet.
  await page.evaluate(() => {
    uploadedFiles['__desc_test__'] = { id:'__desc_test__', original_name:'d.mp4', status:'transcribing', active_kind:'output_lang' };
    activeFileId = '__desc_test__'; renderQueue();
  });
  // queue has an active job for it (no languages in the row)…
  await page.route('**/api/queue', r => r.fulfill({ status:200, contentType:'application/json',
    body: JSON.stringify([{ id:'j', file_id:'__desc_test__', status:'running', progress_pct:60, stage_label:'轉錄', stage_state:'active', stages:[{key:'a',label:'轉錄'}], stage_index:0 }]) }));
  // …and /api/files supplies the descriptor (as the backend would).
  await page.route('**/api/files', r => r.fulfill({ status:200, contentType:'application/json',
    body: JSON.stringify({ files: [{ id:'__desc_test__', original_name:'d.mp4', status:'transcribing', active_kind:'output_lang', languages:[{role:'first',lang:'zh',label:'中文書面語'},{role:'second',lang:'en',label:'英文'}] }] }) }));

  await page.evaluate(() => _pollCardProgress());      // poll: detects missing descriptor → fetches /api/files
  await page.evaluate(() => _pollCardProgress());      // next poll: descriptor present → 2 bars render

  // Descriptor loaded → the topbar shows BOTH target-language bars (the key fix). The pct
  // itself is the transcribe time-estimate (mlx has no real pct), so just assert it's shown.
  await expect(page.locator('#topProgress .tp-lang')).toHaveCount(2);
  await expect(page.locator('#topProgress .tp-pct').first()).toContainText('%');
});
