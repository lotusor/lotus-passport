"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import { SecurityScore } from "@/components/security/SecurityScore";
import {
  PasswordSection,
  PasskeySection,
  SessionsSection,
  LoginHistorySection,
  ConnectedAccountsSection,
  DangerZone,
} from "@/components/security/sections";
import {
  ChangePasswordModal,
  DeleteAccountModal,
} from "@/components/security/modals";
import { Reveal } from "@/components/motion/Reveal";
import { useAuth } from "@/lib/auth-context";
import {
  deleteAccount,
  getProfile,
  getSessions,
  getLoginHistory,
  revokeSession,
  getPasskeys,
  deletePasskey,
  getPasswordStatus,
  getOAuthAccounts,
  unbindOAuth,
  getOAuthBindUrl,
  type UserInfo,
  type PasswordStatus,
  type OAuthAccount,
} from "@/lib/passport-api";
import { scorePassword } from "@/lib/password-strength";
import {
  type SecurityFactors,
  type Passkey,
  type Provider,
  type Session,
  type LoginEvent,
} from "@/lib/data";

const PROVIDER_META: Record<string, { name: string; hint: string }> = {
  wechat: { name: "微信", hint: "扫码快捷登录，绑定后可用微信一键登录" },
  qq: { name: "QQ", hint: "关联 QQ 账号，支持 QQ 快捷登录" },
  github: { name: "GitHub", hint: "面向开发者，支持 GitHub OAuth 登录" },
};
const ALL_PROVIDERS = Object.keys(PROVIDER_META);

function toProviders(accounts: OAuthAccount[]): Provider[] {
  const linked = new Map(accounts.map((a) => [a.provider, a.linked_at]));
  return ALL_PROVIDERS.map((id) => {
    const at = linked.get(id);
    return {
      id: id as Provider["id"],
      name: PROVIDER_META[id].name,
      hint: PROVIDER_META[id].hint,
      linked: Boolean(at),
      account: at ? `绑定于 ${at.slice(0, 10)}` : undefined,
    };
  });
}

/** 列表区块的加载 / 错误占位（数据到达前显示骨架，失败时显示可读错误）。 */
function SectionState({
  loading,
  error,
  children,
}: {
  loading: boolean;
  error: string | null;
  children: React.ReactNode;
}) {
  if (error) {
    return (
      <div className="rounded-3xl border border-danger/30 bg-danger-soft/40 p-6 text-sm text-danger">
        加载失败：{error}
      </div>
    );
  }
  if (loading) {
    return (
      <div className="rounded-3xl border border-line bg-surface p-8 text-center text-sm text-ink-muted shadow-soft">
        加载中…
      </div>
    );
  }
  return <>{children}</>;
}

export function SecurityView() {
  const { user, accessToken, logout, setUser } = useAuth();
  const router = useRouter();

  const [passkeys, setPasskeys] = React.useState<Passkey[]>([]);
  const [sessions, setSessions] = React.useState<Session[] | null>(null);
  const [events, setEvents] = React.useState<LoginEvent[] | null>(null);
  const [profile, setProfile] = React.useState<UserInfo | null>(null);
  const [pwdStatus, setPwdStatus] = React.useState<PasswordStatus | null>(null);
  const [strength, setStrength] = React.useState<string>("—");
  const [providers, setProviders] = React.useState<Provider[]>([]);
  const [loadError, setLoadError] = React.useState<string | null>(null);

  const [pwOpen, setPwOpen] = React.useState(false);
  const [delOpen, setDelOpen] = React.useState(false);

  // 真实拉取：资料(取 has_password 供注销 step-up) / 会话 / 登录历史 / 通行密钥 / 密码状态 / 第三方绑定。
  React.useEffect(() => {
    if (!accessToken) return;
    let alive = true;
    (async () => {
      try {
        const [p, s, h, pks, ps, accs] = await Promise.all([
          getProfile(accessToken),
          getSessions(accessToken),
          getLoginHistory(accessToken),
          getPasskeys(accessToken),
          getPasswordStatus(accessToken),
          getOAuthAccounts(accessToken),
        ]);
        if (!alive) return;
        setProfile(p);
        setSessions(s);
        setEvents(h);
        setPasskeys(pks);
        setPwdStatus(ps);
        setProviders(toProviders(accs));
      } catch (err) {
        if (!alive) return;
        setLoadError(err instanceof Error ? err.message : "加载失败，请刷新重试");
      }
    })();
    return () => {
      alive = false;
    };
  }, [accessToken]);

  const factors: SecurityFactors = React.useMemo(
    () => ({
      password: Boolean(pwdStatus?.has_password),
      monitoring: true,
    }),
    [pwdStatus]
  );

  const handleRevokeSession = async (id: string) => {
    if (!accessToken) return;
    try {
      await revokeSession(accessToken, id);
      setSessions((prev) => (prev ? prev.filter((x) => x.id !== id) : prev));
    } catch (err) {
      setLoadError(err instanceof Error ? err.message : "退出会话失败");
    }
  };

  const handleRemovePasskey = async (id: string) => {
    if (!accessToken) return;
    try {
      await deletePasskey(accessToken, id);
      setPasskeys((prev) => prev.filter((x) => x.id !== id));
    } catch (err) {
      setLoadError(err instanceof Error ? err.message : "删除通行密钥失败");
    }
  };

  const handleToggleProvider = async (id: Provider["id"]) => {
    if (!accessToken) return;
    const cur = providers.find((p) => p.id === id);
    try {
      if (cur?.linked) {
        await unbindOAuth(accessToken, id);
        setProviders((prev) =>
          prev.map((p) =>
            p.id === id ? { ...p, linked: false, account: undefined } : p
          )
        );
      } else {
        // 绑定走真实 OAuth 重定向；完成后回跳本页，useEffect 重新拉取即刷新状态。
        const url = await getOAuthBindUrl(
          accessToken,
          id,
          `${window.location.origin}/profile/security`
        );
        window.location.href = url;
      }
    } catch (err) {
      setLoadError(err instanceof Error ? err.message : "操作失败，请重试");
    }
  };

  const handlePasswordChanged = async (newPassword: string) => {
    if (!accessToken) return;
    const ps = await getPasswordStatus(accessToken);
    setPwdStatus(ps);
    // 用刚设置的新密码估算真实强度，刷新「密码强度」徽章。
    setStrength(newPassword ? scorePassword(newPassword).label : "—");
    // 同步全局 user.has_password，使资料页的「引导设置密码」横幅即时消失。
    setUser({ has_password: ps.has_password });
    setPwOpen(false);
  };

  // §9.4f：切真实注销接口。成功后清除本地会话并跳登录页。
  const handleDeleteAccount = async (currentPassword?: string) => {
    if (!accessToken) throw new Error("登录状态已失效，请重新登录");
    await deleteAccount(accessToken, currentPassword);
    logout();
    router.push("/login");
  };

  const lastChanged = pwdStatus?.password_changed_at?.slice(0, 10) || "—";

  return (
    <>
      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_320px]">
        {/* Sections */}
        <div className="order-2 space-y-6 lg:order-1">
          <Reveal>
            <PasswordSection
              lastChanged={lastChanged}
              strength={strength}
              onEdit={() => setPwOpen(true)}
            />
          </Reveal>
          <Reveal delay={0.04}>
            <PasskeySection
              passkeys={passkeys}
              onRemove={handleRemovePasskey}
            />
          </Reveal>
          <Reveal delay={0.08}>
            <SectionState loading={sessions === null} error={loadError}>
              {sessions ? (
                <SessionsSection sessions={sessions} onRevoke={handleRevokeSession} />
              ) : null}
            </SectionState>
          </Reveal>
          <Reveal delay={0.12}>
            <SectionState loading={events === null} error={events ? null : loadError}>
              {events ? <LoginHistorySection events={events} /> : null}
            </SectionState>
          </Reveal>
          <Reveal delay={0.16}>
            <ConnectedAccountsSection
              providers={providers}
              onToggle={handleToggleProvider}
            />
          </Reveal>
          <Reveal delay={0.2}>
            <DangerZone onDelete={() => setDelOpen(true)} />
          </Reveal>
        </div>

        {/* Sticky score */}
        <aside className="order-1 lg:order-2">
          <div className="lg:sticky lg:top-24">
            <SecurityScore factors={factors} />
            <div className="mt-4 rounded-3xl border border-line bg-surface p-5 shadow-soft">
              <p className="text-sm font-semibold text-ink">安全小贴士</p>
              <p className="mt-2 text-sm leading-relaxed text-ink-muted">
                定期更换高强度密码，并避免在多处复用同一密码。
              </p>
            </div>
          </div>
        </aside>
      </div>

      {/* Modals */}
      <ChangePasswordModal
        open={pwOpen}
        token={accessToken}
        onClose={() => setPwOpen(false)}
        onSuccess={handlePasswordChanged}
      />
      <DeleteAccountModal
        open={delOpen}
        onClose={() => setDelOpen(false)}
        confirmText={user?.username || user?.nickname || "DELETE"}
        requirePassword={!!profile?.has_password}
        onConfirm={handleDeleteAccount}
      />
    </>
  );
}
