'use client';

import { useCallback, useEffect, useState } from 'react';
import { GlassPanel } from '@/components/glass';
import { IconAlert, IconLink, IconRefresh, IconSpinner, PROVIDER_ICONS } from '@/components/icons';
import { Modal } from '@/components/modal';
import { Reveal } from '@/components/reveal';
import { EmptyState, SkeletonRows, TermLoad } from '@/components/term-load';
import { useToast } from '@/components/toast';
import { api, ApiException } from '@/lib/api';
import { useAuth } from '@/lib/auth';
import { fmtRelative, PROVIDER_LABELS } from '@/lib/format';
import type { OAuthAccountRow, PasswordStatus, Provider } from '@/lib/types';

const PROVIDERS: Provider[] = ['github', 'qq', 'wechat'];

export default function ConnectionsPage() {
  const { bindProvider } = useAuth();
  const { push } = useToast();
  const [accounts, setAccounts] = useState<OAuthAccountRow[]>([]);
  const [password, setPassword] = useState<PasswordStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [busyProvider, setBusyProvider] = useState<Provider | null>(null);
  const [unbindTarget, setUnbindTarget] = useState<Provider | null>(null);
  const [unbinding, setUnbinding] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(false);
    try {
      const [res, status] = await Promise.all([
        api<{ accounts: OAuthAccountRow[] }>('/oauth/accounts/'),
        api<PasswordStatus>('/security/password/'),
      ]);
      setAccounts(res.accounts);
      setPassword(status);
    } catch {
      setError(true);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const onBind = async (provider: Provider) => {
    if (busyProvider) return;
    setBusyProvider(provider);
    try {
      await bindProvider(provider);
    } catch (err) {
      push('warning', `无法绑定 ${PROVIDER_LABELS[provider]}`, err instanceof ApiException ? err.message : '网络异常');
      setBusyProvider(null);
    }
  };

  const onUnbind = async () => {
    if (!unbindTarget || unbinding) return;
    setUnbinding(true);
    try {
      await api(`/oauth/${unbindTarget}/`, { method: 'DELETE' });
      push('success', '已解绑', `${PROVIDER_LABELS[unbindTarget]} 身份关联已移除`);
      setUnbindTarget(null);
      await load();
    } catch (err) {
      push('error', '解绑失败', err instanceof ApiException ? err.message : '网络异常');
    } finally {
      setUnbinding(false);
    }
  };

  const boundOf = (p: Provider) => accounts.find((a) => a.provider === p);
  const lastMethodWarning =
    password && !password.has_password && accounts.length === 1
      ? '解绑后账户将无任何登录方式，请先设置密码或绑定其它渠道。'
      : null;

  return (
    <>
      <div className="page-head">
        <p className="kicker">ACCOUNT // 04</p>
        <h1 tabIndex={-1}>登录方式</h1>
        <p className="page-desc">管理绑定到本通行证的第三方身份。首次第三方登录会创建新账户；合并账户请在登录后绑定。</p>
      </div>

      {loading ? (
        <>
          <TermLoad label="loading linked identities" />
          <SkeletonRows n={3} />
        </>
      ) : error ? (
        <GlassPanel>
          <EmptyState
            title="LOAD FAILED // 加载失败"
            action={
              <button type="button" className="btn" onClick={load}>
                <IconRefresh width={16} height={16} />
                重试
              </button>
            }
          />
        </GlassPanel>
      ) : (
        <>
          <div className="provider-grid">
            {PROVIDERS.map((p, i) => {
              const Icon = PROVIDER_ICONS[p];
              const bound = boundOf(p);
              const busy = busyProvider === p;
              return (
                <Reveal key={p} delay={i * 60}>
                  <GlassPanel className="panel" hover>
                    <div className="flex items-center gap-4">
                      <span className={`row-icon ${bound ? 'row-icon--phos' : ''}`}>
                        <Icon />
                      </span>
                      <div className="row-meta">
                        <p className="row-title">{PROVIDER_LABELS[p]}</p>
                        <p className="row-sub">
                          {bound ? `绑定于 ${fmtRelative(bound.linked_at)}` : '未绑定'}
                        </p>
                      </div>
                    </div>
                    <div className="mt-4">
                      {bound ? (
                        <button
                          type="button"
                          className="btn btn-danger btn-sm btn-block"
                          disabled={busyProvider !== null}
                          onClick={() => setUnbindTarget(p)}
                        >
                          解绑
                        </button>
                      ) : (
                        <button
                          type="button"
                          className="btn btn-sm btn-block"
                          disabled={busyProvider !== null}
                          onClick={() => onBind(p)}
                        >
                          {busy ? <IconSpinner width={14} height={14} /> : <IconLink width={14} height={14} />}
                          {busy ? '跳转中' : '绑定'}
                        </button>
                      )}
                    </div>
                  </GlassPanel>
                </Reveal>
              );
            })}
          </div>

          <p className="notice mt-5">
            <IconAlert />
            第三方通道是否可用取决于服务端凭据配置；微信通道未配置时会提示「当前功能开发中」。
          </p>
          {lastMethodWarning && (
            <p className="notice notice--red mt-4">
              <IconAlert />
              {lastMethodWarning}
            </p>
          )}
        </>
      )}

      <Modal
        open={unbindTarget !== null}
        onClose={() => setUnbindTarget(null)}
        title={`解绑 ${unbindTarget ? PROVIDER_LABELS[unbindTarget] : ''}？`}
        footer={
          <>
            <button type="button" className="btn" onClick={() => setUnbindTarget(null)}>
              取消
            </button>
            <button type="button" className="btn btn-danger" disabled={unbinding} onClick={onUnbind}>
              {unbinding ? <IconSpinner width={16} height={16} /> : null}
              确认解绑
            </button>
          </>
        }
      >
        <p className="dim small">
          解绑后无法再用该第三方身份登录本通行证。
          {lastMethodWarning ?? '账户仍保留其它登录方式。'}
        </p>
      </Modal>
    </>
  );
}