import { describe, it, expect, beforeEach } from 'vitest';
import { useAuthStore } from './auth';

beforeEach(() => {
  useAuthStore.setState({ user: null, isLoading: true });
});

describe('useAuthStore', () => {
  it('starts with isLoading=true and user=null', () => {
    expect(useAuthStore.getState().user).toBeNull();
    expect(useAuthStore.getState().isLoading).toBe(true);
  });

  it('setUser updates state and clears loading', () => {
    useAuthStore.getState().setUser({ id: 1, username: 'admin', is_admin: true });
    expect(useAuthStore.getState().user?.username).toBe('admin');
    expect(useAuthStore.getState().isLoading).toBe(false);
  });

  it('clearUser resets to null and clears loading', () => {
    useAuthStore.getState().setUser({ id: 1, username: 'admin', is_admin: true });
    useAuthStore.getState().clearUser();
    expect(useAuthStore.getState().user).toBeNull();
    expect(useAuthStore.getState().isLoading).toBe(false);
  });
});
