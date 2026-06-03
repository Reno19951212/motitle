// frontend/js/user.js — User page: account + change-password + (admin) user mgmt + audit.
async function loadMe() {
  const r = await fetch('/api/me', { credentials: 'same-origin' });
  if (!r.ok) { window.location.href = '/login.html'; return; }
  const me = await r.json();
  document.getElementById('accountUsername').textContent = me.username || '—';
  const chip = document.getElementById('userChipName');
  if (chip) chip.textContent = me.username || '—';
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
