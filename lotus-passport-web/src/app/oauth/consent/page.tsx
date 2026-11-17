'use client';

import { useSearchParams } from 'next/navigation';
import { Suspense, useEffect, useState } from 'react';
import { GlassPanel } from '@/components/glass';
import { IconAlert, IconArrowLeft, IconCheck, IconGlobe } from '@/components/icons';
import { TermLoad } from '@/components/term-load';
import { api, ApiException } from '@/lib/api';
import { initialOf } from '@/lib/format';
import type { ConsentInfo } from '@/lib/types';

function ConsentInner() {
  const params = useSearchParams();
  const ticket = params.get('ticket') ?? '';
  const [info, setInfo] = useState<ConsentInfo | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!ticket) {
      setError('授权请求缺少 ticket 参数，请从应用重新发起登录');
      return;
    }
    api<ConsentInfo>(`/oauth/consent/?ticket=${encodeURIComponent(ticket)}`, { auth: false })
      .then(setInfo)
      .catch((err) => setError(err instanceof ApiException ? err.message : '授权请求加载失败'));
  }, [ticket]);

  return (
    <main className="center-page">
      <GlassPanel className="center-card">
        <p className="kicker">OAUTH // 授权确认</p>

        {error ? (
          <>
            <h1 style={{ fontSize: 'var(--fs-title)' }}>无法完成授权</h1>
            <p className="notice notice--red">
              <IconAlert />
              {error}
            </p>
            <a className="btn btn-block" href="/login">
              <IconArrowLeft width={16} height={16} />
              返回登录
            </a>
          </>
        ) : !info ? (
          <>
            <h1 style={{ fontSize: 'var(--fs-title)' }}>读取授权请求</h1>
            <TermLoad label="querying consent ticket" />
          </>
        ) : (
          <>
            <div className="consent-app">
              {info.app_logo ? (
                <img
                  className="consent-app-icon"
                  src={info.app_logo}
                  width={56}
                  height={56}
                  alt={`${info.app_name} 的图标`}
                  style={{ objectFit: 'cover' }}
                />
              ) : (
                <span className="consent-app-icon" aria-hidden>
                  {initialOf(info.app_name)}
                </span>
              )}
              <div className="flex-col gap-2 flex-1">
                <h1 style={{ fontSize: 'var(--fs-title)' }}>{info.app_name}</h1>
                <span className="chip">
                  <IconGlobe width={12} height={12} />
                  {info.app_origin}
                </span>
              </div>
            </div>

            <p className="dim small">该应用请求以你的 Lotus 通行证身份登录，并获取以下权限：</p>

            <ul className="scope-list">
              {info.scopes.map((s) => (
                <li key={s}>
                  <IconCheck />
                  {s}
                </li>
              ))}
            </ul>

            <p className="mono faint" style={{ fontSize: 'var(--fs-label)' }}>
              身份 {info.passport_user_id.slice(0, 8)}… · 经由 {info.provider} 验证
            </p>

            <form action="/api/v1/oauth/consent/" method="POST" className="flex gap-3">
              <input type="hidden" name="ticket" value={ticket} />
              <button type="submit" name="decision" value="allow" className="btn btn-primary flex-1">
                授权登录
              </button>
              <button type="submit" name="decision" value="deny" className="btn">
                拒绝
              </button>
            </form>

            <p className="faint small">授权后应用仅能读取基本资料；你可以随时在账户中心的「在线会话」中撤销。</p>
          </>
        )}
      </GlassPanel>
    </main>
  );
}

export default function OAuthConsentPage() {
  return (
    <Suspense fallback={<main className="center-page" />}>
      <ConsentInner />
    </Suspense>
  );
}