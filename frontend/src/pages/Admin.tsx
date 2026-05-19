// src/pages/Admin.tsx
// Iter 5 of the Bold variant rollout — full-page motitle-bold layout for
// admin user management + audit log. 2-col grid mirroring iters 2-4:
// .b-rail + .b-main + .b-topbar + .b-body 2-col (left = Users panel with
// inline create form via topbar button, right = Audit panel with filter).
import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuthStore } from '@/stores/auth';
import { useSocket } from '@/providers/SocketProvider';
import { apiFetch, ApiError } from '@/lib/api';
import { BoldRail } from '@/components/BoldRail';
import { ConfirmDialog } from '@/components/ConfirmDialog';
import { Icon } from '@/lib/motitle-icons';
import '@/styles/motitle-bold.css';

interface UserRow {
  id: number;
  username: string;
  is_admin: boolean;
  created_at?: number;
}

interface AuditRow {
  id: number;
  actor_user_id: number;
  action: string;
  target_kind: string | null;
  target_id: string | null;
  ts: number;
  details?: unknown;
}

const AUDIT_LIMITS = [50, 100, 200, 500] as const;

export default function Admin() {
  const navigate = useNavigate();
  const user = useAuthStore((s) => s.user)!;
  const clearUser = useAuthStore((s) => s.clearUser);
  const { state: socketState } = useSocket();

  const [users, setUsers] = useState<UserRow[]>([]);
  const [audit, setAudit] = useState<AuditRow[]>([]);
  const [auditFilterActor, setAuditFilterActor] = useState<string>('all');
  const [auditLimit, setAuditLimit] = useState<number>(100);

  const [showCreate, setShowCreate] = useState(false);
  const [newUsername, setNewUsername] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [newIsAdmin, setNewIsAdmin] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);

  const [resetForId, setResetForId] = useState<number | null>(null);
  const [resetPw, setResetPw] = useState('');
  const [resetError, setResetError] = useState<string | null>(null);

  const [deleting, setDeleting] = useState<UserRow | null>(null);
  const [pageError, setPageError] = useState<string | null>(null);

  async function refreshUsers() {
    try {
      const data = await apiFetch<UserRow[]>('/api/admin/users');
      setUsers(data);
      setPageError(null);
    } catch (e) {
      setPageError(e instanceof ApiError ? e.message : 'Failed to load users');
    }
  }

  async function refreshAudit() {
    try {
      const params = new URLSearchParams({ limit: String(auditLimit) });
      if (auditFilterActor !== 'all') {
        params.set('actor_id', auditFilterActor);
      }
      const data = await apiFetch<AuditRow[]>(`/api/admin/audit?${params.toString()}`);
      setAudit(data);
    } catch {
      /* audit may be empty on first run */
      setAudit([]);
    }
  }

  useEffect(() => {
    refreshUsers();
  }, []);

  useEffect(() => {
    refreshAudit();
  }, [auditFilterActor, auditLimit]);

  function startCreate() {
    setShowCreate(true);
    setNewUsername('');
    setNewPassword('');
    setNewIsAdmin(false);
    setCreateError(null);
  }

  function cancelCreate() {
    setShowCreate(false);
    setCreateError(null);
  }

  async function handleCreate() {
    if (!newUsername.trim() || !newPassword.trim()) {
      setCreateError('Username and password are required');
      return;
    }
    setCreateError(null);
    try {
      await apiFetch('/api/admin/users', {
        method: 'POST',
        body: JSON.stringify({
          username: newUsername.trim(),
          password: newPassword,
          is_admin: newIsAdmin,
        }),
      });
      setShowCreate(false);
      setNewUsername('');
      setNewPassword('');
      setNewIsAdmin(false);
      await refreshUsers();
      await refreshAudit();
    } catch (e) {
      setCreateError(e instanceof ApiError ? e.message : 'Create failed');
    }
  }

  async function handleToggleAdmin(u: UserRow) {
    setPageError(null);
    try {
      await apiFetch(`/api/admin/users/${u.id}/toggle-admin`, { method: 'POST' });
      await refreshUsers();
      await refreshAudit();
    } catch (e) {
      setPageError(e instanceof ApiError ? e.message : 'Toggle failed');
    }
  }

  function startResetPw(id: number) {
    setResetForId(id);
    setResetPw('');
    setResetError(null);
  }

  function cancelResetPw() {
    setResetForId(null);
    setResetPw('');
    setResetError(null);
  }

  async function handleResetPw() {
    if (!resetForId || !resetPw) return;
    setResetError(null);
    try {
      await apiFetch(`/api/admin/users/${resetForId}/reset-password`, {
        method: 'POST',
        body: JSON.stringify({ new_password: resetPw }),
      });
      setResetForId(null);
      setResetPw('');
      await refreshAudit();
    } catch (e) {
      setResetError(e instanceof ApiError ? e.message : 'Reset failed');
    }
  }

  async function handleDelete() {
    if (!deleting) return;
    try {
      await apiFetch(`/api/admin/users/${deleting.id}`, { method: 'DELETE' });
      setDeleting(null);
      await refreshUsers();
      await refreshAudit();
    } catch (e) {
      setPageError(e instanceof ApiError ? e.message : 'Delete failed');
      setDeleting(null);
    }
  }

  async function handleLogout() {
    try {
      await apiFetch('/api/logout', { method: 'POST' });
    } catch {
      /* swallow */
    }
    clearUser();
    navigate('/login');
  }

  const socketConnected = socketState.connected;
  const usernameById = (id: number) =>
    users.find((u) => u.id === id)?.username ?? (id === 0 ? '—' : `#${id}`);

  function formatTs(ts: number): string {
    return new Date(ts * 1000).toLocaleString();
  }

  return (
    <div className="motitle-bold">
      <div className="bold">
        <BoldRail activeId="admin" />
        <div className="b-main">
          {/* Topbar */}
          <div className="b-topbar">
            <button
              type="button"
              className="back-btn"
              onClick={() => navigate('/')}
              aria-label="Back to Dashboard"
            >
              <Icon name="arrow-left" size={12} />
              <span>返回 Back</span>
            </button>
            <div className="topbar-mid">
              <h1 className="page-title">
                <Icon name="user" size={14} color="var(--accent-2)" />
                管理員 Admin
                <span
                  style={{
                    fontFamily: 'var(--font-mono)',
                    color: 'var(--text-dim)',
                    fontWeight: 500,
                    letterSpacing: 0,
                    marginLeft: 6,
                    fontSize: 12,
                  }}
                >
                  · {users.length} users
                </span>
              </h1>
              <div style={{ flex: 1 }} />
              <div className="topbar-actions">
                <button
                  className="run-btn"
                  type="button"
                  onClick={startCreate}
                  aria-label="New user"
                >
                  <Icon name="plus" size={11} color="#fff" />
                  + 新增用戶
                </button>
              </div>
            </div>
            <div className="health-cluster">
              <div
                className={`health-pill ${socketConnected ? 'ok' : 'err'}`}
                title={socketConnected ? 'Socket.IO connected' : 'Socket.IO disconnected'}
              >
                <span className="led" />
                <span className="hk">即時</span>
                <span className="hv">{socketConnected ? '已連' : '離線'}</span>
              </div>
              <button
                type="button"
                className="health-pill"
                onClick={handleLogout}
                title={user ? `登出 ${user.username}` : '登出'}
                style={{ cursor: 'pointer' }}
              >
                <Icon name="user" size={11} />
                <span className="hk">{user?.username ?? '—'}</span>
                <span className="hv">Logout</span>
              </button>
            </div>
          </div>

          {/* Body — 2 col grid */}
          <div className="b-body b-body-entity">
            {/* Left col — Users panel */}
            <div className="b-col" style={{ minHeight: 0 }}>
              <div className="panel" style={{ flex: 1, minHeight: 0 }}>
                <div className="panel-head">
                  <div className="title">
                    <Icon name="user" size={12} /> Users
                  </div>
                  <div className="spacer" />
                </div>
                <div className="panel-body" style={{ padding: 12 }}>
                  {pageError && (
                    <p className="field-err" style={{ marginBottom: 12 }}>
                      {pageError}
                    </p>
                  )}

                  {showCreate && (
                    <div
                      className="panel"
                      style={{
                        marginBottom: 12,
                        border: '1px solid var(--accent-ring)',
                        background: 'var(--accent-soft)',
                      }}
                    >
                      <div className="panel-head">
                        <div className="title">
                          <Icon name="plus" size={12} /> 新增用戶
                        </div>
                        <div className="spacer" />
                      </div>
                      <div className="panel-body" style={{ padding: 12 }}>
                        <form
                          className="entity-form"
                          onSubmit={(e) => {
                            e.preventDefault();
                            handleCreate();
                          }}
                          aria-label="New user"
                        >
                          <div className="field-row">
                            <label htmlFor="username">Username</label>
                            <input
                              id="username"
                              name="username"
                              type="text"
                              value={newUsername}
                              onChange={(e) => setNewUsername(e.target.value)}
                              autoComplete="off"
                              autoFocus
                            />
                          </div>
                          <div className="field-row">
                            <label htmlFor="password">Password</label>
                            <input
                              id="password"
                              name="password"
                              type="password"
                              value={newPassword}
                              onChange={(e) => setNewPassword(e.target.value)}
                              autoComplete="new-password"
                            />
                            <p className="field-hint">至少 8 字元，避免常見密碼。</p>
                          </div>
                          <div className="field-checks">
                            <label>
                              <input
                                type="checkbox"
                                checked={newIsAdmin}
                                onChange={(e) => setNewIsAdmin(e.target.checked)}
                              />
                              admin
                            </label>
                          </div>
                          {createError && <p className="field-err">{createError}</p>}
                          <div className="form-actions">
                            <button
                              type="button"
                              className="btn btn-ghost"
                              onClick={cancelCreate}
                            >
                              Cancel
                            </button>
                            <button
                              type="submit"
                              className="btn btn-primary"
                              disabled={!newUsername.trim() || !newPassword.trim()}
                            >
                              建立 Create
                            </button>
                          </div>
                        </form>
                      </div>
                    </div>
                  )}

                  {users.length === 0 ? (
                    <div className="empty" style={{ padding: '32px 16px' }}>
                      <div className="empty-icon">
                        <Icon name="user" size={20} color="var(--text-dim)" />
                      </div>
                      <div className="empty-title">未有用戶</div>
                      <div className="empty-sub">點 + 新增用戶 開始建立。</div>
                    </div>
                  ) : (
                    <div className="profile-list">
                      {users.map((u) => {
                        const isSelf = u.id === user.id;
                        return (
                          <div
                            key={u.id}
                            className="profile-row user-row"
                            style={{ flexDirection: 'column', alignItems: 'stretch', gap: 8 }}
                          >
                            <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                              <div className="profile-icon">
                                <Icon name="user" size={14} />
                              </div>
                              <div className="profile-text">
                                <div className="profile-name">
                                  {u.username}
                                  {isSelf && (
                                    <span
                                      className="lang-chip"
                                      style={{ marginLeft: 8 }}
                                    >
                                      you
                                    </span>
                                  )}
                                  {u.is_admin && (
                                    <span
                                      className="lang-chip"
                                      style={{
                                        marginLeft: 6,
                                        color: 'var(--accent-2)',
                                        borderColor: 'var(--accent-ring)',
                                      }}
                                    >
                                      admin
                                    </span>
                                  )}
                                </div>
                                <div className="profile-meta">
                                  id #{u.id}
                                  {u.created_at && (
                                    <span style={{ marginLeft: 6 }}>
                                      · 建立 {formatTs(u.created_at)}
                                    </span>
                                  )}
                                </div>
                              </div>
                            </div>
                            <div className="user-actions">
                              <button
                                type="button"
                                className="btn btn-secondary btn-sm"
                                onClick={() => handleToggleAdmin(u)}
                              >
                                {u.is_admin ? 'Revoke admin' : 'Make admin'}
                              </button>
                              <button
                                type="button"
                                className="btn btn-secondary btn-sm"
                                onClick={() => startResetPw(u.id)}
                              >
                                Reset PW
                              </button>
                              <button
                                type="button"
                                className="btn btn-danger-ghost btn-sm"
                                onClick={() => setDeleting(u)}
                                disabled={isSelf}
                                title={isSelf ? '不能刪除自己' : 'Delete user'}
                              >
                                Delete
                              </button>
                            </div>
                            {resetForId === u.id && (
                              <div
                                className="reset-pw-form"
                                style={{
                                  display: 'flex',
                                  flexDirection: 'column',
                                  gap: 6,
                                  padding: 8,
                                  border: '1px solid var(--border)',
                                  borderRadius: 6,
                                  background: 'var(--surface-2)',
                                }}
                              >
                                <label
                                  htmlFor={`reset-pw-${u.id}`}
                                  style={{
                                    fontSize: 11,
                                    color: 'var(--text-dim)',
                                    textTransform: 'uppercase',
                                    letterSpacing: '0.06em',
                                  }}
                                >
                                  New password
                                </label>
                                <input
                                  id={`reset-pw-${u.id}`}
                                  name="new_password"
                                  type="password"
                                  value={resetPw}
                                  onChange={(e) => setResetPw(e.target.value)}
                                  autoComplete="new-password"
                                  style={{
                                    background: 'var(--surface)',
                                    border: '1px solid var(--border)',
                                    color: 'var(--text)',
                                    padding: '6px 8px',
                                    borderRadius: 6,
                                    fontSize: 12,
                                  }}
                                />
                                {resetError && (
                                  <p className="field-err">{resetError}</p>
                                )}
                                <div
                                  style={{
                                    display: 'flex',
                                    gap: 6,
                                    justifyContent: 'flex-end',
                                  }}
                                >
                                  <button
                                    type="button"
                                    className="btn btn-ghost btn-sm"
                                    onClick={cancelResetPw}
                                  >
                                    Cancel
                                  </button>
                                  <button
                                    type="button"
                                    className="btn btn-primary btn-sm"
                                    onClick={handleResetPw}
                                    disabled={!resetPw}
                                  >
                                    Save password
                                  </button>
                                </div>
                              </div>
                            )}
                          </div>
                        );
                      })}
                    </div>
                  )}
                </div>
              </div>
            </div>

            {/* Right col — Audit panel */}
            <div className="b-col" style={{ minHeight: 0 }}>
              <div className="panel" style={{ flex: 1, minHeight: 0 }}>
                <div className="panel-head">
                  <div className="title">
                    <Icon name="clock" size={12} /> Audit Log
                  </div>
                  <div className="spacer" />
                  <div
                    className="audit-filters"
                    style={{ display: 'flex', gap: 8, alignItems: 'center' }}
                  >
                    <select
                      aria-label="Filter by actor"
                      value={auditFilterActor}
                      onChange={(e) => setAuditFilterActor(e.target.value)}
                      style={{
                        background: 'var(--surface-2)',
                        border: '1px solid var(--border)',
                        color: 'var(--text)',
                        padding: '4px 8px',
                        borderRadius: 6,
                        fontSize: 12,
                      }}
                    >
                      <option value="all">All actors</option>
                      {users.map((u) => (
                        <option key={u.id} value={String(u.id)}>
                          {u.username}
                        </option>
                      ))}
                    </select>
                    <select
                      aria-label="Limit"
                      value={String(auditLimit)}
                      onChange={(e) => setAuditLimit(Number(e.target.value))}
                      style={{
                        background: 'var(--surface-2)',
                        border: '1px solid var(--border)',
                        color: 'var(--text)',
                        padding: '4px 8px',
                        borderRadius: 6,
                        fontSize: 12,
                      }}
                    >
                      {AUDIT_LIMITS.map((n) => (
                        <option key={n} value={String(n)}>
                          {n} rows
                        </option>
                      ))}
                    </select>
                  </div>
                </div>
                <div className="panel-body" style={{ padding: 0, overflow: 'auto' }}>
                  {audit.length === 0 ? (
                    <div className="empty" style={{ padding: '48px 16px' }}>
                      <div className="empty-icon">
                        <Icon name="clock" size={20} color="var(--text-dim)" />
                      </div>
                      <div className="empty-title">無 Audit 紀錄</div>
                      <div className="empty-sub">
                        當管理員操作（新增 / 刪除 / 改密碼）時會自動記錄。
                      </div>
                    </div>
                  ) : (
                    <table className="entry-table audit-table">
                      <thead>
                        <tr>
                          <th style={{ width: 160 }}>Time</th>
                          <th style={{ width: 120 }}>Actor</th>
                          <th>Action</th>
                          <th>Target</th>
                        </tr>
                      </thead>
                      <tbody>
                        {audit.map((a) => (
                          <tr key={a.id} className="audit-row">
                            <td
                              style={{
                                fontFamily: 'var(--font-mono)',
                                fontSize: 11,
                                color: 'var(--text-dim)',
                                whiteSpace: 'nowrap',
                              }}
                            >
                              {formatTs(a.ts)}
                            </td>
                            <td style={{ fontSize: 12 }}>
                              {a.actor_user_id === 0
                                ? '— (unauth)'
                                : usernameById(a.actor_user_id)}
                            </td>
                            <td style={{ fontSize: 12 }}>
                              <span className="lang-chip">{a.action}</span>
                            </td>
                            <td
                              style={{
                                fontFamily: 'var(--font-mono)',
                                fontSize: 11,
                                color: 'var(--text-dim)',
                              }}
                            >
                              {a.target_kind && a.target_id
                                ? `${a.target_kind}:${a.target_id}`
                                : '—'}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  )}
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <ConfirmDialog
        open={!!deleting}
        title="Delete user?"
        description={
          deleting
            ? `Delete user "${deleting.username}"? This cannot be undone.`
            : undefined
        }
        confirmLabel="Delete"
        onConfirm={handleDelete}
        onCancel={() => setDeleting(null)}
      />
    </div>
  );
}
