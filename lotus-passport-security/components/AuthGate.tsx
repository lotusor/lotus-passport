"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth-context";

/**
 * 受保护页面的登录守卫。
 *
 * 为什么这么写：
 * - `loading=true` 时（正在从 localStorage 恢复会话 / 调后端拉 userinfo）必须显示加载态，
 *   不能立刻判定为"未登录"——否则会误伤正在恢复会话的正常用户，把他踢去登录页。
 * - `loading=false` 且 `user` 仍为空，才是真·未登录，此时 `router.replace("/login")`。
 * - 已登录则渲染 children。
 *
 * 必须位于 <AuthProvider> 内（根布局已包裹）。公开页面（/login、/auth/callback）不要包它。
 */
export function AuthGate({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth();
  const router = useRouter();

  React.useEffect(() => {
    if (!loading && !user) {
      router.replace("/login");
    }
  }, [loading, user, router]);

  if (loading || !user) {
    return (
      <div className="grid min-h-[100dvh] place-items-center bg-surface">
        <div className="flex flex-col items-center gap-3 text-ink-muted">
          <span className="h-8 w-8 animate-spin rounded-full border-2 border-line border-t-accent" />
          <span className="text-sm">正在验证登录状态…</span>
        </div>
      </div>
    );
  }

  return <>{children}</>;
}
