// frontend/js/user.js — Account page: identity + change-password +
// (admin) user management with inline actions + audit log.
// Single vanilla module, no build step. Mirrors Dashboard/Proofread design system.

const PW_MIN_LEN = 8;
const PW_RULE = '密碼規則：至少 8 個字元，且不能係常見密碼（例如 password、12345678、qwerty）';
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
  document.getElementById('userChipAvatar').textContent = initial(ME.username);

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
    loadUsers();
    loadAudit();
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
