// frontend/js/user.js — Account page: identity + change-password +
// (admin) user management with inline actions + audit log.
// Single vanilla module, no build step. Mirrors Dashboard/Proofread design system.

const PW_MIN_LEN = 8;
const REMARKS_MAX = 500;

// shared state
let ME = null;            // { id, username, is_admin, remarks }
let USERS = [];           // admin: full user list
let USER_MAP = {};        // id -> username (audit actor/target resolution)
let AUDIT_ROWS = [];      // admin: raw audit rows
let auditQuery = '';
let auditFilter = 'all';
let openExpand = null;    // { userId, kind } currently open inline row, or null

// ---- helpers ----
function escapeHtml(s) {
  if (s == null) return '';
  return String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}
function initial(name) { return (name || '?').trim().charAt(0).toUpperCase() || '?'; }
function fmtTs(unixSec) {
  if (!unixSec) return '—';
  const d = new Date(unixSec * 1000);
  const p = n => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${p(d.getMonth()+1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`;
}
function fmtDate(unixSec) {
  if (!unixSec) return '—';
  const d = new Date(unixSec * 1000);
  const p = n => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${p(d.getMonth()+1)}-${p(d.getDate())}`;
}
function showToast(msg, kind = 'info') {
  const stack = document.getElementById('toastStack');
  const t = document.createElement('div');
  t.className = `toast ${kind}`;
  t.textContent = msg;
  stack.appendChild(t);
  setTimeout(() => t.remove(), 4000);
}

// ---- tabs ----
function switchPane(name) {
  document.querySelectorAll('.u-pane').forEach(p => p.classList.remove('on'));
  const pane = document.getElementById('pane-' + name);
  if (pane) pane.classList.add('on');
  document.querySelectorAll('.u-nav-item').forEach(n => n.classList.toggle('on', n.dataset.pane === name));
}
document.querySelectorAll('.u-nav-item').forEach(item => {
  item.addEventListener('click', () => switchPane(item.dataset.pane));
});

// ---- bootstrap ----
async function loadMe() {
  const r = await fetch('/api/me', { credentials: 'same-origin' });
  if (!r.ok) { window.location.href = '/login.html'; return; }
  ME = await r.json();

  document.getElementById('accountUsername').textContent = ME.username || '—';
  document.getElementById('userChipName').textContent = ME.username || '—';
  if (ME.is_admin) {
    const al = document.getElementById('adminLink');
    if (al) al.style.display = 'inline';
  }

  const badge = document.getElementById('accountRole');
  badge.innerHTML = `<span class="pdot"></span>${ME.is_admin ? '管理員' : '用戶'}`;
  badge.className = 'role-pill ' + (ME.is_admin ? 'role-admin' : 'role-user');

  document.getElementById('accountMeta').innerHTML = `
    <span class="meta-chip"><span class="mk">ID</span><span class="mv">${ME.id}</span></span>
    <span class="meta-chip"><span class="mk">角色</span><span class="mv">${ME.is_admin ? 'Administrator' : 'User'}</span></span>`;

  // own remarks (read-only; set by an admin)
  const ownWrap = document.getElementById('ownRemark');
  if (ME.remarks && ME.remarks.trim()) {
    document.getElementById('ownRemarkText').textContent = ME.remarks;
    ownWrap.hidden = false;
  } else {
    ownWrap.hidden = true;
  }

  if (ME.is_admin) {
    document.getElementById('navAdminGroup').hidden = false;
    document.getElementById('navUsers').hidden = false;
    document.getElementById('navAudit').hidden = false;
    // License activate controls are admin-only (POST /api/license/activate is @admin_required).
    // Non-admins still see the read-only 授權 tab (GET /api/license is @login_required).
    const licAdmin = document.getElementById('lic-admin');
    if (licAdmin) licAdmin.hidden = false;
    loadUsers();
    loadAudit();
    document.getElementById('navBeta').hidden = false;
    loadBetaMode();
  }
}

// ---- change password ----
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
  if (r.ok) {
    msg.textContent = '✓ 密碼已更新'; msg.className = 'pw-msg ok'; e.target.reset();
    showToast('密碼已更新', 'success');
  } else {
    msg.textContent = '✕ ' + (data.error || `HTTP ${r.status}`); msg.className = 'pw-msg err';
  }
});

// loadUsers / loadAudit defined in the user-management + audit sections below.
loadMe();

// topbar chip logout (logout provided by auth.js)
const _userChipLogout = document.getElementById('userChipLogout');
if (_userChipLogout) _userChipLogout.addEventListener('click', () => { if (window.logout) window.logout(); });

// ============================================================
// User management (admin)
// ============================================================
const AVATAR_GRADIENTS = [
  'linear-gradient(135deg,#6c63ff,#a78bfa)',
  'linear-gradient(135deg,#38bdf8,#6c63ff)',
  'linear-gradient(135deg,#22c55e,#38bdf8)',
  'linear-gradient(135deg,#f59e0b,#ef4444)',
  'linear-gradient(135deg,#a78bfa,#ef4444)',
];
function avatarGradient(id) { return AVATAR_GRADIENTS[id % AVATAR_GRADIENTS.length]; }

async function loadUsers() {
  const r = await fetch('/api/admin/users', { credentials: 'same-origin' });
  if (!r.ok) { showToast('載入用戶失敗', 'error'); return; }
  USERS = await r.json();
  USER_MAP = {};
  USERS.forEach(u => { USER_MAP[u.id] = u.username; });
  document.getElementById('navUsersCount').textContent = USERS.length;
  renderUsers();
  // audit actor/target labels depend on USER_MAP — re-render if already loaded
  if (AUDIT_ROWS.length) renderAudit();
}

function renderUsers() {
  const tb = document.getElementById('adminUserList');
  if (!USERS.length) { tb.innerHTML = '<tr><td colspan="5" class="empty-row">未有用戶</td></tr>'; return; }
  tb.innerHTML = USERS.map(u => {
    const isMe = ME && u.id === ME.id;
    const rolePill = u.is_admin
      ? '<span class="role-pill role-admin" style="font-size:10px;padding:1px 8px;"><span class="pdot"></span>管理員</span>'
      : '<span class="role-pill role-user" style="font-size:10px;padding:1px 8px;"><span class="pdot"></span>用戶</span>';
    const remark = (u.remarks && u.remarks.trim())
      ? `<div class="remark-text">${escapeHtml(u.remarks)}</div>`
      : '<div class="remark-empty">— 未有備註 —</div>';
    const toggleTitle = u.is_admin ? '降級為用戶' : '升為管理員';
    const toggleIcon = u.is_admin
      ? '<path d="M8 11V3M4 7l4 4 4-4"/>'
      : '<path d="M8 3v8M4 7l4-4 4 4"/>';
    return `
      <tr class="urow ${isMe ? 'me' : ''}" data-testid="admin-user-row" data-user-id="${u.id}">
        <td class="idcell">${u.id}</td>
        <td><div class="u-cell"><div class="u-av" style="background:${avatarGradient(u.id)}">${escapeHtml(initial(u.username))}</div>
          <div><div class="u-name">${escapeHtml(u.username)} ${rolePill}</div>${isMe ? '<div class="u-sub">你自己</div>' : ''}</div></div></td>
        <td class="remark-cell">${remark}</td>
        <td class="timecell">${fmtDate(u.created_at)}</td>
        <td class="actcell">
          <button class="iconbtn" title="備註" data-testid="admin-user-remark" onclick="expandRow(${u.id},'remark')"><svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M11 2l3 3-8 8H3v-3z"/></svg></button>
          <button class="iconbtn" title="重設密碼" data-testid="admin-user-reset" onclick="expandRow(${u.id},'reset')"><svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M13.4 6.5A5.2 5.2 0 1 0 14 9"/><path d="M13.8 2.8 13.9 6.6 10.1 6.4"/></svg></button>
          <button class="iconbtn" title="${toggleTitle}" onclick="toggleAdmin(${u.id})"><svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">${toggleIcon}</svg></button>
          <button class="iconbtn danger" title="${isMe ? '不能刪除自己' : '刪除'}" ${isMe ? 'disabled' : ''} data-testid="admin-user-delete" onclick="expandRow(${u.id},'delete')"><svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M3 4h10M6 4V3h4v1M5 4l.5 9h5L11 4"/></svg></button>
        </td>
      </tr>`;
  }).join('');
  // re-open an expansion if one was active before a re-render
  if (openExpand) {
    const { userId, kind } = openExpand;
    openExpand = null;
    expandRow(userId, kind);
  }
}

function closeExpand() {
  const ex = document.querySelector('#adminUserList tr.expand-row');
  if (ex) ex.remove();
  openExpand = null;
}

function expandRow(userId, kind) {
  // toggle off if same row+kind already open
  if (openExpand && openExpand.userId === userId && openExpand.kind === kind) { closeExpand(); return; }
  closeExpand();
  const u = USERS.find(x => x.id === userId);
  if (!u) return;
  const row = document.querySelector(`#adminUserList tr.urow[data-user-id="${userId}"]`);
  if (!row) return;
  const tr = document.createElement('tr');
  tr.className = 'expand-row';
  let inner = '';
  if (kind === 'delete') {
    inner = `<div class="expand-inner expand-danger">
      <span class="warn">⚠ 確定刪除「${escapeHtml(u.username)}」？此操作無法復原</span>
      <span class="spacer"></span>
      <button class="btn-xs btn-sec" onclick="closeExpand()">取消</button>
      <button class="btn-xs btn-dng" data-testid="admin-user-delete-confirm" onclick="confirmDelete(${userId})">確認刪除</button></div>`;
  } else if (kind === 'reset') {
    inner = `<div class="expand-inner expand-edit">
      <span style="color:var(--accent-2);font-size:12px;font-weight:600;">為「${escapeHtml(u.username)}」設定新密碼</span>
      <input type="password" id="resetPwInput" placeholder="新密碼（≥8 字）">
      <span class="spacer"></span>
      <button class="btn-xs btn-sec" onclick="closeExpand()">取消</button>
      <button class="btn-primary" style="padding:6px 13px;" onclick="confirmReset(${userId})">確認重設</button></div>`;
  } else if (kind === 'remark') {
    const cur = u.remarks || '';
    inner = `<div class="expand-inner expand-remark">
      <div class="er-head"><svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="var(--accent-2)" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><path d="M11 2l3 3-8 8H3v-3z"/></svg>用戶備註 · ${escapeHtml(u.username)}</div>
      <textarea id="remarkInput" maxlength="${REMARKS_MAX}" placeholder="輸入備註，例如：夜更校對員、外判翻譯員、暫停使用…" oninput="document.getElementById('remarkCount').textContent=this.value.length">${escapeHtml(cur)}</textarea>
      <div class="er-foot"><span class="er-count"><span id="remarkCount">${cur.length}</span> / ${REMARKS_MAX}</span><span class="spacer"></span>
        <button class="btn-xs btn-sec" onclick="closeExpand()">取消</button>
        <button class="btn-primary" style="padding:6px 13px;" data-testid="admin-user-remark-save" onclick="saveRemarks(${userId})">儲存備註</button></div></div>`;
  }
  const td = document.createElement('td');
  td.colSpan = 5; td.style.padding = '0';
  td.innerHTML = inner;
  tr.appendChild(td);
  row.after(tr);
  openExpand = { userId, kind };
  const focusEl = tr.querySelector('input, textarea');
  if (focusEl) focusEl.focus();
}

async function confirmDelete(userId) {
  const r = await fetch(`/api/admin/users/${userId}`, { method: 'DELETE', credentials: 'same-origin' });
  if (!r.ok) { const e = await r.json().catch(()=>({})); showToast('刪除失敗：' + (e.error || r.status), 'error'); return; }
  closeExpand();
  showToast('用戶已刪除', 'success');
  loadUsers(); loadAudit();
}

async function confirmReset(userId) {
  const input = document.getElementById('resetPwInput');
  const pw = input ? input.value : '';
  if (pw.length < PW_MIN_LEN) { showToast(`密碼太短（少於 ${PW_MIN_LEN} 字）`, 'error'); return; }
  const r = await fetch(`/api/admin/users/${userId}/reset-password`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, credentials: 'same-origin',
    body: JSON.stringify({ new_password: pw }),
  });
  if (!r.ok) { const e = await r.json().catch(()=>({})); showToast('重設失敗：' + (e.error || r.status), 'error'); return; }
  closeExpand();
  showToast('密碼已重設', 'success');
  loadUsers(); loadAudit();
}

async function saveRemarks(userId) {
  const input = document.getElementById('remarkInput');
  const remarks = input ? input.value : '';
  const r = await fetch(`/api/admin/users/${userId}/remarks`, {
    method: 'PATCH', headers: { 'Content-Type': 'application/json' }, credentials: 'same-origin',
    body: JSON.stringify({ remarks }),
  });
  if (!r.ok) { const e = await r.json().catch(()=>({})); showToast('備註儲存失敗：' + (e.error || r.status), 'error'); return; }
  closeExpand();
  showToast('備註已儲存', 'success');
  loadUsers(); loadAudit();
}

async function toggleAdmin(userId) {
  closeExpand();
  const r = await fetch(`/api/admin/users/${userId}/toggle-admin`, { method: 'POST', credentials: 'same-origin' });
  if (!r.ok) { const e = await r.json().catch(()=>({})); showToast('失敗：' + (e.error || r.status), 'error'); return; }
  showToast('權限已更新', 'success');
  loadUsers(); loadAudit();
}

// create user
document.getElementById('adminUserCreateForm').addEventListener('submit', async (e) => {
  e.preventDefault();
  const fd = new FormData(e.target);
  const pw = fd.get('password') || '';
  if (pw.length < PW_MIN_LEN) { showToast(`密碼太短（少於 ${PW_MIN_LEN} 字）`, 'error'); return; }
  const r = await fetch('/api/admin/users', {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, credentials: 'same-origin',
    body: JSON.stringify({ username: fd.get('username'), password: pw, is_admin: fd.get('is_admin') === 'on' }),
  });
  if (!r.ok) { const er = await r.json().catch(()=>({})); showToast(`建立失敗：${er.error || r.status}`, 'error'); return; }
  e.target.reset();
  showToast('用戶已建立', 'success');
  loadUsers(); loadAudit();
});

// expose inline-handler functions to global scope (onclick=)
window.expandRow = expandRow;
window.closeExpand = closeExpand;
window.confirmDelete = confirmDelete;
window.confirmReset = confirmReset;
window.saveRemarks = saveRemarks;
window.toggleAdmin = toggleAdmin;

// ============================================================
// Audit log (admin)
// ============================================================
// Backend action strings → badge class + label. Audit schema stores ONLY:
// {id, ts, actor_user_id, action, target_kind, target_id, details}. No
// ip/user_agent/status is stored, so none is shown (honesty clamp).
const ACTION_META = {
  'user.create':           { cls: 'act-create', label: '＋ create_user', cat: 'create' },
  'user.delete':           { cls: 'act-delete', label: '✕ delete_user', cat: 'delete' },
  'user.reset_password':   { cls: 'act-update', label: '✎ reset_password', cat: 'update' },
  'user.toggle_admin':     { cls: 'act-update', label: '✎ toggle_admin', cat: 'update' },
  'user.update_remarks':   { cls: 'act-update', label: '✎ update_remarks', cat: 'update' },
  'password_changed':      { cls: 'act-update', label: '✎ password_changed', cat: 'update' },
  'password_change_failed':{ cls: 'act-other',  label: '⚠ pw_change_failed', cat: 'other' },
  'login_failed':          { cls: 'act-other',  label: '⚠ login_failed', cat: 'other' },
};
function actionMeta(action) {
  return ACTION_META[action] || { cls: 'act-other', label: escapeHtml(action), cat: 'other' };
}
function actorLabel(id) {
  if (id === 0 || id == null) return '系統';
  return USER_MAP[id] ? `${USER_MAP[id]} · #${id}` : `#${id}`;
}
function targetLabel(kind, id) {
  if (!kind) return '—';
  if (kind === 'user' && USER_MAP[id]) return `user · ${USER_MAP[id]} (#${id})`;
  return `${kind}${id != null ? ' · ' + id : ''}`;
}

async function loadAudit() {
  const r = await fetch('/api/admin/audit?limit=100', { credentials: 'same-origin' });
  if (!r.ok) return;
  AUDIT_ROWS = await r.json();
  document.getElementById('navAuditCount').textContent = AUDIT_ROWS.length;
  renderAudit();
}

function auditMatches(row) {
  const meta = actionMeta(row.action);
  if (auditFilter !== 'all' && meta.cat !== auditFilter) return false;
  if (auditQuery) {
    const hay = `${row.action} ${actorLabel(row.actor_user_id)} ${targetLabel(row.target_kind, row.target_id)} ${JSON.stringify(row.details||{})}`.toLowerCase();
    if (!hay.includes(auditQuery)) return false;
  }
  return true;
}

function renderAudit() {
  const list = document.getElementById('adminAuditList');
  const rows = AUDIT_ROWS.filter(auditMatches);
  if (!rows.length) { list.innerHTML = '<div class="empty-row">無相符紀錄</div>'; return; }
  list.innerHTML = rows.map(row => {
    const meta = actionMeta(row.action);
    const detailId = `ad-${row.id}`;
    return `
      <div class="audit-item" onclick="toggleAuditDetail(${row.id}, this)">
        <span class="audit-ts">${fmtTs(row.ts)}</span>
        <span class="audit-actor"><span class="av">${escapeHtml(initial(USER_MAP[row.actor_user_id] || '系'))}</span><span class="an">${escapeHtml(actorLabel(row.actor_user_id))}</span></span>
        <span class="act-badge ${meta.cls}">${meta.label}</span>
        <span class="audit-target">${escapeHtml(targetLabel(row.target_kind, row.target_id))}</span>
        <span class="audit-caret">▾</span>
      </div>
      <div class="audit-detail-row" id="${detailId}" style="display:none;">${auditDetailHtml(row)}</div>`;
  }).join('');
}

function auditDetailHtml(row) {
  const summary = `
    <div class="adetail-block"><div class="adetail-block-head">操作摘要 · Summary</div>
      <dl class="adetail-kv">
        <dt>operation</dt><dd>${escapeHtml(row.action)}</dd>
        <dt>actor</dt><dd>${escapeHtml(actorLabel(row.actor_user_id))}</dd>
        <dt>target</dt><dd>${escapeHtml(targetLabel(row.target_kind, row.target_id))}</dd>
        <dt>timestamp</dt><dd>${fmtTs(row.ts)}</dd>
      </dl></div>`;
  let details;
  if (row.details && Object.keys(row.details).length) {
    const kv = Object.entries(row.details).map(([k, v]) =>
      `<dt>${escapeHtml(k)}</dt><dd>${escapeHtml(typeof v === 'object' ? JSON.stringify(v) : String(v))}</dd>`).join('');
    const raw = escapeHtml(JSON.stringify(row.details, null, 2));
    details = `
      <div class="adetail-block"><div class="adetail-block-head">詳情 · Details</div>
        <dl class="adetail-kv">${kv}</dl>
        <div class="araw">${raw}</div>
        <div class="adetail-actions"><button class="btn-xs btn-sec" onclick="event.stopPropagation();copyJson(${row.id})">複製 JSON</button></div></div>`;
  } else {
    details = `<div class="adetail-block"><div class="adetail-block-head">詳情 · Details</div><div class="adetail-empty">— 無額外詳情 —</div></div>`;
  }
  return `<div class="audit-detail-grid">${summary}${details}</div>`;
}

function toggleAuditDetail(id, item) {
  const el = document.getElementById(`ad-${id}`);
  if (!el) return;
  const open = el.style.display !== 'none';
  el.style.display = open ? 'none' : 'block';
  item.classList.toggle('open', !open);
}

function copyJson(id) {
  const row = AUDIT_ROWS.find(r => r.id === id);
  if (!row) return;
  if (!navigator.clipboard) { showToast('剪貼板不支援', 'error'); return; }
  navigator.clipboard.writeText(JSON.stringify(row.details, null, 2))
    .then(() => showToast('已複製 JSON', 'success'))
    .catch(() => showToast('複製失敗', 'error'));
}

// audit search + filter
document.getElementById('auditSearch').addEventListener('input', (e) => {
  auditQuery = e.target.value.trim().toLowerCase();
  renderAudit();
});
document.getElementById('auditFilter').addEventListener('click', (e) => {
  const btn = e.target.closest('.audit-chip');
  if (!btn) return;
  auditFilter = btn.dataset.filter;
  document.querySelectorAll('#auditFilter .audit-chip').forEach(c => c.classList.toggle('on', c === btn));
  renderAudit();
});

window.toggleAuditDetail = toggleAuditDetail;
window.copyJson = copyJson;

// ---- beta test mode (admin) ----
async function loadBetaMode() {
  const r = await fetch('/api/admin/beta-mode', { credentials: 'same-origin' });
  if (!r.ok) return;
  const d = await r.json();
  document.getElementById('betaEnabled').checked = !!d.enabled;
  document.getElementById('betaLlmModel').textContent = d.llm_model || '—';
  document.getElementById('betaKeyStatus').textContent =
    d.key_configured ? '✓ API key 已設定' : '✕ 未設定 API key';
}

document.getElementById('betaSaveBtn').addEventListener('click', async () => {
  const msg = document.getElementById('betaMsg');
  msg.textContent = ''; msg.className = 'pw-msg';
  const body = { enabled: document.getElementById('betaEnabled').checked };
  const key = document.getElementById('betaApiKey').value.trim();
  if (key) body.api_key = key;
  const r = await fetch('/api/admin/beta-mode', {
    method: 'PUT', headers: { 'Content-Type': 'application/json' },
    credentials: 'same-origin', body: JSON.stringify(body),
  });
  const d = await r.json().catch(() => ({}));
  if (r.ok) {
    msg.textContent = '✓ 已儲存'; msg.className = 'pw-msg ok';
    document.getElementById('betaApiKey').value = '';
    showToast('Beta 設定已儲存', 'success');
    loadBetaMode();
  } else {
    msg.textContent = '✕ ' + (d.error || `HTTP ${r.status}`); msg.className = 'pw-msg err';
  }
});
