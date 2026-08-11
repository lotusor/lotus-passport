"use client";

import * as React from "react";
import Link from "next/link";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Reveal } from "@/components/motion/Reveal";
import { Card, SectionCard, Button, Badge } from "@/components/ui";
import { Modal } from "@/components/modal";
import { CopyButton } from "@/components/CopyButton";
import { CompletenessRing } from "@/components/profile/CompletenessRing";
import { Shield, UserCircle, Globe, Pencil, Camera, Check } from "@/components/icons";
import { cn } from "@/lib/cn";
import { useAuth } from "@/lib/auth-context";
import { updateProfile, uploadAvatar, getProfile } from "@/lib/passport-api";
import { Avatar } from "@/components/Avatar";

const PROVIDER_LABELS: Record<string, string> = {
  github: "GitHub",
  wechat: "微信",
  qq: "QQ",
};

type LocalProfile = {
  nickname: string;
  username: string;
  email: string;
  phone: string;
  bio: string;
  avatar: string;
};

function computeScore(p: LocalProfile) {
  let s = 0;
  if (p.nickname.trim()) s += 20;
  if (p.email.trim()) s += 15;
  if (/^1[3-9]\d{9}$/.test(p.phone)) s += 25;
  if (p.bio.trim()) s += 15;
  // 头像单独 +25：上传头像是个独立动作，给奖励最直观，也能把 75→100 凑齐。
  if (p.avatar && p.avatar.trim()) s += 25;
  return Math.min(100, s);
}

// 昵称/手机号均为选填（后端允许为空）；邮箱后端只读、不在此校验。
// 昵称合法约束：2-20 字符，仅限中英文、数字、空格及 _ . -。
const NICKNAME_PATTERN = /^[一-龥A-Za-z0-9_.\- ]+$/;
const schema = z.object({
  username: z
    .string()
    .trim()
    .min(3, "用户名至少 3 个字符")
    .max(64, "用户名最多 64 个字符")
    .optional()
    .or(z.literal("")),
  nickname: z
    .string()
    .trim()
    .max(20, "昵称最多 20 个字符")
    .refine((v) => v === "" || v.length >= 2, "昵称至少 2 个字符")
    .refine(
      (v) => v === "" || NICKNAME_PATTERN.test(v),
      "昵称仅支持中英文、数字、空格及 _ . -"
    )
    .optional()
    .or(z.literal("")),
  phone: z
    .string()
    .refine(
      (v) => v === "" || /^1[3-9]\d{9}$/.test(v),
      "请输入有效的 11 位手机号"
    )
    .optional()
    .or(z.literal("")),
  bio: z.string().max(80, "简介最多 80 个字符").optional(),
});

type FormValues = z.infer<typeof schema>;

function Row({
  label,
  children,
  action,
}: {
  label: string;
  children: React.ReactNode;
  action?: React.ReactNode;
}) {
  return (
    <div className="flex items-center justify-between gap-4 py-3.5">
      <span className="shrink-0 text-sm text-ink-muted">{label}</span>
      <div className="flex min-w-0 items-center gap-2 text-right">
        <span className="min-w-0 truncate text-sm font-medium text-ink">
          {children}
        </span>
        {action}
      </div>
    </div>
  );
}

export function BasicProfile() {
  const { user, accessToken, setUser } = useAuth();

  const [profile, setProfile] = React.useState<LocalProfile>({
    nickname: user?.nickname || "",
    username: user?.username || "",
    email: user?.email || "",
    phone: user?.phone || "",
    bio: user?.bio || "",
    avatar: user?.avatar || "",
  });
  const [avatarLoading, setAvatarLoading] = React.useState(false);
  const [avatarError, setAvatarError] = React.useState<string | null>(null);
  const [editOpen, setEditOpen] = React.useState(false);
  const [savedAt, setSavedAt] = React.useState<string | null>(null);
  const [saveError, setSaveError] = React.useState<string | null>(null);

  // Seed local profile from auth data when user loads
  React.useEffect(() => {
    if (user) {
      setProfile((p) => ({
        ...p,
        nickname: user.nickname || p.nickname,
        username: user.username || p.username,
        email: user.email || p.email,
        phone: user.phone || p.phone,
        bio: user.bio || p.bio,
        avatar: user.avatar || p.avatar,
      }));
    }
  }, [user]);

  // 拉取完整资料（含 /userinfo/ 未返回的 phone / has_password）：
  // 回填资料页，并通过 setUser 丰富全局 user（供注销 step-up 判定等）。
  // 注意：/userinfo/ 契约刻意只返回身份字段，phone 等以 /profile/ 为准。
  React.useEffect(() => {
    if (!accessToken) return;
    getProfile(accessToken)
      .then((p) => setUser(p))
      .catch(() => {
        /* 失败则用 auth 已有 user 兜底，不阻断页面 */
      });
  }, [accessToken, setUser]);

  const score = computeScore(profile);
  const providers = user?.providers || [];

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: {
      username: profile.username,
      nickname: profile.nickname,
      phone: profile.phone,
      bio: profile.bio,
    },
  });

  const onEditOpen = () => {
    setSaveError(null);
    setEditOpen(true);
  };

  // 编辑弹窗是条件挂载的（Modal 内 `open && ...`）。若像之前那样在 onEditOpen 里
  // 先 reset 再 setEditOpen，reset 发生在 input 挂载之前，RHF 拿不到输入值，
  // 提交时 data.nickname/data.bio 为空 -> PATCH 把昵称清空(侧栏变"未登录")、简介不落地。
  // 改为弹窗打开(已挂载)后再 reset，确保字段值正确绑定。
  React.useEffect(() => {
    if (editOpen) {
      reset({
        username: profile.username,
        nickname: profile.nickname,
        phone: profile.phone,
        bio: profile.bio,
      });
    }
    // 仅在打开时重置；profile 取最新值即可，不入依赖以免打字中被重置
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [editOpen, reset]);

  const onSubmit = async (data: FormValues) => {
    setSaveError(null);
    // 只提交后端支持的字段（email 只读忽略，avatar 走上传端点）。
    const payload: {
      username: string;
      nickname: string;
      bio: string;
      phone: string;
    } = {
      username: data.username?.trim() ?? "",
      nickname: data.nickname?.trim() ?? "",
      bio: data.bio?.trim() ?? "",
      phone: data.phone?.trim() ?? "",
    };
    try {
      if (accessToken) {
        const updated = await updateProfile(accessToken, payload);
        setUser(updated); // 同步 hero（nickname/username/phone/bio 来自最新 userinfo）
      }
      setProfile((p) => ({
        ...p,
        username: data.username?.trim() ?? p.username,
        nickname: data.nickname ?? p.nickname,
        bio: data.bio ?? p.bio,
        phone: data.phone ?? p.phone,
      }));
      setSavedAt("刚刚");
      setEditOpen(false);
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : "保存失败，请重试");
    }
  };

  // 头像本地上传：客户端先校验大小/类型，再直传后端（≤128KB）。
  const onAvatarFile = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    e.target.value = ""; // 允许重复选同一文件
    if (!file) return;
    setAvatarError(null);
    if (!file.type.startsWith("image/")) {
      setAvatarError("请选择图片文件（JPG / PNG / WebP / GIF）");
      return;
    }
    if (file.size > 128 * 1024) {
      setAvatarError("头像图片不能超过 128KB");
      return;
    }
    setAvatarLoading(true);
    try {
      const updated = await uploadAvatar(accessToken as string, file);
      setProfile((p) => ({ ...p, avatar: updated.avatar }));
      setUser(updated); // 同步全局（hero / 登录确认页等）
      setSavedAt("刚刚");
    } catch (err) {
      setAvatarError(err instanceof Error ? err.message : "头像上传失败");
    } finally {
      setAvatarLoading(false);
    }
  };

  return (
    <>
      {/* Hero */}
      <Reveal>
        <Card className="overflow-hidden">
          <div className="relative h-24 bg-gradient-to-r from-accent/15 via-warn/10 to-success/10" />
          <div className="px-5 pb-5 sm:px-6">
            <div className="-mt-10 flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
              <div className="flex items-end gap-4">
                <div className="relative">
                  <Avatar
                    src={profile.avatar}
                    name={profile.nickname || user?.email || "?"}
                    size={80}
                  />
                  <label
                    aria-label="更换头像"
                    className="absolute -bottom-1 -right-1 grid h-8 w-8 cursor-pointer place-items-center rounded-full border-2 border-surface bg-ink text-white shadow-soft transition-transform hover:scale-105 min-h-[32px] min-w-[32px]"
                  >
                    {avatarLoading ? (
                      <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-white/40 border-t-white" />
                    ) : (
                      <Camera className="h-4 w-4" />
                    )}
                    <input
                      type="file"
                      accept="image/*"
                      className="hidden"
                      onChange={onAvatarFile}
                    />
                  </label>
                </div>
                <div className="pb-1">
                  <h2 className="text-xl font-bold text-ink">
                    {profile.nickname || "未设置昵称"}
                  </h2>
                  <p className="text-sm text-ink-muted">
                    {user?.passport_user_id
                      ? `ID: ${user.passport_user_id.slice(0, 8)}...`
                      : "加载中..."}
                  </p>
                </div>
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <span className="inline-flex items-center leading-none rounded-full bg-accent-soft px-2.5 py-1 text-xs font-medium text-accent-ink">
                  通行证用户
                </span>
                {providers.map((p) => (
                  <span
                    key={p}
                    className="inline-flex items-center leading-none rounded-full bg-success-soft px-2.5 py-1 text-xs font-medium text-success"
                  >
                    {PROVIDER_LABELS[p] || p}
                  </span>
                ))}
                <Button size="sm" variant="secondary" onClick={onEditOpen}>
                  <Pencil className="h-4 w-4" /> 编辑资料
                </Button>
              </div>
            </div>
            {savedAt && (
              <p className="mt-3 flex items-center gap-1.5 text-sm text-success">
                <Check className="h-4 w-4" /> 资料已保存（{savedAt}）
              </p>
            )}
            {avatarError && (
              <p className="mt-3 text-sm text-danger">{avatarError}</p>
            )}
          </div>
        </Card>
      </Reveal>

      {/* 引导横幅：OAuth-only 账户首次登录后，引导设置账号名 + 密码 */}
      {!user?.has_password && (
        <Reveal delay={0.02}>
          <div className="flex flex-col gap-3 rounded-3xl border border-accent/30 bg-accent-soft/60 p-5 sm:flex-row sm:items-center sm:justify-between">
            <div className="flex min-w-0 items-start gap-3">
              <span className="mt-0.5 grid h-9 w-9 shrink-0 place-items-center rounded-2xl bg-accent text-white">
                <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round">
                  <circle cx="7.5" cy="15.5" r="4.5" />
                  <path d="M10.7 12.3 20 3" />
                  <path d="M16 7l3 3" />
                  <path d="M18 5l3 3" />
                </svg>
              </span>
              <div className="min-w-0">
                <p className="text-sm font-semibold text-ink">
                  建议设置账号名与密码
                </p>
                <p className="mt-0.5 text-xs leading-relaxed text-ink-muted">
                  你当前仅通过第三方账号登录。设置账号名与密码后，下次即可直接密码登录，无需依赖第三方。
                </p>
              </div>
            </div>
            <div className="flex shrink-0 gap-2">
              <Button size="sm" variant="secondary" onClick={onEditOpen}>
                设置账号名
              </Button>
              <Link
                href="/profile/security"
                className="inline-flex items-center justify-center rounded-xl bg-accent px-3.5 py-2 text-sm font-medium text-white transition-colors hover:bg-accent/90 min-h-[40px]"
              >
                设置密码
              </Link>
            </div>
          </div>
        </Reveal>
      )}

      {/* Two-column: cards + aside */}
      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_320px]">
        <div className="order-2 space-y-6 lg:order-1">
          <Reveal delay={0.04}>
            <SectionCard
              icon={UserCircle}
              title="账号信息"
              description="通行证账号的核心标识，绑定后用于跨应用统一登录。"
            >
              <div className="divide-y divide-line">
                <Row
                  label="账号 ID"
                  action={
                    <CopyButton value={user?.passport_user_id || ""} />
                  }
                >
                  <span className="font-mono text-[13px]">
                    {user?.passport_user_id?.slice(0, 12) + "..." || "—"}
                  </span>
                </Row>
                <Row
                  label="用户名"
                  action={
                    !profile.username ? (
                      <button
                        onClick={onEditOpen}
                        className="text-accent underline-offset-2 hover:underline"
                      >
                        去设置
                      </button>
                    ) : undefined
                  }
                >
                  {profile.username ? `@${profile.username}` : "未设置"}
                </Row>
                <Row label="登录方式">
                  <span className="flex flex-wrap justify-end gap-1.5">
                    {providers.length > 0 ? (
                      providers.map((p) => (
                        <Badge key={p} tone="accent">
                          {PROVIDER_LABELS[p] || p}
                        </Badge>
                      ))
                    ) : (
                      <Badge tone="warn">未绑定</Badge>
                    )}
                  </span>
                </Row>
              </div>
            </SectionCard>
          </Reveal>

          <Reveal delay={0.08}>
            <SectionCard
              icon={Globe}
              title="联系方式"
              description="建议完善基础信息"
            >
              <div className="divide-y divide-line">
                <Row
                  label="邮箱"
                  action={
                    <CopyButton value={profile.email} />
                  }
                >
                  {profile.email || "—"}
                </Row>
                <Row label="手机号">
                  {profile.phone || "未填写"}
                </Row>
                <Row label="个人简介">
                  <span className="line-clamp-2">{profile.bio || "—"}</span>
                </Row>
              </div>
            </SectionCard>
          </Reveal>
        </div>

        {/* Aside: completeness + security link */}
        <aside className="order-1 lg:order-2">
          <div className="lg:sticky lg:top-24 space-y-4">
            <CompletenessRing
              score={score}
              hint="完善资料可提升账号完整度与可信度。"
            />
            <a
              href="/profile/security"
              className="flex items-center gap-3 rounded-3xl border border-line bg-surface p-5 text-left shadow-soft transition-colors hover:border-accent/40"
            >
              <span className="grid h-10 w-10 shrink-0 place-items-center rounded-2xl bg-accent-soft text-accent">
                <Shield className="h-5 w-5" />
              </span>
              <div className="min-w-0">
                <p className="text-sm font-semibold text-ink">账户安全</p>
                <p className="text-xs text-ink-muted">
                  密码与登录设备
                </p>
              </div>
            </a>
          </div>
        </aside>
      </div>

      {/* Edit modal */}
      <Modal
        open={editOpen}
        onClose={() => setEditOpen(false)}
        title="编辑资料"
        description="建议完善基础信息"
      >
        <form
          onSubmit={handleSubmit(onSubmit)}
          className="space-y-4"
          noValidate
        >
          <p className="rounded-xl bg-surface px-3.5 py-2.5 text-xs text-ink-muted">
            头像请点击资料卡上的相机图标上传本地图片（≤128KB，支持 JPG / PNG / WebP / GIF）。
          </p>
          <Field
            label="昵称"
            placeholder="2-20 字符，支持中英文、数字、空格及 _ . -"
            error={errors.nickname?.message}
            {...register("nickname")}
          />
          <Field
            label="账号名"
            placeholder="3-64 字符，用于密码登录（仅支持字母、数字及 _ . -）"
            error={errors.username?.message}
            {...register("username")}
          />
          {/* 邮箱为登录标识，后端只读，前端不提供修改入口 */}
          <div>
            <label className="mb-1.5 block text-sm font-medium text-ink-soft">
              邮箱
            </label>
            <input
              disabled
              value={profile.email || ""}
              placeholder="邮箱为登录标识，暂不可修改"
              className="w-full rounded-xl border border-line bg-surface px-3.5 py-3 text-[15px] text-ink/60 outline-none min-h-[44px]"
            />
            <p className="mt-1.5 text-xs text-ink-muted">
              邮箱为登录标识，暂不支持修改。
            </p>
          </div>
          <Field
            label="手机号"
            placeholder="11 位手机号，选填"
            inputMode="numeric"
            error={errors.phone?.message}
            {...register("phone")}
          />
          <Field
            label="个人简介"
            placeholder="一句话介绍自己，选填"
            error={errors.bio?.message}
            {...register("bio")}
          />
          {saveError && (
            <p className="rounded-xl border border-danger/40 bg-danger/10 px-3.5 py-2.5 text-sm text-danger">
              {saveError}
            </p>
          )}
          <div className="flex justify-end gap-3 pt-2">
            <Button
              type="button"
              variant="ghost"
              onClick={() => setEditOpen(false)}
            >
              取消
            </Button>
            <Button type="submit" disabled={isSubmitting}>
              {isSubmitting && (
                <span className="h-4 w-4 animate-spin rounded-full border-2 border-white/40 border-t-white" />
              )}
              保存修改
            </Button>
          </div>
        </form>
      </Modal>
    </>
  );
}

const Field = React.forwardRef<
  HTMLInputElement,
  React.InputHTMLAttributes<HTMLInputElement> & {
    label: string;
    error?: string;
  }
>(function Field({ label, error, ...props }, ref) {
  return (
    <div>
      <label className="mb-1.5 block text-sm font-medium text-ink-soft">
        {label}
      </label>
      <input
        ref={ref}
        {...props}
        className={cn(
          "w-full rounded-xl border bg-surface px-3.5 py-3 text-[15px] text-ink outline-none transition-colors min-h-[44px]",
          error
            ? "border-danger focus:border-danger"
            : "border-line focus:border-accent"
        )}
        aria-invalid={!!error}
      />
      {error && <p className="mt-1.5 text-sm text-danger">{error}</p>}
    </div>
  );
});