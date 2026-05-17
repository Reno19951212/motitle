import { useNavigate } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { useAuthStore } from '@/stores/auth';
import { apiFetch } from '@/lib/api';

export function TopBar() {
  const user = useAuthStore((s) => s.user);
  const clearUser = useAuthStore((s) => s.clearUser);
  const navigate = useNavigate();

  async function handleLogout() {
    try {
      await apiFetch('/logout', { method: 'POST' });
    } catch {
      /* ignore */
    }
    clearUser();
    navigate('/login');
  }

  return (
    <div className="flex items-center justify-between px-6 h-14">
      <h1 className="text-lg font-semibold">MoTitle</h1>
      <div className="flex items-center gap-3">
        <span className="text-sm text-muted-foreground">
          {user?.username}
          {user?.is_admin && ' (admin)'}
        </span>
        <Button variant="outline" size="sm" onClick={handleLogout}>
          Logout
        </Button>
      </div>
    </div>
  );
}
