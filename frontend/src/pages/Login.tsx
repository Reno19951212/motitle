import { useState } from 'react';
import { Navigate, useNavigate } from 'react-router-dom';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { LoginSchema, type LoginData } from '@/lib/schemas/user';
import { useAuthStore, type User } from '@/stores/auth';
import { apiFetch, ApiError } from '@/lib/api';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';

export default function Login() {
  const user = useAuthStore((s) => s.user);
  const setUser = useAuthStore((s) => s.setUser);
  const navigate = useNavigate();
  const [authError, setAuthError] = useState<string | null>(null);
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<LoginData>({ resolver: zodResolver(LoginSchema) });

  if (user) return <Navigate to="/" replace />;

  async function onSubmit(data: LoginData) {
    setAuthError(null);
    try {
      await apiFetch('/login', { method: 'POST', body: JSON.stringify(data) });
      const me = await apiFetch<User>('/api/me');
      setUser(me);
      navigate('/');
    } catch (e) {
      setAuthError(e instanceof ApiError ? e.message : 'Login failed');
    }
  }

  return (
    <div className="min-h-screen grid place-items-center bg-muted/20">
      <form
        onSubmit={handleSubmit(onSubmit)}
        className="w-full max-w-sm space-y-4 p-6 bg-background rounded-lg shadow-md border"
      >
        <h1 className="text-2xl font-semibold">MoTitle Login</h1>
        <div className="space-y-1">
          <Label htmlFor="username">Username</Label>
          <Input id="username" autoComplete="username" {...register('username')} />
          {errors.username && (
            <p className="text-sm text-destructive">{errors.username.message}</p>
          )}
        </div>
        <div className="space-y-1">
          <Label htmlFor="password">Password</Label>
          <Input id="password" type="password" autoComplete="current-password" {...register('password')} />
          {errors.password && (
            <p className="text-sm text-destructive">{errors.password.message}</p>
          )}
          {authError && <p className="text-sm text-destructive">{authError}</p>}
        </div>
        <Button type="submit" disabled={isSubmitting} className="w-full">
          {isSubmitting ? 'Logging in…' : 'Log in'}
        </Button>
      </form>
    </div>
  );
}
