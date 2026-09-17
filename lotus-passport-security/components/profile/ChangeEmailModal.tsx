"use client";

import * as React from "react";
import { Modal } from "@/components/modal";
import { Button } from "@/components/ui";
import { Eye, EyeOff, Alert } from "@/components/icons";
import { changeEmail, sendEmailCode } from "@/lib/passport-api";
import { useCaptcha } from "@/lib/use-captcha";
import { CaptchaField } from "@/components/CaptchaField";
import { cn } from "@/lib/cn";

function Spinner({ className }: { className?: string }) {
  return (
    <svg className={cn("h-4 w-4 animate-spin", className)} viewBox="0 0 24 24" fill="none" aria-hidden>
      <circle cx="12" cy="12" r="9" stroke="currentColor" strokeOpacity="0.25" strokeWidth="3" />
      <path d="M21 12a9 9 0 0 0-9-9" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
    </svg>
  );
}

/**
 * 更改邮箱弹窗（2026-08-27，双重验证）：
 * ① 新邮箱验证码（发到新邮箱，证明拥有新邮箱）；
 * ② 当前邮箱验证码（发到旧邮箱，证明账号主人身份）；
 * ③ 有密码账户另须验密码（step-up）。
 */
export function ChangeEmailModal({
  open,
  onClose,
  token,
  currentEmail,
  hasPassword,
  onSuccess,
}: {
  open: boolean;
  onClose: () => void;
  token: string | null;
  currentEmail: string;
  hasPassword: boolean;
  onSuccess: (newEmail: string) => void;
}) {
  const [newEmail, setNewEmail] = React.useState("");
  const [newCode, setNewCode] = React.useState("");
  const [oldCode, setOldCode] = React.useState("");
  const [password, setPassword] = React.useState("");
  const [showPw, setShowPw] = React.useState(false);
  const [newSent, setNewSent] = React.useState(false);
  const [oldSent, setOldSent] = React.useState(false);
  const [newCountdown, setNewCountdown] = React.useState(0);
  const [oldCountdown, setOldCountdown] = React.useState(0);
  const [sending, setSending] = React.useState<"new" | "old" | null>(null);
  const [submitting, setSubmitting] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  // 人机验证：新/旧邮箱两个发码按钮共用同一个组件（后端按 IP+目标邮箱计数）
  const captcha = useCaptcha();
  const resetCaptcha = captcha.reset;

  // 重置
  React.useEffect(() => {
    if (!open) {
      setNewEmail("");
      setNewCode("");
      setOldCode("");
      setPassword("");
      setNewSent(false);
      setOldSent(false);
      setNewCountdown(0);
      setOldCountdown(0);
      setError(null);
      // 关闭弹窗时清掉已消耗的 token，重开时重新验证
      resetCaptcha();
    }
  }, [open, resetCaptcha]);

  React.useEffect(() => {
    if (newCountdown <= 0 && oldCountdown <= 0) return;
    const t = setTimeout(() => {
      setNewCountdown((s) => Math.max(0, s - 1));
      setOldCountdown((s) => Math.max(0, s - 1));
    }, 1000);
    return () => clearTimeout(t);
  }, [newCountdown, oldCountdown]);

  const emailValid = /^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(newEmail.trim());

  const sendCode = async (which: "new" | "old") => {
    if (!token) {
      setError("登录状态已失效，请重新登录");
      return;
    }
    if (which === "new" && !emailValid) {
      setError("请先输入有效的新邮箱");
      return;
    }
    if (captcha.required && !captcha.token) {
      setError("请先完成人机验证");
      return;
    }
    setSending(which);
    setError(null);
    try {
      if (which === "new") {
        await sendEmailCode(newEmail.trim(), "new", token, captcha.token);
        setNewSent(true);
        setNewCountdown(60);
      } else {
        await sendEmailCode(currentEmail, "old", token, captcha.token);
        setOldSent(true);
        setOldCountdown(60);
      }
      // hCaptcha token 一次性：发送成功后重置，下次需要时重新验证
      resetCaptcha();
    } catch (err: unknown) {
      // 验证码相关错误由 useCaptcha 接管（弹组件 / 提示重试）
      if (captcha.interpret(err)) return;
      setError(err instanceof Error ? err.message : "发送失败，请稍后重试");
    } finally {
      setSending(null);
    }
  };

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (submitting || !token) return;
    setSubmitting(true);
    setError(null);
    try {
      await changeEmail(token, newEmail.trim(), newCode.trim(), oldCode.trim(), password || undefined);
      onSuccess(newEmail.trim());
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "更改失败，请稍后重试");
    } finally {
      setSubmitting(false);
    }
  };

  const codeInputCls =
    "w-full rounded-xl border border-line bg-surface px-3.5 py-3 text-[15px] tracking-widest text-ink outline-none focus:border-accent min-h-[48px]";

  return (
    <Modal open={open} onClose={onClose} title="更改邮箱">
      <form onSubmit={onSubmit} className="space-y-5">
        <div className="flex items-start gap-3 rounded-2xl bg-accent-soft p-4 text-sm leading-relaxed text-accent-ink">
          <Alert className="mt-0.5 h-5 w-5 shrink-0" />
          <span>
            出于安全考虑，需完成<strong>双重验证</strong>：新邮箱验证码（证明你拥有新邮箱）
            + 当前邮箱验证码（证明你是账户主人）{hasPassword ? "，并验证账户密码" : ""}。
          </span>
        </div>

        {/* ① 新邮箱 */}
        <div className="space-y-2">
          <label className="block text-sm font-medium text-ink">新邮箱</label>
          <input
            type="email"
            autoComplete="email"
            value={newEmail}
            onChange={(e) => setNewEmail(e.target.value)}
            placeholder="请输入新邮箱地址"
            className="w-full rounded-xl border border-line bg-surface px-3.5 py-3 text-[15px] text-ink outline-none focus:border-accent min-h-[48px]"
            required
          />
          <div className="flex gap-2">
            <input
              type="text"
              inputMode="numeric"
              maxLength={6}
              placeholder="新邮箱验证码"
              value={newCode}
              onChange={(e) => setNewCode(e.target.value.replace(/\D/g, ""))}
              className={codeInputCls}
              required
            />
            <button
              type="button"
              onClick={() => sendCode("new")}
              disabled={!emailValid || sending === "new" || newCountdown > 0}
              className="shrink-0 rounded-xl border border-accent/40 px-3 text-sm font-medium text-accent transition-colors hover:bg-accent-soft disabled:opacity-50 disabled:hover:bg-transparent min-h-[48px] whitespace-nowrap"
            >
              {sending === "new" ? "发送中…" : newCountdown > 0 ? `${newCountdown}s` : newSent ? "重发" : "发码"}
            </button>
          </div>
          {newSent && (
            <p className="text-xs text-ink-muted">验证码已发送至新邮箱 {newEmail.trim()}</p>
          )}
        </div>

        {/* ② 旧邮箱 */}
        <div className="space-y-2">
          <label className="block text-sm font-medium text-ink">
            当前邮箱 <span className="font-normal text-ink-muted">（{currentEmail}）</span>
          </label>
          <div className="flex gap-2">
            <input
              type="text"
              inputMode="numeric"
              maxLength={6}
              placeholder="当前邮箱验证码"
              value={oldCode}
              onChange={(e) => setOldCode(e.target.value.replace(/\D/g, ""))}
              className={codeInputCls}
              required
            />
            <button
              type="button"
              onClick={() => sendCode("old")}
              disabled={sending === "old" || oldCountdown > 0}
              className="shrink-0 rounded-xl border border-accent/40 px-3 text-sm font-medium text-accent transition-colors hover:bg-accent-soft disabled:opacity-50 disabled:hover:bg-transparent min-h-[48px] whitespace-nowrap"
            >
              {sending === "old" ? "发送中…" : oldCountdown > 0 ? `${oldCountdown}s` : oldSent ? "重发" : "发码"}
            </button>
          </div>
          {oldSent && (
            <p className="text-xs text-ink-muted">验证码已发送至当前邮箱（含垃圾邮件箱）</p>
          )}
        </div>

        {/* ③ 密码 step-up */}
        {hasPassword && (
          <div className="space-y-2">
            <label className="block text-sm font-medium text-ink">账户密码</label>
            <div className="relative">
              <input
                type={showPw ? "text" : "password"}
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="验证身份需输入账户密码"
                className="w-full rounded-xl border border-line bg-surface px-3.5 py-3 pr-11 text-[15px] text-ink outline-none focus:border-accent min-h-[48px]"
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

        <CaptchaField captcha={captcha} />

        {error && (
          <div className="flex items-center gap-2 rounded-xl bg-danger-soft px-3.5 py-2.5 text-sm font-medium text-danger">
            <Alert className="h-4 w-4 shrink-0" /> {error}
          </div>
        )}

        <div className="flex justify-end gap-3">
          <Button variant="secondary" onClick={onClose}>
            取消
          </Button>
          <Button type="submit" disabled={submitting}>
            {submitting && <Spinner />}
            {submitting ? "更改中…" : "确认更改"}
          </Button>
        </div>
      </form>
    </Modal>
  );
}
