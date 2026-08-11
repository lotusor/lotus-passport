"use client";

import * as React from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth-context";
import {
  getOAuthLoginUrl,
  fetchDevStatus,
  getDevLoginUrl,
} from "@/lib/passport-api";
import { Sparkles } from "@/components/icons";

type OAuthProvider = {
  id: "github" | "wechat" | "qq";
  name: string;
  hint: string;
  icon: React.FC<{ className?: string }>;
  bg: string;
  ring: string;
};

const providers: OAuthProvider[] = [
  {
    id: "github",
    name: "GitHub",
    hint: "使用 GitHub 账号登录",
    icon: GitHubIcon,
    bg: "bg-[#24292f] hover:bg-[#1b1f23]",
    ring: "focus-visible:ring-[#24292f]/40",
  },
  {
    id: "wechat",
    name: "微信",
    hint: "使用微信扫码登录",
    icon: WeChatIcon,
    bg: "bg-[#07C160] hover:bg-[#06AD56]",
    ring: "focus-visible:ring-[#07C160]/40",
  },
  {
    id: "qq",
    name: "QQ",
    hint: "使用 QQ 账号登录",
    icon: QQIcon,
    bg: "bg-[#12B7F5] hover:bg-[#0EA6DD]",
    ring: "focus-visible:ring-[#12B7F5]/40",
  },
];

export default function LoginPage() {
  const router = useRouter();
  const { user, loading: restoring } = useAuth();
  const [loading, setLoading] = React.useState<string | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const [devProviders, setDevProviders] = React.useState<string[]>([]);

  // 已登录 → 直接跳走（落地到资料主页，便于首次 OAuth 登录后引导设置账号名/密码）
  React.useEffect(() => {
    if (user) router.replace("/profile/basic");
  }, [user, router]);

  // 探测后端是否开启了模拟登录（仅本地开发；生产返回空数组）
  React.useEffect(() => {
    let alive = true;
    fetchDevStatus().then((s) => {
      if (alive && s.dev_login_enabled) setDevProviders(s.providers);
    });
    return () => {
      alive = false;
    };
  }, []);

  const handleDevLogin = (provider: string) => {
    setLoading(`dev-${provider}`);
    const redirectUri = `${window.location.origin}/auth/callback`;
    window.location.href = getDevLoginUrl(provider, redirectUri);
  };

  const handleLogin = async (provider: "github" | "wechat" | "qq") => {
    setLoading(provider);
    setError(null);
    try {
      // 让后端把签发的 JWT 用 fragment 弹回 SPA 的回调页
      const redirectUri = `${window.location.origin}/auth/callback`;
      const { authorize_url } = await getOAuthLoginUrl(provider, redirectUri);
      window.location.href = authorize_url;
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "请求失败，请稍后重试";
      setError(msg);
    } finally {
      setLoading(null);
    }
  };

  // 恢复会话期间与即将跳走时，不要闪出登录按钮
  if (restoring || user) {
    return (
      <div className="grid min-h-[100dvh] place-items-center bg-surface">
        <div className="flex flex-col items-center gap-3 text-ink-muted">
          <span className="h-8 w-8 animate-spin rounded-full border-2 border-line border-t-accent" />
          <span className="text-sm">正在验证登录状态…</span>
        </div>
      </div>
    );
  }

  return (
    <div className="flex min-h-[100dvh] items-center justify-center px-4">
      <div className="w-full max-w-[400px]">
        {/* Brand */}
        <div className="mb-10 text-center">
          <span className="mx-auto mb-4 grid h-14 w-14 place-items-center rounded-2xl bg-accent text-white shadow-lg">
            <Sparkles className="h-7 w-7" />
          </span>
          <h1 className="text-2xl font-bold tracking-tight text-ink">
            欢迎使用莲花通行证
          </h1>
          <p className="mt-2 text-[15px] leading-relaxed text-ink-muted">
            Lotus Passport — 统一身份认证中心
          </p>
        </div>

        {/* Error banner */}
        {error && (
          <div className="mb-6 rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
            {error}
          </div>
        )}

        {/* OAuth buttons */}
        <div className="space-y-3">
          {providers.map((p) => (
            <button
              key={p.id}
              onClick={() => handleLogin(p.id)}
              disabled={loading !== null}
              aria-label={p.name}
              className={`${p.bg} ${p.ring} flex w-full items-center gap-4 rounded-2xl px-5 py-4 text-left text-white shadow-sm transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-2 disabled:opacity-60 min-h-[56px]`}
            >
              <p.icon className="h-6 w-6 shrink-0" />
              <div className="min-w-0">
                <p className="text-sm font-semibold">
                  {loading === p.id ? "正在跳转..." : p.name}
                </p>
                <p className="text-xs text-white/70">{p.hint}</p>
              </div>
              {loading === p.id && (
                <span className="ml-auto h-4 w-4 animate-spin rounded-full border-2 border-white border-t-transparent" />
              )}
            </button>
          ))}
        </div>

        {/* 密码登录入口 */}
        <div className="mt-6 flex flex-col items-center gap-2">
          <p className="text-xs text-ink-muted">
            若已有账户，可选择密码登录
          </p>
          <Link
            href="/login/password"
            className="inline-flex items-center gap-1.5 rounded-xl border border-line bg-surface px-4 py-2.5 text-sm font-medium text-ink transition-colors hover:border-accent/40 hover:text-accent min-h-[44px]"
          >
            使用密码登录
          </Link>
        </div>

        {/* 开发模式：未配置真实 OAuth 应用时用它跑通全链路 */}
        {devProviders.length > 0 && (
          <div className="mt-8 rounded-2xl border border-dashed border-amber-300 bg-amber-50/60 p-4">
            <div className="mb-3 flex items-center gap-2">
              <span className="rounded-md bg-amber-400/20 px-2 py-0.5 text-[11px] font-semibold text-amber-700">
                DEV
              </span>
              <p className="text-xs text-amber-800">
                后端处于 DEBUG 模式，可用模拟账号直接登录
              </p>
            </div>
            <div className="flex flex-wrap gap-2">
              {devProviders.map((p) => (
                <button
                  key={p}
                  onClick={() => handleDevLogin(p)}
                  disabled={loading !== null}
                  className="rounded-xl border border-amber-300 bg-white px-3 py-2 text-xs font-medium text-amber-900 transition hover:bg-amber-100 disabled:opacity-60"
                >
                  {loading === `dev-${p}` ? "跳转中..." : `模拟 ${p}`}
                </button>
              ))}
            </div>
          </div>
        )}

        <p className="mt-8 text-center text-xs text-ink-muted">
          登录即表示你同意莲花通行证的服务条款与隐私政策
        </p>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Simple inline SVG icons for the three providers
// ---------------------------------------------------------------------------
function GitHubIcon({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="currentColor">
      <path d="M12 0C5.37 0 0 5.37 0 12c0 5.3 3.438 9.8 8.205 11.385.6.113.82-.258.82-.577 0-.285-.01-1.04-.015-2.04-3.338.724-4.042-1.61-4.042-1.61-.546-1.385-1.335-1.755-1.335-1.755-1.087-.744.084-.729.084-.729 1.205.084 1.838 1.236 1.838 1.236 1.07 1.835 2.809 1.305 3.495.998.108-.776.417-1.305.76-1.605-2.665-.3-5.466-1.332-5.466-5.93 0-1.31.465-2.38 1.235-3.22-.135-.303-.54-1.523.105-3.176 0 0 1.005-.322 3.3 1.23.96-.267 1.98-.399 3-.405 1.02.006 2.04.138 3 .405 2.28-1.552 3.285-1.23 3.285-1.23.645 1.653.24 2.873.12 3.176.765.84 1.23 1.91 1.23 3.22 0 4.61-2.805 5.625-5.475 5.92.42.36.81 1.096.81 2.22 0 1.605-.015 2.896-.015 3.286 0 .315.21.69.825.57C20.565 21.795 24 17.295 24 12c0-6.63-5.37-12-12-12z" />
    </svg>
  );
}

function WeChatIcon({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="currentColor">
      <path d="M8.5 11a1.5 1.5 0 1 1 0-3 1.5 1.5 0 0 1 0 3zm5 0a1.5 1.5 0 1 1 0-3 1.5 1.5 0 0 1 0 3zM12 2C6.477 2 2 5.92 2 10.8c0 2.52 1.37 4.78 3.5 6.3L4.5 20l4.5-2.5c.97.26 1.98.4 3 .4.35 0 .7-.02 1.04-.05A5.98 5.98 0 0 1 12 16c0-3.3 2.7-6 6-6 .34 0 .67.03 1 .08C18.46 5.65 15.46 2 12 2z" />
      <path d="M18 11a5 5 0 1 0 0 10 5 5 0 0 0 0-10zm-2.5 3.5a.75.75 0 1 1 0-1.5.75.75 0 0 1 0 1.5zm3.5 0a.75.75 0 1 1 0-1.5.75.75 0 0 1 0 1.5z" />
    </svg>
  );
}

// QQ 互联官方 16×16 小图标（红 #EA1C27 + 白 + 黑 企鹅）。
// UI 规范允许"小图标 + 自定义文字"组合：使用未修改的官方小图标，
// 套用项目自定义的蓝色主题按钮，与 GitHub / 微信保持同款风格。
// https://wiki.connect.qq.com/网站前端页面规范 §1.3 / §2.3
function QQIcon({ className }: { className?: string }) {
  return (
    // eslint-disable-next-line @next/next/no-img-element
    <img
      src="/qq-icon-official.png"
      alt=""
      width={16}
      height={16}
      draggable={false}
      className={className}
    />
  );
}