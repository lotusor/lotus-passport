"use client";

import * as React from "react";
import {
  fetchUserInfo,
  refreshAccessToken,
  type UserInfo,
} from "@/lib/passport-api";

// ---------------------------------------------------------------------------
// Storage keys (localStorage)
// ---------------------------------------------------------------------------
const KEY_ACCESS = "passport_access";
const KEY_REFRESH = "passport_refresh";
const KEY_USER = "passport_user";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------
export interface AuthState {
  /** 已登录则 user 有值；未登录 / 加载中则为 null */
  user: UserInfo | null;
  accessToken: string | null;
  refreshToken: string | null;
  /** true = 正在从 localStorage 恢复或从后端拉取 userinfo */
  loading: boolean;
  /** 非空表示最近一次操作失败 */
  error: string | null;
}

export interface AuthContextValue extends AuthState {
  /** 从 localStorage 恢复会话（页面加载时调用一次） */
  restore: () => Promise<void>;
  /** 保存回调返回的 JWT 并拉取 userinfo */
  login: (access: string, refresh: string) => Promise<void>;
  /** 清除所有状态，删除 localStorage */
  logout: () => void;
  /** 用 refresh token 换新的 access token */
  refresh: () => Promise<string | null>;
  /** 用最新 UserInfo 覆盖当前用户态（保存资料后同步 hero 等展示） */
  setUser: (user: Partial<UserInfo>) => void;
  /** 清除错误 */
  clearError: () => void;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------
function load(key: string): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(key);
}
function save(key: string, value: string) {
  if (typeof window === "undefined") return;
  localStorage.setItem(key, value);
}
function remove(key: string) {
  if (typeof window === "undefined") return;
  localStorage.removeItem(key);
}

// ---------------------------------------------------------------------------
// Context
// ---------------------------------------------------------------------------
const AuthContext = React.createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [state, setState] = React.useState<AuthState>({
    user: null,
    accessToken: null,
    refreshToken: null,
    loading: false,
    error: null,
  });

  const set = (patch: Partial<AuthState>) =>
    setState((prev) => ({ ...prev, ...patch }));

  const restore = React.useCallback(async () => {
    const at = load(KEY_ACCESS);
    const rt = load(KEY_REFRESH);
    if (!at) {
      set({ loading: false });
      return;
    }
    set({ loading: true, accessToken: at, refreshToken: rt });
    try {
      const user = await fetchUserInfo(at);
      set({ user, loading: false, error: null });
    } catch {
      // Token expired? Try refresh
      if (rt) {
        try {
          const newAt = await refreshAccessToken(rt);
          save(KEY_ACCESS, newAt.access);
          const user = await fetchUserInfo(newAt.access);
          set({
            user,
            accessToken: newAt.access,
            loading: false,
            error: null,
          });
          return;
        } catch {
          // refresh also failed — clear everything
        }
      }
      // Token invalid / expired beyond repair
      remove(KEY_ACCESS);
      remove(KEY_REFRESH);
      remove(KEY_USER);
      set({ user: null, accessToken: null, refreshToken: null, loading: false });
    }
  }, []);

  const login = React.useCallback(async (access: string, refresh: string) => {
    save(KEY_ACCESS, access);
    save(KEY_REFRESH, refresh);
    set({ loading: true, accessToken: access, refreshToken: refresh });
    try {
      const user = await fetchUserInfo(access);
      save(KEY_USER, JSON.stringify(user));
      set({ user, loading: false, error: null });
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "登录失败";
      set({ error: msg, loading: false });
    }
  }, []);

  const logout = React.useCallback(() => {
    remove(KEY_ACCESS);
    remove(KEY_REFRESH);
    remove(KEY_USER);
    set({ user: null, accessToken: null, refreshToken: null, error: null });
  }, []);

  const refresh = React.useCallback(async (): Promise<string | null> => {
    const rt = state.refreshToken || load(KEY_REFRESH);
    if (!rt) return null;
    try {
      const result = await refreshAccessToken(rt);
      save(KEY_ACCESS, result.access);
      set({ accessToken: result.access });
      return result.access;
    } catch {
      logout();
      return null;
    }
  }, [state.refreshToken, logout]);

  const clearError = React.useCallback(() => set({ error: null }), []);

  // 合并而非整体替换：/profile/ 的 PATCH 返回体不含 providers/is_active，
  // 若整体替换会把这两个字段抹掉（登录方式徽章消失、is_active 丢失）。
  const setUser = React.useCallback(
    (u: Partial<UserInfo>) =>
      setState((prev) => ({
        ...prev,
        // 合并而非整体替换：保留 providers/is_active 等字段。prev.user 为空时
        // 仅在登录态下发生，这里按 UserInfo 合并（setUser 仅在已登录后调用）。
        user: (prev.user ? { ...prev.user, ...u } : u) as UserInfo,
      })),
    []
  );

  const value = React.useMemo<AuthContextValue>(
    () => ({ ...state, restore, login, logout, refresh, setUser, clearError }),
    [state, restore, login, logout, refresh, setUser, clearError]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = React.useContext(AuthContext);
  if (!ctx) throw new Error("useAuth 必须在 <AuthProvider> 内使用");
  return ctx;
}