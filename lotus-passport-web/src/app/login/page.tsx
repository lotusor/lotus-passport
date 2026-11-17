'use client';

import { AnimatePresence, motion } from 'framer-motion';
import { useRouter, useSearchParams } from 'next/navigation';
import { Suspense, useCallback, useEffect, useRef, useState, type FormEvent } from 'react';
import { GlassPanel } from '@/components/glass';
import { HCaptcha } from '@/components/hcaptcha';
import { IconAlert, IconGithub, IconQQ, IconSpinner, IconWechat } from '@/components/icons';
import { Modal } from '@/components/modal';
import { MrzSample } from '@/components/mrz';
import { PasswordField, TextField } from '@/components/field';
import { Stamp } from '@/components/stamp';
import { useToast } from '@/components/toast';
import { useT } from '@/components/motion';
import { api, ApiException } from '@/lib/api';
import { useAuth } from '@/lib/auth';
import { OTICKET_KEY } from '@/lib/pkce';
import type { DevStatus, Provider } from '@/lib/types';

const EMAIL_RE = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;
const CODE_COOLDOWN_S = 60;

type Tab = 'password' | 'email';

function LoginInner() {
  const router = useRouter();
  const params = useSearchParams();
  const { status, user, loginWithPassword, loginWithEmail, startOAuth, startDevLogin, completeTicket } = useAuth();
  const { push } = useToast();
  const pillT = useT({ duration: 0.32, ease: [0.22, 1, 0.36, 1] });
  const grantedT = useT({ duration: 0.32, ease: [0.34, 1.56, 0.64, 1] });

  const [tab, setTab] = useState<Tab>('password');
  const [identifier, setIdentifier] = useState('');
  const [password, setPassword] = useState('');
  const [email, setEmail] = useState('');
  const [code, setCode] = useState('');
  const [busy, setBusy] = useState(false);
  const [oauthBusy, setOauthBusy] = useState<Provider | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [shakeKey, setShakeKey] = useState(0);
  const [captchaRequired, setCaptchaRequired] = useState(false);
  const [captchaToken, setCaptchaToken] = useState('');
  const [cooldown, setCooldown] = useState(0);
  const [emailNotice, setEmailNotice] = useState<string | null>(null);
  const [devStatus, setDevStatus] = useState<DevStatus | null>(null);
  const [granted, setGranted] = useState(false);
  const [resetOpen, setResetOpen] = useState(false);
  const [resetIdent, setResetIdent] = useState('');
  const [resetBusy, setResetBusy] = useState(false);
  const [resetResult, setResetResult] = useState<{ ok: boolean; msg: string } | null>(null);
  const oticket = useRef<string>('');

  useEffect(() => {
    const t = params.get('oticket') ?? '';
    if (t) {
      oticket.current = t;
      sessionStorage.setItem(OTICKET_KEY, t);
    } else {
      oticket.current = sessionStorage.getItem(OTICKET_KEY) ?? '';
    }
    api<DevStatus>('/dev/status/', { auth: false })
      .then(setDevStatus)
      .catch(() => setDevStatus(null));
  }, [params]);

  useEffect(() => {
    if (cooldown <= 0) return;
    const t = window.setInterval(() => setCooldown((c) => c - 1), 1000);
    return () => window.clearInterval(t);
  }, [cooldown]);

  const afterLogin = useCallback(async () => {
    const ticket = oticket.current || sessionStorage.getItem(OTICKET_KEY) || '';
    if (ticket) {
      sessionStorage.removeItem(OTICKET_KEY);
      try {
        await completeTicket(ticket);
        return;
      } catch (err) {
        const msg = err instanceof ApiException ? err.message : '授权票据无效或已过期';
        push('error', '无法返回应用', msg);
      }
    }
    setGranted(true);
    window.setTimeout(() => router.replace('/account'), 900);
  }, [completeTicket, push, router]);

  useEffect(() => {
    if (status !== 'authed') return;
    if (oticket.current) {
      void afterLogin();
    } else {
      router.replace('/account');
    }
  }, [status, afterLogin, router]);

  const fail = (msg: string) => {
    setError(msg);
    setShakeKey((k) => k + 1);
  };

  const onPasswordSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (busy) return;
    if (!identifier.trim() || !password) {
      fail('请输入账号与密码');
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await loginWithPassword(identifier.trim(), password, captchaToken || undefined);
      await afterLogin();
    } catch (err) {
      if (err instanceof ApiException) {
        if (err.captchaRequired) setCaptchaRequired(true);
        fail(err.message);
      } else {
        fail('网络异常，请稍后重试');
      }
    } finally {
      setBusy(false);
    }
  };

  const onSendCode = async () => {
    if (cooldown > 0 || busy) return;
    if (!EMAIL_RE.test(email.trim())) {
      fail('邮箱格式不正确');
      return;
    }
    setError(null);
    setEmailNotice(null);
    setBusy(true);
    try {
      await api('/security/email/send-code/', {
        method: 'POST',
        auth: false,
        body: { email: email.trim(), purpose: 'login' },
      });
      setCooldown(CODE_COOLDOWN_S);
      push('success', '验证码已发送', '请查收邮件（含垃圾邮件箱）');
    } catch (err) {
      if (err instanceof ApiException && err.status === 503) {
        setEmailNotice(err.message);
      } else {
        fail(err instanceof ApiException ? err.message : '发送失败，请稍后重试');
      }
    } finally {
      setBusy(false);
    }
  };

  const onEmailSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (busy) return;
    if (!EMAIL_RE.test(email.trim())) {
      fail('邮箱格式不正确');
      return;
    }
    if (!code.trim()) {
      fail('请输入邮件中的验证码');
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const { created } = await loginWithEmail(email.trim(), code.trim());
      if (created) push('success', '账户已创建', '邮箱验证码登录即注册，可在账户安全页设置密码');
      await afterLogin();
    } catch (err) {
      fail(err instanceof ApiException ? err.message : '网络异常，请稍后重试');
    } finally {
      setBusy(false);
    }
  };

  const onOAuth = async (provider: Provider) => {
    if (oauthBusy) return;
    setOauthBusy(provider);
    setError(null);
    try {
      await startOAuth(provider);
    } catch (err) {
      push('warning', '无法发起登录', err instanceof ApiException ? err.message : '网络异常');
      setOauthBusy(null);
    }
  };

  const onDevLogin = async (provider: Provider) => {
    setOauthBusy(provider);
    try {
      await startDevLogin(provider);
    } catch {
      push('error', 'DEV 登录失败', '请确认后端 ENABLE_DEV_LOGIN 已开启');
      setOauthBusy(null);
    }
  };

  const onResetRequest = async (e: FormEvent) => {
    e.preventDefault();
    if (resetBusy) return;
    if (!resetIdent.trim()) return;
    setResetBusy(true);
    setResetResult(null);
    try {
      const data = await api<{ detail: string }>('/security/password/reset-request/', {
        method: 'POST',
        auth: false,
        body: { identifier: resetIdent.trim() },
      });
      setResetResult({ ok: true, msg: data.detail });
    } catch (err) {
      setResetResult({
        ok: false,
        msg: err instanceof ApiException ? err.message : '网络异常，请稍后重试',
      });
    } finally {
      setResetBusy(false);
    }
  };

  const switchTab = (next: Tab) => {
    setTab(next);
    setError(null);
    setEmailNotice(null);
  };

  return (
    <main className="login-layout">
      <section className="login-brand" aria-label="Lotus Passport 品牌">
        <Stamp className="login-brand-stamp" label="UNIFIED IDENTITY" />
        <p className="kicker">EACM // UNIFIED IDENTITY</p>
        <h1 className="display-hero">
          LOTUS
          <br />
          <span className="display-outline">PASSPORT</span>
        </h1>
        <p className="login-brand-tag">统一身份认证中枢 — 一次登录，通行全部应用</p>
        <div className="login-brand-feats">
          <span className="chip chip--phos">
            <span className="chip-dot" />
            RS256 签名
          </span>
          <span className="chip">JWKS 公钥分发</span>
          <span className="chip">PKCE 授权码</span>
          <span className="chip">设备信任门</span>
        </div>
        <MrzSample />
      </section>

      <section className="login-auth" aria-label="登录">
        <GlassPanel className="auth-card">
          <header className="flex-col gap-2">
            <h2 className="auth-title">登录通行证</h2>
            <p className="auth-sub">选择一种方式验证你的身份</p>
          </header>

          {oticket.current && (
            <p className="notice">
              <IconAlert />
              外部应用请求登录 — 完成验证后将自动返回该应用。
            </p>
          )}

          <div className="tabs" role="tablist" aria-label="登录方式">
            {(
              [
                ['password', '密码登录'],
                ['email', '邮箱验证码'],
              ] as [Tab, string][]
            ).map(([key, label]) => (
              <button
                key={key}
                type="button"
                role="tab"
                id={`tab-${key}`}
                aria-selected={tab === key}
                aria-controls={`panel-${key}`}
                className="tab"
                onClick={() => switchTab(key)}
              >
                {tab === key && (
                  <motion.span layoutId="login-tab-pill" className="tab-pill" transition={pillT} />
                )}
                <span style={{ position: 'relative' }}>{label}</span>
              </button>
            ))}
          </div>

          {tab === 'password' ? (
            <form
              className="auth-form"
              id="panel-password"
              role="tabpanel"
              aria-labelledby="tab-password"
              onSubmit={onPasswordSubmit}
              key={`pwd-${shakeKey}`}
            >
              <TextField
                label="账号"
                placeholder="邮箱或用户名"
                autoComplete="username"
                value={identifier}
                onChange={(e) => setIdentifier(e.target.value)}
              />
              <PasswordField
                label="密码"
                placeholder="输入密码"
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
              {captchaRequired && <HCaptcha onToken={setCaptchaToken} />}
              {error && (
                <p className="field-err shake" role="alert">
                  <IconAlert width={14} height={14} />
                  {error}
                </p>
              )}
              <button type="submit" className="btn btn-primary btn-block" disabled={busy}>
                {busy ? <IconSpinner width={16} height={16} /> : null}
                {busy ? '验证中' : '登录'}
              </button>
            </form>
          ) : (
            <form
              className="auth-form"
              id="panel-email"
              role="tabpanel"
              aria-labelledby="tab-email"
              onSubmit={onEmailSubmit}
              key={`email-${shakeKey}`}
            >
              <TextField
                label="邮箱"
                type="email"
                placeholder="you@example.com"
                autoComplete="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                hint="未注册的邮箱将自动创建账户"
              />
              <div className="field">
                <label className="label" htmlFor="login-code">
                  验证码
                </label>
                <div className="flex gap-3">
                  <input
                    id="login-code"
                    className="input mono flex-1"
                    style={{ letterSpacing: '0.3em' }}
                    placeholder="6 位数字"
                    inputMode="numeric"
                    autoComplete="one-time-code"
                    maxLength={6}
                    value={code}
                    onChange={(e) => setCode(e.target.value.replace(/\D/g, ''))}
                  />
                  <button type="button" className="btn" style={{ flex: 'none' }} disabled={cooldown > 0 || busy} onClick={onSendCode}>
                    {cooldown > 0 ? `${cooldown}s 后重发` : '发送验证码'}
                  </button>
                </div>
              </div>
              {emailNotice && <p className="notice">{emailNotice}</p>}
              {error && (
                <p className="field-err shake" role="alert">
                  <IconAlert width={14} height={14} />
                  {error}
                </p>
              )}
              <button type="submit" className="btn btn-primary btn-block" disabled={busy}>
                {busy ? <IconSpinner width={16} height={16} /> : null}
                {busy ? '验证中' : '登录 / 注册'}
              </button>
            </form>
          )}

          <div className="divider" aria-hidden>
            OR
          </div>

          <div className="oauth-grid">
            <button type="button" className="oauth-btn" disabled={oauthBusy !== null} onClick={() => onOAuth('github')}>
              {oauthBusy === 'github' ? <IconSpinner width={22} height={22} /> : <IconGithub />}
              GITHUB
            </button>
            <button type="button" className="oauth-btn" disabled={oauthBusy !== null} onClick={() => onOAuth('qq')}>
              {oauthBusy === 'qq' ? <IconSpinner width={22} height={22} /> : <IconQQ />}
              QQ
            </button>
            <button type="button" className="oauth-btn" disabled={oauthBusy !== null} onClick={() => onOAuth('wechat')}>
              {oauthBusy === 'wechat' ? <IconSpinner width={22} height={22} /> : <IconWechat />}
              微信
            </button>
          </div>

          {devStatus?.dev_login_enabled && (
            <div className="dev-block">
              <p className="kicker kicker--amber">DEV // 模拟登录（仅开发环境）</p>
              <div className="dev-block-row">
                {devStatus.providers.map((p) => (
                  <button key={p} type="button" className="btn btn-sm" disabled={oauthBusy !== null} onClick={() => onDevLogin(p)}>
                    模拟 {p}
                  </button>
                ))}
              </div>
            </div>
          )}

          <footer className="auth-foot">
            <button type="button" className="btn btn-ghost btn-sm" onClick={() => setResetOpen(true)}>
              忘记密码？
            </button>
            <span className="faint small">通行证仅做身份认证，不含业务权限</span>
          </footer>
        </GlassPanel>
      </section>

      <AnimatePresence>
        {granted && (
          <motion.div
            className="modal-root"
            style={{ pointerEvents: 'none' }}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
          >
            <motion.div
              className="glass flex-col items-center gap-4"
              style={{ padding: 'var(--sp-7)', textAlign: 'center' }}
              initial={{ scale: 0.9 }}
              animate={{ scale: 1 }}
              transition={grantedT}
            >
              <Stamp animated label="ENTRY GRANTED" />
              <p className="kicker">ACCESS GRANTED</p>
              <p className="dim small">{user?.nickname ? `欢迎回来，${user.nickname}` : '身份已确认，正在进入账户中心'}</p>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>

      <Modal
        open={resetOpen}
        onClose={() => {
          setResetOpen(false);
          setResetResult(null);
        }}
        title="找回密码"
        footer={
          <button type="button" className="btn" onClick={() => setResetOpen(false)}>
            关闭
          </button>
        }
      >
        {resetResult?.ok ? (
          <p className="notice notice--phos">{resetResult.msg}</p>
        ) : (
          <form className="auth-form" onSubmit={onResetRequest}>
            <TextField
              label="账号"
              placeholder="邮箱或用户名"
              value={resetIdent}
              onChange={(e) => setResetIdent(e.target.value)}
              hint="若账户存在且绑定了邮箱，将收到一次性重置链接（30 分钟有效）"
            />
            {resetResult && !resetResult.ok && <p className="notice notice--red">{resetResult.msg}</p>}
            <button type="submit" className="btn btn-primary btn-block" disabled={resetBusy || !resetIdent.trim()}>
              {resetBusy ? <IconSpinner width={16} height={16} /> : null}
              发送重置邮件
            </button>
          </form>
        )}
      </Modal>
    </main>
  );
}

export default function LoginPage() {
  return (
    <Suspense fallback={<main className="center-page" />}>
      <LoginInner />
    </Suspense>
  );
}