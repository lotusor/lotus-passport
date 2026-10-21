"use client";

import * as React from "react";
import Link from "next/link";
import { requestPasswordReset, ApiException } from "@/lib/passport-api";
import { Sparkles } from "@/components/icons";

function ArrowLeftIcon({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round">
      <path d="M19 12H5" />
      <path d="M12 19l-7-7 7-7" />
    </svg>
  );
}

/**
 * 忘记密码 — 请求重置邮件。
 *
 * 低成本方案（2026-08-27）：免费 SMTP + Redis 一次性 token。
 * 未配置邮件服务时后端返回 503，页面提示改用「第三方登录后重设」。
 */
export default function ForgotPasswordPage() {
  const [identifier, setIdentifier] = React.useState("");
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [done, setDone] = React.useState(false);

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (loading) return;
    setLoading(true);
    setError(null);
    try {
      await requestPasswordReset(identifier.trim());
      setDone(true);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "请求失败，请稍后重试";
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
          <h1 className="text-2xl font-bold tracking-tight text-ink">找回密码</h1>
          <p className="mt-2 text-[15px] leading-relaxed text-ink-muted">
            输入账号名或邮箱，我们将发送密码重置链接
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
              如果该账户存在且绑定了邮箱，重置邮件已发送，请注意查收（含垃圾邮件箱）。
              链接 30 分钟内有效，仅可使用一次。
            </div>
            <Link
              href="/login/password"
              className="flex w-full items-center justify-center gap-2 rounded-2xl bg-accent px-5 py-3.5 text-[15px] font-semibold text-white shadow-sm transition-all hover:bg-accent/90 min-h-[52px]"
            >
              返回密码登录
            </Link>
          </div>
        ) : (
          <>
            <form onSubmit={onSubmit} className="space-y-4">
              <div>
                <label className="mb-1.5 block text-sm font-medium text-ink">
                  账号名 / 邮箱
                </label>
                <input
                  type="text"
                  autoComplete="username"
                  value={identifier}
                  onChange={(e) => setIdentifier(e.target.value)}
                  placeholder="请输入账号名或邮箱"
                  className="w-full rounded-xl border border-line bg-surface px-3.5 py-3 text-[15px] text-ink outline-none transition-colors focus:border-accent min-h-[48px]"
                  required
                />
              </div>
              <button
                type="submit"
                disabled={loading}
                className="flex w-full items-center justify-center gap-2 rounded-2xl bg-accent px-5 py-3.5 text-[15px] font-semibold text-white shadow-sm transition-all hover:bg-accent/90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/40 focus-visible:ring-offset-2 disabled:opacity-60 min-h-[52px]"
              >
                {loading ? (
                  <>
                    <span className="h-4 w-4 animate-spin rounded-full border-2 border-white border-t-transparent" />
                    发送中…
                  </>
                ) : (
                  "发送重置邮件"
                )}
              </button>
            </form>
            <p className="mt-6 text-center text-xs leading-relaxed text-ink-muted">
              已绑定 GitHub / QQ 的用户：可直接用第三方登录，进入「账户安全 →
              密码」重设，无需邮件。
            </p>
          </>
        )}

        <div className="mt-6 text-sm">
          <Link
            href="/login/password"
            className="inline-flex items-center gap-1.5 text-ink-muted transition-colors hover:text-ink"
          >
            <ArrowLeftIcon className="h-4 w-4" />
            返回密码登录
          </Link>
        </div>
      </div>
    </div>
  );
}
