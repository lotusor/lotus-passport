'use client';

import { useCallback, useEffect, useState } from 'react';
import { GlassPanel } from '@/components/glass';
import { IconAlert, IconRefresh } from '@/components/icons';
import { Reveal } from '@/components/reveal';
import { DangerPanel } from '@/components/security/danger-panel';
import { EmailPanel } from '@/components/security/email-panel';
import { PasswordPanel } from '@/components/security/password-panel';
import { EmptyState, SkeletonRows, TermLoad } from '@/components/term-load';
import { api } from '@/lib/api';
import type { PasswordStatus, Profile } from '@/lib/types';

export default function SecurityPage() {
  const [profile, setProfile] = useState<Profile | null>(null);
  const [password, setPassword] = useState<PasswordStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(false);
    try {
      const [p, s] = await Promise.all([api<Profile>('/profile/'), api<PasswordStatus>('/security/password/')]);
      setProfile(p);
      setPassword(s);
    } catch {
      setError(true);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <>
      <div className="page-head">
        <p className="kicker">ACCOUNT // 03</p>
        <h1 tabIndex={-1}>账户安全</h1>
        <p className="page-desc">管理密码与邮箱验证。敏感操作需要重新验证身份；密码修改或重置会注销其它会话。</p>
      </div>

      {loading ? (
        <>
          <TermLoad label="loading security factors" />
          <SkeletonRows n={2} />
        </>
      ) : error || !profile || !password ? (
        <GlassPanel>
          <EmptyState
            title="LOAD FAILED // 加载失败"
            desc="无法读取安全因子状态。"
            action={
              <button type="button" className="btn" onClick={load}>
                <IconRefresh width={16} height={16} />
                重试
              </button>
            }
          />
        </GlassPanel>
      ) : (
        <div className="flex-col gap-4">
          <Reveal>
            <PasswordPanel status={password} onChanged={setPassword} />
          </Reveal>
          <Reveal delay={60}>
            <EmailPanel
              email={profile.email}
              hasPassword={password.has_password}
              onChanged={(email) => setProfile((p) => (p ? { ...p, email } : p))}
            />
          </Reveal>
          <Reveal delay={120}>
            <DangerPanel hasPassword={password.has_password} />
          </Reveal>
          {!password.has_password && !profile.email && (
            <p className="notice">
              <IconAlert />
              当前账户既无密码也未绑定邮箱，仅依赖第三方登录。建议至少补充一种自有登录方式。
            </p>
          )}
        </div>
      )}
    </>
  );
}