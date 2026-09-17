"use client";

/**
 * 自适应人机验证（hCaptcha）前端逻辑。
 *
 * 后端在「发码/登录失败次数超过阈值」时才要求验证码，因此这里不是一上来就
 * 渲染组件，而是由调用方在收到 `captcha_required` 错误后通过 `interpret()`
 * 触发。这样正常用户完全看不到验证码。
 *
 * 三处调用点（邮箱登录 / 绑定邮箱 / 换绑邮箱）与密码登录共用同一套契约：
 *   - 错误码 `captcha_required` → 渲染组件
 *   - 错误码 `captcha_invalid`  → 重置组件让用户重来
 *   - 请求体字段名 `captcha`
 *
 * 注意：安全中心（account.eacm.cn）是纯浅色应用（globals.css 里
 * `color-scheme: light`，全站无 dark: 变体），所以 hCaptcha 主题固定浅色。
 * 若将来该应用支持深色模式，改 `theme` 参数即可。
 */
import * as React from "react";

import { ApiException } from "@/lib/passport-api";

const SITE_KEY = process.env.NEXT_PUBLIC_HCAPTCHA_SITE_KEY;
const SCRIPT_SRC = "https://js.hcaptcha.com/1/api.js";

declare global {
  interface Window {
    hcaptcha?: {
      render: (el: HTMLElement, opts: Record<string, unknown>) => number;
      remove: (widgetId: number) => void;
      reset: (widgetId?: number) => void;
    };
  }
}

/** interpret() 的返回值：null 表示与验证码无关，调用方走原有错误分支。 */
export type CaptchaAction = "required" | "invalid" | null;

export interface UseCaptchaResult {
  /** 是否已进入「需要验证码」状态（由后端错误驱动）。 */
  required: boolean;
  /** 已完成的验证 token，未完成时为 null。 */
  token: string | null;
  /** 组件自身的问题（加载失败 / 验证失败）。 */
  error: string | null;
  /** 挂载点，交给 <CaptchaField>。 */
  containerRef: React.RefObject<HTMLDivElement>;
  /** site key 缺失时用于降级提示。 */
  siteKey: string | undefined;
  /** 把后端错误映射成验证码动作。 */
  interpret: (err: unknown) => CaptchaAction;
  /** 重置 token 与组件（验证失败后调用）。 */
  reset: () => void;
  /** 手动置为需要验证码（一般不用，interpret 会处理）。 */
  require: () => void;
}

export function useCaptcha(options?: { theme?: "light" | "dark" }): UseCaptchaResult {
  const theme = options?.theme ?? "light";
  const [required, setRequired] = React.useState(false);
  const [token, setToken] = React.useState<string | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const containerRef = React.useRef<HTMLDivElement>(null);
  const widgetIdRef = React.useRef<number | null>(null);
  const renderedRef = React.useRef(false);

  // 加载并渲染 hCaptcha（仅当后端要求验证码时）。脚本按需注入并去重。
  React.useEffect(() => {
    if (!required || !SITE_KEY || renderedRef.current) return;
    let cancelled = false;

    const renderWidget = () => {
      if (cancelled || !containerRef.current || !window.hcaptcha) return;
      renderedRef.current = true;
      widgetIdRef.current = window.hcaptcha.render(containerRef.current, {
        sitekey: SITE_KEY,
        theme,
        callback: (t: string) => {
          setToken(t);
          setError(null);
        },
        "expired-callback": () => setToken(null),
        "error-callback": () =>
          setError("人机验证组件加载失败，请刷新页面重试"),
      });
    };

    if (window.hcaptcha?.render) {
      renderWidget();
      return () => {
        cancelled = true;
      };
    }

    const existing = document.querySelector(`script[src="${SCRIPT_SRC}"]`);
    if (!existing) {
      const s = document.createElement("script");
      s.src = SCRIPT_SRC;
      s.async = true;
      s.onload = () => renderWidget();
      s.onerror = () =>
        setError("人机验证组件加载失败，请检查网络后重试");
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

    return () => {
      cancelled = true;
    };
  }, [required, theme]);

  const reset = React.useCallback(() => {
    setToken(null);
    if (widgetIdRef.current != null && window.hcaptcha?.reset) {
      try {
        window.hcaptcha.reset(widgetIdRef.current);
      } catch {
        /* 组件已被移除时忽略 */
      }
    }
  }, []);

  const interpret = React.useCallback(
    (err: unknown): CaptchaAction => {
      if (!(err instanceof ApiException)) return null;
      // 后端可能只给 code，也可能额外带 captcha_required 布尔位（密码登录
      // 的 401 分支就是后者），两种都要认。
      if (err.captchaRequired || err.errorCode === "captcha_required") {
        setRequired(true);
        setError(null);
        return "required";
      }
      if (err.errorCode === "captcha_invalid") {
        reset();
        setError("人机验证失败，请重新完成验证");
        return "invalid";
      }
      return null;
    },
    [reset]
  );

  const require = React.useCallback(() => setRequired(true), []);

  return {
    required,
    token,
    error,
    containerRef,
    siteKey: SITE_KEY,
    interpret,
    reset,
    require,
  };
}
