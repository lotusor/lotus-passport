'use client';

import { useState, type FormEvent } from 'react';
import { PasswordField } from '@/components/field';
import { GlassPanel } from '@/components/glass';
import { IconAlert, IconKey, IconSpinner } from '@/components/icons';
import { useToast } from '@/components/toast';
import { api, ApiException } from '@/lib/api';
import { fmtRelative, passwordRuleError, passwordScore } from '@/lib/format';
import type { PasswordStatus } from '@/lib/types';

interface PasswordPanelProps {
  status: PasswordStatus;
  onChanged: (next: PasswordStatus) => void;
}

export function PasswordPanel({ status, onChanged }: PasswordPanelProps) {
  const { push } = useToast();
  const [current, setCurrent] = useState('');
  const [next, setNext] = useState('');
  const [confirm, setConfirm] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const score = passwordScore(next);

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (busy) return;
    const ruleErr = passwordRuleError(next);
    if (ruleErr) {
      setError(ruleErr);
      return;
    }
    if (next !== confirm) {
      setError('两次输入的密码不一致');
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const res = await api<{ has_password: boolean; password_changed_at: string; detail: string }>(
        '/security/password/change/',
        {
          method: 'POST',
          body: { new_password: next, ...(status.has_password ? { current_password: current } : {}) },
        },
      );
      onChanged({ has_password: res.has_password, password_changed_at: res.password_changed_at });
      setCurrent('');
      setNext('');
      setConfirm('');
      push('success', '密码已更新', res.detail);
    } catch (err) {
      setError(err instanceof ApiException ? err.message : '网络异常，请稍后重试');
    } finally {
      setBusy(false);
    }
  };

  return (
    <GlassPanel className="panel">
      <div className="panel-head">
        <h2 className="flex items-center gap-3" style={{ fontSize: 'var(--fs-body)' }}>
          <IconKey width={18} height={18} style={{ color: 'var(--phos)' }} />
          账户密码
        </h2>
        <span className={`chip ${status.has_password ? 'chip--phos' : 'chip--amber'}`}>
          <span className="chip-dot" />
          {status.has_password ? '已设置' : '未设置'}
        </span>
      </div>
      <p className="dim small mb-4">
        {status.has_password
          ? `上次修改：${fmtRelative(status.password_changed_at)}。修改密码后，其它设备的会话将被注销。`
          : '当前账户还没有密码。设置后即可使用「邮箱/用户名 + 密码」登录。'}
      </p>
      <form className="auth-form" onSubmit={onSubmit}>
        {status.has_password && (
          <PasswordField
            label="当前密码"
            autoComplete="current-password"
            value={current}
            onChange={(e) => setCurrent(e.target.value)}
          />
        )}
        <PasswordField
          label={status.has_password ? '新密码' : '设置密码'}
          autoComplete="new-password"
          value={next}
          onChange={(e) => setNext(e.target.value)}
        />
        <div className="flex-col gap-2">
          <div className="strength" aria-hidden>
            {[1, 2, 3, 4].map((i) => (
              <span key={i} className={`strength-seg ${score >= i ? `is-on-${score}` : ''}`} />
            ))}
          </div>
          <p className="field-hint">至少 8 位，需同时包含字母和数字</p>
        </div>
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
        <button type="submit" className="btn btn-primary" disabled={busy}>
          {busy ? <IconSpinner width={16} height={16} /> : null}
          {status.has_password ? '修改密码' : '设置密码'}
        </button>
      </form>
    </GlassPanel>
  );
}