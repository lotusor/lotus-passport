"use client";

import * as React from "react";
import { usePathname, useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth-context";

/**
 * 受保护页面的登录守卫 + 强制邮箱拦截（2026-08-27）。
 *
 * 为什么这么写：
 * - `loading=true` 时（正在从 localStorage 恢复会话 / 调后端拉 userinfo）必须显示加载态，
 *   不能立刻判定为"未登录"——否则会误伤正在恢复会话的正常用户，把他踢去登录页。
 * - `loading=false` 且 `user` 仍为空，才是真·未登录，此时 `router.replace("/login")`。
 * - 已登录但**无邮箱**（OAuth 拿不到邮箱的建号 + 存量账户）→ 拦截到
 *   `/profile/bind-email` 绑定邮箱（密码找回等能力的基础）。绑定页本身
 *   豁免此拦截（避免死循环）。
 * - 已登录且有邮箱则渲染 children。
 *
 * 必须位于 <AuthProvider> 内（根布局已包裹）。公开页面（/login、/auth/callback）不要包它。
 */
export function AuthGate({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth();
  const router = useRouter();
  const pathname = usePathname();

  const onBindPage = pathname?.startsWith("/profile/bind-email");

  React.useEffect(() => {
    if (loading) return;
    if (!user) {
      router.replace("/login");
      return;
    }
    // 强制邮箱：无邮箱账户拦截到绑定页（绑定页自身豁免）
    if (!user.email && !onBindPage) {
      router.replace("/profile/bind-email");
    }
  }, [loading, user, router, onBindPage]);

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

  // 无邮箱且不在绑定页 → 显示跳转中（effect 会 replace）
  if (!user.email && !onBindPage) {
    return (
      <div className="grid min-h-[100dvh] place-items-center bg-surface">
        <div className="flex flex-col items-center gap-3 text-ink-muted">
          <span className="h-8 w-8 animate-spin rounded-full border-2 border-line border-t-accent" />
          <span className="text-sm">正在前往邮箱绑定…</span>
        </div>
      </div>
    );
  }

  return <>{children}</>;
}
