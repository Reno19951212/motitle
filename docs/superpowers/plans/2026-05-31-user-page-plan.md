# User 頁 Implementation Plan（Task B）

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 砌 User 頁（我的帳戶 + 自助改密碼 + admin 用戶管理 + 審計），加一個 `POST /api/me/password` endpoint，`/admin.html` redirect 去 `/user.html`。

**Architecture:** 1 個新 auth endpoint（驗舊密碼+強度+audit+rate-limit）；`user.html` 換走 placeholder，3 個角色分區 section；`js/user.js` 重用現有 `admin.js` 嘅 users/audit 邏輯 + 新 account/change-pw。admin.html redirect + 移除。

**Tech Stack:** Flask（auth blueprint）；vanilla HTML/JS；pytest + Playwright。後端 :5001。

**Spec:** [docs/superpowers/specs/2026-05-31-user-page-design.md](../specs/2026-05-31-user-page-design.md)

---

## Task 1: 後端 `POST /api/me/password`

**Files:** Modify `backend/auth/routes.py`; Create `backend/tests/test_change_password.py`

- [ ] **Step 1: 失敗測試** `backend/tests/test_change_password.py`

跟既有 auth 測試 pattern（用 `app.test_client` + 寫測試用戶入 `app.config["AUTH_DB_PATH"]`；參考 `tests/test_auth_routes.py` / `tests/test_phase6.py` 嘅 login + fixture 寫法）。具體：
```python
"""POST /api/me/password — self change-password (Task B)."""
import pytest
from app import app
from auth import users


@pytest.fixture
def client():
    db = app.config["AUTH_DB_PATH"]
    users.init_db(db)
    # ensure a known user
    try:
        users.create_user(db, "pwtest_u", "OldPass1!", is_admin=False)
    except ValueError:
        users.update_password(db, "pwtest_u", "OldPass1!")
    with app.test_client() as c:
        c.post("/login", json={"username": "pwtest_u", "password": "OldPass1!"})
        yield c
    try:
        users.update_password(db, "pwtest_u", "OldPass1!")  # restore
    except Exception:
        pass


def test_change_password_success(client):
    r = client.post("/api/me/password", json={"old_password": "OldPass1!", "new_password": "NewPass2@"})
    assert r.status_code == 200 and r.get_json()["ok"] is True
    db = app.config["AUTH_DB_PATH"]
    assert users.verify_credentials(db, "pwtest_u", "NewPass2@") is not None
    assert users.verify_credentials(db, "pwtest_u", "OldPass1!") is None


def test_change_password_wrong_old(client):
    r = client.post("/api/me/password", json={"old_password": "WRONG!", "new_password": "NewPass2@"})
    assert r.status_code == 403


def test_change_password_weak_new(client):
    r = client.post("/api/me/password", json={"old_password": "OldPass1!", "new_password": "123"})
    assert r.status_code == 400


def test_change_password_missing_fields(client):
    r = client.post("/api/me/password", json={"old_password": "OldPass1!"})
    assert r.status_code == 400


def test_change_password_requires_login():
    with app.test_client() as c:
        r = c.post("/api/me/password", json={"old_password": "x", "new_password": "y"})
        assert r.status_code in (401, 302)
```
（NOTE：若測試環境有 `R5_AUTH_BYPASS`，`test_change_password_requires_login` 可能唔係 401 —— 跟 repo 既有 auth 測試點處理 bypass 就點寫；可 `@pytest.mark` 或 conftest 對齊。實作者 READ `tests/test_auth_routes.py` 對齊。）

- [ ] **Step 2: Run → FAIL** `cd backend && source venv/bin/activate && pytest tests/test_change_password.py -v` → 404/endpoint 未存在。

- [ ] **Step 3: 實作 endpoint**（`backend/auth/routes.py`）

先 READ `auth/routes.py` 頂部 import + `/api/me`。確保有 `request`、`jsonify`、`current_app`（`/api/me` 已用 current_app）。加 import：
```python
from auth.users import verify_credentials, get_user_by_id, update_password
from auth.passwords import validate_password_strength
```
（`update_password` 加入現有 `from auth.users import …` 行；`validate_password_strength` 新 import。`request`/`jsonify` 若未 import 就加 `from flask import request, jsonify`。）

喺 `/api/me` 之後加：
```python
@bp.post("/api/me/password")
@login_required
@limiter.limit("10 per minute")
def change_own_password():
    data = request.get_json(silent=True) or {}
    old = data.get("old_password") or ""
    new = data.get("new_password") or ""
    if not old or not new:
        return jsonify({"error": "old_password and new_password required"}), 400
    db = current_app.config["AUTH_DB_PATH"]
    if verify_credentials(db, current_user.username, old) is None:
        log_audit(db, actor_id=current_user.id, action="password_change_failed",
                  target_kind="user", target_id=str(current_user.id))
        return jsonify({"error": "舊密碼唔啱"}), 403
    try:
        validate_password_strength(new)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    update_password(db, current_user.username, new)
    log_audit(db, actor_id=current_user.id, action="password_changed",
              target_kind="user", target_id=str(current_user.id))
    return jsonify({"ok": True}), 200
```

- [ ] **Step 4: Run → PASS** `pytest tests/test_change_password.py -v` → 5 PASS（或 login-required case 跟 bypass 調整後 PASS）。
- [ ] **Step 5: Regression** `pytest tests/ -k "auth or password or phase6 or me" -q` → 無新 failure。
- [ ] **Step 6: Commit**
```bash
git add backend/auth/routes.py backend/tests/test_change_password.py
git commit -m "feat(auth): POST /api/me/password self change-password (Task B.1)"
```

---

## Task 2: `user.html` 完整頁 + `js/user.js`

**Files:** Modify `frontend/user.html`（換走 placeholder）; Create `frontend/js/user.js`; Create `frontend/tests/test_user_page.spec.js`

- [ ] **Step 1: 換 `frontend/user.html`**

保留 Task A 嘅 `<aside class="b-rail">`（5-item，User active）+ 既有 rail/.app CSS。將 `<main class="user-main">…placeholder…</main>` 換成內容區，並加 section/table/form CSS。完整 `<main>`：
```html
    <main class="user-main">
      <div class="upage">
        <section class="ucard" id="accountSection">
          <h2>我的帳戶</h2>
          <div class="acct-row">
            <svg width="34" height="34" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.25"><circle cx="8" cy="5.5" r="2.75"/><path d="M2.5 14a5.5 5.5 0 0111 0"/></svg>
            <span class="acct-name" id="accountUsername">—</span>
            <span class="role-badge" id="accountRole">—</span>
          </div>
          <form id="changePwForm" class="pw-form">
            <div class="pw-title">改密碼</div>
            <input type="password" name="old_password" placeholder="舊密碼" autocomplete="current-password" required>
            <input type="password" name="new_password" placeholder="新密碼（≥8 字）" autocomplete="new-password" required>
            <button type="submit" class="btn-primary">更新密碼</button>
            <span id="changePwMsg" class="pw-msg"></span>
          </form>
        </section>

        <section class="ucard" id="userMgmtSection" hidden>
          <div class="ucard-head"><h2>用戶管理</h2></div>
          <form id="adminUserCreateForm" class="create-form">
            <input name="username" placeholder="新用戶名" required>
            <input name="password" type="password" placeholder="密碼（≥8 字）" required>
            <label class="chk"><input type="checkbox" name="is_admin"> 管理員</label>
            <button type="submit" class="btn-primary" data-testid="admin-user-create-submit">新增用戶</button>
          </form>
          <table class="utable"><thead><tr><th>ID</th><th>用戶名</th><th>管理員</th><th>建立時間</th><th>操作</th></tr></thead>
            <tbody id="adminUserList"></tbody></table>
        </section>

        <section class="ucard" id="auditSection" hidden>
          <div class="ucard-head"><h2>審計日誌</h2></div>
          <table class="utable"><thead><tr><th>時間</th><th>操作者</th><th>動作</th><th>對象</th><th>詳情</th></tr></thead>
            <tbody id="adminAuditList"></tbody></table>
        </section>
      </div>
    </main>
```
喺 `<style>` 加（接住 Task A 嘅 rail CSS 後）：
```css
.user-main { align-items:flex-start; justify-content:flex-start; padding:24px; overflow-y:auto; }
.upage { width:100%; max-width:880px; display:flex; flex-direction:column; gap:18px; }
.ucard { background:var(--surface-2); border:1px solid var(--border); border-radius:12px; padding:18px 20px; }
.ucard h2 { margin:0 0 12px; font-size:15px; }
.ucard-head { display:flex; align-items:center; justify-content:space-between; }
.acct-row { display:flex; align-items:center; gap:12px; margin-bottom:14px; }
.acct-name { font-size:16px; font-weight:600; }
.role-badge { font-size:11px; padding:2px 10px; border-radius:999px; }
.role-admin { background:rgba(108,99,255,0.18); color:var(--accent-2); }
.role-user { background:#2a2d36; color:var(--text-dim); }
.pw-form, .create-form { display:flex; align-items:center; gap:8px; flex-wrap:wrap; }
.pw-title { font-size:12px; color:var(--text-dim); width:100%; margin-bottom:2px; }
.pw-form input, .create-form input { background:var(--bg); border:1px solid var(--border); color:var(--text); border-radius:8px; padding:7px 10px; font-size:13px; }
.btn-primary { background:var(--accent-2); color:#0e0f13; border:none; border-radius:8px; padding:7px 14px; font-weight:600; cursor:pointer; font-size:13px; }
.chk { font-size:12px; color:var(--text-dim); display:flex; align-items:center; gap:4px; }
.pw-msg { font-size:12px; } .pw-msg.ok { color:#36d399; } .pw-msg.err { color:#f87171; }
.utable { width:100%; border-collapse:collapse; margin-top:10px; font-size:12.5px; }
.utable th, .utable td { text-align:left; padding:7px 8px; border-bottom:1px solid var(--border); }
.utable th { color:var(--text-dim); font-weight:600; }
.utable .btn-secondary { background:#2a2d36; color:var(--text); border:none; border-radius:6px; padding:4px 8px; cursor:pointer; font-size:11px; margin-right:4px; }
.utable .btn-danger { background:rgba(239,68,68,0.18); color:#f87171; border:none; border-radius:6px; padding:4px 8px; cursor:pointer; font-size:11px; }
```
喺 `</body>` 前加：`<script src="js/user.js"></script>`。

- [ ] **Step 2: Create `frontend/js/user.js`**

重用 admin.js 嘅 users/audit/create 邏輯（loadUsers / deleteUser / resetPassword / toggleAdmin / loadAudit + create-form submit；DOM id 同 admin.html 一致：`adminUserList` / `adminAuditList` / `adminUserCreateForm`）。加 account + change-pw + is_admin gate boot：
```javascript
// frontend/js/user.js — User page: account + change-password + (admin) user mgmt + audit.
async function loadMe() {
  const r = await fetch('/api/me', { credentials: 'same-origin' });
  if (!r.ok) { window.location.href = '/login.html'; return; }
  const me = await r.json();
  document.getElementById('accountUsername').textContent = me.username || '—';
  const badge = document.getElementById('accountRole');
  badge.textContent = me.is_admin ? '管理員' : '用戶';
  badge.className = 'role-badge ' + (me.is_admin ? 'role-admin' : 'role-user');
  if (me.is_admin) {
    document.getElementById('userMgmtSection').hidden = false;
    document.getElementById('auditSection').hidden = false;
    loadUsers();
    loadAudit();
  }
}

document.getElementById('changePwForm').addEventListener('submit', async (e) => {
  e.preventDefault();
  const fd = new FormData(e.target);
  const msg = document.getElementById('changePwMsg');
  msg.textContent = ''; msg.className = 'pw-msg';
  const r = await fetch('/api/me/password', {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, credentials: 'same-origin',
    body: JSON.stringify({ old_password: fd.get('old_password'), new_password: fd.get('new_password') }),
  });
  const data = await r.json().catch(() => ({}));
  if (r.ok) { msg.textContent = '✓ 密碼已更新'; msg.className = 'pw-msg ok'; e.target.reset(); }
  else { msg.textContent = '✕ ' + (data.error || `HTTP ${r.status}`); msg.className = 'pw-msg err'; }
});

// ── reused from admin.js (users + audit; glossaries/profiles intentionally omitted) ──
async function loadUsers() {
  const r = await fetch('/api/admin/users', { credentials: 'same-origin' });
  if (!r.ok) return;
  const usersList = await r.json();
  document.getElementById('adminUserList').innerHTML = usersList.map(u => `
    <tr data-testid="admin-user-row" data-user-id="${u.id}">
      <td>${u.id}</td><td>${u.username}</td><td>${u.is_admin ? '✓' : ''}</td>
      <td>${new Date(u.created_at * 1000).toISOString().slice(0,16).replace('T',' ')}</td>
      <td>
        <button class="btn-secondary" onclick="resetPassword(${u.id}, '${u.username}')">重設密碼</button>
        <button class="btn-secondary" onclick="toggleAdmin(${u.id})">${u.is_admin ? '降級' : '升 admin'}</button>
        <button class="btn-danger" data-testid="admin-user-delete" onclick="deleteUser(${u.id}, '${u.username}')">刪除</button>
      </td>
    </tr>`).join('');
}
async function deleteUser(id, username) {
  if (!confirm(`確定刪除用戶 ${username}？`)) return;
  const r = await fetch(`/api/admin/users/${id}`, { method: 'DELETE', credentials: 'same-origin' });
  if (!r.ok) { const e = await r.json().catch(()=>({})); alert('刪除失敗：' + (e.error || r.status)); return; }
  loadUsers();
}
async function resetPassword(id, username) {
  const pw = prompt(`輸入新密碼 (${username})：`);
  if (!pw) return;
  const r = await fetch(`/api/admin/users/${id}/reset-password`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, credentials: 'same-origin',
    body: JSON.stringify({ new_password: pw }),
  });
  if (!r.ok) { const e = await r.json().catch(()=>({})); alert('失敗：' + (e.error || `HTTP ${r.status}`)); return; }
  alert('密碼已重設');
}
async function toggleAdmin(id) {
  const r = await fetch(`/api/admin/users/${id}/toggle-admin`, { method: 'POST', credentials: 'same-origin' });
  if (!r.ok) { const e = await r.json().catch(()=>({})); alert('失敗：' + (e.error || r.status)); return; }
  loadUsers();
}
async function loadAudit() {
  const r = await fetch('/api/admin/audit?limit=100', { credentials: 'same-origin' });
  if (!r.ok) return;
  const rows = await r.json();
  document.getElementById('adminAuditList').innerHTML = rows.map(a => `
    <tr><td>${new Date(a.ts * 1000).toISOString().slice(0,19).replace('T',' ')}</td>
      <td>${a.actor_user_id}</td><td>${a.action}</td>
      <td>${(a.target_kind || '')} ${(a.target_id || '')}</td>
      <td><pre style="margin:0;font-size:11px;">${a.details ? JSON.stringify(a.details) : ''}</pre></td></tr>`).join('');
}
document.getElementById('adminUserCreateForm').addEventListener('submit', async (e) => {
  e.preventDefault();
  const fd = new FormData(e.target);
  const r = await fetch('/api/admin/users', {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, credentials: 'same-origin',
    body: JSON.stringify({ username: fd.get('username'), password: fd.get('password'), is_admin: fd.get('is_admin') === 'on' }),
  });
  if (!r.ok) { const er = await r.json().catch(()=>({})); alert('建立失敗：' + (er.error || r.status)); return; }
  e.target.reset(); loadUsers();
});
window.deleteUser = deleteUser; window.resetPassword = resetPassword; window.toggleAdmin = toggleAdmin;

loadMe();
```

- [ ] **Step 3: Playwright** `frontend/tests/test_user_page.spec.js`
```javascript
const { test, expect } = require('@playwright/test');
const BASE = process.env.BASE_URL || 'http://localhost:5001';
const USER = process.env.PROBE_USER || 'admin_p3';
const PASS = process.env.PROBE_PASS || 'TestPass1!';

test.use({ storageState: undefined });
async function login(page, u = USER, p = PASS) {
  const r = await page.request.post(BASE + '/login', { data: { username: u, password: p } });
  if (!r.ok()) throw new Error(`Login failed: ${r.status()}`);
}

test('admin sees account + user-mgmt + audit', async ({ page }) => {
  await login(page);
  await page.goto(BASE + '/user.html', { waitUntil: 'networkidle' });
  await expect(page.locator('#accountSection')).toBeVisible();
  await expect(page.locator('#accountUsername')).toHaveText('admin_p3');
  await expect(page.locator('#userMgmtSection')).toBeVisible();
  await expect(page.locator('#auditSection')).toBeVisible();
  await expect(page.locator('#adminUserList tr').first()).toBeVisible({ timeout: 5000 });
});

test('/admin.html redirects to /user.html', async ({ page }) => {
  await login(page);
  const resp = await page.goto(BASE + '/admin.html', { waitUntil: 'domcontentloaded' });
  expect(page.url()).toContain('/user.html');
});

test('change-password wrong old shows error', async ({ page }) => {
  await login(page);
  await page.goto(BASE + '/user.html', { waitUntil: 'networkidle' });
  await page.fill('input[name="old_password"]', 'definitely-wrong');
  await page.fill('input[name="new_password"]', 'BrandNew9$');
  await page.click('#changePwForm button[type="submit"]');
  await expect(page.locator('#changePwMsg.err')).toBeVisible({ timeout: 4000 });
});
```
（非-admin 區隱藏：若有非-admin 測試用戶可加一個 case 斷言 `#userMgmtSection` `hidden`；否則靠 is_admin gate 邏輯 + 上面 admin case。）

- [ ] **Step 4: Run** restart backend；`cd frontend && BASE_URL=http://localhost:5001 npx playwright test tests/test_user_page.spec.js --reporter=line`（/admin.html redirect case 喺 Task 3 之後先 PASS —— 可先跑 account/change-pw 兩個）。
- [ ] **Step 5: Commit**
```bash
git add frontend/user.html frontend/js/user.js frontend/tests/test_user_page.spec.js
git commit -m "feat(ui): User page — account + change-password + admin user mgmt + audit (Task B.2)"
```

---

## Task 3: admin.html 吸納（redirect + 移除）

**Files:** Modify `backend/app.py`; Delete `frontend/admin.html`, `frontend/js/admin.js`

- [ ] **Step 1: redirect `/admin.html`**（`backend/app.py:1514` `serve_admin_page`）

將：
```python
@app.get("/admin.html")
def serve_admin_page():
    …
    return send_from_directory(_FRONTEND_DIR, "admin.html")
```
改為：
```python
@app.get("/admin.html")
def serve_admin_page():
    # Task B: admin UI absorbed into the User page.
    return redirect("/user.html")
```
（保留任何既有 admin-only / login guard 邏輯喺 redirect 之前；若原本有 `if not is_admin: redirect(login)` 就保留，最終 admin redirect 去 /user.html。READ 原函數確認。`redirect` 已 import。）

- [ ] **Step 2: 移除舊檔**
```bash
git rm frontend/admin.html frontend/js/admin.js
```
（grep 確認冇其他頁面 `<script src=".../admin.js">` 或 link 去 admin.html 之外嘅引用；Task A 已將 admin link 變 User rail；topbar 仲有 `#adminLink href="/admin.html"` —— 改 `href="/user.html"` 或留住（redirect 會處理）。最少：READ index.html `#adminLink`，改去 `/user.html` 比較乾淨。）

- [ ] **Step 3: 改 `#adminLink`（index.html）** → `href="/user.html"`（一行）。+ mobile drawer admin link（`#mobileDrawerAdminLink`）同樣改 `/user.html`。

- [ ] **Step 4: Run** restart backend；`npx playwright test tests/test_user_page.spec.js -g "redirect" --reporter=line` → PASS（/admin.html → /user.html）。+ 確認 user_page 全 spec GREEN。
- [ ] **Step 5: Commit**
```bash
git add backend/app.py frontend/index.html
git rm frontend/admin.html frontend/js/admin.js
git commit -m "feat(ui): redirect /admin.html → /user.html; remove absorbed admin page (Task B.3)"
```

---

## Task 4: 整合 + 文檔

- [ ] **Step 1: Restart backend + restore admin_p3 → TestPass1!**（pytest 改過密碼會影響；restore）。
- [ ] **Step 2: 全 spec** `pytest tests/test_change_password.py -q` + `npx playwright test tests/test_user_page.spec.js tests/test_unified_sidebar.spec.js --reporter=line` → 全 PASS（注意 user_page 改密碼測試會真改 admin_p3 密碼 → 用獨立測試用戶或測完 restore；Playwright change-pw case 只測 wrong-old，唔會改到真密碼）。
- [ ] **Step 3: Regression** `pytest tests/ -k "auth or admin or phase6" -q` → 無新 failure。
- [ ] **Step 4: 文檔** CLAUDE.md 加 Task B entry（User 頁、`POST /api/me/password`、admin.html redirect、重用 admin.js 邏輯）。
```bash
git add CLAUDE.md && git commit -m "docs: User page (Task B)"
```

---

## 驗收標準（對應 spec §9）
1. `POST /api/me/password`：舊啱新強→改到；舊錯→403；弱→400；audit 記錄（unit）。
2. user.html：admin 見 4 區、非 admin 見 2 區（帳戶+改密碼）。
3. `/admin.html` → redirect `/user.html`。
4. 用戶管理 + 審計經 user.js（重用 /api/admin/*）運作。
5. 既有頁面零 regression。

## Self-Review notes
- **Spec coverage**：§3 endpoint→T1；§4 user.html+user.js→T2；§5 admin 吸納→T3；§7 測試→T1 pytest + T2/T3 Playwright；§6 檔案表→T1-3。全覆蓋。
- **Placeholder scan**：endpoint code + user.html markup + user.js 全實。`R5_AUTH_BYPASS` login-required case 留 implementer 對齊既有 auth 測試（已註明）。
- **一致性**：DOM id（`adminUserList`/`adminAuditList`/`adminUserCreateForm`/`accountUsername`/`accountRole`/`changePwForm`/`changePwMsg`/`userMgmtSection`/`auditSection`）user.html ↔ user.js 一致；endpoint path `/api/me/password` 前後一致。
- **依賴**：T1（endpoint）獨立先；T2（頁面，用 T1 endpoint）；T3（redirect，要 T2 user.html 存在）；T4 整合。各一 commit。
- **安全**：change-pw 驗舊 + 強度 + audit + rate-limit；admin 區用既有 admin-only endpoint；非 admin gate（唔 call admin endpoint）。
