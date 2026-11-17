'use client';

import { useEffect, useState, type FormEvent } from 'react';
import { PasswordField, TextField } from '@/components/field';
import { GlassPanel } from '@/components/glass';
import { IconAlert, IconMail, IconSpinner } from '@/components/icons';
import { useToast } from '@/components/toast';
import { api, ApiException } from '@/lib/api';

const EMAIL_RE = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;
const COOLDOWN_S = 60;

function useCooldown(): [number, () => void] {
  const [left, setLeft] = useState(0);
  useEffect(() => {
    if (left <= 0) return;
    const t = window.setInterval(() => setLeft((c) => c - 1), 1000);
    return () => window.clearInterval(t);
  }, [left]);
  return [left, () => setLeft(COOLDOWN_S)];
}

interface EmailPanelProps {
  email: string;
  hasPassword: boolean;
  onChanged: (email: string) => void;
}

export function EmailPanel({ email, hasPassword, onChanged }: EmailPanelProps) {
  const { push } = useToast();
  const [target, setTarget] = useState('');
  const [bindCode, setBindCode] = useState('');
  const [newCode, setNewCode] = useState('');
  const [oldCode, setOldCode] = useState('');
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice503, setNotice503] = useState<string | null>(null);
  const [bindCd, startBindCd] = useCooldown();
  const [newCd, startNewCd] = useCooldown();
  const [oldCd, startOldCd] = useCooldown();
  const [sentNew, setSentNew] = useState(false);
  const [sentOld, setSentOld] = useState(false);

  const sendCode = async (purpose: 'bind' | 'new' | 'old', address: string, start: () => void) => {
    if (busy) return;
    setError(null);
    setNotice503(null);
    try {
      await api('/security/email/send-code/', {
        method: 'POST',
        body: { email: address, purpose },
      });
      start();
      if (purpose === 'new') setSentNew(true);
      if (purpose === 'old') setSentOld(true);
      push('success', '验证码已发送', purpose === 'old' ? `已发往当前邮箱 ${email}` : `已发往 ${address}`);
    } catch (err) {
      if (err instanceof ApiException && err.status === 503) {
        setNotice503(err.message);
      } else {
        setError(err instanceof ApiException ? err.message : '发送失败，请稍后重试');
      }
    }
  };

  const onBind = async (e: FormEvent) => {
    e.preventDefault();
    if (busy) return;
    if (!EMAIL_RE.test(target.trim())) {
      setError('邮箱格式不正确');
      return;
    }
    if (!bindCode.trim()) {
      setError('请输入验证码');
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const res = await api<{ detail: string; email: string }>('/security/email/bind/', {
        method: 'POST',
        body: {
          email: target.trim(),
          code: bindCode.trim(),
          ...(hasPassword ? { current_password: password } : {}),
        },
      });
      onChanged(res.email);
      push('success', '邮箱绑定成功', res.email);
    } catch (err) {
      setError(err instanceof ApiException ? err.message : '网络异常，请稍后重试');
    } finally {
      setBusy(false);
    }
  };

  const onChange = async (e: FormEvent) => {
    e.preventDefault();
    if (busy) return;
    if (!EMAIL_RE.test(target.trim())) {
      setError('新邮箱格式不正确');
      return;
    }
    if (!newCode.trim() || !oldCode.trim()) {
      setError('请填齐新邮箱与当前邮箱的两个验证码');
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const res = await api<{ detail: string; email: string }>('/security/email/change/', {
        method: 'POST',
        body: {
          new_email: target.trim(),
          new_code: newCode.trim(),
          old_code: oldCode.trim(),
          ...(hasPassword ? { current_password: password } : {}),
        },
      });
      onChanged(res.email);
      setTarget('');
      setNewCode('');
      setOldCode('');
      setPassword('');
      setSentNew(false);
      setSentOld(false);
      push('success', '邮箱已更改', res.email);
    } catch (err) {
      setError(err instanceof ApiException ? err.message : '网络异常，请稍后重试');
    } finally {
      setBusy(false);
    }
  };

  const codeInput = (id: string, label: string, value: string, set: (v: string) => void) => (
    <div className="field">
      <label className="label" htmlFor={id}>
        {label}
      </label>
      <input
        id={id}
        className="input mono"
        style={{ letterSpacing: '0.3em' }}
        placeholder="6 位数字"
        inputMode="numeric"
        maxLength={6}
        value={value}
        onChange={(e) => set(e.target.value.replace(/\D/g, ''))}
      />
    </div>
  );

  return (
    <GlassPanel className="panel">
      <div className="panel-head">
        <h2 className="flex items-center gap-3" style={{ fontSize: 'var(--fs-body)' }}>
          <IconMail width={18} height={18} style={{ color: 'var(--phos)' }} />
          邮箱{email ? '换绑' : '绑定'}
        </h2>
        <span className={`chip ${email ? 'chip--phos' : 'chip--amber'}`}>
          <span className="chip-dot" />
          {email || '未绑定'}
        </span>
      </div>

      {notice503 && <p className="notice mb-4">{notice503}</p>}

      {!email ? (
        <form className="auth-form" onSubmit={onBind}>
          <p className="dim small">验证码将发送到目标邮箱，以证明你拥有该邮箱。</p>
          <TextField
            label="目标邮箱"
            type="email"
            placeholder="you@example.com"
            value={target}
            onChange={(e) => setTarget(e.target.value)}
          />
          <div className="flex gap-3 items-center">
            <div className="flex-1">{codeInput('bind-code', '验证码', bindCode, setBindCode)}</div>
            <button
              type="button"
              className="btn"
              style={{ flex: 'none', marginTop: 'var(--sp-5)' }}
              disabled={bindCd > 0 || busy || !EMAIL_RE.test(target.trim())}
              onClick={() => sendCode('bind', target.trim(), startBindCd)}
            >
              {bindCd > 0 ? `${bindCd}s` : '发送验证码'}
            </button>
          </div>
          {hasPassword && (
            <PasswordField
              label="账户密码（安全验证）"
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          )}
          {error && (
            <p className="field-err" role="alert">
              <IconAlert width={14} height={14} />
              {error}
            </p>
          )}
          <button type="submit" className="btn btn-primary" disabled={busy}>
            {busy ? <IconSpinner width={16} height={16} /> : null}
            绑定邮箱
          </button>
        </form>
      ) : (
        <form className="auth-form" onSubmit={onChange}>
          <div className="wizard-steps" aria-hidden>
            <span className={`wizard-step ${sentNew ? 'is-done' : 'is-active'}`}>01 验证新邮箱</span>
            <span className={`wizard-step ${sentOld ? 'is-done' : sentNew ? 'is-active' : ''}`}>02 确认旧邮箱</span>
            <span className={`wizard-step ${sentNew && sentOld ? 'is-active' : ''}`}>03 完成换绑</span>
          </div>
          <p className="dim small">双重验证：新邮箱收码证明所有权，当前邮箱收码确认是本人操作。</p>
          <TextField
            label="新邮箱"
            type="email"
            placeholder="new@example.com"
            value={target}
            onChange={(e) => setTarget(e.target.value)}
          />
          <div className="flex gap-3 items-center">
            <div className="flex-1">{codeInput('new-code', '新邮箱验证码', newCode, setNewCode)}</div>
            <button
              type="button"
              className="btn"
              style={{ flex: 'none', marginTop: 'var(--sp-5)' }}
              disabled={newCd > 0 || busy || !EMAIL_RE.test(target.trim())}
              onClick={() => sendCode('new', target.trim(), startNewCd)}
            >
              {newCd > 0 ? `${newCd}s` : '发送到新邮箱'}
            </button>
          </div>
          <div className="flex gap-3 items-center">
            <div className="flex-1">{codeInput('old-code', '当前邮箱验证码', oldCode, setOldCode)}</div>
            <button
              type="button"
              className="btn"
              style={{ flex: 'none', marginTop: 'var(--sp-5)' }}
              disabled={oldCd > 0 || busy}
              onClick={() => sendCode('old', email, startOldCd)}
            >
              {oldCd > 0 ? `${oldCd}s` : '发送到当前邮箱'}
            </button>
          </div>
          {hasPassword && (
            <PasswordField
              label="账户密码（安全验证）"
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          )}
          {error && (
            <p className="field-err" role="alert">
              <IconAlert width={14} height={14} />
              {error}
            </p>
          )}
          <button type="submit" className="btn btn-primary" disabled={busy}>
            {busy ? <IconSpinner width={16} height={16} /> : null}
            确认换绑
          </button>
        </form>
      )}
    </GlassPanel>
  );
}