// frontend/js/admin.js — Phase 3 admin dashboard CRUD.
function switchTab(name) {
  document.querySelectorAll(".tab").forEach(t => t.classList.remove("active"));
  document.querySelectorAll(".panel").forEach(p => p.classList.remove("active"));
  const tabBtn = document.getElementById("adminTab" + name[0].toUpperCase() + name.slice(1));
  const panel = document.getElementById("panel" + name[0].toUpperCase() + name.slice(1));
  if (tabBtn) tabBtn.classList.add("active");
  if (panel) panel.classList.add("active");
  if (name === "audit") loadAudit();
  if (name === "glossaries") loadGlossaries();
}

async function loadUsers() {
  const r = await fetch("/api/admin/users", {credentials: "same-origin"});
  if (!r.ok) return;
  const users = await r.json();
  const tbody = document.getElementById("adminUserList");
  tbody.innerHTML = users.map(u => `
    <tr data-testid="admin-user-row" data-user-id="${u.id}">
      <td>${u.id}</td>
      <td>${u.username}</td>
      <td>${u.is_admin ? "✓" : ""}</td>
      <td>${new Date(u.created_at * 1000).toISOString().slice(0, 16).replace('T', ' ')}</td>
      <td>
        <button class="btn btn-secondary" onclick="resetPassword(${u.id}, '${u.username}')">重設密碼</button>
        <button class="btn btn-secondary" onclick="toggleAdmin(${u.id})">${u.is_admin ? "降級" : "升 admin"}</button>
        <button class="btn btn-danger" data-testid="admin-user-delete"
                onclick="deleteUser(${u.id}, '${u.username}')">刪除</button>
      </td>
    </tr>
  `).join("");
}

async function deleteUser(id, username) {
  if (!confirm(`確定刪除用戶 ${username}？`)) return;
  const r = await fetch(`/api/admin/users/${id}`, {method: "DELETE", credentials: "same-origin"});
  if (!r.ok) {
    const err = await r.json().catch(() => ({}));
    alert("刪除失敗：" + (err.error || r.status));
    return;
  }
  loadUsers();
}

async function resetPassword(id, username) {
  const pw = prompt(`輸入新密碼 (${username})：`);
  if (!pw) return;
  const r = await fetch(`/api/admin/users/${id}/reset-password`, {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    credentials: "same-origin",
    body: JSON.stringify({new_password: pw}),
  });
  if (!r.ok) {
    // R6 audit E8 — surface backend's password policy error (e.g.
    // "at least 8 chars" / "too common") instead of just "失敗：400".
    const err = await r.json().catch(() => ({}));
    alert("失敗：" + (err.error || `HTTP ${r.status}`));
    return;
  }
  alert("密碼已重設");
}

async function toggleAdmin(id) {
  const r = await fetch(`/api/admin/users/${id}/toggle-admin`, {
    method: "POST", credentials: "same-origin"
  });
  if (!r.ok) {
    const err = await r.json().catch(() => ({}));
    alert("失敗：" + (err.error || r.status));
    return;
  }
  loadUsers();
}

async function loadGlossaries() {
  const r = await fetch("/api/glossaries", {credentials: "same-origin"});
  if (!r.ok) return;
  const data = await r.json();
  const glossaries = data.glossaries || [];
  const tbody = document.getElementById("adminGlossaryList");
  if (!tbody) return;
  tbody.innerHTML = glossaries.map(g => `
    <tr>
      <td>${g.id.slice(0, 8)}…</td>
      <td>${g.name}</td>
      <td>${(g.source_lang || '?').toUpperCase()}</td>
      <td>${(g.target_lang || '?').toUpperCase()}</td>
      <td>${g.entry_count || 0}</td>
      <td>${g.user_id !== null && g.user_id !== undefined ? g.user_id : '(共享)'}</td>
    </tr>
  `).join("");
}

async function loadAudit() {
  const r = await fetch("/api/admin/audit?limit=100", {credentials: "same-origin"});
  if (!r.ok) return;
  const rows = await r.json();
  const tbody = document.getElementById("adminAuditList");
  tbody.innerHTML = rows.map(a => `
    <tr>
      <td>${new Date(a.ts * 1000).toISOString().slice(0, 19).replace('T', ' ')}</td>
      <td>${a.actor_user_id}</td>
      <td>${a.action}</td>
      <td>${a.target_kind || ''} ${a.target_id || ''}</td>
      <td><pre style="margin:0;font-size:11px;">${a.details ? JSON.stringify(a.details) : ''}</pre></td>
    </tr>
  `).join("");
}

document.getElementById("adminUserCreateForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const fd = new FormData(e.target);
  const r = await fetch("/api/admin/users", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    credentials: "same-origin",
    body: JSON.stringify({
      username: fd.get("username"),
      password: fd.get("password"),
      is_admin: fd.get("is_admin") === "on",
    }),
  });
  if (!r.ok) {
    const err = await r.json().catch(() => ({}));
    alert("建立失敗：" + (err.error || r.status));
    return;
  }
  e.target.reset();
  loadUsers();
});

window.switchTab = switchTab;
window.loadUsers = loadUsers;
window.loadAudit = loadAudit;
window.loadGlossaries = loadGlossaries;
window.deleteUser = deleteUser;
window.resetPassword = resetPassword;
window.toggleAdmin = toggleAdmin;
