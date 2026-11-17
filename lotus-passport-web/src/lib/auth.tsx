'use client';

import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { api, ApiException, AUTH_EXPIRED_EVENT } from './api';
import { callbackUri, createPkcePair, storeVerifier } from './pkce';
import { clearTokens, getAccess, setTokens } from './tokens';
import type { Provider, TokenPair, UserInfo } from './types';

type AuthStatus = 'booting' | 'guest' | 'authed';

interface AuthContextValue {
  status: AuthStatus;
  user: UserInfo | null;
  loginWithPassword: (identifier: string, password: string, captcha?: string) => Promise<UserInfo>;
  loginWithEmail: (email: string, code: string) => Promise<{ user: UserInfo; created: boolean }>;
  startOAuth: (provider: Provider) => Promise<void>;
  startDevLogin: (provider: Provider) => Promise<void>;
  bindProvider: (provider: Provider) => Promise<void>;
  completeTicket: (ticket: string) => Promise<void>;
  refreshUser: () => Promise<void>;
  resumeSession: () => Promise<void>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<AuthStatus>('booting');
  const [user, setUser] = useState<UserInfo | null>(null);
  const restored = useRef(false);

  const loadUser = useCallback(async (): Promise<UserInfo> => {
    const me = await api<UserInfo>('/userinfo/');
    setUser(me);
    setStatus('authed');
    return me;
  }, []);

  useEffect(() => {
    if (restored.current) return;
    restored.current = true;
    if (!getAccess()) {
      setStatus('guest');
      return;
    }
    loadUser().catch(() => {
      clearTokens();
      setUser(null);
      setStatus('guest');
    });
  }, [loadUser]);

  useEffect(() => {
    const onExpired = () => {
      clearTokens();
      setUser(null);
      setStatus('guest');
    };
    window.addEventListener(AUTH_EXPIRED_EVENT, onExpired);
    return () => window.removeEventListener(AUTH_EXPIRED_EVENT, onExpired);
  }, []);

  const adoptTokens = useCallback(
    async (pair: TokenPair): Promise<UserInfo> => {
      setTokens(pair);
      return loadUser();
    },
    [loadUser],
  );

  const loginWithPassword = useCallback(
    async (identifier: string, password: string, captcha?: string) => {
      const pair = await api<TokenPair>('/login/', {
        method: 'POST',
        auth: false,
        body: { identifier, password, ...(captcha ? { captcha } : {}) },
      });
      return adoptTokens(pair);
    },
    [adoptTokens],
  );

  const loginWithEmail = useCallback(
    async (email: string, code: string) => {
      const pair = await api<TokenPair>('/login/email/', {
        method: 'POST',
        auth: false,
        body: { email, code },
      });
      const me = await adoptTokens(pair);
      return { user: me, created: Boolean(pair.created) };
    },
    [adoptTokens],
  );

  const startOAuth = useCallback(async (provider: Provider) => {
    const { verifier, challenge } = await createPkcePair();
    storeVerifier(verifier);
    const qs = new URLSearchParams({
      redirect_uri: callbackUri(),
      code_challenge: challenge,
      code_challenge_method: 'S256',
    });
    const data = await api<{ authorize_url: string }>(`/oauth/${provider}/login/?${qs}`, { auth: false });
    window.location.assign(data.authorize_url);
  }, []);

  const startDevLogin = useCallback(async (provider: Provider) => {
    const { verifier, challenge } = await createPkcePair();
    storeVerifier(verifier);
    const qs = new URLSearchParams({
      provider,
      redirect_uri: callbackUri(),
      code_challenge: challenge,
      code_challenge_method: 'S256',
    });
    window.location.assign(`/api/v1/dev/login/?${qs}`);
  }, []);

  const bindProvider = useCallback(async (provider: Provider) => {
    const qs = new URLSearchParams({ redirect_uri: callbackUri() });
    const data = await api<{ authorize_url: string }>(`/oauth/${provider}/bind/?${qs}`, { method: 'POST' });
    window.location.assign(data.authorize_url);
  }, []);

  const completeTicket = useCallback(async (ticket: string) => {
    const data = await api<{ redirect_url: string }>('/oauth/continue/', {
      method: 'POST',
      body: { ticket },
    });
    window.location.assign(data.redirect_url);
  }, []);

  const refreshUser = useCallback(async () => {
    await loadUser();
  }, [loadUser]);

  const resumeSession = useCallback(async () => {
    try {
      await loadUser();
    } catch {
      clearTokens();
      setUser(null);
      setStatus('guest');
      throw new Error('session resume failed');
    }
  }, [loadUser]);

  const logout = useCallback(async () => {
    const refresh = typeof window !== 'undefined' ? window.localStorage.getItem('lp.refresh') ?? '' : '';
    try {
      await api('/logout/', { method: 'POST', body: { refresh_token: refresh } });
    } catch (err) {
      if (!(err instanceof ApiException) || err.status !== 401) {
        /* 登出尽力而为：服务端吊销失败不阻塞本地清退 */
      }
    }
    clearTokens();
    setUser(null);
    setStatus('guest');
  }, []);

  const value = useMemo<AuthContextValue>(
    () => ({
      status,
      user,
      loginWithPassword,
      loginWithEmail,
      startOAuth,
      startDevLogin,
      bindProvider,
      completeTicket,
      refreshUser,
      resumeSession,
      logout,
    }),
    [status, user, loginWithPassword, loginWithEmail, startOAuth, startDevLogin, bindProvider, completeTicket, refreshUser, resumeSession, logout],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within AuthProvider');
  return ctx;
}