# 統一左側欄（5-item rail）Implementation Plan（Task A）

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 將所有頁嘅最左側 rail 統一為剛好 5 個 nav item（主頁/檔案/校對/術語表/User），移除 Pipeline+語言+restart（功能不失），新增 `user.html` placeholder。

**Architecture:** Vanilla HTML，每頁各自 inline rail（無 build step，跟現狀）。每頁寫同一套 5-item rail markup，只差 active-state + in-page-route(index) vs cross-page-link(其他頁)。後端加一條靜態 route serve `user.html`。

**Tech Stack:** HTML/CSS/vanilla JS；Flask 靜態 route；Playwright。後端 :5001。

**Spec:** [docs/superpowers/specs/2026-05-31-unified-sidebar-design.md](../specs/2026-05-31-unified-sidebar-design.md)

---

## Canonical 5-item rail（reference — 各 task 用呢套，只改 active class）

**Cross-page-link 版本**（用喺 proofread / Glossary / user / admin）—— `{ON_x}` = 當前頁嗰個加 ` on`，其餘空：
```html
    <a class="rail-btn{ON_home}" href="/" title="主頁"><svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><path d="M2 8l6-5 6 5v6H2z M6 14V9h4v5"/></svg><span class="tt">主頁</span></a>
    <a class="rail-btn{ON_files}" href="/" title="檔案"><svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="3" width="12" height="10" rx="1"/><path d="M2 6h12M2 10h12M5 3v10M11 3v10"/></svg><span class="tt">檔案</span></a>
    <a class="rail-btn{ON_proof}" href="proofread.html" title="校對"><svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><path d="M11 2l3 3-8 8H3v-3z"/></svg><span class="tt">校對</span></a>
    <a class="rail-btn{ON_gloss}" href="Glossary.html" title="術語表"><svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><path d="M3 3h4a3 3 0 013 3v8a2 2 0 00-2-2H3z M13 3H9a3 3 0 00-3 3v8a2 2 0 012-2h5z"/></svg><span class="tt">術語表</span></a>
    <a class="rail-btn{ON_user}" href="user.html" title="User"><svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><circle cx="8" cy="5.5" r="2.75"/><path d="M2.5 14a5.5 5.5 0 0111 0"/></svg><span class="tt">User</span></a>
```
注意：`主頁` + `檔案` 喺其他頁都連 `/`（返 dashboard）—— 跟現狀（Glossary/proofread 本來就係咁），index 內部先用 data-route 分 home/files view。

---

## Task 1: 後端 route + `user.html` placeholder + Playwright spec（RED 基線）

**Files:** Create `frontend/user.html`, `frontend/tests/test_unified_sidebar.spec.js`; Modify `backend/app.py`

- [ ] **Step 1: 加後端靜態 route**（`backend/app.py`，跟現有 `serve_glossary_page` pattern，約 line 1491）

喺 `serve_glossary_page` 之後加：
```python
@app.get("/user.html")
@login_required
def serve_user_page():
    return send_from_directory(_FRONTEND_DIR, "user.html")
```
（`_FRONTEND_DIR`、`@login_required`、`send_from_directory` 已 import / 定義。）

- [ ] **Step 2: 建 `frontend/user.html` placeholder**

用同 Glossary.html 一致嘅骨架（topbar 簡化 + b-rail）。最小版本：
```html
<!DOCTYPE html>
<html lang="zh-HK">
<head>
  <meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>MoTitle — User</title>
  <link rel="stylesheet" href="css/responsive.css">
  <style>
    :root { --bg:#0e0f13; --surface-2:#1a1c22; --accent-soft:rgba(108,99,255,0.15); --accent-2:#8b85ff; --text:#e7e8ec; --text-dim:#9aa0ab; --border:#2a2d36; }
    * { box-sizing:border-box; } body { margin:0; background:var(--bg); color:var(--text); font-family:system-ui,-apple-system,"PingFang HK","Microsoft JhengHei",sans-serif; }
    .app { display:flex; min-height:100vh; }
    .b-rail { width:56px; flex-shrink:0; background:var(--surface-2); display:flex; flex-direction:column; align-items:center; gap:4px; padding:10px 0; border-right:1px solid var(--border); }
    .b-rail .mark { width:32px; height:32px; border-radius:8px; background:var(--accent-soft); color:var(--accent-2); display:flex; align-items:center; justify-content:center; font-weight:800; margin-bottom:8px; }
    .rail-btn { position:relative; width:40px; height:40px; border:none; background:transparent; color:var(--text-dim); border-radius:8px; display:flex; align-items:center; justify-content:center; cursor:pointer; text-decoration:none; }
    .rail-btn:hover { color:var(--text); background:var(--surface-2); }
    .rail-btn.on { color:var(--accent-2); background:var(--accent-soft); }
    .rail-btn .tt { position:absolute; left:48px; white-space:nowrap; background:#000; padding:3px 8px; border-radius:6px; font-size:12px; opacity:0; pointer-events:none; transition:opacity .12s; }
    .rail-btn:hover .tt { opacity:1; }
    .b-rail .flex1 { flex:1; }
    .user-main { flex:1; display:flex; align-items:center; justify-content:center; flex-direction:column; gap:10px; color:var(--text-dim); }
  </style>
</head>
<body>
  <div class="app">
    <aside class="b-rail">
      <div class="mark" title="MoTitle">M</div>
      <a class="rail-btn" href="/" title="主頁"><svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><path d="M2 8l6-5 6 5v6H2z M6 14V9h4v5"/></svg><span class="tt">主頁</span></a>
      <a class="rail-btn" href="/" title="檔案"><svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="3" width="12" height="10" rx="1"/><path d="M2 6h12M2 10h12M5 3v10M11 3v10"/></svg><span class="tt">檔案</span></a>
      <a class="rail-btn" href="proofread.html" title="校對"><svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><path d="M11 2l3 3-8 8H3v-3z"/></svg><span class="tt">校對</span></a>
      <a class="rail-btn" href="Glossary.html" title="術語表"><svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><path d="M3 3h4a3 3 0 013 3v8a2 2 0 00-2-2H3z M13 3H9a3 3 0 00-3 3v8a2 2 0 012-2h5z"/></svg><span class="tt">術語表</span></a>
      <a class="rail-btn on" href="user.html" title="User"><svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><circle cx="8" cy="5.5" r="2.75"/><path d="M2.5 14a5.5 5.5 0 0111 0"/></svg><span class="tt">User</span></a>
      <div class="flex1"></div>
    </aside>
    <main class="user-main">
      <svg width="48" height="48" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.25"><circle cx="8" cy="5.5" r="2.75"/><path d="M2.5 14a5.5 5.5 0 0111 0"/></svg>
      <div style="font-size:15px;">User 介面（建設中）</div>
      <div style="font-size:12px;">admin / user 管理 + 個人設定將喺 Task B 加入</div>
    </main>
  </div>
</body>
</html>
```

- [ ] **Step 3: 寫 Playwright spec（覆蓋全部頁，RED 基線）** `frontend/tests/test_unified_sidebar.spec.js`

```javascript
// Unified 5-item left rail across all pages (Task A).
const { test, expect } = require('@playwright/test');
const BASE = process.env.BASE_URL || 'http://localhost:5001';
const USER = process.env.PROBE_USER || 'admin_p3';
const PASS = process.env.PROBE_PASS || 'TestPass1!';
const EXPECTED = ['主頁', '檔案', '校對', '術語表', 'User'];

test.use({ storageState: undefined });

async function login(page) {
  const r = await page.request.post(BASE + '/login', { data: { username: USER, password: PASS } });
  if (!r.ok()) throw new Error(`Login failed: ${r.status()}`);
}

// pageUrl, activeLabel
const PAGES = [
  ['/', '主頁'],
  ['/proofread.html', '校對'],
  ['/Glossary.html', '術語表'],
  ['/user.html', 'User'],
  ['/admin.html', 'User'],
];

for (const [url, active] of PAGES) {
  test(`rail on ${url} = exactly 5 items [主頁,檔案,校對,術語表,User]`, async ({ page }) => {
    await login(page);
    await page.goto(BASE + url, { waitUntil: 'domcontentloaded' });
    const rail = page.locator('.b-rail');
    await expect(rail).toBeVisible();
    const labels = await rail.locator('.rail-btn .tt').allInnerTexts();
    expect(labels.map(s => s.trim())).toEqual(EXPECTED);
    // no removed items
    const text = await rail.innerText();
    expect(text).not.toContain('Pipeline');
    expect(text).not.toContain('語言');
    expect(text).not.toContain('服務狀態');
  });
}

test('user.html reachable (200) after login', async ({ page }) => {
  await login(page);
  const r = await page.request.get(BASE + '/user.html');
  expect(r.status()).toBe(200);
});

test('index topbar 設定 gear opens language-config', async ({ page }) => {
  await login(page);
  await page.goto(BASE + '/', { waitUntil: 'domcontentloaded' });
  await page.locator('#settingsGearBtn').click();
  // language-config manage modal/panel appears
  await expect(page.locator('text=語言配置').first()).toBeVisible({ timeout: 3000 });
});
```

- [ ] **Step 4: Run（RED）** — backend 要 running + admin_p3=TestPass1!。
`cd frontend && BASE_URL=http://localhost:5001 npx playwright test tests/test_unified_sidebar.spec.js -g "user.html reachable" --reporter=line` → user.html 200 PASS（route+page 已建）；其餘 rail tests 對未改頁面係 RED（expected）。

- [ ] **Step 5: Commit**
```bash
git add backend/app.py frontend/user.html frontend/tests/test_unified_sidebar.spec.js
git commit -m "feat(ui): user.html placeholder + GET /user.html route + unified-sidebar spec (Task A.1)"
```

---

## Task 2: `index.html` rail 修剪 + topbar 設定齒輪

**Files:** Modify `frontend/index.html`

- [ ] **Step 1: 修剪 rail**（line 1364-1374 `<aside class="b-rail" id="bRail">`）

刪除呢三個（Pipeline / 語言 / restart）button：
```html
        <button class="rail-btn" data-route="pipeline">…<span class="tt">Pipeline</span></button>
        <button class="rail-btn" data-route="lang">…<span class="tt">語言</span></button>
```
同埋 `<div class="flex1"></div>` 之後嗰個 `<button … id="restartBtn" …>…</button>`。

保留 `主頁`(data-route home, on) + `檔案`(data-route files) + `校對`(data-route proof) buttons 不變。將現有 `術語表` `<a>` 保留。**新增** User link（喺術語表之後）：
```html
        <a class="rail-btn" href="user.html" title="User"><svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><circle cx="8" cy="5.5" r="2.75"/><path d="M2.5 14a5.5 5.5 0 0111 0"/></svg><span class="tt">User</span></a>
```
最終 index rail 5 個：主頁(btn) / 檔案(btn) / 校對(btn) / 術語表(a) / User(a)。`<div class="flex1"></div>` 保留（撐高度）。

- [ ] **Step 2: topbar 加 `⚙ 設定` 齒輪（接駁語言配置）+ 搬 restart**

喺 topbar（`#adminLink` ⚙ 管理 附近，約 line 1406）加：
```html
            <button id="settingsGearBtn" class="rail-btn" title="設定（語言配置）" onclick="openLangConfigManageModal()" style="width:auto;padding:0 8px;"><svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><circle cx="8" cy="8" r="2.5"/><path d="M8 1v2M8 13v2M1 8h2M13 8h2M3 3l1.4 1.4M11.6 11.6L13 13M3 13l1.4-1.4M11.6 4.4L13 3"/></svg> 設定</button>
```
（`openLangConfigManageModal()` 已存在於 index.html line 3422，開語言配置管理 modal。先 READ 確認 `data-route="lang"` 原本撳邊個 function；若唔係 `openLangConfigManageModal` 就用嗰個真 function。）restart：`restartService()` 已存在；topbar 已有 health-cluster，將 restart 接駁去一個 topbar 細按鈕（reuse 同 svg）即可，唔需要喺 rail。

- [ ] **Step 3: Run（GREEN for index）**
`cd frontend && BASE_URL=http://localhost:5001 npx playwright test tests/test_unified_sidebar.spec.js -g "rail on / =" --reporter=line` → index rail 5-item PASS；`-g "設定 gear"` → PASS。
（手動再確認 home/files/proof data-route 切換、術語表 link 仍正常。）

- [ ] **Step 4: Commit**
```bash
git add frontend/index.html
git commit -m "feat(ui): index rail → 5 items + topbar 設定 gear for language config (Task A.2)"
```

---

## Task 3: `proofread.html` rail → 5-item

**Files:** Modify `frontend/proofread.html`（line 703 `<aside class="b-rail">`）

- [ ] **Step 1: 換 rail**

將成個 `<aside class="b-rail">…</aside>`（703 起）嘅內部 rail-btn（主頁/檔案/校對-on/Pipeline/術語表/語言 + restart）換成 canonical cross-page-link 版本，`校對` active（`{ON_proof}` = ` on`，其餘空），保留 `<div class="mark">` + 結尾 `<div class="flex1"></div>`：
```html
  <aside class="b-rail">
    <div class="mark" title="MoTitle">M</div>
    <a class="rail-btn" href="/" title="主頁"><svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><path d="M2 8l6-5 6 5v6H2z M6 14V9h4v5"/></svg><span class="tt">主頁</span></a>
    <a class="rail-btn" href="/" title="檔案"><svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="3" width="12" height="10" rx="1"/><path d="M2 6h12M2 10h12M5 3v10M11 3v10"/></svg><span class="tt">檔案</span></a>
    <a class="rail-btn on" href="proofread.html" title="校對"><svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><path d="M11 2l3 3-8 8H3v-3z"/></svg><span class="tt">校對</span></a>
    <a class="rail-btn" href="Glossary.html" title="術語表"><svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><path d="M3 3h4a3 3 0 013 3v8a2 2 0 00-2-2H3z M13 3H9a3 3 0 00-3 3v8a2 2 0 012-2h5z"/></svg><span class="tt">術語表</span></a>
    <a class="rail-btn" href="user.html" title="User"><svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><circle cx="8" cy="5.5" r="2.75"/><path d="M2.5 14a5.5 5.5 0 0111 0"/></svg><span class="tt">User</span></a>
    <div class="flex1"></div>
  </aside>
```
（`backToDashboard()` 由 `href="/"` 取代 — 行為相同：返 dashboard。）

- [ ] **Step 2: Run** `npx playwright test tests/test_unified_sidebar.spec.js -g "proofread.html" --reporter=line` → PASS。
- [ ] **Step 3: Commit** `git add frontend/proofread.html && git commit -m "feat(ui): proofread rail → 5 items (Task A.3)"`

---

## Task 4: `Glossary.html` rail → 5-item

**Files:** Modify `frontend/Glossary.html`（line 502 `<aside class="b-rail">`）

- [ ] **Step 1: 換 rail** — 同 Task 3 一樣嘅 canonical cross-page-link 版本，但 `術語表` active（`on`）、其餘空。刪走現有嘅 Pipeline + 語言 `<a>`。最終 5 item，`術語表` 嗰個 `<a class="rail-btn on" href="Glossary.html">`。
- [ ] **Step 2: Run** `-g "Glossary.html"` → PASS。
- [ ] **Step 3: Commit** `git add frontend/Glossary.html && git commit -m "feat(ui): glossary rail → 5 items (Task A.4)"`

---

## Task 5: `admin.html` rail（加最小 shell）

**Files:** Modify `frontend/admin.html`（`<body>` line 29 起；現時冇 rail/shell）

- [ ] **Step 1: 加 rail CSS + flex shell**

喺 admin.html `<style>` 內加（若無 `:root` 變量就加基本值，或 reuse 現有 admin CSS 變量）：
```css
.admin-shell { display:flex; align-items:stretch; min-height:100vh; }
.b-rail { width:56px; flex-shrink:0; background:#1a1c22; display:flex; flex-direction:column; align-items:center; gap:4px; padding:10px 0; border-right:1px solid #2a2d36; }
.b-rail .mark { width:32px; height:32px; border-radius:8px; background:rgba(108,99,255,0.15); color:#8b85ff; display:flex; align-items:center; justify-content:center; font-weight:800; margin-bottom:8px; }
.rail-btn { position:relative; width:40px; height:40px; border:none; background:transparent; color:#9aa0ab; border-radius:8px; display:flex; align-items:center; justify-content:center; cursor:pointer; text-decoration:none; }
.rail-btn:hover { color:#e7e8ec; background:#1a1c22; }
.rail-btn.on { color:#8b85ff; background:rgba(108,99,255,0.15); }
.rail-btn .tt { position:absolute; left:48px; white-space:nowrap; background:#000; color:#fff; padding:3px 8px; border-radius:6px; font-size:12px; opacity:0; pointer-events:none; }
.rail-btn:hover .tt { opacity:1; }
.admin-content { flex:1; min-width:0; padding:0 16px; }
```

- [ ] **Step 2: Wrap body content + 加 rail**

`<body>` 改成：
```html
<body>
  <div class="admin-shell">
    <aside class="b-rail">
      <div class="mark" title="MoTitle">M</div>
      <a class="rail-btn" href="/" title="主頁"><svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><path d="M2 8l6-5 6 5v6H2z M6 14V9h4v5"/></svg><span class="tt">主頁</span></a>
      <a class="rail-btn" href="/" title="檔案"><svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="3" width="12" height="10" rx="1"/><path d="M2 6h12M2 10h12M5 3v10M11 3v10"/></svg><span class="tt">檔案</span></a>
      <a class="rail-btn" href="proofread.html" title="校對"><svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><path d="M11 2l3 3-8 8H3v-3z"/></svg><span class="tt">校對</span></a>
      <a class="rail-btn" href="Glossary.html" title="術語表"><svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><path d="M3 3h4a3 3 0 013 3v8a2 2 0 00-2-2H3z M13 3H9a3 3 0 00-3 3v8a2 2 0 012-2h5z"/></svg><span class="tt">術語表</span></a>
      <a class="rail-btn on" href="user.html" title="User"><svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><circle cx="8" cy="5.5" r="2.75"/><path d="M2.5 14a5.5 5.5 0 0111 0"/></svg><span class="tt">User</span></a>
      <div style="flex:1"></div>
    </aside>
    <div class="admin-content">
      <h1>MoTitle 管理</h1>
      <!-- … 現有 tabs + panels 原封不動搬入呢度 … -->
    </div>
  </div>
</body>
```
（即係：將原本 `<body>` 直接子元素（`<h1>` + `.tabs` + 各 `.panel`）原封不動 wrap 入 `.admin-content`，前面加 `.b-rail`。所有 id/JS 不變。）

- [ ] **Step 3: Run** `-g "admin.html"` → PASS（rail 5-item，User active）。手動確認 admin tabs/panels 仍正常。
- [ ] **Step 4: Commit** `git add frontend/admin.html && git commit -m "feat(ui): admin rail → 5 items + minimal shell (Task A.5)"`

---

## Task 6: 整合驗證 + 全 suite

- [ ] **Step 1: Restart backend + restore admin_p3**（`pkill -if app.py` → start；`update_password admin_p3 TestPass1!`），等 /login rate window。
- [ ] **Step 2: Run 全 spec** `cd frontend && BASE_URL=http://localhost:5001 npx playwright test tests/test_unified_sidebar.spec.js --reporter=line` → 全 PASS（5 頁 rail + user.html 200 + 設定 gear）。若撞 429 分批 `-g` 跑。
- [ ] **Step 3: Regression** 既有 Playwright（dashboard / proofread / glossary 相關）抽幾個跑，確認 rail 改動冇整爛現有流程。
- [ ] **Step 4: 文檔** CLAUDE.md 加 unified-sidebar entry（5-item rail、Pipeline→strip、語言→設定齒輪、user.html placeholder、Task B defer）。
```bash
git add CLAUDE.md && git commit -m "docs: unified 5-item sidebar (Task A)"
```

---

## 驗收標準（對應 spec §8）
1. 5 頁 rail = 5 item（主頁/檔案/校對/術語表/User），順序/active/連結正確。
2. rail 無 Pipeline/語言/restart。
3. 語言配置仍可由 index topbar `⚙ 設定` 打開。
4. `user.html` 可達（200，rail User active）。
5. 既有 dashboard/proofread/glossary 功能零 regression。

## Self-Review notes
- **Spec coverage**：§1 5-item→canonical+T2-5；§3 移除項→T2（Pipeline/語言/restart）；§4 user.html→T1；§5 檔案表→T1-5；§6 測試→Playwright spec（T1 寫、各 task 跑）；§7 範圍→純前端+1 route。全覆蓋。
- **Placeholder scan**：每 task 有實 markup/命令。`openLangConfigManageModal` 要 implementer READ 確認（plan 有講 fallback）。無 TBD。
- **一致性**：canonical rail SVG/順序/`.tt` label 各 task 一致；User SVG（person）+ `href="user.html"` 一致；active class `on` 用法一致。
- **依賴**：T1（route+page+spec）先；T2-5 各改一頁、跑對應 `-g`；T6 整合。各 task 一個 commit。
- **admin.html note**：admin 加最小 shell（T5）；Task B 會將 admin 吸納入 user.html（spec §9）—— T5 係過渡一致化，唔白做（user 未到 B 之前 admin 都一致）。
