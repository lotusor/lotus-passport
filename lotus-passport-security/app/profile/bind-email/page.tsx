"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth-context";
import { bindEmail, sendEmailCode, fetchUserInfo } from "@/lib/passport-api";
import { useCaptcha } from "@/lib/use-captcha";
import { CaptchaField } from "@/components/CaptchaField";
import { Sparkles, Eye, EyeOff } from "@/components/icons";

/**
 * 首次绑定邮箱（强制邮箱策略的落地页，2026-08-27）。
 *
 * OAuth（QQ/微信/私密 GitHub）登录建号可能拿不到邮箱——此类账户（以及存量
 * 无邮箱账户）登录后被 AuthGate 拦截到本页：输入目标邮箱 → 验证码发到该邮箱
 * → 验证通过 + （有密码账户）验密码后绑定。绑完才能使用其它功能。
 */
export default function BindEmailPage() {
  const router = useRouter();
  const { user, accessToken, logout, setUser } = useAuth();

  const [email, setEmail] = React.useState("");
  const [code, setCode] = React.useState("");
  const [password, setPassword] = React.useState("");
  const [showPw, setShowPw] = React.useState(false);
  const [sent, setSent] = React.useState(false);
  const [sending, setSending] = React.useState(false);
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [countdown, setCountdown] = React.useState(0);
  const captcha = useCaptcha();

  React.useEffect(() => {
    // 未登录 → 登录页；已有邮箱的用户不该在这里
    if (!user) {
      router.replace("/login");
      return;
    }
    if (user.email) router.replace("/profile/basic");
  }, [user, router]);

  React.useEffect(() => {
    if (countdown <= 0) return;
    const t = setTimeout(() => setCountdown((s) => s - 1), 1000);
    return () => clearTimeout(t);
  }, [countdown]);

  const emailValid = /^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email.trim());
  const needPassword = Boolean(user?.has_password);

  const onSend = async () => {
    if (sending || !emailValid || countdown > 0 || !accessToken) {
      if (!accessToken) setError("登录状态已失效，请重新登录");
      return;
    }
    if (captcha.required && !captcha.token) {
      setError("请先完成人机验证");
      return;
    }
    setSending(true);
    setError(null);
    try {
      await sendEmailCode(email.trim(), "bind", accessToken, captcha.token);
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
    if (!accessToken) {
      setError("登录状态已失效，请重新登录");
      return;
    }
    setLoading(true);
    setError(null);
    try {
      await bindEmail(accessToken, email.trim(), code.trim(), password || undefined);
      // 绑定成功：刷新 user（拿新 email）后回资料页
      const fresh = await fetchUserInfo(accessToken);
      setUser(fresh);
      router.replace("/profile/basic");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "绑定失败，请稍后重试");
    } finally {
      setLoading(false);
    }
  };

  const onSignOut = () => {
    logout();
    router.replace("/login");
  };

  return (
    <div className="flex min-h-[100dvh] items-center justify-center px-4">
      <div className="w-full max-w-[420px]">
        <div className="mb-8 text-center">
          <span className="mx-auto mb-4 grid h-14 w-14 place-items-center rounded-2xl bg-accent text-white shadow-lg">
            <Sparkles className="h-7 w-7" />
          </span>
          <h1 className="text-2xl font-bold tracking-tight text-ink">绑定邮箱</h1>
          <p className="mt-2 text-[15px] leading-relaxed text-ink-muted">
            为了保障账户安全（含找回密码），请为你的通行证绑定一个邮箱
          </p>
        </div>

        {error && (
          <div className="mb-6 rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
            {error}
          </div>
        )}

        <form onSubmit={onSubmit} className="space-y-4">
          <div>
            <label className="mb-1.5 block text-sm font-medium text-ink">邮箱地址</label>
            <input
              type="email"
              autoComplete="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="请输入你的邮箱地址"
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

          {needPassword && (
            <div>
              <label className="mb-1.5 block text-sm font-medium text-ink">
                账户密码
              </label>
              <div className="relative">
                <input
                  type={showPw ? "text" : "password"}
                  autoComplete="current-password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="验证身份需输入账户密码"
                  className="w-full rounded-xl border border-line bg-surface px-3.5 py-3 pr-11 text-[15px] text-ink outline-none transition-colors focus:border-accent min-h-[48px]"
                  required
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
          )}

          <button
            type="submit"
            disabled={loading}
            className="flex w-full items-center justify-center gap-2 rounded-2xl bg-accent px-5 py-3.5 text-[15px] font-semibold text-white shadow-sm transition-all hover:bg-accent/90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/40 focus-visible:ring-offset-2 disabled:opacity-60 min-h-[52px]"
          >
            {loading ? (
              <>
                <span className="h-4 w-4 animate-spin rounded-full border-2 border-white border-t-transparent" />
                绑定中…
              </>
            ) : (
              "绑定邮箱"
            )}
          </button>
        </form>

        <div className="mt-6 text-center text-sm">
          <button
            type="button"
            onClick={onSignOut}
            className="text-ink-muted transition-colors hover:text-ink min-h-[44px]"
          >
            换一个账户登录
          </button>
        </div>
      </div>
    </div>
  );
}
