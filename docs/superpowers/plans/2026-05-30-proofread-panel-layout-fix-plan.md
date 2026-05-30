# Proofread 面板錯位修復 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 從 `frontend/proofread.html` 完全移除「自訂 Prompt」面板，令剩餘嘅「詞彙表」+「字幕設定」兩個 panel 回復正常並排比例同高度，消除 MacBook 14" 上嘅錯位。

**Architecture:** 純前端改動。`.rv-b-vid-panels` 係一個 2 欄固定高度 grid，原本為 2 個 panel 設計，被誤塞入第 3 個 child（`#promptPanel`）後產生 implicit 第 2 行，壓扁頂部兩 panel。移除第 3 個 child（HTML + CSS + JS 一齊刪）後，grid 自然回復單行 2 欄、兩 panel 各佔全高。Backend 零改動，per-file `prompt_overrides` 資料模型同 API 完全保留。

**Tech Stack:** Vanilla HTML/CSS/JS（無 build step）、Playwright（E2E）。後端 Flask 已喺 venv 運行於 `http://localhost:5001`。

**Spec:** [docs/superpowers/specs/2026-05-30-proofread-panel-layout-fix-design.md](../specs/2026-05-30-proofread-panel-layout-fix-design.md)

---

## 前置條件

- Backend 已喺 venv 運行於 `http://localhost:5001`（已啟動）。若未起：
  ```bash
  cd "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai/backend"
  source venv/bin/activate && set -a && source .env && set +a
  nohup python app.py > /tmp/backend.log 2>&1 &
  sleep 5 && curl -sf http://localhost:5001/api/health | head -c 60
  ```
- Registry 至少有 1 個檔案（已確認有 2 個 V6 檔：`601db8e1e240`、`e047eafc35d4`）。
- Playwright 從 `frontend/` 目錄跑：`cd frontend && BASE_URL=http://localhost:5001 npx playwright test <spec> --reporter=line`
- 登入：`admin_p3` / `AdminPass1!`（若啱啱跑過 pytest 要先 reset 密碼，見 spec / handoff）。

## File Structure

| 檔案 | 責任 | 動作 |
|---|---|---|
| `frontend/proofread.html` | Proofread 編輯器（單檔 HTML+CSS+JS） | **Modify** — 刪 #promptPanel HTML + .rv-b-prompt-* CSS + prompt JS |
| `frontend/tests/test_proofread_layout.spec.js` | 版面回歸測試（panel 移除 + 兩 panel 尺寸） | **Create** |
| `frontend/tests/test_prompt_panel.spec.js` | 舊：proofread 自訂 Prompt panel E2E | **Delete**（測已移除功能） |
| `frontend/tests/test_v6_pipeline_strip.spec.js` | dashboard pipeline strip + proofread V6 prompt | **Modify** — 刪 Test 6 + Test 7（proofread-coupled），保留 Test 1–5（dashboard strip） |
| `CLAUDE.md` | 開發參考 | **Modify** — 加一段移除記錄 |
| `README.md` | 用戶文檔（繁中） | **Modify** — 一句移除說明（若有對應段落） |

---

## Task 1: 寫版面回歸測試（RED）

**Files:**
- Create: `frontend/tests/test_proofread_layout.spec.js`

- [ ] **Step 1: 建立測試檔**

```js
// E2E regression for the proofread panel layout fix (2026-05-30).
// Guards: (1) 自訂 Prompt panel fully removed; (2) 詞彙表 + 字幕設定 share one
// row at proper height (not crushed to ~88px by a stray 3rd grid child).
const { test, expect } = require('@playwright/test');

const BASE = process.env.BASE_URL || 'http://localhost:5001';
const USER = process.env.PROBE_USER || 'admin_p3';
const PASS = process.env.PROBE_PASS || 'AdminPass1!';

test.use({ storageState: undefined });

test.describe('proofread panel layout', () => {
  test.beforeEach(async ({ page }) => {
    const r = await page.request.post(BASE + '/login', { data: { username: USER, password: PASS } });
    if (!r.ok()) throw new Error(`Login failed: ${r.status()}`);
  });

  async function openProofread(page) {
    const filesR = await page.request.get(BASE + '/api/files');
    const files = (await filesR.json()).files || [];
    test.skip(files.length === 0, 'No files in registry — upload one first');
    const fid = files[0].id;
    await page.setViewportSize({ width: 1512, height: 900 }); // MacBook 14"
    await page.goto(`${BASE}/proofread.html?file_id=${fid}`);
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(1500);
    return fid;
  }

  test('自訂 Prompt panel is fully removed', async ({ page }) => {
    await openProofread(page);
    await expect(page.locator('#promptPanel')).toHaveCount(0);
    await expect(page.locator('#promptTemplate')).toHaveCount(0);
    await expect(page.locator('#promptCommitBtn')).toHaveCount(0);
  });

  test('詞彙表 + 字幕設定 fill one row at proper height', async ({ page }) => {
    await openProofread(page);
    const glo = await page.locator('#glossaryPanel').boundingBox();
    const sub = await page.locator('#subtitleSettingsPanel').boundingBox();
    expect(glo).not.toBeNull();
    expect(sub).not.toBeNull();
    // Not crushed (pre-fix both were ~88px)
    expect(glo.height).toBeGreaterThan(180);
    expect(sub.height).toBeGreaterThan(180);
    // Same row → equal height + same top
    expect(Math.abs(glo.height - sub.height)).toBeLessThan(24);
    expect(Math.abs(glo.y - sub.y)).toBeLessThan(8);
    // Two columns side by side
    expect(sub.x).toBeGreaterThan(glo.x);
  });
});
```

- [ ] **Step 2: 跑測試確認 RED**

Run: `cd frontend && BASE_URL=http://localhost:5001 npx playwright test tests/test_proofread_layout.spec.js --reporter=line`
Expected: **2 FAIL** —
- `自訂 Prompt panel is fully removed` → fail（`#promptPanel` count = 1）
- `fill one row at proper height` → fail（`glo.height`/`sub.height` ≈ 88，唔 > 180）

（呢個 task 唔 commit，留待 Task 3 GREEN 之後一齊 commit。）

---

## Task 2: 移除自訂 Prompt（HTML + CSS + JS）

**Files:**
- Modify: `frontend/proofread.html`

> 用 string-anchored 編輯（Edit tool），唔好靠純行號 — 每次刪除會令後面行號浮動，但 string match 唔受影響。每步刪完即 grep 確認。

- [ ] **Step 1: 刪 HTML — 整個 `#promptPanel` block**

刪除由 `<!-- 自訂 Prompt (v3.18 Stage 2) -->` 起，到收 `#promptPanel` 嘅 `</div>` 為止（撰寫時 ~927–983 行）。起始錨：

```html
                <!-- 自訂 Prompt (v3.18 Stage 2) -->
                <div class="rv-b-prompt-panel" id="promptPanel">
```

結束錨（呢個 `</div>` 收 `#promptPanel`，緊接其後嗰個 `</div>` 收 `.rv-b-vid-panels` — **必須保留** 收 grid 嗰個）：

```html
                    </div>
                  </div>
                </div>
              </div>    <!-- ← 呢個收 .rv-b-vid-panels，保留 -->
```

刪完 `.rv-b-vid-panels` 應只剩 2 個 child：`#glossaryPanel` + `#subtitleSettingsPanel`。

- [ ] **Step 2: 刪 CSS — `.rv-b-prompt-*` 全組 rule**

刪除由 `/* 自訂 Prompt Panel (v3.18 Stage 2) */`（~355）到 `.rv-b-prompt-actions { ... }` 收 `}`（~425）嘅整段，包括以下 11 條 selector：
`.rv-b-prompt-panel`、`.rv-b-prompt-scope`、`.rv-b-prompt-body`、`.rv-b-prompt-row`、`.rv-b-prompt-label`、`.rv-b-prompt-select`、`.rv-b-prompt-section`、`.rv-b-prompt-section > summary`、`.rv-b-prompt-section[open] > summary`、`.rv-b-prompt-textarea`、`.rv-b-prompt-actions`。
保留下一個 comment `/* Glossary Apply Modal */`（~427）。

- [ ] **Step 3: 刪 JS — Prompt Panel 整段 function block**

刪除由 comment `// Prompt Panel (v3.18 Stage 2)`（連上面嘅 `====` 分隔線，~1796）到 `commitPromptOverrides()` 收嘅 `}`（~1958）嘅整段，即 6 個 function：
`initPromptPanel()`、`showPromptPanelForFile()`、`applyPromptTemplate()`、`onPromptDirty()`、`clearPromptOverrides()`、`commitPromptOverrides()`。
保留下一個 `// Load` 分隔線 comment（~1960）。

- [ ] **Step 4: 刪 JS — 2 個 module 變量**

刪除呢兩行（~1055–1056）：

```js
  let _promptTemplates = [];      // populated by initPromptPanel from GET /api/prompt_templates
  let _promptDirty = false;       // textarea content differs from server state
```

- [ ] **Step 5: 刪 JS — `init()` 內嘅 call site**

喺 `init()` 內刪除呢一行（~1988，喺 `syncSourceDropdowns();` 之後、`await loadSegments();` 之前）：

```js
      initPromptPanel();
```

- [ ] **Step 6: grep 確認零殘留**

Run:
```bash
cd "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai"
grep -nE "promptPanel|promptTemplate|promptAnchor|promptSingle|promptEnrich|promptPass1|promptQwen3Context|promptRefinerPrompt|promptCommitBtn|promptApplyTemplateBtn|rv-b-prompt|initPromptPanel|showPromptPanelForFile|applyPromptTemplate|onPromptDirty|clearPromptOverrides|commitPromptOverrides|_promptTemplates|_promptDirty" frontend/proofread.html
```
Expected: **零輸出**（完全冇殘留 reference）。

---

## Task 3: 驗證 console + 校正版面（GREEN）

**Files:**
- Modify（可能）: `frontend/proofread.html`（`.rv-b-vid-panels` 高度微調，視乎截圖）

- [ ] **Step 1: 改寫診斷 script 量度 + 截圖（移除後）**

覆寫 `frontend/diag_proofread_layout.mjs`（已存在，調查時建立）做移除後驗證：量度 `.rv-b-vid-panels` 容器（childCount 應 = 2）、`#glossaryPanel`、`#subtitleSettingsPanel`，並收集 `page.on('console', ...)` 嘅 error，最後截圖 `.rv-b-video-col`。

```js
import { chromium } from '@playwright/test';
const BASE = 'http://localhost:5001';
const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: { width: 1512, height: 900 }, deviceScaleFactor: 2 });
const page = await ctx.newPage();
const errors = [];
page.on('console', m => { if (m.type() === 'error') errors.push(m.text()); });
page.on('pageerror', e => errors.push('PAGEERROR: ' + e.message));
await page.request.post(BASE + '/login', { data: { username: 'admin_p3', password: 'AdminPass1!' } });
const files = (await (await page.request.get(BASE + '/api/files')).json()).files || [];
await page.goto(`${BASE}/proofread.html?file_id=${files[0].id}`, { waitUntil: 'networkidle' });
await page.waitForTimeout(2000);
const m = await page.evaluate(() => {
  const box = (s) => { const e = document.querySelector(s); if (!e) return null; const r = e.getBoundingClientRect(); return { h: Math.round(r.height), y: Math.round(r.y), x: Math.round(r.x) }; };
  const c = document.querySelector('.rv-b-vid-panels');
  const cs = c && getComputedStyle(c);
  // does 字幕設定 body overflow (scroll) ?
  const ssBody = document.querySelector('.rv-b-ss-body');
  return {
    containerChildCount: c ? c.children.length : 'MISSING',
    gridRows: cs && cs.gridTemplateRows,
    glossary: box('#glossaryPanel'), subtitle: box('#subtitleSettingsPanel'),
    ssScroll: ssBody ? { scrollH: ssBody.scrollHeight, clientH: ssBody.clientHeight, overflowing: ssBody.scrollHeight > ssBody.clientHeight + 2 } : null,
  };
});
console.log(JSON.stringify(m, null, 2));
console.log('CONSOLE ERRORS:', errors.length ? errors : 'none');
const col = await page.$('.rv-b-video-col');
if (col) await col.screenshot({ path: 'diag_after_videocol.png' });
await browser.close();
```

Run: `cd frontend && node diag_proofread_layout.mjs`
Expected: `containerChildCount: 2`、`gridRows` 係單一 row、`CONSOLE ERRORS: none`、`glossary.h` 同 `subtitle.h` 都 > 180 且大致相等。

- [ ] **Step 2: 睇截圖 + 判斷是否要微調高度**

用 Read tool 睇 `frontend/diag_after_videocol.png`。檢查：兩 panel 並排齊頂、字幕設定 6 行（字型/大小/顏色/輪廓色/輪廓寬/底部邊距）完整可見。
- 若 Step 1 嘅 `ssScroll.overflowing === false` 且截圖見到 6 行齊 → **無需改 CSS**，跳去 Step 4。
- 若 `ssScroll.overflowing === true`（字幕設定仍 scroll） → 做 Step 3 微調。

- [ ] **Step 3:（條件性）微調 `.rv-b-vid-panels` 高度**

喺 `frontend/proofread.html` 將：

```css
    .rv-b-vid-panels {
      display: grid; grid-template-columns: 1fr 1fr; gap: 12px;
      flex-shrink: 0; min-height: 0;
      height: 220px; max-height: 40vh;
    }
```

改 `height: 220px` 做啱嘅值（以 Step 1 量度為準，例如字幕設定需要 ~240px 就寫 `height: 240px`）。改完重跑 Step 1 確認 `ssScroll.overflowing === false`。

- [ ] **Step 4: 跑回歸測試確認 GREEN**

Run: `cd frontend && BASE_URL=http://localhost:5001 npx playwright test tests/test_proofread_layout.spec.js --reporter=line`
Expected: **2 PASS**。

- [ ] **Step 5: Commit（移除 + 版面 + 新測試）**

```bash
cd "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai"
git add frontend/proofread.html frontend/tests/test_proofread_layout.spec.js
git commit -m "fix(proofread): remove 自訂 Prompt panel, restore 2-panel grid layout"
```

---

## Task 4: 更新既有 prompt 測試

**Files:**
- Delete: `frontend/tests/test_prompt_panel.spec.js`
- Modify: `frontend/tests/test_v6_pipeline_strip.spec.js`

- [ ] **Step 1: 刪整個 test_prompt_panel.spec.js**

```bash
cd "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai"
git rm frontend/tests/test_prompt_panel.spec.js
```
（呢個檔 3 個 test 全部測 proofread 已移除嘅自訂 Prompt panel。）

- [ ] **Step 2: 從 test_v6_pipeline_strip.spec.js 刪走 proofread-coupled 嘅 Test 6 + Test 7**

刪除兩個 `test(...)` block：
- `test("proofreadPanelShowsV6FieldsForV6File", ...)`（~343 行）— navigate 去 proofread 並 assert `#promptQwen3Context` / `#promptRefinerPrompt` 可見。
- `test("proofreadCommitV6OverridesPatchesFile", ...)`（~380 行）— navigate 去 proofread、填 `#promptQwen3Context`、撳 `#promptCommitBtn`、assert PATCH。

同時更新檔頂 doc-comment 移走第 6、7 點（`* 6. Proofread page shows V6 fields ...` / `* 7. Committing V6 prompt overrides in Proofread ...`）。
**保留** Test 1–5（測 dashboard `#inlinePromptPanel` strip — 唔同組件，唔受影響）。

- [ ] **Step 3: 跑 test_v6_pipeline_strip.spec.js 確認剩餘 test 通過**

Run: `cd frontend && BASE_URL=http://localhost:5001 npx playwright test tests/test_v6_pipeline_strip.spec.js --reporter=line`
Expected: 剩餘 dashboard-strip test 全 PASS（冇 proofread prompt 相關 fail）。

> 連跑多個 spec 會撞 `/login` rate limit（10/min/IP）。若見 429，等 ~60s 再跑，或單檔跑。呢個唔係 regression。

- [ ] **Step 4: Commit**

```bash
cd "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai"
git add frontend/tests/test_v6_pipeline_strip.spec.js
git commit -m "test(proofread): drop self-訂 Prompt panel tests (panel removed)"
```

---

## Task 5: 清理 artifact + 文檔 + 收尾

**Files:**
- Delete: `frontend/diag_proofread_layout.mjs`、`frontend/diag_*.png`
- Modify: `CLAUDE.md`、`README.md`

- [ ] **Step 1: 刪診斷 artifact（唔 commit 入 repo）**

```bash
cd "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai/frontend"
rm -f diag_proofread_layout.mjs diag_proofread_full.png diag_proofread_videocol.png diag_after_videocol.png
```

- [ ] **Step 2: 更新 CLAUDE.md**

喺「Completed Features」最上方加一段（緊貼 v3.21 entry 之上）：

```markdown
### Proofread 版面修復 — 移除自訂 Prompt 面板（2026-05-30）
- **問題**：Proofread 影片下方嘅 `.rv-b-vid-panels` 係 2 欄固定高度 grid，但 v3.18 將「自訂 Prompt」(`#promptPanel`) 作為第 3 個 grid child 塞入，產生 implicit 第 2 行，將「詞彙表」+「字幕設定」壓扁到 ~88px（MacBook 14" 1512×982 實測），自訂 Prompt 半欄孤立。
- **修復**：完全移除自訂 Prompt 面板（`frontend/proofread.html` 嘅 #promptPanel HTML + `.rv-b-prompt-*` CSS + 6 個 prompt JS function + 2 變量 + call site）。grid 回復單行 2 欄，兩 panel 各佔全高。
- **保留**：per-file `prompt_overrides` 資料模型 + `PATCH /api/files/<id>` + `/api/prompt_templates` API 完全不變（只移除 proofread UI 入口）；dashboard `📝 自訂` chip 保留。Backend 零改動。
- **測試**：新增 `frontend/tests/test_proofread_layout.spec.js`（panel 移除 + 兩 panel 尺寸）；刪 `test_prompt_panel.spec.js`；`test_v6_pipeline_strip.spec.js` 移走 2 個 proofread-coupled test（保留 5 個 dashboard-strip test）。
- **Spec/Plan**：[spec](docs/superpowers/specs/2026-05-30-proofread-panel-layout-fix-design.md) / [plan](docs/superpowers/plans/2026-05-30-proofread-panel-layout-fix-plan.md)。
```

- [ ] **Step 3: 更新 README.md（輕量）**

`grep -n "自訂 Prompt\|prompt" README.md`。若有提及 proofread 自訂 Prompt 功能嘅段落，加一句註明該編輯入口已從校對頁移除（資料/API 保留）。若 README 無相關段落，跳過呢步（唔強加）。

- [ ] **Step 4: Commit 文檔**

```bash
cd "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai"
git add CLAUDE.md README.md
git commit -m "docs: record proofread 自訂 Prompt panel removal"
```

- [ ] **Step 5: 最終人手 smoke（操作者）**

```
open http://localhost:5001/proofread.html?file_id=601db8e1e240
```
肉眼確認：影片下方只剩 詞彙表 + 字幕設定 並排各半、高度正常、字幕設定 6 行齊、詞彙表內部 scroll；自訂 Prompt 完全唔見；console 無 error。另外縮窄視窗到 ≤1024px 確認單欄 stack 仍正常。

---

## 驗收標準（對應 spec §7）

1. ✅ Proofread 影片下方只剩 詞彙表 + 字幕設定，並排各半、高度正常、字幕設定 6 行完整、詞彙表內部 scroll。
2. ✅ 自訂 Prompt panel 完全消失，console 零相關 JS error。
3. ✅ `grep` proofread.html 零殘留 prompt-panel reference（Task 2 Step 6）。
4. ✅ ≤1024px 響應式單欄 stack 正常（Task 5 Step 5）。
5. ✅ `test_proofread_layout.spec.js` 2 PASS；`test_prompt_panel.spec.js` 已刪；`test_v6_pipeline_strip.spec.js` 剩餘 test PASS。
6. ✅ Backend 零改動。

## Self-Review notes

- **Spec coverage**：spec §4.1（移除）→ Task 2；§4.2（版面）→ Task 3；§4.3（驗證）→ Task 3 Step 1-4 + Task 5 Step 5；§4.4（測試）→ Task 1 + Task 4；§5（範圍外/清理）→ Task 5；§7 驗收 → 上表。全覆蓋。
- **Type/ID consistency**：移除目標 ID（`#promptPanel`/`#promptTemplate`/`#promptCommitBtn`/`#promptQwen3Context`/`#promptRefinerPrompt`/`#promptAnchor`/`#promptSingle`/`#promptEnrich`/`#promptPass1`）同 grep guard 一致；保留 ID（`#glossaryPanel`/`#subtitleSettingsPanel`/`.rv-b-vid-panels`/dashboard `#inlinePromptPanel`）一致。
- **No placeholders**：所有 step 有實際 code / 指令 / 預期輸出；高度數值以截圖實測決定（Task 3 條件分支已寫明判斷準則，非 placeholder）。
