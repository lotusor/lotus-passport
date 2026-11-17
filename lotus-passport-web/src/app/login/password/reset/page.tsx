'use client';

import Link from 'next/link';
import { useSearchParams } from 'next/navigation';
import { Suspense, useState, type FormEvent } from 'react';
import { GlassPanel } from '@/components/glass';
import { PasswordField } from '@/components/field';
import { IconAlert, IconArrowLeft, IconCheck, IconSpinner } from '@/components/icons';
import { api, ApiException } from '@/lib/api';
import { passwordRuleError, passwordScore } from '@/lib/format';

function StrengthMeter({ password }: { password: string }) {
  const score = passwordScore(password);
  return (
    <div className="flex-col gap-2">
      <div className="strength" aria-hidden>
        {[1, 2, 3, 4].map((i) => (
          <span key={i} className={`strength-seg ${score >= i ? `is-on-${score}` : ''}`} />
        ))}
      </div>
      <p className="field-hint">至少 8 位，需同时包含字母和数字</p>
    </div>
  );
}

function ResetInner() {
  const params = useSearchParams();
  const token = params.get('token') ?? '';
  const [pw, setPw] = useState('');
  const [confirm, setConfirm] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (busy) return;
    const ruleErr = passwordRuleError(pw);
    if (ruleErr) {
      setError(ruleErr);
      return;
    }
    if (pw !== confirm) {
      setError('两次输入的密码不一致');
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await api('/security/password/reset/', {
        method: 'POST',
        auth: false,
        body: { token, new_password: pw },
      });
      setDone(true);
    } catch (err) {
      setError(err instanceof ApiException ? err.message : '网络异常，请稍后重试');
    } finally {
      setBusy(false);
    }
  };

  return (
    <main className="center-page">
      <GlassPanel className="center-card">
        <p className="kicker">SECURITY // 重置密码</p>
        <h1 style={{ fontSize: 'var(--fs-title)' }}>设置新密码</h1>

        {!token ? (
          <>
            <p className="notice notice--red">
              <IconAlert />
              重置链接缺少 token 参数，请从邮件中的完整链接打开。
            </p>
            <Link className="btn btn-block" href="/login">
              <IconArrowLeft width={16} height={16} />
              返回登录
            </Link>
          </>
        ) : done ? (
          <>
            <p className="notice notice--phos">
              <IconCheck />
              密码已重置，所有会话已注销。请使用新密码重新登录。
            </p>
            <Link className="btn btn-primary btn-block" href="/login">
              前往登录
            </Link>
          </>
        ) : (
          <form className="auth-form" onSubmit={onSubmit}>
            <PasswordField
              label="新密码"
              autoComplete="new-password"
              value={pw}
              onChange={(e) => setPw(e.target.value)}
            />
            <StrengthMeter password={pw} />
            <PasswordField
              label="确认新密码"
              autoComplete="new-password"
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
            />
            {error && (
              <p className="field-err" role="alert">
                <IconAlert width={14} height={14} />
                {error}
              </p>
            )}
            <button type="submit" className="btn btn-primary btn-block" disabled={busy}>
              {busy ? <IconSpinner width={16} height={16} /> : null}
              重置密码
            </button>
            <p className="faint small">重置成功后，旧密码对应的全部会话将被吊销。</p>
          </form>
        )}
      </GlassPanel>
    </main>
  );
}

export default function PasswordResetPage() {
  return (
    <Suspense fallback={<main className="center-page" />}>
      <ResetInner />
    </Suspense>
  );
}