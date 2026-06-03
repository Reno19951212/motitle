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

  // Inject one output_lang file (2 target languages) + render its card.
  await page.evaluate(() => {
    const FID = '__sync_test__';
    uploadedFiles[FID] = {
      id: FID, original_name: 'sync.mp4', status: 'transcribing', translation_status: null,
      active_kind: 'output_lang',
      languages: [{ role:'first', lang:'yue', label:'口語廣東話' }, { role:'second', lang:'en', label:'英文' }],
    };
    activeFileId = FID; renderQueue(); renderStatusCard();
  });

  // Mock /api/queue to return that file as a running job at 42%.
  await page.route('**/api/queue', route => route.fulfill({
    status: 200, contentType: 'application/json',
    body: JSON.stringify([{
      id: 'job1', file_id: '__sync_test__', type: 'asr', status: 'running',
      progress_pct: 42, stage_label: '轉錄', stage_state: 'active',
      stages: [{key:'asr',label:'轉錄'},{key:'derive',label:'輸出'}], stage_index: 0,
      pipeline_kind: 'output_lang',
    }]),
  }));

  // Drive one poll cycle deterministically.
  await page.evaluate(() => _pollCardProgress());

  // #topProgress now shows live progress (42%) on the per-language bars.
  await expect(page.locator('#topProgress .tp-fill').first()).toHaveAttribute('style', /width:\s*42%/);
  await expect(page.locator('#topProgress .tp-pct').first()).toContainText('42%');
  // The card's status badge synced to the live stage from /api/queue.
  const badge = page.locator('#queueList .queue-item[data-file-id="__sync_test__"] .qh .badge');
  await expect(badge).toContainText('轉錄');
  await expect(badge).toContainText('42%');
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
  await page.evaluate(() => _pollCardProgress());      // next poll: descriptor present → bars render at 60%

  await expect(page.locator('#topProgress .tp-lang')).toHaveCount(2);
  await expect(page.locator('#topProgress .tp-pct').first()).toContainText('60%');
});
