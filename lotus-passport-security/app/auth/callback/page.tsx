"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth-context";
import { fetchUserInfo, type UserInfo } from "@/lib/passport-api";
import { Avatar } from "@/components/Avatar";
import { Check, X, Sparkles } from "@/components/icons";

const PROVIDER_LABELS: Record<string, string> = {
  github: "GitHub",
  wechat: "微信",
  qq: "QQ",
};

/**
 * OAuth / DEBUG 登录回调页。
 *
 * 后端在 OAuth 回调完成后重定向到：
 *   /auth/callback#access_token=...&refresh_token=...&passport_user_id=...
 *
 * 流程（参考 passport.eacm.cn 的登录确认环节）：
 *   1. 从 fragment 取出 token，先用 access_token 拉一次 userinfo 作为「预览」，不落库；
 *   2. 展示「是否以 [头像][昵称] 的身份登录」确认卡片；
 *   3. 用户点「确认登录」才真正调用 login() 存储令牌并完成登录；点「取消」则丢弃 token 返回登录页。
 *
 * 这样在登录回调的等待/确认期间就能把用户头像与昵称展示出来，避免无声无息地登录。
 */
type Status = "loading" | "preview" | "confirming" | "error" | "bound";

export default function AuthCallbackPage() {
  const router = useRouter();
  const { login, accessToken, setUser } = useAuth();
  const [status, setStatus] = React.useState<Status>("loading");
  const [message, setMessage] = React.useState("正在核对登录信息...");
  const [preview, setPreview] = React.useState<UserInfo | null>(null);
  const [tokens, setTokens] = React.useState<{ access: string; refresh: string } | null>(
    null
  );
  const [boundProvider, setBoundProvider] = React.useState<string | null>(null);

  React.useEffect(() => {
    // 第三方账号「绑定」回跳：后端 OAuthCallbackView 在 link_mode 下重定向到
    // /auth/callback?bound=<provider>&status=success。此时用户已登录，刷新
    // userinfo（含最新 providers）后跳回安全页即可看到新关联的平台。
    const search = new URLSearchParams(window.location.search);
    const bound = search.get("bound");
    if (bound) {
      setBoundProvider(bound);
      setStatus("bound");
      if (accessToken) {
        fetchUserInfo(accessToken)
          .then((u) => setUser(u))
          .catch(() => {});
      }
      const t = setTimeout(() => router.replace("/profile/security"), 1600);
      return () => clearTimeout(t);
    }

    const hash = window.location.hash.substring(1);
    const params = new URLSearchParams(hash);
    const access = params.get("access_token");
    const refresh = params.get("refresh_token");

    if (!access || !refresh) {
      setStatus("error");
      setMessage("未收到登录凭证，请返回登录页重试。");
      return;
    }
    setTokens({ access, refresh });

    // 仅拉预览，不存储 —— 等用户确认后再 login()
    fetchUserInfo(access)
      .then((u) => {
        setPreview(u);
        setStatus("preview");
      })
      .catch(() => {
        setStatus("error");
        setMessage("登录凭证无效或已过期，请重新登录。");
      });
  }, []);

  const confirmLogin = async () => {
    if (!tokens) return;
    setStatus("confirming");
    setMessage("正在完成登录...");
    try {
      await login(tokens.access, tokens.refresh);
      // login() 已存储令牌并设置 user，auth 上下文会驱动跳转；这里兜底一次。
      router.replace("/profile/security");
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "登录失败";
      setStatus("error");
      setMessage(msg);
    }
  };

  const cancelLogin = () => {
    router.replace("/login");
  };

  const name = preview?.nickname || preview?.email || "该账户";

  return (
    <div className="flex min-h-[100dvh] items-center justify-center px-4">
      <div className="w-full max-w-[380px] text-center">
        <span className="mx-auto mb-5 grid h-14 w-14 place-items-center rounded-2xl bg-accent text-white shadow-lg">
          <Sparkles className="h-7 w-7" />
        </span>

        {status === "loading" && (
          <span className="mx-auto mb-3 h-6 w-6 animate-spin rounded-full border-2 border-accent border-t-transparent" />
        )}

        <h2 className="text-lg font-semibold text-ink">
          {status === "error" ? "登录失败" : "莲花通行证"}
        </h2>

        {status === "bound" ? (
          <>
            <span className="mx-auto mb-5 grid h-16 w-16 place-items-center rounded-full bg-success-soft text-success">
              <Check className="h-8 w-8" />
            </span>
            <h2 className="text-lg font-semibold text-ink">关联成功</h2>
            <p className="mt-2 text-sm text-ink-muted">
              已成功关联{" "}
              {PROVIDER_LABELS[boundProvider ?? ""] || boundProvider || "第三方"}{" "}
              账号，即将跳转到账户安全页…
            </p>
          </>
        ) : status === "preview" && preview ? (
          <>
            <div className="my-5 flex flex-col items-center gap-3">
              <Avatar
                src={preview.avatar}
                name={preview.nickname || preview.email || "?"}
                size={72}
              />
              <div>
                <p className="text-[15px] font-medium text-ink">
                  是否以 <span className="text-accent">{name}</span> 的身份登录
                </p>
                {preview.email && (
                  <p className="mt-1 text-xs text-ink-muted">{preview.email}</p>
                )}
              </div>
            </div>
            <div className="flex gap-3">
              <button
                onClick={cancelLogin}
                className="flex flex-1 items-center justify-center gap-1.5 rounded-xl border border-line bg-surface px-4 py-3 text-sm font-semibold text-ink-soft shadow-sm transition hover:border-danger/40 hover:text-danger min-h-[44px]"
              >
                <X className="h-4 w-4" /> 取消
              </button>
              <button
                onClick={confirmLogin}
                className="flex flex-1 items-center justify-center gap-1.5 rounded-xl bg-accent px-4 py-3 text-sm font-semibold text-white shadow-sm transition hover:bg-accent/90 min-h-[44px]"
              >
                <Check className="h-4 w-4" /> 确认登录
              </button>
            </div>
          </>
        ) : status === "confirming" ? (
          <p className="mt-2 text-sm text-ink-muted">{message}</p>
        ) : status === "error" ? (
          <>
            <p className="mt-2 text-sm text-ink-muted">{message}</p>
            <button
              onClick={cancelLogin}
              className="mt-6 rounded-xl bg-accent px-6 py-3 text-sm font-semibold text-white shadow-sm transition hover:bg-accent/90 min-h-[44px]"
            >
              返回登录页
            </button>
          </>
        ) : (
          <p className="mt-2 text-sm text-ink-muted">{message}</p>
        )}
      </div>
    </div>
  );
}
