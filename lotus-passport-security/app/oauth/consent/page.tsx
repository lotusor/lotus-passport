"use client";

import * as React from "react";
import { Suspense } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { getOAuthConsentInfo, type OAuthConsentInfo } from "@/lib/passport-api";
import { Sparkles, ShieldCheck, Check, X } from "@/components/icons";

const PROVIDER_LABELS: Record<string, string> = {
  github: "GitHub",
  wechat: "微信",
  qq: "QQ",
};

/** 页面外壳：用 Suspense 包住读取 useSearchParams 的内层，规避 Next 预渲染告警。 */
export default function OAuthConsentPage() {
  return (
    <Suspense fallback={null}>
      <ConsentInner />
    </Suspense>
  );
}

type Status = "loading" | "ready" | "error";

function ConsentInner() {
  const searchParams = useSearchParams();
  const ticket = searchParams.get("ticket") || "";

  const [status, setStatus] = React.useState<Status>("loading");
  const [message, setMessage] = React.useState("正在准备授权信息…");
  const [info, setInfo] = React.useState<OAuthConsentInfo | null>(null);
  const [decision, setDecision] = React.useState<string>("");
  const [submitting, setSubmitting] = React.useState(false);

  // 用 hidden input 传递 decision，而不是依赖 submit 按钮的 value：
  // 此前用两个 <button type=submit name=decision value=allow/deny>，但 onSubmit
  // 里 setSubmitting(true) 会让按钮瞬间 disabled，浏览器提交时丢失该按钮的
  // name=value → 后端读不到 decision → 永远走 deny 分支（oauth_error=access_denied）。
  const submit = (d: "allow" | "deny") => {
    setDecision(d);
    setSubmitting(true);
    const form = document.getElementById("consent-form") as HTMLFormElement | null;
    if (!form) return;
    // 同步写入 hidden input 的 value，不依赖 React 渲染时序；
    // 这样即便按钮已被 disabled，decision 也一定随表单提交。
    const hidden = form.querySelector<HTMLInputElement>('input[name="decision"]');
    if (hidden) hidden.value = d;
    form.submit();
  };

  React.useEffect(() => {
    if (!ticket) {
      setStatus("error");
      setMessage("缺少授权票据，请重新发起登录。");
      return;
    }
    getOAuthConsentInfo(ticket)
      .then((d) => {
        setInfo(d);
        setStatus("ready");
      })
      .catch(() => {
        setStatus("error");
        setMessage("授权请求无效或已过期，请重新发起登录。");
      });
  }, [ticket]);

  const providerLabel = info
    ? PROVIDER_LABELS[info.provider] || info.provider
    : "";

  return (
    <div className="flex min-h-[100dvh] items-center justify-center px-4">
      <div className="w-full max-w-[420px]">
        {/* Brand */}
        <div className="mb-8 text-center">
          <span className="mx-auto mb-4 grid h-14 w-14 place-items-center rounded-2xl bg-accent text-white shadow-lg">
            <Sparkles className="h-7 w-7" />
          </span>
          <h1 className="text-2xl font-bold tracking-tight text-ink">
            授权登录
          </h1>
          <p className="mt-2 text-[15px] leading-relaxed text-ink-muted">
            莲花通行证 · 统一身份认证中心
          </p>
        </div>

        {status === "error" ? (
          <div className="rounded-2xl border border-red-200 bg-red-50 px-5 py-6 text-center">
            <p className="text-sm text-red-700">{message}</p>
            <Link
              href="/login"
              className="mt-5 inline-flex items-center justify-center rounded-xl bg-accent px-6 py-3 text-sm font-semibold text-white shadow-sm transition hover:bg-accent/90 min-h-[44px]"
            >
              返回登录
            </Link>
          </div>
        ) : status === "loading" ? (
          <div className="flex flex-col items-center gap-3 text-ink-muted">
            <span className="h-8 w-8 animate-spin rounded-full border-2 border-line border-t-accent" />
            <span className="text-sm">{message}</span>
          </div>
        ) : info ? (
          <>
            <div className="rounded-2xl border border-line bg-surface p-5">
              {/* 申请授权的应用 */}
              <div className="flex items-center gap-3">
                <span className="grid h-11 w-11 shrink-0 place-items-center rounded-xl bg-accent/10 text-accent">
                  <ShieldCheck className="h-6 w-6" />
                </span>
                <div className="min-w-0">
                  <p className="text-[15px] font-semibold text-ink">
                    {info.app_name}
                  </p>
                  <p className="truncate text-xs text-ink-muted">
                    {info.app_origin}
                  </p>
                </div>
              </div>

              <div className="my-4 h-px bg-line" />

              <p className="text-sm text-ink-soft">
                该应用请求使用你的莲花通行证身份登录，并获取以下信息：
              </p>
              <ul className="mt-3 space-y-2">
                {info.scopes.map((s) => (
                  <li
                    key={s}
                    className="flex items-start gap-2 text-sm text-ink-soft"
                  >
                    <Check className="mt-0.5 h-4 w-4 shrink-0 text-success" />
                    <span>{s}</span>
                  </li>
                ))}
              </ul>
            </div>

            <p className="mt-3 text-center text-xs text-ink-muted">
              你正在通过 <span className="font-medium">{providerLabel}</span>{" "}
              账号授权
            </p>

            {/* 授权 / 取消：原生表单提交，让浏览器跟随后端 302 跳回应用。
                decision 用 hidden input 传递，避免 submit 按钮 disabled 丢值 */}
            <form
              id="consent-form"
              method="post"
              action="/api/v1/oauth/consent/"
              className="mt-5 flex gap-3"
            >
              <input type="hidden" name="ticket" value={ticket} />
              <input type="hidden" name="decision" value={decision} />
              <button
                type="button"
                onClick={() => submit("deny")}
                disabled={submitting}
                className="flex flex-1 items-center justify-center gap-1.5 rounded-xl border border-line bg-surface px-4 py-3 text-sm font-semibold text-ink-soft shadow-sm transition hover:border-danger/40 hover:text-danger disabled:opacity-60 min-h-[44px]"
              >
                <X className="h-4 w-4" /> 取消
              </button>
              <button
                type="button"
                onClick={() => submit("allow")}
                disabled={submitting}
                className="flex flex-1 items-center justify-center gap-1.5 rounded-xl bg-accent px-4 py-3 text-sm font-semibold text-white shadow-sm transition hover:bg-accent/90 disabled:opacity-60 min-h-[44px]"
              >
                <Check className="h-4 w-4" /> 授权登录
              </button>
            </form>

            <p className="mt-6 text-center text-xs text-ink-muted">
              授权即表示你同意该应用按上述范围使用你的资料
            </p>
          </>
        ) : null}
      </div>
    </div>
  );
}
