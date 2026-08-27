"use client";

import * as React from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { confirmPasswordReset } from "@/lib/passport-api";
import { Sparkles, Eye, EyeOff } from "@/components/icons";

/**
 * 密码重置确认页（邮件链接落地页 /login/password/reset?token=...）。
 * 成功后后端吊销该账户全部会话，跳回登录页用新密码重新登录。
 */
export default function ResetPasswordPage() {
  const router = useRouter();
  const [token, setToken] = React.useState("");
  const [password, setPassword] = React.useState("");
  const [showPw, setShowPw] = React.useState(false);
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [done, setDone] = React.useState(false);

  React.useEffect(() => {
    const t = new URLSearchParams(window.location.search).get("token") || "";
    setToken(t);
    if (!t) {
      setError("缺少重置 token，请从邮件中的链接进入本页。");
    }
  }, []);

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (loading || !token) return;
    if (password.length < 8 || !/[A-Za-z]/.test(password) || !/\d/.test(password)) {
      setError("密码至少 8 位，且需同时包含字母和数字");
      return;
    }
    setLoading(true);
    setError(null);
    try {
      await confirmPasswordReset(token, password);
      setDone(true);
      setTimeout(() => router.replace("/login/password"), 2200);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "重置失败，请稍后重试";
      setError(msg);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex min-h-[100dvh] items-center justify-center px-4">
      <div className="w-full max-w-[400px]">
        <div className="mb-10 text-center">
          <span className="mx-auto mb-4 grid h-14 w-14 place-items-center rounded-2xl bg-accent text-white shadow-lg">
            <Sparkles className="h-7 w-7" />
          </span>
          <h1 className="text-2xl font-bold tracking-tight text-ink">设置新密码</h1>
          <p className="mt-2 text-[15px] leading-relaxed text-ink-muted">
            重置成功后所有已登录会话将被注销
          </p>
        </div>

        {error && (
          <div className="mb-6 rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
            {error}
          </div>
        )}

        {done ? (
          <div className="space-y-6">
            <div className="rounded-2xl border border-emerald-200 bg-emerald-50 px-4 py-4 text-sm leading-relaxed text-emerald-800">
              密码已重置，正在跳转登录页，请使用新密码登录…
            </div>
          </div>
        ) : (
          <form onSubmit={onSubmit} className="space-y-4">
            <div>
              <label className="mb-1.5 block text-sm font-medium text-ink">新密码</label>
              <div className="relative">
                <input
                  type={showPw ? "text" : "password"}
                  autoComplete="new-password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="至少 8 位，含字母和数字"
                  className="w-full rounded-xl border border-line bg-surface px-3.5 py-3 pr-11 text-[15px] text-ink outline-none transition-colors focus:border-accent min-h-[48px]"
                  required
                  disabled={!token}
                />
                <button
                  type="button"
                  onClick={() => setShowPw((v) => !v)}
                  aria-label={showPw ? "隐藏密码" : "显示密码"}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-ink-muted transition-colors hover:text-ink"
                >
                  {showPw ? <EyeOff className="h-5 w-5" /> : <Eye className="h-5 w-5" />}
                </button>
              </div>
            </div>
            <button
              type="submit"
              disabled={loading || !token}
              className="flex w-full items-center justify-center gap-2 rounded-2xl bg-accent px-5 py-3.5 text-[15px] font-semibold text-white shadow-sm transition-all hover:bg-accent/90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/40 focus-visible:ring-offset-2 disabled:opacity-60 min-h-[52px]"
            >
              {loading ? (
                <>
                  <span className="h-4 w-4 animate-spin rounded-full border-2 border-white border-t-transparent" />
                  提交中…
                </>
              ) : (
                "重置密码"
              )}
            </button>
          </form>
        )}

        <div className="mt-6 text-sm">
          <Link
            href="/login"
            className="inline-flex items-center gap-1.5 text-ink-muted transition-colors hover:text-ink"
          >
            返回登录页
          </Link>
        </div>
      </div>
    </div>
  );
}
