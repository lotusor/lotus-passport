"use client";

import * as React from "react";
import {
  Card,
  SectionCard,
  Badge,
  Button,
} from "@/components/ui";
import {
  Lock,
  Key,
  Fingerprint,
  Desktop,
  History,
  Alert,
  Link2,
  Unlink,
  Wechat,
  Qq,
  Github,
  Trash,
  Check,
} from "@/components/icons";
import type {
  Passkey,
  Session,
  LoginEvent,
  Provider,
} from "@/lib/data";
import { cn } from "@/lib/cn";

/* --------------------------- Password --------------------------- */
export function PasswordSection({
  lastChanged,
  strength,
  onEdit,
}: {
  lastChanged: string;
  strength: string;
  onEdit: () => void;
}) {
  return (
    <SectionCard
      icon={Lock}
      title="登录密码"
      description="定期更换高强度密码，是保障账户安全的第一道防线。"
      action={<Button size="sm" onClick={onEdit}>修改密码</Button>}
    >
      <div className="flex flex-wrap items-center gap-x-8 gap-y-3 text-sm">
        <div>
          <p className="text-ink-muted">上次修改</p>
          <p className="mt-0.5 font-medium text-ink">{lastChanged}</p>
        </div>
        <div>
          <p className="text-ink-muted">密码强度</p>
          <p className="mt-0.5">
            <Badge tone={strength === "强" ? "success" : strength === "中" ? "warn" : "danger"}>
              {strength}
            </Badge>
          </p>
        </div>
      </div>
    </SectionCard>
  );
}

/* --------------------------- Passkeys --------------------------- */
export function PasskeySection({
  passkeys,
  onRemove,
}: {
  passkeys: Passkey[];
  onRemove: (id: string) => void;
}) {
  return (
    <SectionCard
      icon={Fingerprint}
      title="通行密钥 (Passkey)"
      description="当前功能待开发。"
    >
      {passkeys.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-line bg-paper/60 p-6 text-center text-sm text-ink-muted">
          当前功能待开发。
        </div>
      ) : (
        <ul className="divide-y divide-line">
          {passkeys.map((pk) => (
            <li key={pk.id} className="flex items-center gap-4 py-3.5 first:pt-0 last:pb-0">
              <span className="grid h-10 w-10 shrink-0 place-items-center rounded-2xl bg-success-soft text-success">
                <Key className="h-5 w-5" />
              </span>
              <div className="min-w-0 flex-1">
                <p className="truncate font-medium text-ink">{pk.name}</p>
                <p className="truncate text-sm text-ink-muted">
                  {pk.device} · 添加于 {pk.added}
                </p>
              </div>
              <span className="hidden text-sm text-ink-muted sm:block">
                {pk.lastUsed}
              </span>
              <button
                onClick={() => onRemove(pk.id)}
                aria-label={`移除 ${pk.name}`}
                className="grid h-9 w-9 place-items-center rounded-xl text-ink-muted hover:bg-danger-soft hover:text-danger min-h-[44px] min-w-[44px]"
              >
                <Trash className="h-4 w-4" />
              </button>
            </li>
          ))}
        </ul>
      )}
    </SectionCard>
  );
}

/* --------------------------- Sessions --------------------------- */
export function SessionsSection({
  sessions,
  onRevoke,
}: {
  sessions: Session[];
  onRevoke: (id: string) => void;
}) {
  return (
    <SectionCard
      icon={Desktop}
      title="登录设备与活跃会话"
      description="管理当前已登录的设备，发现陌生设备请立即退出。"
    >
      <ul className="divide-y divide-line">
        {sessions.map((s) => (
          <li key={s.id} className="flex items-center gap-4 py-3.5 first:pt-0 last:pb-0">
            <span className="grid h-10 w-10 shrink-0 place-items-center rounded-2xl bg-paper text-ink-soft">
              <Desktop className="h-5 w-5" />
            </span>
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2">
                <p className="truncate font-medium text-ink">{s.device}</p>
                {s.current && <Badge tone="success">当前会话</Badge>}
              </div>
              <p className="truncate text-sm text-ink-muted">
                {s.browser} · {s.location} · {s.lastActive}
              </p>
            </div>
            {!s.current && (
              <button
                onClick={() => onRevoke(s.id)}
                className="rounded-xl px-3 py-2 text-sm font-medium text-ink-soft hover:bg-ink/5 min-h-[44px]"
              >
                退出
              </button>
            )}
          </li>
        ))}
      </ul>
    </SectionCard>
  );
}

/* ------------------------- Login History ------------------------ */
export function LoginHistorySection({ events }: { events: LoginEvent[] }) {
  return (
    <SectionCard
      icon={History}
      title="登录历史"
      description="最近 30 天的登录记录，异常登录会被自动标记。"
    >
      <ul className="divide-y divide-line">
        {events.map((e) => {
          const failed = e.status === "failed";
          return (
            <li
              key={e.id}
              className={cn(
                "flex items-center gap-4 py-3.5 first:pt-0 last:pb-0",
                failed && "rounded-2xl bg-danger-soft/50 px-3 -mx-3"
              )}
            >
              <span
                className={cn(
                  "grid h-10 w-10 shrink-0 place-items-center rounded-2xl",
                  failed ? "bg-danger-soft text-danger" : "bg-success-soft text-success"
                )}
              >
                {failed ? <Alert className="h-5 w-5" /> : <Check className="h-5 w-5" />}
              </span>
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <p className="truncate font-medium text-ink">{e.time}</p>
                  <Badge tone={failed ? "danger" : "success"}>
                    {failed ? "失败" : "成功"}
                  </Badge>
                </div>
                <p className="truncate text-sm text-ink-muted">
                  {e.location} · {e.device} · {e.ip}
                </p>
              </div>
            </li>
          );
        })}
      </ul>
    </SectionCard>
  );
}

/* ----------------------- Connected Accounts --------------------- */
const providerIcon: Record<Provider["id"], React.ComponentType<React.SVGProps<SVGSVGElement>>> = {
  wechat: Wechat,
  qq: Qq,
  github: Github,
};

export function ConnectedAccountsSection({
  providers,
  onToggle,
}: {
  providers: Provider[];
  onToggle: (id: Provider["id"]) => void;
}) {
  return (
    <SectionCard
      icon={Link2}
      title="关联第三方账号"
      description="绑定后可使用对应平台一键登录，身份由莲花通行证统一签发。"
    >
      <ul className="divide-y divide-line">
        {providers.map((p) => {
          const Icon = providerIcon[p.id];
          return (
            <li key={p.id} className="flex items-center gap-4 py-4 first:pt-0 last:pb-0">
              <span className="grid h-11 w-11 shrink-0 place-items-center rounded-2xl bg-paper text-ink-soft">
                <Icon className="h-5 w-5" />
              </span>
              <div className="min-w-0 flex-1">
                <p className="font-medium text-ink">{p.name}</p>
                <p className="truncate text-sm text-ink-muted">
                  {p.linked ? `已绑定：${p.account}` : p.hint}
                </p>
              </div>
              {p.linked ? (
                <Button size="sm" variant="secondary" onClick={() => onToggle(p.id)}>
                  <Unlink className="h-4 w-4" /> 解绑
                </Button>
              ) : (
                <Button size="sm" onClick={() => onToggle(p.id)}>
                  <Link2 className="h-4 w-4" /> 绑定
                </Button>
              )}
            </li>
          );
        })}
      </ul>
    </SectionCard>
  );
}

/* -------------------------- Danger Zone ------------------------- */
export function DangerZone({ onDelete }: { onDelete: () => void }) {
  return (
    <Card className="overflow-hidden border-danger/30">
      <div className="border-b border-danger/20 bg-danger-soft/40 p-5 sm:p-6">
        <div className="flex items-center gap-3">
          <span className="grid h-11 w-11 shrink-0 place-items-center rounded-2xl bg-danger-soft text-danger">
            <Alert className="h-5 w-5" />
          </span>
          <div>
            <h3 className="text-lg font-semibold tracking-tight text-ink">危险操作</h3>
            <p className="mt-1 text-sm text-ink-muted">
              注销账户将永久删除你的通行证及所有关联数据，且不可恢复。
            </p>
          </div>
        </div>
      </div>
      <div className="flex flex-wrap items-center justify-between gap-4 p-5 sm:p-6">
        <p className="text-sm text-ink-muted">
          注销后，你将无法使用本通行证登录任何接入服务。
        </p>
        <Button variant="danger" onClick={onDelete}>
          <Trash className="h-4 w-4" /> 注销账户
        </Button>
      </div>
    </Card>
  );
}
