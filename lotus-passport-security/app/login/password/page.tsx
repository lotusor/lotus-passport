"use client";

import * as React from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth-context";
import { passwordLogin, ApiException } from "@/lib/passport-api";
import { Sparkles, Eye, EyeOff } from "@/components/icons";

const HCAPTCHA_SITE_KEY = process.env.NEXT_PUBLIC_HCAPTCHA_SITE_KEY;

declare global {
  interface Window {
    hcaptcha?: {
      render: (el: HTMLElement, opts: Record<string, unknown>) => number;
      remove: (widgetId: number) => void;
      reset: (widgetId?: number) => void;
    };
  }
}

function ArrowLeftIcon({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round">
      <path d="M19 12H5" />
      <path d="M12 19l-7-7 7-7" />
    </svg>
  );
}

export default function PasswordLoginPage() {
  const router = useRouter();
  const { user, login } = useAuth();

  const [identifier, setIdentifier] = React.useState("");
  const [password, setPassword] = React.useState("");
  const [showPw, setShowPw] = React.useState(false);
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [locked, setLocked] = React.useState(false);
  const [lockRemaining, setLockRemaining] = React.useState(0);
  const [showCaptcha, setShowCaptcha] = React.useState(false);
  const [captchaToken, setCaptchaToken] = React.useState<string | null>(null);
  const [captchaError, setCaptchaError] = React.useState<string | null>(null);
  const captchaRef = React.useRef<HTMLDivElement | null>(null);
  const captchaRendered = React.useRef(false);

  // 已登录 → 直接跳走
  React.useEffect(() => {
    if (user) router.replace("/profile/basic");
  }, [user, router]);

  // 锁定倒计时：lockRemaining 归零后自动解除锁定
  React.useEffect(() => {
    if (!locked) return;
    const t = setInterval(() => {
      setLockRemaining((s) => {
        if (s <= 1) {
          setLocked(false);
          return 0;
        }
        return s - 1;
      });
    }, 1000);
    return () => clearInterval(t);
  }, [locked]);

  // 加载并渲染 hCaptcha 组件（仅当后端要求验证码时）
  React.useEffect(() => {
    if (!showCaptcha || !HCAPTCHA_SITE_KEY || captchaRendered.current) return;
    let cancelled = false;
    const renderWidget = () => {
      if (cancelled || !captchaRef.current || !window.hcaptcha) return;
      captchaRendered.current = true;
      window.hcaptcha.render(captchaRef.current, {
        sitekey: HCAPTCHA_SITE_KEY,
        theme: "light",
        callback: (t: string) => setCaptchaToken(t),
        "expired-callback": () => setCaptchaToken(null),
        "error-callback": () => setCaptchaError("人机验证组件加载失败，请刷新页面重试"),
      });
    };
    if (window.hcaptcha?.render) {
      renderWidget();
    } else {
      const src = "https://js.hcaptcha.com/1/api.js";
      const existing = document.querySelector(`script[src="${src}"]`);
      if (!existing) {
        const s = document.createElement("script");
        s.src = src;
        s.async = true;
        s.onload = () => renderWidget();
        document.body.appendChild(s);
      } else {
        const poll = setInterval(() => {
          if (window.hcaptcha?.render) {
            clearInterval(poll);
            renderWidget();
          }
        }, 200);
        setTimeout(() => clearInterval(poll), 6000);
      }
    }
    return () => {
      cancelled = true;
    };
  }, [showCaptcha]);

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (loading) return;
    // 已要求验证码但未完成时拦截
    if (showCaptcha && !captchaToken) {
      setError("请先完成人机验证");
      return;
    }
    setLoading(true);
    setError(null);
    setCaptchaError(null);
    try {
      const tokens = await passwordLogin(
        identifier.trim(),
        password,
        captchaToken || undefined
      );
      await login(tokens.access, tokens.refresh);
      router.replace("/profile/basic");
    } catch (err: unknown) {
      if (
        err instanceof ApiException &&
        err.errorCode === "locked" &&
        typeof err.retryAfter === "number"
      ) {
        setError(null);
        setLocked(true);
        setLockRemaining(err.retryAfter);
      } else if (err instanceof ApiException && err.captchaRequired) {
        setError(null);
        setShowCaptcha(true);
      } else if (err instanceof ApiException && err.errorCode === "captcha_invalid") {
        setCaptchaToken(null);
        setCaptchaError("人机验证失败，请重新完成验证");
      } else {
        const msg = err instanceof Error ? err.message : "登录失败，请稍后重试";
        setError(msg);
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex min-h-[100dvh] items-center justify-center px-4">
      <div className="w-full max-w-[400px]">
        {/* Brand */}
        <div className="mb-10 text-center">
          <span className="mx-auto mb-4 grid h-14 w-14 place-items-center rounded-2xl bg-accent text-white shadow-lg">
            <Sparkles className="h-7 w-7" />
          </span>
          <h1 className="text-2xl font-bold tracking-tight text-ink">
            密码登录
          </h1>
          <p className="mt-2 text-[15px] leading-relaxed text-ink-muted">
            使用账号名 / 邮箱与密码登录莲花通行证
          </p>
        </div>

        {/* Locked banner (account brute-force lockout) */}
        {locked && (
          <div className="mb-6 rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
            账户已锁定，请于 {Math.floor(lockRemaining / 60)} 分 {lockRemaining % 60} 秒后重试
          </div>
        )}

        {/* Error banner */}
        {error && (
          <div className="mb-6 rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
            {error}
          </div>
        )}

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

          <div>
            <label className="mb-1.5 block text-sm font-medium text-ink">
              密码
            </label>
            <div className="relative">
              <input
                type={showPw ? "text" : "password"}
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="请输入密码"
                className="w-full rounded-xl border border-line bg-surface px-3.5 py-3 pr-11 text-[15px] text-ink outline-none transition-colors focus:border-accent min-h-[48px]"
                required
              />
              <button
                type="button"
                onClick={() => setShowPw((v) => !v)}
                aria-label={showPw ? "隐藏密码" : "显示密码"}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-ink-muted transition-colors hover:text-ink"
              >
                {showPw ? (
                  <EyeOff className="h-5 w-5" />
                ) : (
                  <Eye className="h-5 w-5" />
                )}
              </button>
            </div>
          </div>

          {showCaptcha && (
            <div>
              <label className="mb-1.5 block text-sm font-medium text-ink">
                人机验证
              </label>
              {HCAPTCHA_SITE_KEY ? (
                <div ref={captchaRef} />
              ) : (
                <div className="rounded-xl border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-700">
                  验证码组件未配置（缺少 NEXT_PUBLIC_HCAPTCHA_SITE_KEY）
                </div>
              )}
              {captchaError && (
                <p className="mt-1.5 text-sm text-red-600">{captchaError}</p>
              )}
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
                登录中…
              </>
            ) : (
              "登录"
            )}
          </button>
        </form>

        <div className="mt-6 text-center">
          <Link
            href="/login"
            className="inline-flex items-center gap-1.5 text-sm text-ink-muted transition-colors hover:text-ink"
          >
            <ArrowLeftIcon className="h-4 w-4" />
            返回其他登录方式
          </Link>
        </div>

        <p className="mt-8 text-center text-xs text-ink-muted">
          还没有账户？使用上方第三方登录即可创建通行证
        </p>
      </div>
    </div>
  );
}
