"use client";

import * as React from "react";
import { Reveal } from "@/components/motion/Reveal";
import { Card, SectionCard, Button, Badge } from "@/components/ui";
import { Modal } from "@/components/modal";
import {
  Wechat,
  Qq,
  Github,
  Link2,
  Unlink,
  ShieldCheck,
  Check,
} from "@/components/icons";
import { useAuth } from "@/lib/auth-context";
import { getOAuthBindUrl, unbindOAuth } from "@/lib/passport-api";

type ProviderId = "github" | "wechat" | "qq";

const PROVIDER_META: Record<
  ProviderId,
  {
    name: string;
    hint: string;
    color: string;
    soft: string;
    Icon: React.ComponentType<React.SVGProps<SVGSVGElement>>;
  }
> = {
  wechat: {
    name: "微信",
    hint: "扫码快捷登录，绑定后可用微信一键登录",
    color: "#1aad19",
    soft: "#e6f7e6",
    Icon: Wechat,
  },
  qq: {
    name: "QQ",
    hint: "关联 QQ 账号，支持 QQ 快捷登录",
    color: "#12b7f5",
    soft: "#e6f5fd",
    Icon: Qq,
  },
  github: {
    name: "GitHub",
    hint: "面向开发者，支持 GitHub OAuth 登录",
    color: "#24292f",
    soft: "#eef0f2",
    Icon: Github,
  },
};

export function OAuthBindings() {
  const { user, accessToken, setUser } = useAuth();
  const linkedProviders = user?.providers || [];

  const [connectId, setConnectId] = React.useState<ProviderId | null>(null);
  const [unlinkId, setUnlinkId] = React.useState<ProviderId | null>(null);
  const [busy, setBusy] = React.useState(false);
  const [linkError, setLinkError] = React.useState<string | null>(null);

  const connectProvider = connectId ? PROVIDER_META[connectId] : null;
  const unlinkProvider = unlinkId ? PROVIDER_META[unlinkId] : null;

  /** 真实 OAuth 绑定：调后端 /oauth/{provider}/bind/ 拿到 authorize_url 后跳转。
   *  微信的二维码由微信授权页自身展示，本端不再自行生成。 */
  const doLink = async () => {
    if (!connectId) return;
    if (!accessToken) {
      setLinkError("登录状态已失效，请重新登录");
      return;
    }
    setBusy(true);
    setLinkError(null);
    try {
      const url = await getOAuthBindUrl(
        accessToken,
        connectId,
        `${window.location.origin}/auth/callback`
      );
      window.location.href = url;
    } catch (e) {
      setBusy(false);
      setLinkError(e instanceof Error ? e.message : "发起绑定失败，请重试");
    }
  };

  const doUnlink = async () => {
    if (!unlinkId) return;
    if (!accessToken) {
      setLinkError("登录状态已失效，请重新登录");
      return;
    }
    setBusy(true);
    setLinkError(null);
    try {
      await unbindOAuth(accessToken, unlinkId);
      // 乐观更新全局 providers，驱动资料页/安全页徽章刷新
      if (user) {
        setUser({
          ...user,
          providers: (user.providers || []).filter((p) => p !== unlinkId),
        });
      }
      setUnlinkId(null);
    } catch (e) {
      setLinkError(e instanceof Error ? e.message : "解除失败，请重试");
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <Reveal>
        <Card className="flex flex-col gap-3 p-5 sm:flex-row sm:items-center sm:justify-between sm:p-6">
          <div className="flex items-start gap-3">
            <span className="grid h-10 w-10 shrink-0 place-items-center rounded-2xl bg-accent-soft text-accent">
              <ShieldCheck className="h-5 w-5" />
            </span>
            <div>
              <p className="font-semibold text-ink">统一登录说明</p>
              <p className="mt-0.5 text-sm leading-relaxed text-ink-muted">
                莲花通行证聚合微信、QQ、GitHub 的 OAuth 登录，验证身份后签发统一
                JWT。业务权限由各接入方（如 E-algo Rank）自行维护。
              </p>
            </div>
          </div>
        </Card>
      </Reveal>

      <Reveal delay={0.04}>
        <SectionCard
          icon={Link2}
          title="关联第三方账号"
          description="绑定后可使用对应平台一键登录，无需记忆通行证密码。"
        >
          <ul className="divide-y divide-line">
            {(["github", "wechat", "qq"] as ProviderId[]).map((id) => {
              const meta = PROVIDER_META[id];
              const Icon = meta.Icon;
              const linked = linkedProviders.includes(id);
              return (
                <li key={id} className="flex items-center gap-4 py-4">
                  <span
                    className="grid h-12 w-12 shrink-0 place-items-center rounded-2xl"
                    style={{ background: meta.soft, color: meta.color }}
                  >
                    <Icon className="h-6 w-6" />
                  </span>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <p className="font-medium text-ink">{meta.name}</p>
                      {linked ? (
                        <Badge tone="success">
                          <Check className="h-3 w-3" /> 已关联
                        </Badge>
                      ) : (
                        <Badge tone="neutral">未关联</Badge>
                      )}
                    </div>
                    <p className="text-sm text-ink-muted">{meta.hint}</p>
                  </div>
                  <div className="shrink-0">
                    {linked ? (
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={() => setUnlinkId(id)}
                        className="text-danger hover:bg-danger-soft"
                      >
                        <Unlink className="h-4 w-4" /> 解除
                      </Button>
                    ) : (
                      <Button
                        size="sm"
                        variant="secondary"
                        onClick={() => setConnectId(id)}
                      >
                        <Link2 className="h-4 w-4" /> 关联
                      </Button>
                    )}
                  </div>
                </li>
              );
            })}
          </ul>
        </SectionCard>
      </Reveal>

      {/* Connect modal */}
      <Modal
        open={!!connectProvider}
        onClose={() => !busy && setConnectId(null)}
        title={`关联 ${connectProvider?.name ?? ""}`}
        description="按提示完成授权，即可使用该账号一键登录通行证。"
      >
        {connectId && (
          <div className="flex flex-col items-center gap-4 py-2">
            <p className="rounded-2xl bg-ink/5 px-4 py-3 text-center text-sm text-ink-muted">
              即将跳转至 {connectProvider?.name} 授权页面，
              <br />
              {connectId === "wechat"
                ? "用微信扫一扫完成授权后即可关联。"
                : "登录并确认后即可关联。"}
            </p>
            {linkError && <p className="text-sm text-danger">{linkError}</p>}
            <div className="flex w-full gap-3">
              <Button
                variant="ghost"
                className="flex-1"
                onClick={() => setConnectId(null)}
                disabled={busy}
              >
                取消
              </Button>
              <Button className="flex-1" onClick={doLink} disabled={busy}>
                {busy && (
                  <span className="h-4 w-4 animate-spin rounded-full border-2 border-white/40 border-t-white" />
                )}
                {busy ? "授权中…" : "授权并绑定"}
              </Button>
            </div>
          </div>
        )}
      </Modal>

      {/* Unlink confirm */}
      <Modal
        open={!!unlinkProvider}
        onClose={() => !busy && setUnlinkId(null)}
        title={`解除 ${unlinkProvider?.name ?? ""} 关联`}
        description="解除后使用该平台将无法一键登录，需改用密码或其余方式。"
      >
        {linkError && <p className="mb-3 text-sm text-danger">{linkError}</p>}
        <div className="flex gap-3 pt-2">
          <Button
            variant="ghost"
            className="flex-1"
            onClick={() => setUnlinkId(null)}
            disabled={busy}
          >
            取消
          </Button>
          <Button
            variant="danger"
            className="flex-1"
            onClick={doUnlink}
            disabled={busy}
          >
            {busy && (
              <span className="h-4 w-4 animate-spin rounded-full border-2 border-white/40 border-t-white" />
            )}
            {busy ? "处理中…" : "确认解除"}
          </Button>
        </div>
      </Modal>
    </>
  );
}
