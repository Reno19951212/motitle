// ============================================================
// AI 助手聊天窗 E2E（proofread 頁）— 開窗 → 送訊息 → 批量預覽卡片 →
// 套用選中 → 逐行 ✓ + 段落表文字更新 → 還原 → 文字回復。
//
// 決定性設計（零真 LLM）：
//   - 只 mock POST /ai-chat/parse（page.route）。mock payload 嘅 proposal
//     一定要同 registry 現值 byte-exact — 所以測試先用 request API 打真
//     /ai-chat/expand，攞佢嘅 proposal 塞入 mock parse 回應。
//   - /ai-chat/expand、/ai-chat/apply 同其他所有 endpoint 全部行真後端。
//
// ⚠️ 呢個 spec 需要一個載有 ai-chat routes 嘅 live backend（ai-chat-window
//    branch 或已合併之後嘅 code）。對住無 ai-chat routes 嘅舊後端會直接
//    fail（expand 404）。亦需要 registry 有一個 output_lang 檔（見下面
//    boot recipe）。
//
// Boot recipe（同 .superpowers/sdd/task-12-report.md 一致）：
//   1. Seed backend/data/registry.json 一個 synthetic output_lang entry
//      （id 預設 e2e-aichat-1，可用 env AI_CHAT_FILE_ID 覆寫）：
//      zh+en 兩軌、2 cues（"今朝有晨操。" pending ／"晨操之後休息。"
//      approved）、by_lang + {lang}_text mirror + aligned_bilingual +
//      content_asr_segments，加 list-route 必需欄位 original_name/
//      stored_name/status:"done"/translation_status:"done"/size/
//      uploaded_at/glossary_ids:[]/glossary_llm:true/mt_style。
//   2. 用 scratch launcher boot（R5_AUTH_BYPASS / R5_LICENSE_BYPASS 係
//      Flask config flags，唔係 env vars）：import app、set
//      LOGIN_DISABLED/R5_AUTH_BYPASS/R5_LICENSE_BYPASS = True、
//      _load_registry() + _start_registry_flusher()、
//      socketio.run(host=127.0.0.1, port=5003)。Env：
//      FLASK_SECRET_KEY=test-secret R5_HTTPS=0。
//      （唔好用 5001 — 用戶 live backend；5002 可能有另一 session 嘅
//        stale listener。）
//   3. 行測試（scratch config 只需 testDir 指返呢個 tests/ 目錄 +
//      timeout 30s，唔要 repo config 嘅 globalSetup/storageState —
//      bypass 後端唔使 login）：
//      cd frontend && BASE_URL=http://localhost:5003 \
//        npx playwright test tests/test_ai_chat_window.spec.js \
//        --config=/path/to/scratch.config.js
//
// 冪等：測試開頭有 reset prologue（真 expand+apply 早操→晨操），
// 所以上次跑一半留低嘅 dirty state 會被還原。
// ============================================================
const { test, expect, request } = require('@playwright/test');

const BASE = process.env.BASE_URL || 'http://localhost:5003';
const FID = process.env.AI_CHAT_FILE_ID || 'e2e-aichat-1';
const OPS = [{ op: 'replace_term', from: '晨操', to: '早操', langs: 'all' }];

async function expandOps(api, ops) {
  const r = await api.post(`/api/files/${FID}/ai-chat/expand`, { data: { ops } });
  expect(r.ok(), `expand 失敗（HTTP ${r.status()}）— 後端有冇 ai-chat routes？檔案 ${FID} 有冇 seed？`).toBeTruthy();
  return r.json();
}

async function applyItems(api, items) {
  const r = await api.post(`/api/files/${FID}/ai-chat/apply`, {
    data: { items: items.map(it => ({ idx: it.idx, lang: it.lang, after: it.after,
                                      expected_text: it.expected_text,
                                      start: it.start, end: it.end })) },
  });
  expect(r.ok()).toBeTruthy();
  return r.json();
}

async function getTranslations(api) {
  const r = await api.get(`/api/files/${FID}/translations`);
  expect(r.ok()).toBeTruthy();
  return (await r.json()).translations;
}

test('AI 助手：開窗 → 批量預覽 → 套用選中 → 還原', async ({ page }) => {
  const api = await request.newContext({ baseURL: BASE });

  // ---- Reset prologue（冪等）：上次 run 留低嘅「早操」全部還原做「晨操」 ----
  const dirty = await expandOps(api, [{ op: 'replace_term', from: '早操', to: '晨操', langs: 'all' }]);
  if (dirty.proposal.items.length) await applyItems(api, dirty.proposal.items);

  // ---- 真 expand 攞 proposal（同 registry 現值一致 — apply 嘅衝突檢查先會過）----
  const expanded = await expandOps(api, OPS);
  expect(expanded.proposal.items.length).toBe(2);
  expect(expanded.proposal.totals).toEqual({ matched: 2, approved: 1 });
  expect(expanded.grid_len).toBe(2);

  // ---- 只 mock /ai-chat/parse — proposal 用真 expand 嘅（apply 係真）----
  const parsed = {
    reply: '明白，全部「晨操」改做「早操」。',
    ops: expanded.ops,
    proposal: expanded.proposal,
    rerun_active: false,
    render_active: false,
    grid_len: expanded.grid_len,
  };
  let parseCalls = 0;
  await page.route('**/ai-chat/parse', route => {
    parseCalls += 1;
    return route.fulfill({ status: 200, contentType: 'application/json',
                           body: JSON.stringify(parsed) });
  });

  // ---- 開 proofread 頁（file_id URL param）----
  await page.goto(`${BASE}/proofread.html?file_id=${FID}`);
  const rail = page.locator('.rv-b-rail-item');
  await expect(rail).toHaveCount(2);
  await expect(rail.nth(0).locator('.rv-b-rail-text-1')).toContainText('晨操');

  // ---- 開 AI 助手窗 ----
  await page.click('#aiChatBtn');
  await expect(page.locator('#acPop')).toBeVisible();

  // ---- 送訊息 → 批量預覽卡片 ----
  await page.fill('#acInput', '把所有「晨操」改成「早操」');
  await page.click('#acSend');
  const card = page.locator('.ac-card');
  await expect(card).toBeVisible();
  expect(parseCalls).toBe(1);
  await expect(card.locator('.ac-row')).toHaveCount(2);
  await expect(card.locator('.ac-row').nth(0).locator('.diff ins')).toContainText('今朝有早操。');
  // 已批核行（idx 1）預設唔剔 → 淨係 1 項會套用
  await expect(card.locator('.ac-row').nth(1).locator('.ap')).toHaveText('已批核');
  await expect(card.locator('input[data-ck]').nth(0)).toBeChecked();
  await expect(card.locator('input[data-ck]').nth(1)).not.toBeChecked();
  const applyBtn = card.locator('[data-apply]');
  await expect(applyBtn).toHaveText('套用選中 (1)');

  // ---- 套用選中（真 /ai-chat/apply）→ 逐行 ✓ + toast + 段落表更新 ----
  await applyBtn.click();
  await expect(page.locator('#toastStack')).toContainText('已套用 1 項');
  await expect(card.locator('.ac-row').nth(0).locator('.st .ok')).toHaveText('✓');
  await expect(card.locator('[data-un]')).toHaveCount(1);
  // p.refresh() 重載 translations → rail row 0 文字已更新
  await expect(rail.nth(0).locator('.rv-b-rail-text-1')).toContainText('早操');

  // ---- API 驗證：三庫寫入 + 「AI 助手」審計 + 批核狀態唔郁 ----
  let rows = await getTranslations(api);
  expect(rows[0].zh_text).toBe('今朝有早操。');
  expect(rows[0].by_lang.zh.text).toBe('今朝有早操。');
  expect(rows[0].status).toBe('pending');   // 無剔「套用後批核」→ keep status
  expect(rows[0].glossary_changes.some(
    c => c.source === 'AI 助手' && c.after === '今朝有早操。')).toBeTruthy();
  expect(rows[1].zh_text).toBe('晨操之後休息。');   // 已批核行冇被掂
  expect(rows[1].status).toBe('approved');

  // ---- 還原（真 apply，expected_text=已套用文字、status 一齊還原）----
  await card.locator('[data-un]').click();
  await expect(page.locator('#toastStack')).toContainText('已還原');
  await expect(card.locator('.ac-row .st .ok')).toHaveCount(0);
  await expect(rail.nth(0).locator('.rv-b-rail-text-1')).toContainText('晨操');

  rows = await getTranslations(api);
  expect(rows[0].zh_text).toBe('今朝有晨操。');
  expect(rows[0].by_lang.zh.text).toBe('今朝有晨操。');
  expect(rows[0].status).toBe('pending');

  await api.dispose();
});
