import { create } from 'zustand';

export interface User {
  id: number;
  username: string;
  is_admin: boolean;
}

interface AuthState {
  user: User | null;
  isLoading: boolean;
  setUser: (u: User) => void;
  clearUser: () => void;
}

export const useAuthStore = create<AuthState>((set) => ({
  user: null,
  isLoading: true,
  setUser: (u) => set({ user: u, isLoading: false }),
  clearUser: () => set({ user: null, isLoading: false }),
}));
