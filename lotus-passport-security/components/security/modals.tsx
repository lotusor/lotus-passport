"use client";

import * as React from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Modal } from "@/components/modal";
import { Button } from "@/components/ui";
import { Eye, EyeOff, Key, Check, Alert } from "@/components/icons";
import type { Passkey } from "@/lib/data";
import { registerPasskey, changePassword } from "@/lib/passport-api";
import { scorePassword } from "@/lib/password-strength";
import { cn } from "@/lib/cn";

function Spinner({ className }: { className?: string }) {
  return (
    <svg
      className={cn("h-4 w-4 animate-spin", className)}
      viewBox="0 0 24 24"
      fill="none"
      aria-hidden
    >
      <circle cx="12" cy="12" r="9" stroke="currentColor" strokeOpacity="0.25" strokeWidth="3" />
      <path d="M21 12a9 9 0 0 0-9-9" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
    </svg>
  );
}

function Field({
  label,
  error,
  children,
}: {
  label: string;
  error?: string;
  children: React.ReactNode;
}) {
  return (
    <label className="block">
      <span className="mb-1.5 block text-sm font-medium text-ink-soft">{label}</span>
      {children}
      {error && (
        <span className="mt-1.5 flex items-center gap-1 text-xs font-medium text-danger">
          <Alert className="h-3.5 w-3.5" /> {error}
        </span>
      )}
    </label>
  );
}

function PasswordInput({
  value,
  onChange,
  placeholder,
  invalid,
}: {
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  invalid?: boolean;
}) {
  const [show, setShow] = React.useState(false);
  return (
    <div
      className={cn(
        "flex items-center gap-2 rounded-xl border bg-surface px-3.5 transition-colors",
        invalid ? "border-danger" : "border-line focus-within:border-accent"
      )}
    >
      <input
        type={show ? "text" : "password"}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className="h-12 w-full bg-transparent text-[15px] text-ink outline-none placeholder:text-ink-muted/60"
      />
      <button
        type="button"
        onClick={() => setShow((s) => !s)}
        aria-label={show ? "隐藏密码" : "显示密码"}
        className="grid h-9 w-9 shrink-0 place-items-center rounded-lg text-ink-muted hover:bg-ink/5 min-h-[44px] min-w-[44px]"
      >
        {show ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
      </button>
    </div>
  );
}

function StrengthMeter({ pw }: { pw: string }) {
  const s = scorePassword(pw);
  if (!pw) return null;
  const barColor =
    s.tone === "success"
      ? "bg-success"
      : s.tone === "warn"
        ? "bg-warn"
        : "bg-danger";
  const labelColor =
    s.tone === "success"
      ? "text-success"
      : s.tone === "warn"
        ? "text-warn"
        : "text-danger";
  return (
    <div className="mt-2">
      <div className="h-1.5 w-full overflow-hidden rounded-full bg-ink/10">
        <div
          className={cn("h-full rounded-full transition-all duration-200", barColor)}
          style={{ width: `${s.percent}%` }}
        />
      </div>
      <div className="mt-1.5 flex items-center justify-between text-xs">
        <span className={cn("font-medium", labelColor)}>强度：{s.label}</span>
        {s.tips.length > 0 && <span className="text-ink-muted">{s.tips[0]}</span>}
      </div>
    </div>
  );
}

/* ---------------------- Change Password ---------------------- */
const schema = z
  .object({
    // 当前密码：OAuth-only 账户没有密码，故允许为空（后端对无密码账户放行）。
    current: z.string(),
    next: z
      .string()
      .min(8, "密码至少 8 位")
      .regex(/[A-Za-z]/, "需包含字母")
      .regex(/[0-9]/, "需包含数字"),
    confirm: z.string().min(1, "请再次输入新密码"),
  })
  .refine((d) => d.next === d.confirm, {
    message: "两次输入的密码不一致",
    path: ["confirm"],
  })
  .refine((d) => d.next !== d.current, {
    message: "新密码不能与当前密码相同",
    path: ["next"],
  });

type FormValues = z.infer<typeof schema>;

export function ChangePasswordModal({
  open,
  onClose,
  onSuccess,
  token,
}: {
  open: boolean;
  onClose: () => void;
  /** 成功时把设置的新密码回传，供父组件刷新「密码强度」徽章 */
  onSuccess: (newPassword: string) => void;
  token?: string | null;
}) {
  const {
    handleSubmit,
    watch,
    setValue,
    setError,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: { current: "", next: "", confirm: "" },
  });
  const [formError, setFormError] = React.useState<string | null>(null);

  React.useEffect(() => {
    if (!open) {
      setFormError(null);
    }
  }, [open]);

  const onSubmit = async (data: FormValues) => {
    if (!token) {
      setFormError("登录状态已失效，请重新登录");
      return;
    }
    setFormError(null);
    try {
      await changePassword(token, data.next, data.current || undefined);
      onSuccess(data.next);
    } catch (err) {
      const msg = err instanceof Error ? err.message : "修改失败，请稍后重试";
      // 后端针对「当前密码不正确」「无登录方式」等给出具体文案，直接暴露给用户。
      setError("current", { message: msg });
      setFormError(msg);
    }
  };

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="修改登录密码"
      description="请先验证当前密码，再设置新的高强度密码。"
    >
      <form onSubmit={handleSubmit(onSubmit)} className="space-y-4" noValidate>
        <Field label="当前密码" error={errors.current?.message}>
          <PasswordInput
            value={watch("current")}
            onChange={(v) => setValue("current", v, { shouldValidate: true })}
            placeholder="请输入当前密码（OAuth-only 账户可留空）"
            invalid={!!errors.current}
          />
        </Field>
        <Field label="新密码" error={errors.next?.message}>
          <PasswordInput
            value={watch("next")}
            onChange={(v) => setValue("next", v, { shouldValidate: true })}
            placeholder="至少 8 位，含字母与数字"
            invalid={!!errors.next}
          />
          <StrengthMeter pw={watch("next")} />
        </Field>
        <Field label="确认新密码" error={errors.confirm?.message}>
          <PasswordInput
            value={watch("confirm")}
            onChange={(v) => setValue("confirm", v, { shouldValidate: true })}
            placeholder="再次输入新密码"
            invalid={!!errors.confirm}
          />
        </Field>
        {formError && (
          <div className="flex items-center gap-2 rounded-xl bg-danger-soft px-3.5 py-2.5 text-sm font-medium text-danger">
            <Alert className="h-4 w-4 shrink-0" /> {formError}
          </div>
        )}
        <div className="flex justify-end gap-3 pt-1">
          <Button type="button" variant="secondary" onClick={onClose}>
            取消
          </Button>
          <Button type="submit" disabled={isSubmitting}>
            {isSubmitting && <Spinner />}
            {isSubmitting ? "保存中…" : "保存新密码"}
          </Button>
        </div>
      </form>
    </Modal>
  );
}

/* ------------------------ Add Passkey ------------------------ */
export function AddPasskeyModal({
  open,
  onClose,
  onSuccess,
  token,
}: {
  open: boolean;
  onClose: () => void;
  onSuccess: (pk: Passkey) => void;
  token?: string | null;
}) {
  const [phase, setPhase] = React.useState<"idle" | "creating">("idle");
  const [name, setName] = React.useState("");
  const [error, setError] = React.useState<string | null>(null);

  React.useEffect(() => {
    if (!open) {
      setPhase("idle");
      setName("");
      setError(null);
    }
  }, [open]);

  const start = async () => {
    if (!token) {
      setError("登录状态已失效，请重新登录");
      return;
    }
    setPhase("creating");
    setError(null);
    try {
      const pk = await registerPasskey(token, name.trim() || undefined);
      onSuccess(pk);
    } catch (err) {
      setError(err instanceof Error ? err.message : "注册失败，请稍后重试");
      setPhase("idle");
    }
  };

  return (
    <Modal open={open} onClose={onClose} title="添加通行密钥">
      <div className="space-y-4">
        <div className="flex items-start gap-3 rounded-2xl bg-accent-soft p-4 text-sm text-accent-ink">
          <Key className="mt-0.5 h-5 w-5 shrink-0" />
          <span>系统将调用你设备的指纹或面容识别，完成一次性的密钥注册。</span>
        </div>
        {phase !== "creating" && (
          <Field label="名称（选填）">
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="如：MacBook Touch ID"
              className="h-12 w-full rounded-xl border border-line bg-surface px-3.5 text-[15px] text-ink outline-none focus:border-accent"
            />
          </Field>
        )}
        <div className="flex items-center justify-center rounded-2xl border border-line bg-paper py-8">
          {phase === "creating" ? (
            <div className="flex flex-col items-center gap-3 text-ink-muted">
              <Spinner className="h-7 w-7 text-accent" />
              <span className="text-sm">正在调用设备认证…</span>
            </div>
          ) : (
            <div className="text-center">
              <p className="text-sm font-medium text-ink">准备就绪</p>
              <p className="mt-1 text-xs text-ink-muted">点击下方按钮开始注册</p>
            </div>
          )}
        </div>
        {error && (
          <div className="flex items-center gap-2 rounded-xl bg-danger-soft px-3.5 py-2.5 text-sm font-medium text-danger">
            <Alert className="h-4 w-4 shrink-0" /> {error}
          </div>
        )}
        <div className="flex justify-end gap-3">
          <Button variant="secondary" onClick={onClose}>
            取消
          </Button>
          <Button onClick={start} disabled={phase === "creating"}>
            {phase === "creating" ? "注册中…" : "开始注册"}
          </Button>
        </div>
      </div>
    </Modal>
  );
}

/* ------------------------ Confirm delete ------------------------ */
export function DeleteAccountModal({
  open,
  onClose,
  confirmText,
  requirePassword,
  onConfirm,
}: {
  open: boolean;
  onClose: () => void;
  /** 用户需原样输入的核对文字（通常是用户名） */
  confirmText: string;
  /** 账户是否设有密码；true 时渲染密码输入框并要求填写（§9.4f step-up） */
  requirePassword: boolean;
  /** 异步提交注销；resolve 表示成功（父组件负责登出/跳转），reject 时把错误显示出来 */
  onConfirm: (currentPassword: string | undefined) => Promise<void>;
}) {
  const [value, setValue] = React.useState("");
  const [password, setPassword] = React.useState("");
  const [submitting, setSubmitting] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  React.useEffect(() => {
    if (!open) {
      setValue("");
      setPassword("");
      setSubmitting(false);
      setError(null);
    }
  }, [open]);

  const match = value.trim() === confirmText;

  const handleConfirm = async () => {
    if (!match || submitting) return;
    setSubmitting(true);
    setError(null);
    try {
      await onConfirm(requirePassword ? password : undefined);
      // 成功：父组件会登出并跳转，组件随之卸载
    } catch (err) {
      setError(err instanceof Error ? err.message : "注销失败，请稍后重试");
      setSubmitting(false);
    }
  };

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="注销账户"
      description={`请输入「${confirmText}」以确认注销，此操作不可恢复。`}
    >
      <div className="space-y-4">
        <input
          value={value}
          onChange={(e) => setValue(e.target.value)}
          placeholder={confirmText}
          disabled={submitting}
          className="h-12 w-full rounded-xl border border-danger/40 bg-surface px-3.5 text-[15px] text-ink outline-none focus:border-danger"
        />
        {requirePassword && (
          <Field label="账户密码（step-up 验证）" error={undefined}>
            <PasswordInput
              value={password}
              onChange={setPassword}
              placeholder="请输入当前账户密码"
              invalid={false}
            />
          </Field>
        )}
        {error && (
          <div className="flex items-center gap-2 rounded-xl bg-danger-soft px-3.5 py-2.5 text-sm font-medium text-danger">
            <Alert className="h-4 w-4 shrink-0" /> {error}
          </div>
        )}
        <div className="flex justify-end gap-3">
          <Button variant="secondary" onClick={onClose} disabled={submitting}>
            取消
          </Button>
          <Button variant="danger" disabled={!match || submitting} onClick={handleConfirm}>
            {submitting && <Spinner />}
            {submitting ? "注销中…" : "确认注销"}
          </Button>
        </div>
      </div>
    </Modal>
  );
}
