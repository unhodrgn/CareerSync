import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import { api, SESSION_EXPIRED_EVENT } from '@/api/client';
import { paths } from '@/routes/paths';
import type { UserOut } from '@/types/auth';
import type { Role } from '@/types/common';
import { clearToken, getToken, setToken } from './tokenStorage';

type AuthStatus = 'loading' | 'guest' | 'signed-in';

interface AuthValue {
  status: AuthStatus;
  user: UserOut | null;
  /** True after a request came back 401 with a token: the login page says the session expired. */
  sessionExpired: boolean;
  login: (email: string, password: string) => Promise<UserOut>;
  logout: () => void;
  /** Replace the current user, e.g. with the response of POST /api/users/me/consent. */
  setUser: (user: UserOut) => void;
}

const AuthContext = createContext<AuthValue | null>(null);

/** Holds the token and the current user (GET /api/users/me); exposes login/logout. */
export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUserState] = useState<UserOut | null>(null);
  const [status, setStatus] = useState<AuthStatus>(() => (getToken() ? 'loading' : 'guest'));
  const [sessionExpired, setSessionExpired] = useState(false);

  // A stored token from an earlier visit in this tab: load its user, or drop it if the server refuses it
  useEffect(() => {
    if (!getToken()) return;
    let cancelled = false;
    api
      .me()
      .then((me) => {
        if (cancelled) return;
        setUserState(me);
        setStatus('signed-in');
      })
      .catch(() => {
        if (cancelled) return;
        clearToken();
        setStatus('guest');
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    const onExpired = () => {
      setUserState(null);
      setStatus('guest');
      setSessionExpired(true);
    };
    window.addEventListener(SESSION_EXPIRED_EVENT, onExpired);
    return () => window.removeEventListener(SESSION_EXPIRED_EVENT, onExpired);
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    clearToken();
    const token = await api.login({ email, password });
    setToken(token.access_token);
    try {
      const me = await api.me();
      setUserState(me);
      setStatus('signed-in');
      setSessionExpired(false);
      return me;
    } catch (error) {
      clearToken();
      throw error;
    }
  }, []);

  const logout = useCallback(() => {
    clearToken();
    setUserState(null);
    setStatus('guest');
    setSessionExpired(false);
  }, []);

  const setUser = useCallback((next: UserOut) => setUserState(next), []);

  const value = useMemo(
    () => ({ status, user, sessionExpired, login, logout, setUser }),
    [status, user, sessionExpired, login, logout, setUser],
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthValue {
  const value = useContext(AuthContext);
  if (!value) throw new Error('useAuth must be used inside AuthProvider');
  return value;
}

/** Where a signed-in user of this role lands. */
export function homeFor(role: Role): string {
  return role === 'seeker' ? paths.seeker.recommended : paths.company.jobs;
}

/** A `?next=` value is followed only when it is a path on this site (no scheme, no `//host`). */
export function safeNext(next: string | null): string | null {
  return next && next.startsWith('/') && !next.startsWith('//') && !next.startsWith('/\\') ? next : null;
}

/** Where to send a user right after signing in: consent first when the server asks for it (D17). */
export function afterSignIn(user: UserOut, next: string | null): string {
  const target = safeNext(next) ?? homeFor(user.role);
  if (user.consent_required) return `${paths.consent}?next=${encodeURIComponent(target)}`;
  return target;
}
