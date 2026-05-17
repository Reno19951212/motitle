import { useEffect, useState } from 'react';
import { apiFetch, ApiError } from '@/lib/api';
import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from '@/components/ui/tabs';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';

interface UserRow {
  id: number;
  username: string;
  is_admin: boolean;
}

interface AuditRow {
  id: number;
  actor_id: number;
  action: string;
  target_kind: string;
  target_id: string;
  ts: number;
}

export default function Admin() {
  const [users, setUsers] = useState<UserRow[]>([]);
  const [audit, setAudit] = useState<AuditRow[]>([]);
  const [newUser, setNewUser] = useState({ username: '', password: '', is_admin: false });
  const [err, setErr] = useState<string | null>(null);

  async function refreshUsers() {
    try {
      setUsers(await apiFetch<UserRow[]>('/api/admin/users'));
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : 'Failed to load users');
    }
  }

  async function refreshAudit() {
    try {
      setAudit(await apiFetch<AuditRow[]>('/api/admin/audit?limit=200'));
    } catch {
      /* swallow — audit may be empty on first run */
    }
  }

  useEffect(() => {
    refreshUsers();
    refreshAudit();
  }, []);

  async function createUser() {
    setErr(null);
    try {
      await apiFetch('/api/admin/users', { method: 'POST', body: JSON.stringify(newUser) });
      setNewUser({ username: '', password: '', is_admin: false });
      refreshUsers();
      refreshAudit();
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : 'Create failed');
    }
  }

  async function deleteUser(id: number) {
    setErr(null);
    if (!window.confirm('Delete user? This cannot be undone.')) return;
    try {
      await apiFetch(`/api/admin/users/${id}`, { method: 'DELETE' });
      refreshUsers();
      refreshAudit();
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : 'Delete failed');
    }
  }

  async function toggleAdmin(id: number) {
    setErr(null);
    try {
      await apiFetch(`/api/admin/users/${id}/toggle-admin`, { method: 'POST' });
      refreshUsers();
      refreshAudit();
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : 'Toggle failed');
    }
  }

  async function resetPassword(id: number) {
    setErr(null);
    const pw = window.prompt('New password (≥8 chars):');
    if (!pw) return;
    try {
      await apiFetch(`/api/admin/users/${id}/reset-password`, {
        method: 'POST',
        body: JSON.stringify({ password: pw }),
      });
      refreshAudit();
      window.alert('Password reset');
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : 'Reset failed');
    }
  }

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-semibold">Admin</h1>
      {err && <p className="text-sm text-destructive">{err}</p>}
      <Tabs defaultValue="users">
        <TabsList>
          <TabsTrigger value="users">Users</TabsTrigger>
          <TabsTrigger value="audit">Audit</TabsTrigger>
        </TabsList>
        <TabsContent value="users" className="space-y-4">
          <div className="grid grid-cols-[1fr_1fr_auto_auto] gap-2 items-end p-3 border rounded">
            <div>
              <Label>Username</Label>
              <Input
                value={newUser.username}
                onChange={(e) => setNewUser({ ...newUser, username: e.target.value })}
              />
            </div>
            <div>
              <Label>Password</Label>
              <Input
                type="password"
                value={newUser.password}
                onChange={(e) => setNewUser({ ...newUser, password: e.target.value })}
              />
            </div>
            <label className="flex items-center gap-2 text-sm pb-2">
              <input
                type="checkbox"
                checked={newUser.is_admin}
                onChange={(e) => setNewUser({ ...newUser, is_admin: e.target.checked })}
              />{' '}
              admin
            </label>
            <Button
              onClick={createUser}
              disabled={!newUser.username || !newUser.password}
            >
              Create
            </Button>
          </div>
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b">
                <th className="p-2 text-left">ID</th>
                <th className="p-2 text-left">Username</th>
                <th className="p-2 text-left">Admin?</th>
                <th className="p-2 text-right">Actions</th>
              </tr>
            </thead>
            <tbody>
              {users.length === 0 && (
                <tr>
                  <td colSpan={4} className="p-4 text-center text-muted-foreground">
                    No users.
                  </td>
                </tr>
              )}
              {users.map((u) => (
                <tr key={u.id} className="border-b">
                  <td className="p-2">{u.id}</td>
                  <td className="p-2">{u.username}</td>
                  <td className="p-2">{u.is_admin ? 'yes' : 'no'}</td>
                  <td className="p-2">
                    <div className="flex gap-2 justify-end">
                      <Button size="sm" variant="outline" onClick={() => toggleAdmin(u.id)}>
                        Toggle admin
                      </Button>
                      <Button size="sm" variant="outline" onClick={() => resetPassword(u.id)}>
                        Reset pw
                      </Button>
                      <Button size="sm" variant="destructive" onClick={() => deleteUser(u.id)}>
                        Delete
                      </Button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </TabsContent>
        <TabsContent value="audit">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b">
                <th className="p-2 text-left">Time</th>
                <th className="p-2 text-left">Actor</th>
                <th className="p-2 text-left">Action</th>
                <th className="p-2 text-left">Target</th>
              </tr>
            </thead>
            <tbody>
              {audit.length === 0 && (
                <tr>
                  <td colSpan={4} className="p-4 text-center text-muted-foreground">
                    No audit entries yet.
                  </td>
                </tr>
              )}
              {audit.map((a) => (
                <tr key={a.id} className="border-b">
                  <td className="p-2 text-xs">{new Date(a.ts * 1000).toLocaleString()}</td>
                  <td className="p-2">{a.actor_id}</td>
                  <td className="p-2">{a.action}</td>
                  <td className="p-2 text-xs">{a.target_kind}:{a.target_id}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </TabsContent>
      </Tabs>
    </div>
  );
}
