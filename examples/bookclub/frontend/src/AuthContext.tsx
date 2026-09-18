import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import { api, json } from './api';
import type { User } from './types';

interface AuthContextValue {
  user: User | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (name: string, email: string, password: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!localStorage.getItem('bookclub_token')) {
      setLoading(false);
      return;
    }
    api<{ user: User }>('/auth/me')
      .then(({ user: currentUser }) => setUser(currentUser))
      .catch(() => localStorage.removeItem('bookclub_token'))
      .finally(() => setLoading(false));
  }, []);

  const storeSession = useCallback((token: string, currentUser: User) => {
    localStorage.setItem('bookclub_token', token);
    setUser(currentUser);
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    const result = await api<{ user: User; token: string }>('/auth/login', {
      method: 'POST', ...json({ email, password }),
    });
    storeSession(result.token, result.user);
  }, [storeSession]);

  const register = useCallback(async (name: string, email: string, password: string) => {
    const result = await api<{ user: User; token: string }>('/auth/register', {
      method: 'POST', ...json({ name, email, password }),
    });
    storeSession(result.token, result.user);
  }, [storeSession]);

  const logout = useCallback(() => {
    localStorage.removeItem('bookclub_token');
    setUser(null);
  }, []);

  const value = useMemo(() => ({ user, loading, login, register, logout }), [user, loading, login, register, logout]);
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) throw new Error('useAuth must be used within AuthProvider');
  return context;
}

