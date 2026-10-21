"use client";

/**
 * 人机验证挂载块。由 <useCaptcha> 驱动，只在后端要求验证码时渲染。
 *
 * 用法：
 *   const captcha = useCaptcha();
 *   ...
 *   <CaptchaField captcha={captcha} />
 */
import * as React from "react";

import type { UseCaptchaResult } from "@/lib/use-captcha";

export function CaptchaField({
  captcha,
  label = "人机验证",
}: {
  captcha: UseCaptchaResult;
  label?: string;
}) {
  if (!captcha.required) return null;

  return (
    <div>
      <label className="mb-1.5 block text-sm font-medium text-ink">{label}</label>
      {captcha.siteKey ? (
        <div ref={captcha.containerRef} />
      ) : (
        <div className="rounded-xl border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-700">
          验证码组件未配置（缺少 NEXT_PUBLIC_HCAPTCHA_SITE_KEY）
        </div>
      )}
      {captcha.error && (
        <p className="mt-1.5 text-sm text-red-600">{captcha.error}</p>
      )}
    </div>
  );
}
