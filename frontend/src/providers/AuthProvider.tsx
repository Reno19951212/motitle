import { useEffect, type ReactNode } from 'react';
import { apiFetch } from '@/lib/api';
import { useAuthStore, type User } from '@/stores/auth';

export function AuthProvider({ children }: { children: ReactNode }) {
  const setUser = useAuthStore((s) => s.setUser);
  const clearUser = useAuthStore((s) => s.clearUser);
  const isLoading = useAuthStore((s) => s.isLoading);

  useEffect(() => {
    let cancelled = false;
    apiFetch<User>('/api/me')
      .then((u) => {
        if (!cancelled) setUser(u);
      })
      .catch(() => {
        if (!cancelled) clearUser();
      });
    return () => {
      cancelled = true;
    };
  }, [setUser, clearUser]);

  if (isLoading) return <div className="p-8 text-muted-foreground">Loading…</div>;
  return <>{children}</>;
}
