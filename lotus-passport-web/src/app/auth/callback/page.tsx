'use client';

import { useRouter, useSearchParams } from 'next/navigation';
import { Suspense, useEffect, useRef, useState } from 'react';
import { GlassPanel } from '@/components/glass';
import { IconAlert, IconArrowLeft, IconCheck } from '@/components/icons';
import { TermLoad } from '@/components/term-load';
import { useToast } from '@/components/toast';
import { api, ApiException } from '@/lib/api';
import { useAuth } from '@/lib/auth';
import { OTICKET_KEY, takeVerifier } from '@/lib/pkce';
import { setTokens } from '@/lib/tokens';
import type { TokenPair } from '@/lib/types';

interface Step {
  label: string;
  state: 'run' | 'ok' | 'fail';
}

function CallbackInner() {
  const params = useSearchParams();
  const router = useRouter();
  const { push } = useToast();
  const { resumeSession } = useAuth();
  const [steps, setSteps] = useState<Step[]>([]);
  const [error, setError] = useState<string | null>(null);
  const ran = useRef(false);

  useEffect(() => {
    if (ran.current) return;
    ran.current = true;

    const mark = (label: string, state: Step['state']) =>
      setSteps((prev) => {
        const next = prev.filter((s) => s.label !== label);
        return [...next, { label, state }];
      });

    const run = async () => {
      const bound = params.get('bound');
      if (bound) {
        push('success', '绑定成功', `第三方身份已关联到当前账户`);
        router.replace('/account/connections');
        return;
      }

      const code = params.get('code');
      const hash = window.location.hash;

      try {
        if (code) {
          mark('解析授权码', 'ok');
          mark('PKCE 换取令牌', 'run');
          const verifier = takeVerifier();
          const pair = await api<TokenPair>('/oauth/token/', {
            method: 'POST',
            auth: false,
            body: { code, code_verifier: verifier },
          });
          setTokens(pair);
          mark('PKCE 换取令牌', 'ok');
        } else if (hash.includes('access_token')) {
          mark('解析回调 fragment', 'run');
          const frag = new URLSearchParams(hash.slice(1));
          const access = frag.get('access_token') ?? '';
          const refresh = frag.get('refresh_token') ?? '';
          if (!access || !refresh) throw new ApiException(400, 400, '回调缺少令牌参数');
          setTokens({ access, refresh, passport_user_id: frag.get('passport_user_id') ?? '' });
          mark('解析回调 fragment', 'ok');
        } else {
          throw new ApiException(400, 400, '回调参数缺失：未找到授权码或令牌');
        }

        window.history.replaceState(null, '', window.location.pathname);
        mark('恢复身份与会话', 'run');
        await resumeSession();
        mark('恢复身份与会话', 'ok');

        const ticket = sessionStorage.getItem(OTICKET_KEY) ?? '';
        if (ticket) {
          sessionStorage.removeItem(OTICKET_KEY);
          mark('签发应用授权码', 'run');
          const data = await api<{ redirect_url: string }>('/oauth/continue/', {
            method: 'POST',
            body: { ticket },
          });
          window.location.assign(data.redirect_url);
          return;
        }
        router.replace('/account');
      } catch (err) {
        const msg = err instanceof ApiException ? err.message : '登录回调处理失败，请重试';
        setError(msg);
        setSteps((prev) => prev.map((s) => (s.state === 'run' ? { ...s, state: 'fail' } : s)));
      }
    };

    void run();
  }, [params, push, router, resumeSession]);

  return (
    <main className="center-page">
      <GlassPanel className="center-card">
        <p className="kicker">AUTH // HANDSHAKE</p>
        <h1 style={{ fontSize: 'var(--fs-title)' }}>正在完成登录</h1>
        <div className="flex-col gap-2 mono small" aria-live="polite">
          {steps.map((s) => (
            <div key={s.label} className="flex items-center gap-3">
              {s.state === 'run' ? (
                <TermLoad label={s.label} />
              ) : (
                <>
                  <span style={{ color: s.state === 'ok' ? 'var(--phos)' : 'var(--red)' }}>
                    {s.state === 'ok' ? <IconCheck width={14} height={14} /> : <IconAlert width={14} height={14} />}
                  </span>
                  <span className="dim">{s.label}</span>
                  <span className="faint" style={{ marginLeft: 'auto' }}>
                    {s.state === 'ok' ? 'OK' : 'FAIL'}
                  </span>
                </>
              )}
            </div>
          ))}
        </div>
        {error && (
          <>
            <p className="notice notice--red">
              <IconAlert />
              {error}
            </p>
            <a className="btn btn-block" href="/login">
              <IconArrowLeft width={16} height={16} />
              返回登录
            </a>
          </>
        )}
      </GlassPanel>
    </main>
  );
}

export default function AuthCallbackPage() {
  return (
    <Suspense fallback={<main className="center-page" />}>
      <CallbackInner />
    </Suspense>
  );
}