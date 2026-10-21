"use client";

import * as React from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth-context";
import { emailLogin, sendEmailCode,
  continueGenericLogin,
} from "@/lib/passport-api";
import { useCaptcha } from "@/lib/use-captcha";
import { CaptchaField } from "@/components/CaptchaField";
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
 * 邮箱验证码登录（2026-08-27）：已有账户直接登录；新邮箱自动注册。
 * 「验证码即登录即注册」——无需单独注册页。
 */
export default function EmailLoginPage() {
  const router = useRouter();
  const { user, login } = useAuth();

  const [email, setEmail] = React.useState("");
  const [code, setCode] = React.useState("");
  const [sent, setSent] = React.useState(false);
  const [sending, setSending] = React.useState(false);
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [countdown, setCountdown] = React.useState(0);
  const captcha = useCaptcha();

  React.useEffect(() => {
    if (user) router.replace("/profile/basic");
  }, [user, router]);

  // 重发倒计时
  React.useEffect(() => {
    if (countdown <= 0) return;
    const t = setTimeout(() => setCountdown((s) => s - 1), 1000);
    return () => clearTimeout(t);
  }, [countdown]);

  const emailValid = /^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email.trim());

  const onSend = async () => {
    if (sending || !emailValid || countdown > 0) return;
    if (captcha.required && !captcha.token) {
      setError("请先完成人机验证");
      return;
    }
    setSending(true);
    setError(null);
    try {
      await sendEmailCode(email.trim(), "login", null, captcha.token);
      setSent(true);
      setCountdown(60);
      // hCaptcha token 一次性：发送成功后重置，下次需要时重新验证
      captcha.reset();
    } catch (err: unknown) {
      // 验证码相关错误由 useCaptcha 接管（弹组件 / 提示重试）
      if (captcha.interpret(err)) return;
      setError(err instanceof Error ? err.message : "发送失败，请稍后重试");
    } finally {
      setSending(false);
    }
  };

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (loading) return;
    if (!sent) {
      setError("请先获取验证码");
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const tokens = await emailLogin(email.trim(), code.trim());
      await login(tokens.access, tokens.refresh);
      // 通用 OAuth 入口：有 oticket 时回接入方而非资料页
      if (await continueGenericLogin(tokens.access)) return;
      router.replace("/profile/basic");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "登录失败，请稍后重试");
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
          <h1 className="text-2xl font-bold tracking-tight text-ink">邮箱验证码登录</h1>
          <p className="mt-2 text-[15px] leading-relaxed text-ink-muted">
            未注册的邮箱将自动创建通行证账户
          </p>
        </div>

        {error && (
          <div className="mb-6 rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
            {error}
          </div>
        )}

        <form onSubmit={onSubmit} className="space-y-4">
          <div>
            <label className="mb-1.5 block text-sm font-medium text-ink">邮箱</label>
            <input
              type="email"
              autoComplete="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="请输入邮箱地址"
              className="w-full rounded-xl border border-line bg-surface px-3.5 py-3 text-[15px] text-ink outline-none transition-colors focus:border-accent min-h-[48px]"
              required
            />
          </div>

          <div>
            <label className="mb-1.5 block text-sm font-medium text-ink">验证码</label>
            <div className="flex gap-2">
              <input
                type="text"
                inputMode="numeric"
                maxLength={6}
                autoComplete="one-time-code"
                value={code}
                onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))}
                placeholder="6 位数字验证码"
                className="w-full rounded-xl border border-line bg-surface px-3.5 py-3 text-[15px] tracking-widest text-ink outline-none transition-colors focus:border-accent min-h-[48px]"
                required
              />
              <button
                type="button"
                onClick={onSend}
                disabled={!emailValid || sending || countdown > 0}
                className="shrink-0 rounded-xl border border-accent/40 px-4 text-sm font-medium text-accent transition-colors hover:bg-accent-soft disabled:opacity-50 disabled:hover:bg-transparent min-h-[48px] whitespace-nowrap"
              >
                {sending ? "发送中…" : countdown > 0 ? `${countdown}s 后重发` : sent ? "重新发送" : "获取验证码"}
              </button>
            </div>
            {sent && (
              <p className="mt-1.5 text-xs text-ink-muted">
                验证码已发送至 {email.trim()}（含垃圾邮件箱），10 分钟内有效
              </p>
            )}
          </div>

          <CaptchaField captcha={captcha} />

          <button
            type="submit"
            disabled={loading}
            className="flex w-full items-center justify-center gap-2 rounded-2xl bg-accent px-5 py-3.5 text-[15px] font-semibold text-white shadow-sm transition-all hover:bg-accent/90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/40 focus-visible:ring-offset-2 disabled:opacity-60 min-h-[52px]"
          >
            {loading ? (
              <>
                <span className="h-4 w-4 animate-spin rounded-full border-2 border-white border-t-transparent" />
                登录中…
              </>
            ) : (
              "登录 / 注册"
            )}
          </button>
        </form>

        <div className="mt-6 text-sm">
          <Link
            href="/login"
            className="inline-flex items-center gap-1.5 text-ink-muted transition-colors hover:text-ink"
          >
            <ArrowLeftIcon className="h-4 w-4" />
            返回其他登录方式
          </Link>
        </div>
      </div>
    </div>
  );
}
